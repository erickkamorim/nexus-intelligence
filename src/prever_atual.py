"""
NEXUS Forecast · Fase 4 · Gera e publica as previsões de hoje.

Uso (na raiz do projeto, depois da coleta e de pelo menos um backtest):
    python src/prever_atual.py

Usa a metodologia validada no último backtest:
  * IPCA: SARIMA com intervalos calibrados pelos erros do backtest, mais o Focus;
  * Câmbio: passeio aleatório com intervalos empíricos.
Grava um retrato completo em previsoes_publicadas (lido pela API e pelo site).
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from coleta.armazenamento import preparar_esquema  # noqa: E402
from coleta.modelos import BRASILIA  # noqa: E402
from forecast.atual import mensagens, previsao_cambio, previsao_ipca, tabela_desempenho  # noqa: E402
from forecast.fontes import FonteBanco  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/nexus_db")

ULTIMA_EXECUCAO = """
    SELECT DISTINCT ON (serie) id, serie, iniciado_em
    FROM backtest_execucoes ORDER BY serie, id DESC"""


def ler_backtest(conn) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    execucoes = conn.execute(ULTIMA_EXECUCAO).fetchall()
    if not execucoes:
        raise RuntimeError("Nenhum backtest encontrado. Rode antes: python src/rodar_backtest.py")
    ids = {serie: id_ for id_, serie, _ in execucoes}
    datas = {serie: quando.isoformat() for _, serie, quando in execucoes}
    cur = conn.execute(
        """SELECT p.medida, p.modelo, p.origem, p.h, p.alvo, p.previsto::float, p.li80::float, p.ls80::float,
                  p.li95::float, p.ls95::float, p.realizado::float
           FROM backtest_previsoes p WHERE p.execucao_id = %s AND p.modelo = 'sarima'""", (ids.get("ipca_mensal"),))
    previsoes = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
    cur = conn.execute(
        """SELECT e.serie, m.medida, m.comparacao, m.modelo, m.h, m.n, m.rmse::float, m.rmse_relativo::float,
                  m.cobertura80::float, m.cobertura95::float, m.veredito
           FROM backtest_metricas m JOIN backtest_execucoes e ON e.id = m.execucao_id
           WHERE m.execucao_id = ANY(%s)""", (list(ids.values()),))
    metricas = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
    return previsoes, metricas, datas


def versao_codigo() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ, capture_output=True,
                              text=True, timeout=5).stdout.strip() or None
    except Exception:
        return None


def main():
    import psycopg

    agora = datetime.now(BRASILIA)
    with psycopg.connect(DATABASE_URL) as conn:
        preparar_esquema(conn)
        fonte = FonteBanco(conn)
        backtest, metricas, datas_backtest = ler_backtest(conn)
        print("Ajustando o SARIMA com todos os dados conhecidos hoje (escolha de ordem incluída)...")
        ipca = previsao_ipca(fonte, agora, backtest)
        cambio = previsao_cambio(fonte, agora)
        desempenho = tabela_desempenho(metricas)
        conteudo = {
            "gerado_em": agora.isoformat(timespec="seconds"),
            "backtest": datas_backtest,
            "ipca": ipca,
            "cambio": cambio,
            "desempenho": desempenho,
            "mensagens": mensagens(desempenho),
        }
        conn.execute("INSERT INTO previsoes_publicadas (versao_codigo, conteudo) VALUES (%s, %s)",
                     (versao_codigo(), json.dumps(conteudo, ensure_ascii=False)))
        conn.commit()

    print(f"\nIPCA (último mês conhecido: {ipca['ultimo_conhecido'][:7]}, modelo {ipca['especificacao']})")
    for p in ipca["previsoes"]:
        faixa = f"[{p['li80']}, {p['ls80']}]" if p["li80"] is not None else "(sem calibração)"
        print(f"  {p['alvo'][:7]}  previsto {p['previsto']:>7}  faixa 80% {faixa:<22} Focus {p['focus']}")
    a = ipca["acumulado_12m"][-1]
    print(f"  Acumulado 12 meses até {a['alvo'][:7]}: {a['previsto']}% (80%: {a['li80']} a {a['ls80']}) · Focus {a['focus']}%")
    print(f"\nDólar (última cotação: {cambio['ultimo_conhecido']})")
    for p in cambio["previsoes"]:
        print(f"  +{p['h']:>2} dias úteis  R$ {p['previsto']}  faixa 80% [R$ {p['li80']}, R$ {p['ls80']}]")
    print("\nMensagens do dashboard:")
    for serie, texto in conteudo["mensagens"].items():
        print(f"  {serie}: {texto}")
    print("\nPrevisões publicadas na tabela previsoes_publicadas.")


if __name__ == "__main__":
    main()
