"""Calendário de divulgações do IBGE (API v3): data em que cada IPCA foi publicado.

Formato conferido com amostra real (13/11/2026):
  * a API ignora o parâmetro de busca e devolve todas as pesquisas, então o
    filtro é feito aqui, pelo produto_id (IPCA = 9256; IPCA-15 = 9260);
  * o mês de referência vem em ano_referencia_inicio / mes_referencia_inicio;
  * data_divulgacao vem como "dd/mm/aaaa HH:MM:SS", sem fuso. Interpretamos
    como horário de Brasília, a leitura mais conservadora (a mais tardia);
  * o calendário não cobre os anos mais antigos (2004-2006 voltou vazio).
    Para esses meses, sgs.py usa um limite superior comprovado.
"""

from datetime import date, datetime

from .http import montar_url, obter_json
from .modelos import BRASILIA

URL = "https://servicodados.ibge.gov.br/api/v3/calendario/"
PRODUTO_IPCA = 9256
CAMPOS = ("produto_id", "ano_referencia_inicio", "mes_referencia_inicio", "data_divulgacao")


def interpretar(itens: list[dict], agora: datetime) -> dict[date, datetime]:
    """Mês de referência -> momento da divulgação, só para divulgações já ocorridas.
    Datas agendadas para o futuro não são prova de publicação e ficam de fora."""
    divulgacoes: dict[date, datetime] = {}
    for item in itens:
        faltando = [c for c in CAMPOS if c not in item]
        if faltando:
            raise ValueError(f"Formato do calendário do IBGE mudou: faltam {faltando} em {item!r}")
        if item["produto_id"] != PRODUTO_IPCA:
            continue
        ano, mes = int(item["ano_referencia_inicio"]), int(item["mes_referencia_inicio"])
        if not (1 <= mes <= 12 and ano > 1900):
            raise ValueError(f"Mês de referência inválido no calendário do IBGE: {item!r}")
        referencia = date(ano, mes, 1)
        quando = datetime.strptime(item["data_divulgacao"].strip(), "%d/%m/%Y %H:%M:%S").replace(tzinfo=BRASILIA)
        if quando > agora:
            continue
        if quando.date() <= referencia.replace(day=28):
            raise ValueError(f"Divulgação {quando:%d/%m/%Y} antes do fim do mês {referencia:%m/%Y}: {item!r}")
        # Se o mesmo mês aparecer mais de uma vez, vale a primeira divulgação
        divulgacoes[referencia] = min(quando, divulgacoes.get(referencia, quando))
    return divulgacoes


def baixar(inicio: date, fim: date, obter=obter_json, por_pagina: int = 500) -> list[dict]:
    itens, pagina = [], 1
    while True:
        url = montar_url(URL, {"de": f"{inicio:%m-%d-%Y}", "ate": f"{fim:%m-%d-%Y}",
                               "qtd": por_pagina, "page": pagina})
        resposta = obter(url)
        lote = resposta.get("items", [])
        itens += lote
        if not lote or pagina >= int(resposta.get("totalPages", 1)):
            return itens
        pagina += 1


def coletar(inicio: date, fim: date, agora: datetime, obter=obter_json) -> dict[date, datetime]:
    return interpretar(baixar(inicio, fim, obter), agora)
