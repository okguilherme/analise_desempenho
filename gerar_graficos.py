"""
gerar_graficos.py — Geração dos gráficos finais (A1 vs A2)

Requisitos: pandas, numpy, matplotlib, seaborn
Uso: python3 gerar_graficos.py
(rode na pasta que contém dataset_A1.csv e dataset_A2.csv)

Padrão adotado em TODO o trabalho (tabelas e gráficos):
  - Estimador central: MÉDIA (consistente com gerar_tabelas.py)
  - Barras/bandas de erro: IC95% (bootstrap via seaborn), nunca desvio padrão
  - Cores: A1 = vermelho (#d62728), A2 = azul (#1f77b4)
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import os

sns.set_theme(style="whitegrid", context="paper", font_scale=1.2)

CORES = {'A1': '#d62728', 'A2': '#1f77b4'}
PALETTE = [CORES['A1'], CORES['A2']]
HUE_ORDER = ['A1', 'A2']
CARGAS = [100, 500, 1000, 2000]
OUTDIR = "graficos"


def main():
    os.makedirs(OUTDIR, exist_ok=True)

    print("Carregando datasets...")
    df_a1 = pd.read_csv("dataset_A1.csv")
    df_a2 = pd.read_csv("dataset_A2_limpo.csv")

  

    df_a2['cpu_util_pct_comparavel'] = df_a2[['cpu_util_pct_ec2_1', 'cpu_util_pct_ec2_2']].mean(axis=1)
    df_a1['cpu_util_pct_comparavel'] = df_a1['cpu_util_pct']

    cols_comuns = ['arquitetura', 'carga_vus', 'lat_p95_ms', 'throughput_rps',
                   'taxa_erro', 'cpu_util_pct_comparavel']
    df_comparativo = pd.concat([df_a1[cols_comuns], df_a2[cols_comuns]], ignore_index=True)

    # ---------------------------------------------------------- Gráfico 1
    print("Gerando Gráfico 1: Ponto de Inflexão (Latência)...")
    plt.figure(figsize=(10, 6))
    sns.lineplot(data=df_comparativo, x='carga_vus', y='lat_p95_ms', hue='arquitetura',
                 hue_order=HUE_ORDER, marker='o', estimator='mean', errorbar=('ci', 95),
                 palette=PALETTE, linewidth=2.5)
    plt.title("O Ponto de Inflexão: Latência P95 (Monolito vs Escalonamento Horizontal)", pad=15)
    plt.xlabel("Carga (VUs)")
    plt.ylabel("Latência P95 (ms) - Escala Logarítmica")
    plt.yscale("log")
    plt.xticks(CARGAS)
    plt.axhline(500, color='gray', linestyle=':', alpha=0.6, label='SLA (500ms)')
    # anotação do ponto de ruptura
    plt.annotate('1.000 VUs\nPrimeira violação\nconsistente do SLA',
                 xy=(1000, 4368), xytext=(1150, 1600),
                 arrowprops=dict(arrowstyle='->', color='#444444', lw=1.3),
                 fontsize=9, ha='left', color='#444444')
    plt.legend(title='Arquitetura')
    plt.savefig(f"{OUTDIR}/grafico_1_inflexao_latencia.png", dpi=300, bbox_inches="tight")
    plt.close()

    # ---------------------------------------------------------- Gráfico 2
    print("Gerando Gráfico 2: Vazão Sustentada (RPS)...")
    plt.figure(figsize=(10, 6))
    sns.lineplot(data=df_comparativo, x='carga_vus', y='throughput_rps', hue='arquitetura',
                 hue_order=HUE_ORDER, marker='o', estimator='mean', errorbar=('ci', 95),
                 palette=PALETTE, linewidth=2.5)
    plt.title("Vazão (Throughput) Comparativa: Requisições Processadas por Segundo", pad=15)
    plt.xlabel("Carga (VUs)")
    plt.ylabel("Vazão Média (RPS) — banda = IC95%")
    plt.xticks(CARGAS)
    plt.legend(title='Arquitetura', loc='upper left')
    plt.savefig(f"{OUTDIR}/grafico_2_vazao_comparativa.png", dpi=300, bbox_inches="tight")
    plt.close()

    # ---------------------------------------------------------- Gráfico 3
    print("Gerando Gráfico 3: Causa e Efeito (CPU pico vs Erros no Monolito A1)...")
    fig, ax1 = plt.subplots(figsize=(10, 6))
    ax1.set_xlabel('Carga (VUs)')
    ax1.set_ylabel('Uso de CPU Pico (%)', color=CORES['A1'])
    sns.lineplot(data=df_a1, x='carga_vus', y='cpu_util_peak_pct', marker='o', ax=ax1,
                 color=CORES['A1'], label='CPU Pico (A1)', errorbar=('ci', 95))
    ax1.tick_params(axis='y', labelcolor=CORES['A1'])
    ax1.axhline(80, ls='--', color='black', alpha=0.5, label='Limiar de Saturação (80%)')
    ax1.set_ylim(0, 105)

    ax2 = ax1.twinx()
    ax2.set_ylabel('Taxa de Erro (%)', color='#2ca02c')
    df_a1['taxa_erro_pct'] = df_a1['taxa_erro'] * 100
    sns.lineplot(data=df_a1, x='carga_vus', y='taxa_erro_pct', marker='s', ax=ax2,
                 color='#2ca02c', label='Taxa de Erro', errorbar=('ci', 95))
    ax2.tick_params(axis='y', labelcolor='#2ca02c')

    fig.tight_layout()
    plt.title("Monolito (A1): Saturação de Hardware vs Degradação do Serviço", pad=15)
    ax1.get_legend().remove()
    ax2.get_legend().remove()
    fig.legend(loc="upper left", bbox_to_anchor=(0.1, 0.9))
    plt.savefig(f"{OUTDIR}/grafico_3_cpu_vs_erros_A1.png", dpi=300, bbox_inches="tight")
    plt.close()

    # ---------------------------------------------------------- Gráfico 4
    print("Gerando Gráfico 4: Dispersão e Estabilidade (Box + pontos)...")
    plt.figure(figsize=(11, 6.5))
    ax = sns.boxplot(data=df_comparativo, x='carga_vus', y='lat_p95_ms', hue='arquitetura', 
                     
                      hue_order=HUE_ORDER, palette=PALETTE, width=0.6, showfliers=False)
    sns.stripplot(data=df_comparativo, x='carga_vus', y='lat_p95_ms', hue='arquitetura',
                  hue_order=HUE_ORDER, dodge=True, palette=PALETTE, size=3, alpha=0.25,
                  legend=False, ax=ax)
    plt.yscale("log")
    plt.title("Dispersão da Latência: Monolito vs Escalonamento Horizontal", pad=15)
    plt.xlabel("Carga (VUs)")
    plt.ylabel("Latência P95 (ms) - Escala Logarítmica")
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles[:2], labels[:2], title='Arquitetura')
    plt.savefig(f"{OUTDIR}/grafico_4_dispersao_boxplot.png", dpi=300, bbox_inches="tight")
    plt.close()

    # ---------------------------------------------------------- Gráfico 5
    print("Gerando Gráfico 5: CPU Comparativa (A1 vs A2)...")
    plt.figure(figsize=(10, 6))
    sns.lineplot(data=df_comparativo, x='carga_vus', y='cpu_util_pct_comparavel', hue='arquitetura',
                 hue_order=HUE_ORDER, marker='o', estimator='mean', errorbar=('ci', 95),
                 palette=PALETTE, linewidth=2.5)
    plt.axhline(80, color='black', linestyle='--', alpha=0.5, label='Limiar de Saturação (80%)')
    plt.title("Uso de CPU Comparativo (A1: 1 instância | A2: média de 2 instâncias)", pad=15)
    plt.xlabel("Carga (VUs)")
    plt.ylabel("CPU Média (%) — banda = IC95%")
    plt.figtext(0.5, -0.03,
                "Nota: CPU apresentada por instância (média), não soma total do cluster.",
                ha="center", fontsize=8, style='italic', color='#555555')
    plt.xticks(CARGAS)
    plt.legend(title='Arquitetura')
    plt.savefig(f"{OUTDIR}/grafico_5_cpu_comparativa.png", dpi=300, bbox_inches="tight")
    plt.close()

    # ---------------------------------------------------------- Gráfico 6 (novo)
    print("Gerando Gráfico 6: Taxa de Erro Comparativa (A1 vs A2)...")
    df_comparativo['taxa_erro_pct'] = df_comparativo['taxa_erro'] * 100
    plt.figure(figsize=(10, 6))
    sns.lineplot(data=df_comparativo, x='carga_vus', y='taxa_erro_pct', hue='arquitetura',
                 hue_order=HUE_ORDER, marker='o', estimator='mean', errorbar=('ci', 95),
                 palette=PALETTE, linewidth=2.5)
    plt.title("Taxa de Erro Comparativa: Monolito vs Escalonamento Horizontal", pad=15)
    plt.xlabel("Carga (VUs)")
    plt.ylabel("Taxa de Erro (%) — banda = IC95%")
    plt.xticks(CARGAS)
    plt.legend(title='Arquitetura')
    plt.savefig(f"{OUTDIR}/grafico_6_taxa_erro_comparativa.png", dpi=300, bbox_inches="tight")
    plt.close()

    gerar_grafico_7(df_a1, df_a2)

    print(f"\n 7 gráficos gerados em alta resolução (300 DPI) na pasta '{OUTDIR}/'.")


def gerar_grafico_7(df_a1, df_a2):
    print("Gerando Gráfico 7: Correlação CPU pico x Latência (Slide 9)...")
    from scipy import stats as sp_stats
    rho_a1, _ = sp_stats.spearmanr(df_a1['cpu_util_peak_pct'], df_a1['lat_p95_ms'])
    rho_a2, _ = sp_stats.spearmanr(df_a2['cpu_util_peak_pct'], df_a2['lat_p95_ms'])

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), sharey=True)
    for ax, df_x, arq, rho in [(axes[0], df_a1, 'A1', rho_a1), (axes[1], df_a2, 'A2', rho_a2)]:
        sc = ax.scatter(df_x['cpu_util_peak_pct'], df_x['lat_p95_ms'], c=df_x['carga_vus'],
                         cmap='viridis', alpha=0.75, s=45, edgecolor='white', linewidth=0.5)
        ax.set_yscale('log')
        ax.set_xlabel('CPU pico (%)')
        ax.set_title(f'{arq} (Spearman ρ={rho:.3f})')
        ax.axvline(80, color='red', linestyle=':', alpha=0.5)
    axes[0].set_ylabel('Latência P95 (ms) — escala log')
    cbar = fig.colorbar(sc, ax=axes, label='Carga (VUs)', shrink=0.85)
    fig.suptitle('Correlação CPU Pico × Latência P95 (por arquitetura)', y=1.02)
    plt.savefig(f"{OUTDIR}/grafico_7_correlacao_cpu_latencia.png", dpi=300, bbox_inches="tight")
    plt.close()


if __name__ == "__main__":
    main()
