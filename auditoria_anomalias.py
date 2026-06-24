import pandas as pd

# Carregar o dataset
df = pd.read_csv('dataset_A2_limpo.csv')

# Ordenar por data de início (Timeline real)
df['inicio'] = pd.to_datetime(df['inicio'])
df = df.sort_values(by=['carga_vus', 'inicio'])

# Colunas pedidas pela auditoria
colunas_auditoria = [
    'inicio', 'replica', 'lat_p95_ms', 'alb_target_response_time_p95_ms',
    'throughput_rps', 'taxa_erro', 'total_reqs', 'vus_max_atingido', 'duracao_s'
]

print("=== AUDITORIA A2: 1000 VUs ===")
df_1000 = df[df['carga_vus'] == 1000][colunas_auditoria].copy()
# Formatando para facilitar a leitura
df_1000['inicio'] = df_1000['inicio'].dt.strftime('%d/%m %H:%M')
df_1000['lat_p95_ms'] = df_1000['lat_p95_ms'].round(2)
df_1000['alb_target_response_time_p95_ms'] = df_1000['alb_target_response_time_p95_ms'].round(2)
df_1000['taxa_erro'] = (df_1000['taxa_erro'] * 100).round(4).astype(str) + '%'
print(df_1000.to_markdown(index=False))

print("\n\n=== AUDITORIA A2: 2000 VUs ===")
df_2000 = df[df['carga_vus'] == 2000][colunas_auditoria].copy()
df_2000['inicio'] = df_2000['inicio'].dt.strftime('%d/%m %H:%M')
df_2000['lat_p95_ms'] = df_2000['lat_p95_ms'].round(2)
df_2000['alb_target_response_time_p95_ms'] = df_2000['alb_target_response_time_p95_ms'].round(2)
df_2000['taxa_erro'] = (df_2000['taxa_erro'] * 100).round(4).astype(str) + '%'
print(df_2000.to_markdown(index=False))


print("\n\n=== AUDITORIA A2: 100 VUs ===")
df_100 = df[df['carga_vus'] == 100][colunas_auditoria].copy()
df_100['inicio'] = df_100['inicio'].dt.strftime('%d/%m %H:%M')
df_100['lat_p95_ms'] = df_100['lat_p95_ms'].round(2)
df_100['alb_target_response_time_p95_ms'] = df_100['alb_target_response_time_p95_ms'].round(2)
df_100['taxa_erro'] = (df_100['taxa_erro'] * 100).round(4).astype(str) + '%'
print(df_100.to_markdown(index=False))



print("\n\n=== AUDITORIA A2: 1000 VUs ===")
df_1000 = df[df['carga_vus'] == 1000][colunas_auditoria].copy()
df_1000['inicio'] = df_1000['inicio'].dt.strftime('%d/%m %H:%M')
df_1000['lat_p95_ms'] = df_1000['lat_p95_ms'].round(2)
df_1000['alb_target_response_time_p95_ms'] = df_1000['alb_target_response_time_p95_ms'].round(2)
df_1000['taxa_erro'] = (df_1000['taxa_erro'] * 100).round(4).astype(str) + '%'
print(df_1000.to_markdown(index=False))
