"""
gerar_tabelas.py — Geração das tabelas estatísticas (A1 vs A2)

Requisitos: pandas, numpy, scipy, statsmodels
Uso: python3 gerar_tabelas.py
(rode na pasta que contém dataset_A1.csv e dataset_A2.csv)

Gera 4 arquivos em tabelas/:
  1. estatistica_descritiva.csv  -> média ± IC95% de TODAS as métricas coletadas
                                     (lat_p95_ms usa bootstrap; o resto usa t-Student)
  2. mann_whitney.csv            -> teste de hipótese A1 vs A2, por carga e métrica,
                                     com p-value bruto E ajustado (Holm-Bonferroni),
                                     Cliff's delta com IC95% via bootstrap
  3. resumo_overhead_ganho.csv   -> overhead ISOLADO do ALB (k6 vs ALB TargetResponseTime,
                                     só dentro do A2) + diferença total A1 vs A2 + ganhos
"""
import os
import numpy as np
import pandas as pd
from scipy import stats

CARGAS = [100, 500, 1000, 2000]
OUTDIR = "tabelas"
N_BOOT = 10000
rng = np.random.default_rng(42)

METRICAS_COMUNS = {
    'lat_p95_ms': 'Latência P95 (ms)',
    'lat_p90_ms': 'Latência P90 (ms)',
    'lat_avg_ms': 'Latência média (ms)',
    'lat_med_ms': 'Latência mediana (ms)',
    'throughput_rps': 'Throughput (req/s)',
    'taxa_erro': 'Taxa de erro (fração)',
    'cpu_util_pct': 'CPU média (%)',
    'cpu_util_peak_pct': 'CPU pico (%)',
    'cpu_credit_balance': 'CPUCreditBalance',
}
METRICAS_A2_EXCLUSIVAS = {
    'alb_target_response_time_p95_ms': 'Latência de backend (ALB, ms)',
    'alb_active_connections': 'Conexões ativas (ALB)',
    'alb_healthy_host_count': 'Hosts saudáveis (ALB)',
}
LOWER_IS_BETTER = {'lat_p95_ms': True, 'throughput_rps': False, 'taxa_erro': True,
                    'cpu_util_pct': True, 'cpu_util_peak_pct': True}
METRICAS_MANN_WHITNEY = ['lat_p95_ms', 'throughput_rps', 'taxa_erro', 'cpu_util_pct', 'cpu_util_peak_pct']
# Nota: "menor é melhor" pra CPU aqui significa "mais longe da saturação (OE3)",
# não que CPU baixo seja um objetivo em si -- é uma leitura de segurança/folga,
# não de "performance" no mesmo sentido de latência/throughput.
USA_BOOTSTRAP = {'lat_p95_ms'}  # métricas de cauda pesada -> bootstrap em vez de t-Student


def ic95_t(x):
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 2:
        return (x[0] if n == 1 else np.nan), np.nan, n
    m = x.mean()
    sem = x.std(ddof=1) / np.sqrt(n)
    tcrit = stats.t.ppf(0.975, df=n - 1)
    return m, tcrit * sem, n


def ic95_bootstrap(x, n_boot=N_BOOT):
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 2:
        return (x[0] if n == 1 else np.nan), np.nan, n
    boot_means = rng.choice(x, size=(n_boot, n), replace=True).mean(axis=1)
    lo, hi = np.percentile(boot_means, [2.5, 97.5])
    m = x.mean()
    half = max(m - lo, hi - m)
    return m, half, n


def cliffs_delta(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    more = sum((xi > y).sum() for xi in x)
    less = sum((xi < y).sum() for xi in x)
    return (more - less) / (len(x) * len(y))


def cliffs_delta_ic95(x, y, n_boot=N_BOOT):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    nx, ny = len(x), len(y)
    deltas = np.empty(n_boot)
    for i in range(n_boot):
        xb = rng.choice(x, size=nx, replace=True)
        yb = rng.choice(y, size=ny, replace=True)
        more = (xb[:, None] > yb[None, :]).sum()
        less = (xb[:, None] < yb[None, :]).sum()
        deltas[i] = (more - less) / (nx * ny)
    lo, hi = np.percentile(deltas, [2.5, 97.5])
    return lo, hi


def holm_bonferroni(p_values):
    """Correção de Holm-Bonferroni (step-down), sem dependência externa.
    Retorna (rejeitar_H0_array, p_ajustado_array), alinhados à ordem original."""
    p = np.asarray(p_values, dtype=float)
    m = len(p)
    order = np.argsort(p)
    p_sorted = p[order]
    p_adj_sorted = np.empty(m)
    running_max = 0.0
    for i in range(m):
        val = min((m - i) * p_sorted[i], 1.0)
        running_max = max(running_max, val)
        p_adj_sorted[i] = running_max
    p_adj = np.empty(m)
    p_adj[order] = p_adj_sorted
    reject = p_adj < 0.05
    return reject, p_adj


def magnitude(delta):
    ad = abs(delta)
    if ad < 0.147: return "desprezível"
    if ad < 0.33: return "pequeno"
    if ad < 0.474: return "médio"
    return "grande"


def carregar_dados():
    a1 = pd.read_csv("dataset_A1.csv")
    a2 = pd.read_csv("dataset_A2_limpo.csv")
    
    a2['cpu_util_pct'] = a2[['cpu_util_pct_ec2_1', 'cpu_util_pct_ec2_2']].mean(axis=1)
    a2['cpu_credit_balance'] = a2[['cpu_credit_balance_ec2_1', 'cpu_credit_balance_ec2_2']].mean(axis=1)
    df = pd.concat([a1, a2], ignore_index=True, sort=False)
    return df


def gerar_descritiva(df):
    linhas = []
    for carga in CARGAS:
        for arq in ['A1', 'A2']:
            sub = df[(df.carga_vus == carga) & (df.arquitetura == arq)]
            for col, label in METRICAS_COMUNS.items():
                if col not in sub.columns:
                    continue
                if col in USA_BOOTSTRAP:
                    m, half, n = ic95_bootstrap(sub[col])
                    metodo = 'bootstrap'
                else:
                    m, half, n = ic95_t(sub[col])
                    metodo = 't-student'
                linhas.append({'carga_vus': carga, 'arquitetura': arq, 'metrica': label,
                                'coluna': col, 'metodo_ic': metodo, 'n': n,
                                'media': round(m, 4) if pd.notna(m) else None,
                                'ic95': round(half, 4) if pd.notna(half) else None})
            if arq == 'A2':
                for col, label in METRICAS_A2_EXCLUSIVAS.items():
                    if col not in sub.columns:
                        continue
                    m, half, n = ic95_t(sub[col])
                    linhas.append({'carga_vus': carga, 'arquitetura': arq, 'metrica': label,
                                    'coluna': col, 'metodo_ic': 't-student', 'n': n,
                                    'media': round(m, 4) if pd.notna(m) else None,
                                    'ic95': round(half, 4) if pd.notna(half) else None})
    return pd.DataFrame(linhas)


def gerar_mann_whitney(df):
    linhas = []
    for carga in CARGAS:
        for metrica in METRICAS_MANN_WHITNEY:
            x = df[(df.carga_vus == carga) & (df.arquitetura == 'A1')][metrica]
            y = df[(df.carga_vus == carga) & (df.arquitetura == 'A2')][metrica]
            u, p = stats.mannwhitneyu(x, y, alternative='two-sided')
            delta = cliffs_delta(x, y)
            delta_lo, delta_hi = cliffs_delta_ic95(x, y)
            linhas.append({'carga_vus': carga, 'metrica': metrica, 'U': u,
                            'p_value': p, 'cliffs_delta': round(delta, 4),
                            'cliffs_delta_ic95_lo': round(delta_lo, 4),
                            'cliffs_delta_ic95_hi': round(delta_hi, 4),
                            'magnitude': magnitude(delta)})
    mw = pd.DataFrame(linhas)

    reject, p_adj = holm_bonferroni(mw['p_value'])
    mw['p_ajustado_holm'] = p_adj
    mw['significativo_5pct'] = reject

    direcoes = []
    for _, r in mw.iterrows():
        if not r['significativo_5pct']:
            direcoes.append('empate (n.s.)')
        elif LOWER_IS_BETTER[r['metrica']]:
            direcoes.append('A1 melhor' if r['cliffs_delta'] < 0 else 'A2 melhor')
        else:
            direcoes.append('A1 melhor' if r['cliffs_delta'] > 0 else 'A2 melhor')
    mw['direcao'] = direcoes
    mw['p_value'] = mw['p_value'].round(6)
    mw['p_ajustado_holm'] = mw['p_ajustado_holm'].round(6)
    return mw


def gerar_overhead_ganho(df, desc):
    linhas = []
    for carga in CARGAS:
        sub = df[(df.carga_vus == carga) & (df.arquitetura == 'A2')]
        k6_lat = sub['lat_p95_ms'].mean()
        alb_lat = sub['alb_target_response_time_p95_ms'].mean()
        overhead_ms = k6_lat - alb_lat
        overhead_pct = (overhead_ms / alb_lat) * 100 if alb_lat else None
        linhas.append({'carga_vus': carga, 'tipo': 'overhead_ALB_isolado_ms', 'valor': round(overhead_ms, 2)})
        linhas.append({'carga_vus': carga, 'tipo': 'overhead_ALB_isolado_pct', 'valor': round(overhead_pct, 2)})

    for carga in CARGAS:
        r1 = desc[(desc.carga_vus == carga) & (desc.arquitetura == 'A1') & (desc.coluna == 'lat_p95_ms')].iloc[0]
        r2 = desc[(desc.carga_vus == carga) & (desc.arquitetura == 'A2') & (desc.coluna == 'lat_p95_ms')].iloc[0]
        diff = (r2['media'] / r1['media'] - 1) * 100
        linhas.append({'carga_vus': carga, 'tipo': 'diferenca_total_arquitetura_pct', 'valor': round(diff, 2)})

    for carga in [1000, 2000]:
        rl1 = desc[(desc.carga_vus == carga) & (desc.arquitetura == 'A1') & (desc.coluna == 'lat_p95_ms')].iloc[0]
        rl2 = desc[(desc.carga_vus == carga) & (desc.arquitetura == 'A2') & (desc.coluna == 'lat_p95_ms')].iloc[0]
        rt1 = desc[(desc.carga_vus == carga) & (desc.arquitetura == 'A1') & (desc.coluna == 'throughput_rps')].iloc[0]
        rt2 = desc[(desc.carga_vus == carga) & (desc.arquitetura == 'A2') & (desc.coluna == 'throughput_rps')].iloc[0]
        ganho_lat = (1 - rl2['media'] / rl1['media']) * 100
        ganho_thr = (rt2['media'] / rt1['media'] - 1) * 100
        linhas.append({'carga_vus': carga, 'tipo': 'ganho_latencia_pct', 'valor': round(ganho_lat, 2)})
        linhas.append({'carga_vus': carga, 'tipo': 'ganho_throughput_pct', 'valor': round(ganho_thr, 2)})
    return pd.DataFrame(linhas)


def gerar_correlacao(df):
    """Correlação CPU x Latência (Slide 9: 'Provar que CPU é o gargalo'),
    incluindo CPUCreditBalance em cargas sustentadas (1000/2000 VUs), por
    arquitetura. Usa Spearman (não assume linearidade nem normalidade)."""
    linhas = []
    for arq in ['A1', 'A2']:
        sub = df[df.arquitetura == arq]
        rho, p = stats.spearmanr(sub['cpu_util_pct'], sub['lat_p95_ms'])
        linhas.append({'arquitetura': arq, 'comparacao': 'CPU_media_x_lat_p95',
                        'cargas': 'todas', 'n': len(sub),
                        'spearman_rho': round(rho, 4), 'p_value': p})

        rho, p = stats.spearmanr(sub['cpu_util_peak_pct'], sub['lat_p95_ms'])
        linhas.append({'arquitetura': arq, 'comparacao': 'CPU_pico_x_lat_p95',
                        'cargas': 'todas', 'n': len(sub),
                        'spearman_rho': round(rho, 4), 'p_value': p})

        sub_sustentada = sub[sub.carga_vus.isin([1000, 2000])]
        rho, p = stats.spearmanr(sub_sustentada['cpu_credit_balance'], sub_sustentada['lat_p95_ms'])
        linhas.append({'arquitetura': arq, 'comparacao': 'CPUCreditBalance_x_lat_p95',
                        'cargas': '1000+2000 (sustentada)', 'n': len(sub_sustentada),
                        'spearman_rho': round(rho, 4), 'p_value': p})

    corr = pd.DataFrame(linhas)
    corr['p_value'] = corr['p_value'].round(6)
    return corr


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    print("Carregando datasets...")
    df = carregar_dados()
    df.to_csv(f"{OUTDIR}/dataset_completo_A1_A2.csv", index=False)

    print("Gerando estatística descritiva (média ± IC95%, todas as métricas)...")
    print("  -> lat_p95_ms usa bootstrap (cauda pesada); demais usam t-Student")
    desc = gerar_descritiva(df)
    desc.to_csv(f"{OUTDIR}/estatistica_descritiva.csv", index=False)

    print("Gerando Mann-Whitney U + Cliff's delta (com IC95%) + correção Holm-Bonferroni...")
    mw = gerar_mann_whitney(df)
    mw.to_csv(f"{OUTDIR}/mann_whitney.csv", index=False)

    print("Gerando overhead isolado do ALB + diferença total + ganhos...")
    resumo = gerar_overhead_ganho(df, desc)
    resumo.to_csv(f"{OUTDIR}/resumo_overhead_ganho.csv", index=False)

    print("Gerando correlação CPU x Latência (+ CPUCreditBalance em carga sustentada)...")
    corr = gerar_correlacao(df)
    corr.to_csv(f"{OUTDIR}/correlacao_cpu_latencia.csv", index=False)

    print(f"\n 5 arquivos gerados na pasta '{OUTDIR}/'.")
    print(f"   - dataset_completo_A1_A2.csv ({len(df)} linhas)")
    print(f"   - estatistica_descritiva.csv ({len(desc)} linhas)")
    print(f"   - mann_whitney.csv ({len(mw)} linhas)")
    print(f"   - resumo_overhead_ganho.csv ({len(resumo)} linhas)")
    print(f"   - correlacao_cpu_latencia.csv ({len(corr)} linhas)")


if __name__ == "__main__":
    main()
