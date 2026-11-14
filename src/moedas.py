"""
NEXUS Intelligence - cotações PTAX de fechamento de outras moedas.

Alimenta a faixa de moedas no topo do dashboard. Fonte: serviço Olinda do
Banco Central (PTAX), boletim de Fechamento, em R$ por 1 unidade da moeda.
A PTAX é uma taxa de referência diária, não uma cotação em tempo real.

Uso:
    python src/moedas.py            # últimos 45 dias
    python src/moedas.py --dias 400
"""

import argparse
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from coleta.http import montar_url, obter_json  # noqa: E402
from coleta.modelos import BRASILIA  # noqa: E402

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/nexus_db")
URL = ("https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
       "CotacaoMoedaPeriodo(moeda=@moeda,dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)")

# Moedas com PTAX publicada pelo Banco Central
MOEDAS = ["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD"]

log = logging.getLogger("nexus.moedas")


def interpretar(moeda: str, registros: list[dict]) -> list[tuple]:
    """Só o boletim de Fechamento, uma linha por dia (o último publicado, se houver mais de um)."""
    por_dia = {}
    for r in registros:
        if r.get("tipoBoletim") != "Fechamento":
            continue
        momento = datetime.fromisoformat(str(r["dataHoraCotacao"])).replace(tzinfo=BRASILIA)
        compra, venda = r.get("cotacaoCompra"), r.get("cotacaoVenda")
        if compra is None or venda is None or float(venda) <= 0:
            continue
        atual = por_dia.get(momento.date())
        if atual is None or momento > atual[4]:
            por_dia[momento.date()] = (moeda, momento.date(), float(compra), float(venda), momento)
    return sorted(por_dia.values(), key=lambda l: l[1])


def coletar(moeda: str, inicio: date, fim: date, obter=obter_json) -> list[tuple]:
    url = montar_url(URL, {
        "@moeda": f"'{moeda}'",
        "@dataInicial": f"'{inicio:%m-%d-%Y}'",
        "@dataFinalCotacao": f"'{fim:%m-%d-%Y}'",
        "$select": "cotacaoCompra,cotacaoVenda,dataHoraCotacao,tipoBoletim",
        "$format": "json",
    })
    return interpretar(moeda, obter(url).get("value", []))


def gravar(conn, linhas: list[tuple]) -> int:
    with conn.transaction():
        conn.cursor().executemany(
            """INSERT INTO cotacoes_moedas (moeda, data, compra, venda, boletim_em)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (moeda, data) DO UPDATE
                 SET compra = EXCLUDED.compra, venda = EXCLUDED.venda,
                     boletim_em = EXCLUDED.boletim_em, coletado_em = NOW()""",
            linhas)
    return len(linhas)


def main():
    import psycopg

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--dias", type=int, default=45)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    fim = datetime.now(BRASILIA).date()
    inicio = fim - timedelta(days=args.dias)
    falhas = []
    with psycopg.connect(DATABASE_URL) as conn:
        for moeda in MOEDAS:
            try:
                n = gravar(conn, coletar(moeda, inicio, fim))
                log.info("%s: %d dias", moeda, n)
            except Exception:
                log.exception("%s: falha na coleta", moeda)
                falhas.append(moeda)
    if len(falhas) == len(MOEDAS):
        sys.exit(1)
    if falhas:
        log.warning("Moedas sem atualização: %s", ", ".join(falhas))


if __name__ == "__main__":
    main()
