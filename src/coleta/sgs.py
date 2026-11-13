"""Coletor do SGS (Banco Central): IPCA mensal.

O SGS devolve apenas data e valor: não informa quando o dado foi publicado.
A data de divulgação do IPCA vem do calendário do IBGE (ver ibge.py) e é
anexada aqui (ver anexar_divulgacao).
"""

from datetime import date, datetime, timedelta

from .http import montar_url, obter_json
from .modelos import Observacao

URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"


def janelas(inicio: date, fim: date, anos: int = 10) -> list[tuple[date, date]]:
    """Divide o período em janelas menores que `anos` anos.

    Séries diárias do SGS aceitam no máximo 10 anos por consulta.
    """
    if inicio > fim:
        raise ValueError("inicio posterior ao fim")
    resultado, atual = [], inicio
    while atual <= fim:
        try:
            limite = atual.replace(year=atual.year + anos) - timedelta(days=1)
        except ValueError:  # 29/02 em ano não bissexto
            limite = atual.replace(year=atual.year + anos, day=28) - timedelta(days=1)
        fim_janela = min(limite, fim)
        resultado.append((atual, fim_janela))
        atual = fim_janela + timedelta(days=1)
    return resultado


def interpretar(registros: list[dict], serie: str, fonte: str, mensal: bool) -> list[Observacao]:
    """Converte o JSON do SGS. Datas ou valores inválidos viram valor None
    (a validação decide o que fazer com eles)."""
    saida = []
    for r in registros:
        try:
            dia = datetime.strptime(r["data"], "%d/%m/%Y").date()
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"Data inválida no SGS: {r!r}")
        if mensal:
            dia = dia.replace(day=1)
        try:
            valor = float(str(r.get("valor")).replace(",", "."))
        except (TypeError, ValueError):
            valor = None
        saida.append(Observacao(serie, dia, valor, None, "nao_verificavel", fonte))
    return saida


def coletar_ipca(inicio: date, fim: date, divulgacoes: dict[date, datetime], obter=obter_json) -> list[Observacao]:
    """IPCA mensal (SGS 433) com a data de divulgação do calendário do IBGE."""
    observacoes = []
    for ini, fim_j in janelas(inicio, fim):
        url = montar_url(URL.format(codigo=433), {
            "formato": "json",
            "dataInicial": ini.strftime("%d/%m/%Y"),
            "dataFinal": fim_j.strftime("%d/%m/%Y"),
        })
        observacoes += interpretar(obter(url), "ipca_mensal", "sgs_433", mensal=True)

    return anexar_divulgacao(observacoes, divulgacoes)


def anexar_divulgacao(observacoes: list[Observacao], divulgacoes: dict[date, datetime]) -> list[Observacao]:
    """Anexa a data de divulgação de cada mês.

    1. Mês no calendário do IBGE -> data exata ('ibge_calendario').
    2. Mês fora do calendário, mas com um mês POSTERIOR no calendário ->
       o IPCA é publicado em ordem cronológica, então o mês já estava publicado
       quando saiu o primeiro mês posterior do calendário. Essa data é um
       limite superior comprovado: pode ser mais tarde que a publicação real,
       nunca mais cedo ('ibge_limite_superior').
    3. Sem nenhuma das duas provas -> 'nao_verificavel' (fica fora dos backtests).
    """
    meses_calendario = sorted(divulgacoes)
    saida = []
    for o in observacoes:
        exata = divulgacoes.get(o.data_referencia)
        if exata:
            quando, origem = exata, "ibge_calendario"
        else:
            posteriores = [divulgacoes[m] for m in meses_calendario if m > o.data_referencia]
            quando = min(posteriores) if posteriores else None
            origem = "ibge_limite_superior" if quando else "nao_verificavel"
        saida.append(Observacao(o.serie, o.data_referencia, o.valor, quando, origem, o.fonte))
    return saida
