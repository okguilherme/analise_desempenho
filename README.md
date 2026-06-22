# Avaliação de Servidores Web: Impacto do Balanceamento de Carga em Ambiente AWS

Comparação de desempenho entre um servidor web monolítico em instância única
(**A1**) e uma arquitetura com balanceamento de carga via AWS ALB + 2
instâncias (**A2**), sob 4 níveis de carga (100/500/1.000/2.000 VUs),
30 réplicas por cenário.

## Estrutura do repositório

```
.
├── README.md
├── build_dataset.py          # ETL: consolida réplicas brutas de A1 -> dataset_A1.csv
├── build_dataset_A2.py       # ETL: consolida réplicas brutas de A2 -> dataset_A2_<carga>.csv
├── gerar_tabelas.py          # Estatística: descritiva, Mann-Whitney, correlação, overhead
├── gerar_graficos.py         # Gera os 7 gráficos finais (PNG, 300 DPI)
├── dataset_A1.csv            # Dataset consolidado de A1 (120 réplicas)
├── dataset_A2.csv            # Dataset consolidado de A2 (120 réplicas, 4 cargas concatenadas)
├── tabelas/                  # Saída de gerar_tabelas.py
│   ├── dataset_completo_A1_A2.csv
│   ├── estatistica_descritiva.csv
│   ├── mann_whitney.csv
│   ├── resumo_overhead_ganho.csv
│   └── correlacao_cpu_latencia.csv
└── graficos/                 # Saída de gerar_graficos.py
    ├── grafico_1_inflexao_latencia.png
    ├── grafico_2_vazao_comparativa.png
    ├── grafico_3_cpu_vs_erros_A1.png
    ├── grafico_4_dispersao_boxplot.png
    ├── grafico_5_cpu_comparativa.png
    ├── grafico_6_taxa_erro_comparativa.png
    └── grafico_7_correlacao_cpu_latencia.png

```

## Como reproduzir

Requisitos: `pip install pandas numpy scipy matplotlib seaborn`

```bash
# 1. Consolidar os dados brutos (já feito; só roda se houver réplicas novas)
python3 build_dataset.py <pasta_com_tar_gz_A1> dataset_A1.csv
python3 build_dataset_A2.py <pasta_repNN_A2_100> 100 A2_100.csv
python3 build_dataset_A2.py <pasta_repNN_A2_500> 500 A2_500.csv
python3 build_dataset_A2.py <pasta_repNN_A2_1000> 1000 A2_1000.csv
python3 build_dataset_A2.py <pasta_repNN_A2_2000> 2000 A2_2000.csv
awk 'FNR==1 && NR!=1{next}{print}' A2_100.csv A2_500.csv A2_1000.csv A2_2000.csv > dataset_A2.csv

# 2. Gerar tabelas estatísticas
python3 gerar_tabelas.py

# 3. Gerar gráficos
python3 gerar_graficos.py
```

## Rastreabilidade: Slide → Análise

Esse repositório foi auditado item a item contra o planejamento original
(Objetivos Específicos do Slide 4, Métricas do Slide 5, Análise Estatística
Prevista do Slide 9). Mapa de cobertura:

| Item do planejamento | Onde está respondido |
|---|---|
| OE1 (curva de latência + SLA 500ms) | Gráfico 1 |
| OE2 (ganho de throughput) | Gráfico 2 + `ganho_throughput_pct` |
| OE3 (saturação de CPU > 80%) | Gráficos 3, 5, 7 + Mann-Whitney de CPU |
| OE4 (ponto de inflexão) | Gráfico 1 + Mann-Whitney por carga |
| Comparação de latência (Slide 9) | Gráfico 1 |
| Comparação de throughput (Slide 9) | Gráfico 2 |
| **Correlação CPU × Latência (Slide 9)** | Gráfico 7 + `correlacao_cpu_latencia.csv` |
| Teste de significância (Slide 9) | `mann_whitney.csv` (IC95% + Mann-Whitney) |
| Overhead do ALB (Slide 9) | `resumo_overhead_ganho.csv` (`overhead_ALB_isolado_*`) |
| CPUCreditBalance / modelo burstable (OE3) | `correlacao_cpu_latencia.csv` — sem correlação com latência (ver Limitações) |

## Metodologia estatística

- **Estimador central:** média (consistente em todas as tabelas e gráficos)
- **Intervalo de confiança:** 95%. `lat_p95_ms` usa **bootstrap** (10.000
  reamostragens) por ser uma métrica de cauda pesada; as demais métricas usam
  **t-Student**. Os gráficos usam bootstrap via `seaborn errorbar=('ci',95)`
  para todas as curvas (consistente com a tabela)
- **Teste de hipótese:** Mann-Whitney U comparando A1 vs A2 por nível de
  carga, em **5 métricas**: latência P95, throughput, taxa de erro, CPU
  média e CPU pico (20 comparações no total: 4 cargas × 5 métricas)
- **Tamanho de efeito:** Cliff's delta com IC95% via bootstrap
- **Correção para múltiplas comparações:** Holm-Bonferroni sobre as 20
  comparações, coluna `p_ajustado_holm` em `mann_whitney.csv`
- **Correlação:** Spearman entre CPU (média e pico) e latência P95, por
  arquitetura, usando todas as réplicas; e entre CPUCreditBalance e latência
  P95, restrito às cargas sustentadas (1.000/2.000 VUs)

## Resultados principais

| Carga | Vencedor (latência) | Vencedor (throughput) | Vencedor (erro) |
|---|---|---|---|
| 100 VUs | empate (p=0,12) | empate na prática (diferença de 0,05%) | empate |
| 500 VUs | **A1** (overhead do ALB ainda não compensa) | **A2** | **A2** |
| 1.000 VUs | **A2** (ponto de inflexão da latência) | **A2** | **A2** |
| 2.000 VUs | **A2** | empate após correção de Holm-Bonferroni* | **A2** |

\* Sem correção, p=0,036. Após Holm-Bonferroni, p_ajustado=0,109 — a alta
variância do A1 nessa carga (IC95% de ±201 req/s) não sustenta significância
após corrigir as comparações múltiplas. **H1 é totalmente confirmada em
1.000 VUs (latência + throughput); em 2.000 VUs só a latência se sustenta
estatisticamente.**

- Overhead **isolado** do ALB: 1,2% a 5,1% em todas as cargas — pequeno e estável
- Ganho de A2 em 1.000 VUs: latência -34,9%, throughput +150%
- Ganho de A2 em 2.000 VUs: latência -68,4%
- **CPU pico correlaciona muito mais forte com latência que CPU média**
  (A1: ρ=0,665 vs 0,450; A2: ρ=0,787 vs 0,459) — reforça CPU pico como a
  métrica certa pra avaliar saturação (OE3)
- **CPUCreditBalance não correlaciona com latência em carga sustentada**
  (ρ≈0,06, p>0,6 nas duas arquiteturas) — o modelo burstable nunca foi um
  fator limitante; os créditos nunca chegaram perto de esgotar
- **CPU pico do A2 é alto também** (93-98% a partir de 500 VUs por
  instância), maior que o pico do A1 nas mesmas cargas (73-88%), mas A2
  ainda assim performa muito melhor — CPU pico isolado não explica toda a
  diferença entre arquiteturas (ver Gráfico 7: réplicas de A2 com CPU pico
  ~100% e latência ainda baixa em 2.000 VUs)
- **`HealthyHostCount` do ALB cai para 1,82±0,07 em 2.000 VUs** (era
  exatamente 2,0 nas demais cargas) — evidência direta de falha de health
  check sob saturação extrema

## Gráficos gerados

| # | Gráfico | Objetivo |
|---|---|---|
| 1 | Ponto de Inflexão (Latência P95 × Carga) | OE1, OE4 |
| 2 | Vazão Comparativa (Throughput × Carga) | OE2 |
| 3 | Causa e Efeito (CPU pico × Taxa de Erro, só A1) | OE3 |
| 4 | Dispersão (Boxplot da Latência P95) | Transversal |
| 5 | CPU Comparativa (A1 vs A2) | OE3 |
| 6 | Taxa de Erro Comparativa (A1 vs A2) | OE3 |
| 7 | Correlação CPU Pico × Latência (A1 vs A2) | OE3 (Slide 9) |

## Limitações conhecidas

- `lat_p99` não foi coletada (k6 registrou apenas P90 e P95)
- O período de rampa (~60s, ~25% do tempo de teste) não foi descartado dos
  agregados porque o `resultado.json` do k6 só traz o resumo final. Análise
  do `metricas.txt` mostrou que a rampa responde por 14,5%-21,3% das
  requisições (abaixo da fração de tempo), e o viés é simétrico entre A1 e
  A2 — não compromete a comparação relativa.
- O estágio de "spike" (P3) previsto na matriz de cenários original (Slide
  8, para cargas altas) não está presente nos dados finais — todas as
  réplicas seguem o padrão rampa+platô, provavelmente resultado da fusão de
  Fatores 3+4 pedida pelo professor. Vale confirmar que isso foi intencional.
- Taxa de erro e throughput foram medidos só pelo lado k6 (cliente); as
  métricas nativas do ALB (`HTTPCode_Target_5XX`, `RequestCount`) previstas
  no Slide 5 como fonte adicional não foram coletadas/cruzadas.
- CPUCreditBalance e Conexões Ativas (`ActiveConnectionCount`) têm
  estatística descritiva e (a primeira) correlação calculada, mas não têm
  uma narrativa/gráfico dedicado explorando "saturação de conexões" (OE4)
  com a mesma profundidade das demais métricas.
