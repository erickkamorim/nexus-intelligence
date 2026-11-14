"""Calendário de divulgações do IBGE (API v3): data em que cada IPCA foi publicado.

Formato conferido com amostra real (13/11/2026):
  * a API ignora o parâmetro de busca e devolve todas as pesquisas, então o
    filtro é feito aqui, pelo produto_id (IPCA = 9256; IPCA-15 = 9260);
  * o mês de referência vem em ano_referencia_inicio / mes_referencia_inicio;
  * data_divulgacao vem como "dd/mm/aaaa HH:MM:SS", sem fuso. Interpretamos
    como horário de Brasília, a leitura mais conservadora (a mais tardia);
  * o calendário não cobre os anos mais antigos (2004-2006 voltou vazio).
    Para esses meses, sgs.py usa um limite superior comprovado.

A API do IBGE não responde a servidores fora do Brasil (como os do GitHub
Actions). Por isso existe uma cópia do calendário no repositório
(data/referencia/calendario_ibge_ipca.json), exportada de um computador no
Brasil com src/exportar_calendario_ibge.py. A cópia guarda também as datas
já agendadas; cada uma só passa a valer depois que acontece, pela mesma regra
de interpretar().
"""

import json
from datetime import date, datetime
from pathlib import Path

from .http import montar_url, obter_json
from .modelos import BRASILIA

URL = "https://servicodados.ibge.gov.br/api/v3/calendario/"
PRODUTO_IPCA = 9256
CAMPOS = ("produto_id", "ano_referencia_inicio", "mes_referencia_inicio", "data_divulgacao")


HORA_DIVULGACAO = 9  # o IBGE divulga o IPCA às 9h de Brasília


def ler_data(texto: str) -> datetime:
    """Lê a data do calendário como horário de Brasília. Em 2017 e 2018 parte dos
    registros vem com hora entre 0h e 3h, antes do horário em que o IBGE publica:
    a hora não é confiável e lê-la ao pé da letra anteciparia o dado em até 9 horas.
    Nesses casos vale o fim do dia, um limite superior seguro."""
    quando = datetime.strptime(texto.strip(), "%d/%m/%Y %H:%M:%S").replace(tzinfo=BRASILIA)
    if quando.hour < HORA_DIVULGACAO:
        quando = quando.replace(hour=23, minute=59, second=0)
    return quando


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
        quando = ler_data(item["data_divulgacao"])
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


def salvar_copia(itens: list[dict], caminho: Path, exportado_em: datetime) -> list[dict]:
    """Guarda só os itens do IPCA, com os campos usados, para a automação ler sem a API."""
    ipca = [{c: item[c] for c in CAMPOS} for item in itens if item.get("produto_id") == PRODUTO_IPCA]
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps({"fonte": URL, "exportado_em": exportado_em.isoformat(timespec="seconds"),
                                   "produto_id": PRODUTO_IPCA, "itens": ipca},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
    return ipca


def ler_copia(caminho: Path) -> tuple[list[dict], datetime]:
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return dados["itens"], datetime.fromisoformat(dados["exportado_em"])


def ultima_data_agendada(itens: list[dict]) -> datetime | None:
    datas = [ler_data(i["data_divulgacao"]) for i in itens if i.get("produto_id") == PRODUTO_IPCA]
    return max(datas) if datas else None
