"""Coletor da PTAX (Banco Central, serviço Olinda).

Cada cotação traz `dataHoraCotacao`: o momento em que o boletim foi publicado.
É a data de divulgação comprovada do dólar.
"""

from datetime import date, datetime

from .http import montar_url, obter_json
from .modelos import BRASILIA, Observacao

URL = ("https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
       "CotacaoDolarPeriodo(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)")


def janelas_anuais(inicio: date, fim: date) -> list[tuple[date, date]]:
    return [(max(inicio, date(a, 1, 1)), min(fim, date(a, 12, 31))) for a in range(inicio.year, fim.year + 1)]


def interpretar(registros: list[dict]) -> list[Observacao]:
    saida = []
    for r in registros:
        bruto = r.get("dataHoraCotacao")
        try:
            momento = datetime.fromisoformat(str(bruto)).replace(tzinfo=BRASILIA)
        except (TypeError, ValueError):
            raise ValueError(f"dataHoraCotacao inválida na PTAX: {r!r}")
        valor = r.get("cotacaoVenda")
        saida.append(Observacao(
            serie="ptax_venda",
            data_referencia=momento.date(),
            valor=float(valor) if valor is not None else None,
            disponivel_em=momento,
            origem_disponibilidade="ptax_datahora_cotacao",
            fonte="olinda_ptax",
        ))
    return saida


def coletar(inicio: date, fim: date, obter=obter_json) -> list[Observacao]:
    observacoes = []
    for ini, fim_j in janelas_anuais(inicio, fim):
        url = montar_url(URL, {
            "@dataInicial": f"'{ini:%m-%d-%Y}'",
            "@dataFinalCotacao": f"'{fim_j:%m-%d-%Y}'",
            "$select": "cotacaoVenda,dataHoraCotacao",
            "$format": "json",
        })
        observacoes += interpretar(obter(url).get("value", []))
    return observacoes


def dias_uteis(observacoes: list[Observacao]) -> list[date]:
    """Calendário de dias úteis do BCB: os dias em que houve boletim PTAX."""
    return sorted({o.data_referencia for o in observacoes})
