"""Coletor do Boletim Focus: expectativas mensais do IPCA (serviço Olinda).

A API publica estatísticas diárias, mas o Relatório Focus é divulgado no
primeiro dia útil de cada semana, com a estatística do último dia útil da
semana anterior. Só essas estatísticas entram na comparação, e a data de
disponibilidade é o dia útil seguinte (calendário de dias úteis da PTAX).
"""

from bisect import bisect_right
from datetime import date, datetime, time, timedelta

from .http import montar_url, obter_json
from .modelos import BRASILIA, ExpectativaFocus

URL = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativaMercadoMensais"
CAMPOS = "Indicador,Data,DataReferencia,Media,Mediana,DesvioPadrao,Minimo,Maximo,numeroRespondentes,baseCalculo"
PAGINA = 10_000
# Convenção conservadora: o relatório sai pela manhã; só consideramos a partir das 09h.
HORA_DIVULGACAO = time(9, 0)


def _num(valor):
    return None if valor is None else float(valor)


def mes_alvo(texto: str) -> date:
    mes, ano = str(texto).split("/")
    return date(int(ano), int(mes), 1)


def baixar(inicio: date, obter=obter_json) -> list[dict]:
    """Baixa todas as páginas (a API limita o tamanho de cada resposta)."""
    registros, pulo = [], 0
    while True:
        url = montar_url(URL, {
            "$filter": f"Indicador eq 'IPCA' and Data ge '{inicio:%Y-%m-%d}'",
            "$select": CAMPOS,
            "$orderby": "Data,DataReferencia,baseCalculo",
            "$top": PAGINA,
            "$skip": pulo,
            "$format": "json",
        })
        pagina = obter(url).get("value", [])
        registros += pagina
        if len(pagina) < PAGINA:
            return registros
        pulo += PAGINA


def fechamentos_semanais(datas: list[date], hoje: date) -> set[date]:
    """Último dia com estatística em cada semana já encerrada."""
    por_semana: dict[tuple[int, int], date] = {}
    for d in datas:
        chave = tuple(d.isocalendar())[:2]
        por_semana[chave] = max(por_semana.get(chave, d), d)
    fim_semana_atual = hoje - timedelta(days=hoje.weekday()) - timedelta(days=1)  # domingo anterior
    return {d for d in por_semana.values() if d <= fim_semana_atual}


def proximo_dia_util(dia: date, calendario: list[date]) -> date | None:
    i = bisect_right(calendario, dia)
    return calendario[i] if i < len(calendario) else None


def interpretar(registros: list[dict], calendario: list[date], hoje: date) -> list[ExpectativaFocus]:
    datas = [date.fromisoformat(r["Data"][:10]) for r in registros]
    fechamentos = fechamentos_semanais(datas, hoje)
    saida = []
    for r, dia in zip(registros, datas):
        no_relatorio = dia in fechamentos
        divulgacao = proximo_dia_util(dia, calendario) if no_relatorio else None
        momento = datetime.combine(divulgacao, HORA_DIVULGACAO, BRASILIA) if divulgacao else None
        saida.append(ExpectativaFocus(
            data_estatistica=dia,
            mes_alvo=mes_alvo(r["DataReferencia"]),
            base_calculo=int(r["baseCalculo"]),
            mediana=_num(r.get("Mediana")),
            media=_num(r.get("Media")),
            desvio_padrao=_num(r.get("DesvioPadrao")),
            minimo=_num(r.get("Minimo")),
            maximo=_num(r.get("Maximo")),
            respondentes=None if r.get("numeroRespondentes") is None else int(r["numeroRespondentes"]),
            entra_no_relatorio=no_relatorio,
            disponivel_em=momento,
            origem_disponibilidade="focus_relatorio_semanal" if momento else "nao_verificavel",
        ))
    return saida


def coletar(inicio: date, calendario: list[date], hoje: date, obter=obter_json) -> list[ExpectativaFocus]:
    return interpretar(baixar(inicio, obter), calendario, hoje)
