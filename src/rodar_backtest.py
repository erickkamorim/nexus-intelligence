"""
NEXUS Forecast · Fase 2 · Backtest dos modelos de referência e do Focus.

Uso (na raiz do projeto, com DATABASE_URL configurada e a coleta da Fase 1 feita):
    python src/rodar_backtest.py

O que faz:
  * IPCA: uma origem logo após cada divulgação do IBGE registrada no calendário
    (a partir de jan/2017), horizontes de 1 a 6 meses;
  * Câmbio: 250 origens semanais (a cada 5 dias úteis), horizontes 1, 5, 10 e 21;
  * compara cada modelo com a referência obrigatória (Diebold-Mariano com
    correção para sobreposição) e, no IPCA, também com o Boletim Focus;
  * grava previsões e métricas no banco e em data/backtest/*.csv.
"""

import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from coleta.armazenamento import preparar_esquema  # noqa: E402
from forecast.backtest import ConfigSerie, executar, origens_semanais  # noqa: E402
from forecast.fontes import FonteBanco  # noqa: E402
from forecast.metricas import resumo  # noqa: E402
from forecast.modelos import MODELOS_CAMBIO, MODELOS_IPCA  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/nexus_db")

IPCA = ConfigSerie("ipca_mensal", "mensal", horizontes=[1, 2, 3, 4, 5, 6], n_erros_intervalo=60, minimo_historico=72)
CAMBIO = ConfigSerie("ptax_venda", "diaria", horizontes=[1, 5, 10, 21], n_erros_intervalo=500, minimo_historico=300)
PASSO_CAMBIO = 5


def versao_codigo() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ, capture_output=True,
                              text=True, timeout=5).stdout.strip() or None
    except Exception:
        return None


def gravar(conn, cfg: ConfigSerie, referencia: str, parametros: dict, previsoes: pd.DataFrame,
           metricas: dict[str, pd.DataFrame]) -> int:
    with conn.transaction():
        execucao = conn.execute(
            "INSERT INTO backtest_execucoes (serie, referencia, versao_codigo, parametros) VALUES (%s, %s, %s, %s) RETURNING id",
            (cfg.serie, referencia, versao_codigo(), json.dumps(parametros))).fetchone()[0]
        cols = ["modelo", "origem", "ultimo_conhecido", "h", "alvo", "previsto", "li80", "ls80", "li95", "ls95", "realizado"]
        p = previsoes.reindex(columns=cols).astype(object).where(previsoes.reindex(columns=cols).notna(), None)
        with conn.cursor().copy(f"COPY backtest_previsoes (execucao_id, {', '.join(cols)}) FROM STDIN") as copia:
            for linha in p.itertuples(index=False):
                copia.write_row((execucao, *linha))
        cols_m = ["modelo", "h", "n", "mae", "rmse", "rmse_relativo", "cobertura80", "cobertura95",
                  "n_comum", "dm", "p_valor", "p_melhor", "veredito"]
        for comparacao, m in metricas.items():
            m = m.reindex(columns=cols_m).astype(object).where(m.reindex(columns=cols_m).notna(), None)
            conn.cursor().executemany(
                f"INSERT INTO backtest_metricas (execucao_id, comparacao, {', '.join(cols_m)}) "
                f"VALUES (%s, %s, {', '.join(['%s'] * len(cols_m))})",
                [(execucao, comparacao, *linha) for linha in m.itertuples(index=False)])
    return execucao


def mostrar(titulo: str, m: pd.DataFrame) -> None:
    print(f"\n=== {titulo} ===")
    colunas = [c for c in ["h", "modelo", "n", "mae", "rmse", "rmse_relativo", "cobertura80", "cobertura95",
                           "p_melhor", "veredito"] if c in m]
    with pd.option_context("display.width", 200, "display.max_columns", 20, "display.float_format", "{:.4f}".format):
        print(m[colunas].to_string(index=False))


def main():
    import psycopg

    pasta = RAIZ / "data" / "backtest"
    pasta.mkdir(parents=True, exist_ok=True)
    with psycopg.connect(DATABASE_URL) as conn:
        preparar_esquema(conn)
        fonte = FonteBanco(conn)

        # ---------------- IPCA: origens logo após cada divulgação com data exata
        origens = [d + timedelta(minutes=1) for d in fonte.divulgacoes_ipca()]
        prev = executar(fonte, IPCA, MODELOS_IPCA, origens, usar_focus=True)
        m_ref = resumo(prev, "ingenuo", passo=1)
        m_focus = resumo(prev, "focus_mediana", passo=1)
        gravar(conn, IPCA, "ingenuo",
               {"origens": len(origens), "horizontes": IPCA.horizontes, "n_erros_intervalo": IPCA.n_erros_intervalo,
                "primeira_origem": str(min(origens)), "ultima_origem": str(max(origens))},
               prev, {"ingenuo": m_ref, "focus_mediana": m_focus})
        prev.to_csv(pasta / "ipca_previsoes.csv", index=False)
        m_ref.to_csv(pasta / "ipca_metricas_vs_ingenuo.csv", index=False)
        m_focus.to_csv(pasta / "ipca_metricas_vs_focus.csv", index=False)
        mostrar("IPCA · comparação com o modelo ingênuo", m_ref)
        mostrar("IPCA · comparação com o Boletim Focus (mesma origem, mesmo mês-alvo)", m_focus)

        # ---------------- Câmbio: origens semanais
        calendario = fonte.atual(CAMBIO.serie).index
        origens = origens_semanais(calendario, 250, max(CAMBIO.horizontes), PASSO_CAMBIO)
        prev = executar(fonte, CAMBIO, MODELOS_CAMBIO, origens)
        m_rw = resumo(prev, "passeio_aleatorio", passo=PASSO_CAMBIO)
        gravar(conn, CAMBIO, "passeio_aleatorio",
               {"origens": len(origens), "passo_dias_uteis": PASSO_CAMBIO, "horizontes": CAMBIO.horizontes,
                "n_erros_intervalo": CAMBIO.n_erros_intervalo,
                "primeira_origem": str(min(origens)), "ultima_origem": str(max(origens))},
               prev, {"passeio_aleatorio": m_rw})
        prev.to_csv(pasta / "cambio_previsoes.csv", index=False)
        m_rw.to_csv(pasta / "cambio_metricas.csv", index=False)
        mostrar("Câmbio · comparação com o passeio aleatório (referência obrigatória)", m_rw)

    print(f"\nResultados gravados no banco (backtest_*) e em {pasta}")


if __name__ == "__main__":
    main()
