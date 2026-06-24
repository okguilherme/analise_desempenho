"""
ETL - Consolidação do experimento A1 vs A2 (AWS Load Testing)

Lê arquivos .tar.gz no formato "lote*_<ARQ>_<CARGA>_vus*.tar.gz", cada um contendo:
    <CARGA>/repNN/resultado.json
    <CARGA>/repNN/horario.txt
    <CARGA>/repNN/cloudwatch/{cpu_utilization,cpu_credit_balance,cpu_surplus_credit_balance}.json

Gera um único CSV com 1 linha por réplica (unidade de análise correta para o
Mann-Whitney/bootstrap, já que resultado.json é o agregado de toda a execução).

Uso:
    python3 build_dataset.py <pasta_com_tar_gz> <csv_saida>
"""
import json
import os
import re
import sys
import tarfile
import tempfile
import zipfile
from datetime import datetime, timedelta

import pandas as pd

CLOUDWATCH_PERIOD_S = 300  # confirmado: --period 300 (granularidade básica EC2)

CW_FILES = {
    "cpu_utilization.json": "cpu_util_pct",
    "cpu_credit_balance.json": "cpu_credit_balance",
    "cpu_surplus_credit_balance.json": "cpu_surplus_credit",
}


def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def overlap_seconds(a_start, a_end, b_start, b_end) -> float:
    latest_start = max(a_start, b_start)
    earliest_end = min(a_end, b_end)
    return max(0.0, (earliest_end - latest_start).total_seconds())


def windowed_peak_value(datapoints, test_start, test_end, field="Maximum"):
    """Pico (campo Maximum) considerando apenas os buckets que de fato se
    sobrepõem à janela do teste — evita herdar o pico de uma réplica vizinha
    que tenha caído no mesmo bucket de 5 min."""
    candidates = []
    for dp in datapoints:
        bucket_start = parse_iso(dp["Timestamp"])
        bucket_end = bucket_start + timedelta(seconds=CLOUDWATCH_PERIOD_S)
        if overlap_seconds(test_start, test_end, bucket_start, bucket_end) > 0:
            candidates.append(dp[field])
    return max(candidates) if candidates else None


def weighted_cw_value(datapoints, test_start, test_end, field="Average"):
    """Pondera os datapoints do CloudWatch pela sobreposição real com a janela
    do teste (horario.txt), em vez de simplesmente tirar a média dos 3 buckets
    (dois deles costumam ser período ocioso antes/depois do teste)."""
    total_w, total_v = 0.0, 0.0
    for dp in datapoints:
        bucket_start = parse_iso(dp["Timestamp"])
        bucket_end = bucket_start + timedelta(seconds=CLOUDWATCH_PERIOD_S)
        w = overlap_seconds(test_start, test_end, bucket_start, bucket_end)
        if w > 0:
            total_w += w
            total_v += w * dp[field]
    return (total_v / total_w) if total_w > 0 else None


def parse_rep(rep_path: str, arquitetura: str, carga: int) -> dict:
    with open(os.path.join(rep_path, "resultado.json")) as f:
        res = json.load(f)
    m = res["metrics"]

    with open(os.path.join(rep_path, "horario.txt")) as f:
        lines = [l.strip() for l in f if l.strip()]
    inicio = parse_iso(lines[0].split(": ", 1)[1])
    fim = parse_iso(lines[1].split(": ", 1)[1])

    dur = m["http_req_duration"]
    row = {
        "arquitetura": arquitetura,
        "carga_vus": carga,
        "replica": os.path.basename(rep_path),
        "inicio": inicio.isoformat(),
        "fim": fim.isoformat(),
        "duracao_s": (fim - inicio).total_seconds(),
        # Latência (k6 http_req_duration) — em ms
        "lat_avg_ms": dur.get("avg"),
        "lat_med_ms": dur.get("med"),
        "lat_p90_ms": dur.get("p(90)"),
        "lat_p95_ms": dur.get("p(95)"),
        "lat_max_ms": dur.get("max"),
        "lat_min_ms": dur.get("min"),
        # Throughput
        "throughput_rps": m["http_reqs"]["rate"],
        "total_reqs": m["http_reqs"]["count"],
        # Taxa de erro (http_req_failed é Rate metric: passes=count "failed=true")
        "taxa_erro": m["http_req_failed"]["value"],
        "reqs_falhas": m["http_req_failed"]["passes"],
        "reqs_sucesso": m["http_req_failed"]["fails"],
        # Sanity check de VUs atingidos
        "vus_min": m["vus"]["min"],
        "vus_max_atingido": m["vus"]["max"],
        "iterations": m["iterations"]["count"],
    }

    cw_dir = os.path.join(rep_path, "cloudwatch")
    for fname, colname in CW_FILES.items():
        fpath = os.path.join(cw_dir, fname)
        if os.path.exists(fpath):
            with open(fpath) as f:
                cw = json.load(f)
            row[colname] = weighted_cw_value(cw["Datapoints"], inicio, fim)
        else:
            row[colname] = None

    # Pico de CPU (Maximum) -- só dos buckets que sobrepõem o teste.
    # Complementa cpu_util_pct (média) pra checar o limiar de saturação (OE3: CPU > 80%).
    cpu_path = os.path.join(cw_dir, "cpu_utilization.json")
    if os.path.exists(cpu_path):
        with open(cpu_path) as f:
            cw = json.load(f)
        row["cpu_util_peak_pct"] = windowed_peak_value(cw["Datapoints"], inicio, fim)
    else:
        row["cpu_util_peak_pct"] = None

    return row


def find_scenario_dirs(extract_root: str, archive_filename: str = None) -> list:
    """
    Encontra todas as pastas de réplicas dentro de extract_root.
    Suporta dois layouts:
      1) Pasta "loteX_A#_CARGA_vus (N)/CARGA/repNN" -- nome de arquitetura/carga
         vem do nome da própria pasta interna.
      2) Pasta "CARGA/repNN" solta (sem prefixo lote) -- nesse caso arquitetura/
         carga são inferidos do nome do arquivo .zip/.tar.gz enviado.
    Retorna lista de tuplas (arquitetura, carga, caminho_da_pasta_carga).
    """
    results = []
    matched = set()

    for dirpath, dirnames, _ in os.walk(extract_root):
        base = os.path.basename(dirpath)
        m = re.search(r"_(A\d+)_(\d+)_vus", base)
        if m:
            arquitetura, carga = m.group(1), int(m.group(2))
            for sub_root, sub_dirs, _ in os.walk(dirpath):
                if str(carga) in sub_dirs:
                    cd = os.path.join(sub_root, str(carga))
                    results.append((arquitetura, carga, cd))
                    matched.add(os.path.normpath(cd))
                    break

    if archive_filename:
        m2 = re.search(r"_(A\d+)_(\d+)_vus", archive_filename)
        if m2:
            arquitetura, carga = m2.group(1), int(m2.group(2))
            for dirpath, dirnames, _ in os.walk(extract_root):
                if str(carga) in dirnames:
                    cd = os.path.join(dirpath, str(carga))
                    if os.path.normpath(cd) not in matched:
                        results.append((arquitetura, carga, cd))
                        matched.add(os.path.normpath(cd))

    return results


def extract_any(path: str, dest: str):
    if path.endswith(".zip"):
        with zipfile.ZipFile(path) as zf:
            zf.extractall(dest)
    else:
        with tarfile.open(path) as tf:
            tf.extractall(dest)


def parse_archive(archive_path: str) -> list:
    fname = os.path.basename(archive_path)
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        extract_any(archive_path, tmp)

        scenarios = find_scenario_dirs(tmp, archive_filename=fname)
        if not scenarios:
            raise ValueError(f"Não achei nenhum cenário (pasta de carga) dentro de {fname}")

        for arquitetura, carga, carga_dir in scenarios:
            reps = sorted(
                d for d in os.listdir(carga_dir)
                if os.path.isdir(os.path.join(carga_dir, d))
            )
            count = 0
            for rep in reps:
                rep_path = os.path.join(carga_dir, rep)
                try:
                    rows.append(parse_rep(rep_path, arquitetura, carga))
                    count += 1
                except Exception as e:
                    print(f"  [AVISO] Falhou {fname}/{carga}/{rep}: {e}")
            print(f"{fname} -> arq={arquitetura}, carga={carga}: {count} réplicas processadas")

    return rows


def main(input_dir: str, output_csv: str):
    tar_files = sorted(
        os.path.join(input_dir, f)
        for f in os.listdir(input_dir)
        if f.endswith(".gz") or f.endswith(".tgz") or f.endswith(".zip")
    )
    if not tar_files:
        print(f"Nenhum .tar.gz encontrado em {input_dir}")
        return

    all_rows = []
    for tp in tar_files:
        all_rows.extend(parse_archive(tp))

    df = pd.DataFrame(all_rows)
    df = df.sort_values(["arquitetura", "carga_vus", "replica"]).reset_index(drop=True)
    df.to_csv(output_csv, index=False)
    print(f"\nDataset consolidado: {len(df)} linhas -> {output_csv}")
    print("\nResumo por cenário (arquitetura x carga):")
    print(df.groupby(["arquitetura", "carga_vus"]).size())


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python3 build_dataset.py <pasta_com_tar_gz> <csv_saida>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
