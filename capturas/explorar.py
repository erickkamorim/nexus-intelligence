import os, json, psycopg
c = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
def q(s, *a):
    cur = c.execute(s, a); return cur.fetchall()
print("snapshots:", q("select count(*), min(gerado_em), max(gerado_em), count(distinct gerado_em::date) from previsoes_publicadas"))
print("por dia:", q("select gerado_em::date, count(*) from previsoes_publicadas group by 1 order by 1"))
r = q("select conteudo from previsoes_publicadas order by id limit 1")[0][0]
print("chaves:", list(r.keys())); print("ipca keys:", list(r["ipca"].keys())); print("ipca prev[0]:", r["ipca"]["previsoes"][0])
print("cambio keys:", list(r["cambio"].keys())); print("cambio prev[0]:", r["cambio"]["previsoes"][0])
print("acum:", r["ipca"].get("acumulado_12m", [None])[0])
print("alvos ipca por snapshot:", q("""select gerado_em::date, string_agg(distinct p->>'alvo', ',') from previsoes_publicadas, jsonb_array_elements(conteudo->'ipca'->'previsoes') p group by 1 order by 1"""))
print("ipca ultimos:", q("select data_referencia, valor from serie_atual where serie='ipca_mensal' order by 1 desc limit 4"))
print("divulgacoes:", q("select mes_referencia, divulgado_em from divulgacoes where serie='ipca_mensal' and mes_referencia >= '2026-06-01' order by 1"))
print("series:", q("select serie, count(*), min(data_referencia), max(data_referencia) from serie_atual group by 1"))
print("tabelas:", q("select table_name from information_schema.tables where table_schema='public' order by 1"))
print("backtest exec:", q("select serie, count(*), max(iniciado_em) from backtest_execucoes group by 1"))
