"""
ETL - A2 (ALB + 2x EC2) — extensão do build_dataset.py original

Estrutura por réplica:
    <CARGA>/repNN/resultado.json
    <CARGA>/repNN/horario.txt
    <CARGA>/repNN/cloudwatch/
        ec2_1_cpu_utilization.json / cpu_credit_balance / cpu_surplus_credit_balance
        ec2_2_cpu_utilization.json / cpu_credit_balance / cpu_surplus_credit_balance
        alb_target_response_time.json   (ExtendedStatistics.p95, em segundos)
        alb_active_connection_count.json (campo "Sum")
        alb_healthy_host_count.json

Uso:
    python3 build_dataset_A2.py <pasta_com_repNN> <carga_vus> <csv_saida>
"""
import json
import os
import sys
from datetime import datetime, timedelta

import pandas as pd

CLOUDWATCH_PERIOD_S = 300


def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def overlap_seconds(a_start, a_end, b_start, b_end) -> float:
    latest_start = max(a_start, b_start)
    earliest_end = min(a_end, b_end)
    return max(0.0, (earliest_end - latest_start).total_seconds())


def weighted_value(datapoints, test_start, test_end, extractor):
    """Pondera datapoints pela sobreposição real com a janela do teste.
    `extractor` é uma função que recebe o datapoint e devolve o valor numérico
    (permite lidar com 'Average', 'Sum', ou campos aninhados como
    ExtendedStatistics.p95)."""
    total_w, total_v = 0.0, 0.0
    for dp in datapoints:
        bucket_start = parse_iso(dp["Timestamp"])
        bucket_end = bucket_start + timedelta(seconds=CLOUDWATCH_PERIOD_S)
        w = overlap_seconds(test_start, test_end, bucket_start, bucket_end)
        if w > 0:
            val = extractor(dp)
            if val is not None:
                total_w += w
                total_v += w * val
    return (total_v / total_w) if total_w > 0 else None


def load_cw(rep_path, fname):
    fpath = os.path.join(rep_path, "cloudwatch", fname)
    if not os.path.exists(fpath):
        return None
    with open(fpath) as f:
        return json.load(f)["Datapoints"]


def windowed_peak(datapoints, test_start, test_end, field="Maximum"):
    """Pico (campo Maximum) considerando só os buckets que sobrepõem a janela
    do teste -- mesma lógica usada no build_dataset.py do A1."""
    candidates = []
    for dp in datapoints:
        bucket_start = parse_iso(dp["Timestamp"])
        bucket_end = bucket_start + timedelta(seconds=CLOUDWATCH_PERIOD_S)
        if overlap_seconds(test_start, test_end, bucket_start, bucket_end) > 0:
            candidates.append(dp[field])
    return max(candidates) if candidates else None


def parse_rep(rep_path: str, carga: int) -> dict:
    with open(os.path.join(rep_path, "resultado.json")) as f:
        res = json.load(f)
    m = res["metrics"]

    with open(os.path.join(rep_path, "horario.txt")) as f:
        lines = [l.strip() for l in f if l.strip()]
    inicio = parse_iso(lines[0].split(": ", 1)[1])
    fim = parse_iso(lines[1].split(": ", 1)[1])

    dur = m["http_req_duration"]
    row = {
        "arquitetura": "A2",
        "carga_vus": carga,
        "replica": os.path.basename(rep_path),
        "inicio": inicio.isoformat(),
        "fim": fim.isoformat(),
        "duracao_s": (fim - inicio).total_seconds(),
        "lat_avg_ms": dur.get("avg"),
        "lat_med_ms": dur.get("med"),
        "lat_p90_ms": dur.get("p(90)"),
        "lat_p95_ms": dur.get("p(95)"),
        "lat_max_ms": dur.get("max"),
        "lat_min_ms": dur.get("min"),
        "throughput_rps": m["http_reqs"]["rate"],
        "total_reqs": m["http_reqs"]["count"],
        "taxa_erro": m["http_req_failed"]["value"],
        "reqs_falhas": m["http_req_failed"]["passes"],
        "reqs_sucesso": m["http_req_failed"]["fails"],
        "vus_min": m["vus"]["min"],
        "vus_max_atingido": m["vus"]["max"],
        "iterations": m["iterations"]["count"],
    }

    # ---- CPU por instância (ec2_1 / ec2_2) ----
    cpu_vals = {}
    cpu_peak_vals = {}
    for inst in ["ec2_1", "ec2_2"]:
        for metric, colname in [
            ("cpu_utilization.json", "cpu_util_pct"),
            ("cpu_credit_balance.json", "cpu_credit_balance"),
            ("cpu_surplus_credit_balance.json", "cpu_surplus_credit"),
        ]:
            dps = load_cw(rep_path, f"{inst}_{metric}")
            val = weighted_value(dps, inicio, fim, lambda dp: dp.get("Average")) if dps else None
            row[f"{colname}_{inst}"] = val
            if colname == "cpu_util_pct":
                cpu_vals[inst] = val

        # pico de CPU por instância
        dps_cpu = load_cw(rep_path, f"{inst}_cpu_utilization.json")
        peak = windowed_peak(dps_cpu, inicio, fim) if dps_cpu else None
        row[f"cpu_util_peak_pct_{inst}"] = peak
        cpu_peak_vals[inst] = peak

    # CPU agregada (média e máxima entre as 2 instâncias) -- comparável ao A1
    valid_cpu = [v for v in cpu_vals.values() if v is not None]
    row["cpu_util_pct_media_instancias"] = sum(valid_cpu) / len(valid_cpu) if valid_cpu else None
    row["cpu_util_pct_max_instancia"] = max(valid_cpu) if valid_cpu else None

    # Pico de CPU agregado: pega o maior pico entre as 2 instâncias (a que mais sofreu)
    valid_peaks = [v for v in cpu_peak_vals.values() if v is not None]
    row["cpu_util_peak_pct"] = max(valid_peaks) if valid_peaks else None

    # ---- Métricas do ALB ----
    dps = load_cw(rep_path, "alb_target_response_time.json")
    row["alb_target_response_time_p95_ms"] = (
        weighted_value(dps, inicio, fim, lambda dp: dp.get("ExtendedStatistics", {}).get("p95") * 1000
                        if dp.get("ExtendedStatistics", {}).get("p95") is not None else None)
        if dps else None
    )

    dps = load_cw(rep_path, "alb_active_connection_count.json")
    row["alb_active_connections"] = (
        weighted_value(dps, inicio, fim, lambda dp: dp.get("Sum")) if dps else None
    )

    dps = load_cw(rep_path, "alb_healthy_host_count.json")
    row["alb_healthy_host_count"] = (
        weighted_value(dps, inicio, fim, lambda dp: dp.get("Average") or dp.get("Sum") or dp.get("Minimum"))
        if dps else None
    )

    return row


def main(reps_dir: str, carga: int, output_csv: str):
    reps = sorted(d for d in os.listdir(reps_dir) if os.path.isdir(os.path.join(reps_dir, d)) and d.startswith("rep"))
    rows = []
    for rep in reps:
        try:
            rows.append(parse_rep(os.path.join(reps_dir, rep), carga))
        except Exception as e:
            print(f"  [AVISO] Falhou {rep}: {e}")
    df = pd.DataFrame(rows).sort_values("replica").reset_index(drop=True)
    df.to_csv(output_csv, index=False)
    print(f"Processadas {len(df)} réplicas -> {output_csv}")
    print(f"\nalb_healthy_host_count: {df['alb_healthy_host_count'].notna().sum()}/{len(df)} réplicas com dado válido")
    print(f"alb_active_connections: {df['alb_active_connections'].notna().sum()}/{len(df)} réplicas com dado válido")
    print(f"alb_target_response_time_p95_ms: {df['alb_target_response_time_p95_ms'].notna().sum()}/{len(df)} réplicas com dado válido")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Uso: python3 build_dataset_A2.py <pasta_com_repNN> <carga_vus> <csv_saida>")
        sys.exit(1)
    main(sys.argv[1], int(sys.argv[2]), sys.argv[3])
