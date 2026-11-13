"""Calendário de divulgações do IBGE (API v3): data em que cada IPCA foi publicado.

ATENÇÃO: o formato exato da resposta ainda precisa ser conferido com uma
amostra real (python src/coletar_forecast.py --sondar). Por isso o leitor é
defensivo: procura os campos pelo nome e, se não reconhecer um item, falha
com uma mensagem clara em vez de adivinhar uma data.
"""

import re
from datetime import date, datetime

from .http import montar_url, obter_json
from .modelos import BRASILIA

URL = "https://servicodados.ibge.gov.br/api/v3/calendario/"
MESES = {m: i for i, m in enumerate(
    ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
     "agosto", "setembro", "outubro", "novembro", "dezembro"], start=1)}


def e_ipca_cheio(texto: str) -> bool:
    """IPCA mensal, excluindo IPCA-15 e IPCA-E."""
    t = texto.upper()
    return "IPCA" in t and not re.search(r"IPCA[\s-]*(15|E\b)", t)


def _texto(item: dict) -> str:
    return " ".join(str(v) for k, v in item.items() if isinstance(v, str))


def _data_divulgacao(item: dict) -> datetime:
    for chave, valor in item.items():
        if "divulga" in chave.lower() and isinstance(valor, str):
            for formato in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                try:
                    return datetime.strptime(valor.strip(), formato).replace(tzinfo=BRASILIA)
                except ValueError:
                    continue
    raise ValueError(f"Data de divulgação não encontrada no item: {item!r}")


def _mes_referencia(item: dict) -> date:
    for chave, valor in item.items():
        if any(p in chave.lower() for p in ("referencia", "periodo")) and isinstance(valor, str):
            m = re.search(r"(\d{1,2})/(\d{4})", valor)
            if m:
                return date(int(m.group(2)), int(m.group(1)), 1)
    texto = _texto(item).lower()
    m = re.search(r"refer[eê]ncia:?\s*(\d{1,2})/(\d{4})", texto)
    if m:
        return date(int(m.group(2)), int(m.group(1)), 1)
    m = re.search(r"(" + "|".join(MESES) + r")\s*(?:de\s*)?/?\s*(\d{4})", texto)
    if m:
        return date(int(m.group(2)), MESES[m.group(1)], 1)
    raise ValueError(f"Mês de referência não encontrado no item: {item!r}")


def interpretar(itens: list[dict]) -> dict[date, datetime]:
    divulgacoes: dict[date, datetime] = {}
    for item in itens:
        if not e_ipca_cheio(_texto(item)):
            continue
        mes, quando = _mes_referencia(item), _data_divulgacao(item)
        if quando.date() <= mes.replace(day=28):
            raise ValueError(f"Divulgação {quando:%d/%m/%Y} antes do fim do mês {mes:%m/%Y}: {item!r}")
        # Se houver mais de um registro para o mês, vale a primeira divulgação
        divulgacoes[mes] = min(quando, divulgacoes.get(mes, quando))
    return divulgacoes


def baixar(inicio: date, fim: date, obter=obter_json) -> list[dict]:
    itens, pagina = [], 1
    while True:
        url = montar_url(URL, {"busca": "IPCA", "de": f"{inicio:%m-%d-%Y}", "ate": f"{fim:%m-%d-%Y}",
                               "tipo": 1, "qtd": 100, "page": pagina})
        resposta = obter(url)
        lote = resposta.get("items", []) if isinstance(resposta, dict) else resposta
        itens += lote
        total = resposta.get("totalPages", resposta.get("total_pages", 1)) if isinstance(resposta, dict) else 1
        if not lote or pagina >= total:
            return itens
        pagina += 1


def coletar(inicio: date, fim: date, obter=obter_json) -> dict[date, datetime]:
    return interpretar(baixar(inicio, fim, obter))
