"""
NEXUS Forecast · Backtest dos modelos de referência, do Focus e do SARIMA/ARIMA.

Uso (na raiz do projeto, com DATABASE_URL configurada e a coleta da Fase 1 feita):
    python src/rodar_backtest.py               # completo (SARIMA leva alguns minutos)
    python src/rodar_backtest.py --sem-sarima  # só referências e Focus (rápido)
    python src/rodar_backtest.py --serie ipca  # só uma das séries

Memória: a seleção de ordem usa 2 processos em paralelo por padrão. Para mudar,
defina NEXUS_PROCESSOS antes de rodar (1 = sem paralelismo, menor uso de memória).

Mesmas origens e horizontes da Fase 2:
  * IPCA: uma origem logo após cada divulgação com data exata (a partir de jan/2017),
    horizontes de 1 a 6 meses; também avalia o acumulado em 12 meses;
  * Câmbio: 250 origens a cada 5 dias úteis, horizontes 1, 5, 10 e 21.
Comparações: referência obrigatória (Diebold-Mariano com correção para
sobreposição), no IPCA também o Boletim Focus e a média sazonal. A cobertura
dos intervalos de 80% e 95% aparece em todas as tabelas, inclusive a dos
intervalos calibrados (modelos com sufixo _calibrado).
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from coleta.armazenamento import preparar_esquema  # noqa: E402
from forecast.backtest import ConfigSerie, executar, origens_semanais  # noqa: E402
from forecast.calibracao import calibrar  # noqa: E402
from forecast.fontes import FonteBanco  # noqa: E402
from forecast.metricas import resumo  # noqa: E402
from forecast.modelos import MODELOS_CAMBIO, MODELOS_IPCA  # noqa: E402
from forecast.sarima import ModeloSarima, grade_cambio, grade_ipca  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/nexus_db")

IPCA = ConfigSerie("ipca_mensal", "mensal", horizontes=[1, 2, 3, 4, 5, 6], n_erros_intervalo=60, minimo_historico=72)
CAMBIO = ConfigSerie("ptax_venda", "diaria", horizontes=[1, 5, 10, 21], n_erros_intervalo=500, minimo_historico=300)
PASSO_CAMBIO = 5
COLUNAS_PREV = ["medida", "modelo", "origem", "ultimo_conhecido", "h", "alvo", "previsto",
                "li80", "ls80", "li95", "ls95", "realizado", "detalhe"]
COLUNAS_MET = ["modelo", "h", "n", "mae", "rmse", "rmse_relativo", "cobertura80", "cobertura95",
               "n_comum", "dm", "p_valor", "p_melhor", "veredito"]


def versao_codigo() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ, capture_output=True,
                              text=True, timeout=5).stdout.strip() or None
    except Exception:
        return None


def _sem_nan(df: pd.DataFrame, colunas: list[str]) -> pd.DataFrame:
    df = df.reindex(columns=colunas).astype(object)
    return df.where(df.notna(), None)


def gravar(conn, cfg, referencia, parametros, previsoes, metricas: dict[tuple[str, str], pd.DataFrame]) -> int:
    with conn.transaction():
        execucao = conn.execute(
            "INSERT INTO backtest_execucoes (serie, referencia, versao_codigo, parametros) VALUES (%s, %s, %s, %s) RETURNING id",
            (cfg.serie, referencia, versao_codigo(), json.dumps(parametros, default=str))).fetchone()[0]
        with conn.cursor().copy(f"COPY backtest_previsoes (execucao_id, {', '.join(COLUNAS_PREV)}) FROM STDIN") as copia:
            for linha in _sem_nan(previsoes, COLUNAS_PREV).itertuples(index=False):
                copia.write_row((execucao, *linha))
        for (medida, comparacao), m in metricas.items():
            conn.cursor().executemany(
                f"INSERT INTO backtest_metricas (execucao_id, medida, comparacao, {', '.join(COLUNAS_MET)}) "
                f"VALUES (%s, %s, %s, {', '.join(['%s'] * len(COLUNAS_MET))})",
                [(execucao, medida, comparacao, *l) for l in _sem_nan(m, COLUNAS_MET).itertuples(index=False)])
    return execucao


def gravar_em_conexao_nova(cfg, referencia, parametros, previsoes, metricas) -> int:
    """O backtest leva vários minutos de cálculo: grava numa conexão aberta agora,
    para não depender de uma conexão que o banco possa ter encerrado por inatividade."""
    import psycopg

    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        return gravar(conn, cfg, referencia, parametros, previsoes, metricas)


def mostrar(titulo: str, m: pd.DataFrame) -> None:
    print(f"\n=== {titulo} ===")
    if m.empty:
        print("(sem dados)")
        return
    colunas = [c for c in ["h", "modelo", "n", "rmse", "rmse_relativo", "cobertura80", "cobertura95",
                           "p_melhor", "veredito"] if c in m]
    with pd.option_context("display.width", 220, "display.max_columns", 20, "display.float_format", "{:.4f}".format):
        print(m[colunas].to_string(index=False))


class Progresso:
    """Mostra a origem atual, o tempo decorrido e uma estimativa do tempo restante."""

    def __init__(self, rotulo: str):
        self.rotulo, self.inicio = rotulo, time.time()

    def __call__(self, i: int, total: int, origem) -> None:
        decorrido = time.time() - self.inicio
        restante = decorrido / (i - 1) * (total - i + 1) if i > 1 else 0
        print(f"\r  {self.rotulo}: origem {i}/{total} ({str(origem)[:10]})  "
              f"decorrido {decorrido / 60:4.1f} min  restante ~{restante / 60:4.1f} min   ", end="", flush=True)
        if i == total:
            print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sem-sarima", action="store_true", help="Roda só as referências e o Focus")
    parser.add_argument("--serie", choices=["ipca", "cambio", "todas"], default="todas")
    args = parser.parse_args()

    import psycopg

    pasta = RAIZ / "data" / "backtest"
    pasta.mkdir(parents=True, exist_ok=True)
    # autocommit: cada leitura é uma transação curta. Uma transação aberta durante
    # todo o backtest seguraria travas e faria a atualização diária esperar.
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        preparar_esquema(conn)
        fonte = FonteBanco(conn, reconectar=lambda: psycopg.connect(DATABASE_URL, autocommit=True))

        # ---------------------------------------------------------------- IPCA
        if args.serie in ("ipca", "todas"):
            rodar_ipca(conn, fonte, args, pasta)
        if args.serie in ("cambio", "todas"):
            rodar_cambio(conn, fonte, args, pasta)
    print(f"\nResultados gravados no banco (backtest_*) e em {pasta}")


def rodar_ipca(conn, fonte, args, pasta):
    sarima = ModeloSarima("sarima", grade_ipca(), "nivel", reselecionar_a_cada=12, minimo=72)
    modelos = MODELOS_IPCA + ([] if args.sem_sarima else [sarima])
    origens = [d + timedelta(minutes=1) for d in fonte.divulgacoes_ipca()]
    inicio = time.time()
    print(f"IPCA: {len(origens)} origens, modelos {[m.nome for m in modelos]} ...")
    prev = executar(fonte, IPCA, modelos, origens, usar_focus=True, acumulado_12m=True,
                    ao_avancar=Progresso("IPCA"))
    sarima.backend.encerrar()
    print(f"IPCA concluído em {time.time() - inicio:.0f}s")
    # intervalos calibrados com erros passados já publicados em cada origem
    prev = pd.concat([prev, calibrar(prev, "sarima")], ignore_index=True)

    metricas = {}
    for medida, rotulo in (("variacao", "variação mensal"), ("acumulado_12m", "acumulado em 12 meses")):
        for ref, nome_ref in (("ingenuo", "modelo ingênuo"), ("focus_mediana", "Boletim Focus"),
                              ("media_sazonal_5a", "melhor modelo simples (média sazonal)")):
            m = resumo(prev, ref, passo=1, medida=medida)
            metricas[(medida, ref)] = m
            m.to_csv(pasta / f"ipca_{medida}_vs_{ref}.csv", index=False)
            mostrar(f"IPCA · {rotulo} · comparação com o {nome_ref}", m)
    parametros = {"origens": len(origens), "horizontes": IPCA.horizontes,
                  "n_erros_intervalo": IPCA.n_erros_intervalo, "primeira_origem": min(origens),
                  "ultima_origem": max(origens), "selecoes_sarima": sarima.selecoes,
                  "falhas_sarima": sarima.falhas}
    gravar_em_conexao_nova(IPCA, "ingenuo", parametros, prev, metricas)
    prev.to_csv(pasta / "ipca_previsoes.csv", index=False)
    if sarima.selecoes:
        print("\nOrdens do SARIMA escolhidas (só com dados de cada origem):")
        for s in sarima.selecoes:
            print(f"  {str(s['origem'])[:10]}  {s['especificacao']:<38} AIC {s['aic']:.1f}  ({s['n_obs']} meses)")



def rodar_cambio(conn, fonte, args, pasta):
    arima = ModeloSarima("arima_log", grade_cambio(), "log", reselecionar_a_cada=52, minimo=300)
    modelos = MODELOS_CAMBIO + ([] if args.sem_sarima else [arima])
    calendario = fonte.atual(CAMBIO.serie).index
    origens = origens_semanais(calendario, 250, max(CAMBIO.horizontes), PASSO_CAMBIO)
    inicio = time.time()
    print(f"\nCâmbio: {len(origens)} origens, modelos {[m.nome for m in modelos]} ...")
    prev = executar(fonte, CAMBIO, modelos, origens, ao_avancar=Progresso("Câmbio"))
    arima.backend.encerrar()
    print(f"Câmbio concluído em {time.time() - inicio:.0f}s")
    prev = pd.concat([prev, calibrar(prev, "arima_log")], ignore_index=True)
    m = resumo(prev, "passeio_aleatorio", passo=PASSO_CAMBIO)
    m.to_csv(pasta / "cambio_metricas.csv", index=False)
    mostrar("Câmbio · comparação com o passeio aleatório (referência obrigatória)", m)
    parametros = {"origens": len(origens), "passo_dias_uteis": PASSO_CAMBIO, "horizontes": CAMBIO.horizontes,
                  "n_erros_intervalo": CAMBIO.n_erros_intervalo, "primeira_origem": min(origens),
                  "ultima_origem": max(origens), "selecoes_arima": arima.selecoes, "falhas_arima": arima.falhas}
    gravar_em_conexao_nova(CAMBIO, "passeio_aleatorio", parametros, prev, {("variacao", "passeio_aleatorio"): m})
    prev.to_csv(pasta / "cambio_previsoes.csv", index=False)
    if arima.selecoes:
        print("\nOrdens do ARIMA escolhidas:")
        for s in arima.selecoes:
            print(f"  {str(s['origem'])[:10]}  {s['especificacao']:<24} AIC {s['aic']:.1f}  ({s['n_obs']} dias)")


if __name__ == "__main__":  # necessário no Windows para os processos paralelos
    main()
