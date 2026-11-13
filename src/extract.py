"""
NEXUS Intelligence - Extração de indicadores do Banco Central (API SGS).

Uso (na raiz do projeto):
    python src/extract.py
    python src/extract.py --inicio 01/01/2020

Gera:
    data/indicadores.csv   -> formato longo: indicador, codigo_sgs, data_referencia, valor
    logs/extract.log       -> registro de cada execução
"""

import argparse
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parent.parent
PASTA_DADOS = RAIZ / "data"
PASTA_LOGS = RAIZ / "logs"
ARQUIVO_SAIDA = PASTA_DADOS / "indicadores.csv"

# código SGS -> (nome interno, faixa de valores plausíveis)
SERIES = {
    432: ("selic_meta", (0.0, 50.0)),     # % ao ano
    433: ("ipca_mensal", (-5.0, 10.0)),   # variação % no mês
    1: ("dolar_venda", (1.0, 15.0)),      # R$ por US$
}

URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
TENTATIVAS = 3
CABECALHOS = {"User-Agent": "NEXUS-Intelligence/1.0 (+https://github.com/erickkamorim/nexus-intelligence)", "Accept": "application/json"}

log = logging.getLogger("nexus.extract")


def configurar_log():
    PASTA_LOGS.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        handlers=[
            logging.FileHandler(PASTA_LOGS / "extract.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def baixar_serie(codigo: int, inicio: str, fim: str) -> list[dict]:
    """Chama a API SGS com novas tentativas em caso de falha temporária."""
    params = {"formato": "json", "dataInicial": inicio, "dataFinal": fim}
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            resp = requests.get(URL.format(codigo=codigo), params=params, timeout=30, headers=CABECALHOS)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as erro:
            log.warning("Série %s: tentativa %s/%s falhou (%s)", codigo, tentativa, TENTATIVAS, erro)
            if tentativa == TENTATIVAS:
                raise
            time.sleep(2 * tentativa)
    return []


def transformar(dados: list[dict], codigo: int, nome: str) -> pd.DataFrame:
    """Converte o JSON da API (data dd/mm/aaaa, valor em texto) para tipos corretos."""
    df = pd.DataFrame(dados)
    if df.empty:
        return pd.DataFrame(columns=["indicador", "codigo_sgs", "data_referencia", "valor"])

    df["data_referencia"] = pd.to_datetime(df["data"], format="%d/%m/%Y", errors="coerce").dt.date
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    df["indicador"] = nome
    df["codigo_sgs"] = codigo
    return df[["indicador", "codigo_sgs", "data_referencia", "valor"]]


def validar(df: pd.DataFrame, nome: str, faixa: tuple[float, float]) -> pd.DataFrame:
    """Regras de qualidade: datas e valores válidos, sem duplicados, valores plausíveis."""
    total = len(df)

    invalidos = df["data_referencia"].isna() | df["valor"].isna()
    if invalidos.any():
        log.warning("%s: %s registro(s) com data ou valor inválido removido(s)", nome, int(invalidos.sum()))
        df = df[~invalidos]

    duplicados = df.duplicated(subset=["indicador", "data_referencia"], keep="last")
    if duplicados.any():
        log.warning("%s: %s data(s) duplicada(s) removida(s)", nome, int(duplicados.sum()))
        df = df[~duplicados]

    futuro = df["data_referencia"] > date.today()
    if futuro.any():
        log.warning("%s: %s registro(s) com data futura", nome, int(futuro.sum()))

    minimo, maximo = faixa
    fora = (df["valor"] < minimo) | (df["valor"] > maximo)
    if fora.any():
        # Não remove: pode ser um dado real atípico. Fica registrado para análise.
        log.warning("%s: %s valor(es) fora da faixa esperada [%s, %s]", nome, int(fora.sum()), minimo, maximo)

    log.info("%s: %s de %s registros aprovados", nome, len(df), total)
    return df.sort_values("data_referencia")


def main():
    parser = argparse.ArgumentParser(description="Extrai indicadores do Banco Central (SGS)")
    parser.add_argument("--inicio", default="01/01/2023",
                        help="Data inicial dd/mm/aaaa (2023 garante o IPCA 12 meses desde jan/2024)")
    args = parser.parse_args()

    configurar_log()
    inicio = args.inicio
    fim = date.today().strftime("%d/%m/%Y")
    log.info("Início da extração: %s até %s", inicio, fim)

    partes, falhas = [], []
    for codigo, (nome, faixa) in SERIES.items():
        try:
            bruto = baixar_serie(codigo, inicio, fim)
            df = validar(transformar(bruto, codigo, nome), nome, faixa)
            partes.append(df)
        except Exception as erro:  # registra e segue para as outras séries
            log.error("%s (SGS %s): falha na extração - %s", nome, codigo, erro)
            falhas.append(nome)

    if not partes:
        log.error("Nenhuma série extraída. Arquivo não foi gerado.")
        sys.exit(1)

    resultado = pd.concat(partes, ignore_index=True)
    resultado["extraido_em"] = datetime.now().isoformat(timespec="seconds")

    PASTA_DADOS.mkdir(exist_ok=True)
    resultado.to_csv(ARQUIVO_SAIDA, index=False, encoding="utf-8")

    resumo = resultado.groupby("indicador")["data_referencia"].agg(["count", "min", "max"])
    log.info("Arquivo gerado: %s\n%s", ARQUIVO_SAIDA, resumo.to_string())

    if falhas:
        log.error("Séries com falha: %s", ", ".join(falhas))
        sys.exit(2)


if __name__ == "__main__":
    main()
