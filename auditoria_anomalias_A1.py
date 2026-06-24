import pandas as pd

# Carregar o dataset do Monolito (A1)
try:
    df_a1 = pd.read_csv('dataset_A1.csv')
except FileNotFoundError:
    print("Erro: Arquivo dataset_A1.csv não encontrado na pasta atual.")
    exit()

# Ordenar por data de início (Timeline real)
df_a1['inicio'] = pd.to_datetime(df_a1['inicio'])
df_a1 = df_a1.sort_values(by=['carga_vus', 'inicio'])

# Colunas pedidas pela auditoria para o A1 (não temos métricas de ALB aqui)
colunas_auditoria = [
    'inicio', 'replica', 'lat_p95_ms', 'throughput_rps', 
    'taxa_erro', 'cpu_util_pct', 'total_reqs', 'duracao_s'
]

print("=== AUDITORIA A1 (MONOLITO): 1000 VUs ===")
df_1000 = df_a1[df_a1['carga_vus'] == 1000][colunas_auditoria].copy()
df_1000['inicio'] = df_1000['inicio'].dt.strftime('%d/%m %H:%M')
df_1000['lat_p95_ms'] = df_1000['lat_p95_ms'].round(2)
df_1000['taxa_erro'] = (df_1000['taxa_erro'] * 100).round(4).astype(str) + '%'
print(df_1000.to_markdown(index=False))

print("\n\n=== AUDITORIA A1 (MONOLITO): 2000 VUs ===")
df_2000 = df_a1[df_a1['carga_vus'] == 2000][colunas_auditoria].copy()
df_2000['inicio'] = df_2000['inicio'].dt.strftime('%d/%m %H:%M')
df_2000['lat_p95_ms'] = df_2000['lat_p95_ms'].round(2)
df_2000['taxa_erro'] = (df_2000['taxa_erro'] * 100).round(4).astype(str) + '%'
print(df_2000.to_markdown(index=False))
