"""Validação dos dados coletados, antes de qualquer gravação.

Problemas graves impedem a gravação da fonte inteira (nada de carga parcial).
Avisos são gravados no log e no resumo da execução.
"""

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from .modelos import ORIGENS_FOCUS, ORIGENS_SERIE, ExpectativaFocus, Observacao


@dataclass(frozen=True)
class Problema:
    regra: str
    chave: str
    detalhe: str
    grave: bool


def _ausente(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def _proximo_mes(d: date) -> date:
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1)


def validar_serie(obs: list[Observacao], frequencia: str, faixa: tuple[float, float],
                  hoje: date) -> list[Problema]:
    if frequencia not in ("mensal", "diaria"):
        raise ValueError("frequencia deve ser 'mensal' ou 'diaria'")
    p: list[Problema] = []
    if not obs:
        return [Problema("vazia", "-", "Nenhuma observação recebida", True)]

    # Duplicidades: mesma data com valores diferentes é grave; idênticas são aviso
    por_data = defaultdict(set)
    for o in obs:
        por_data[o.data_referencia].add(o.valor)
    for dia, n in Counter(o.data_referencia for o in obs).items():
        if n > 1:
            conflito = len(por_data[dia]) > 1
            p.append(Problema("duplicidade", str(dia),
                              f"{n} registros{' com valores diferentes' if conflito else ' idênticos'}", conflito))

    minimo, maximo = faixa
    for o in obs:
        chave = f"{o.serie} {o.data_referencia}"
        if _ausente(o.valor):
            p.append(Problema("valor_ausente", chave, "Valor ausente ou inválido", True))
        elif not minimo <= o.valor <= maximo:
            p.append(Problema("fora_da_faixa", chave, f"{o.valor} fora de [{minimo}, {maximo}]", False))
        if o.data_referencia > hoje:
            p.append(Problema("data_futura", chave, "Data de referência no futuro", True))
        if o.origem_disponibilidade not in ORIGENS_SERIE:
            p.append(Problema("origem_invalida", chave, o.origem_disponibilidade, True))
        if (o.origem_disponibilidade == "nao_verificavel") != (o.disponivel_em is None):
            p.append(Problema("disponibilidade_incoerente", chave, "Origem e data de divulgação não batem", True))
        if o.disponivel_em is not None:
            # Um dado não pode ser divulgado antes de o período de referência terminar
            inicio_valido = _proximo_mes(o.data_referencia) if frequencia == "mensal" else o.data_referencia
            if o.disponivel_em.date() < inicio_valido:
                p.append(Problema("divulgado_antes_do_periodo", chave,
                                  f"Divulgado em {o.disponivel_em:%d/%m/%Y}", True))
            if o.disponivel_em.date() > hoje:
                p.append(Problema("divulgacao_futura", chave, "Divulgação no futuro", True))

    datas = sorted(set(o.data_referencia for o in obs))
    if frequencia == "mensal":
        for d in datas:
            if d.day != 1:
                p.append(Problema("frequencia", str(d), "Série mensal com data fora do dia 1", True))
        for a, b in zip(datas, datas[1:]):
            if b != _proximo_mes(a):
                p.append(Problema("lacuna", f"{a} → {b}", "Meses faltando na série mensal", True))
    else:
        for d in datas:
            if d.weekday() >= 5:
                p.append(Problema("frequencia", str(d), "Cotação em fim de semana", True))
        for a, b in zip(datas, datas[1:]):
            if (b - a).days > 5:  # feriados prolongados explicam até ~5 dias corridos
                p.append(Problema("lacuna", f"{a} → {b}", f"{(b - a).days} dias sem cotação", False))
    return p


def validar_focus(regs: list[ExpectativaFocus]) -> list[Problema]:
    p: list[Problema] = []
    if not regs:
        return [Problema("vazia", "-", "Nenhuma expectativa recebida", True)]
    chaves = Counter((r.data_estatistica, r.mes_alvo, r.base_calculo) for r in regs)
    for chave, n in chaves.items():
        if n > 1:
            p.append(Problema("duplicidade", str(chave), f"{n} registros na mesma chave", True))
    for r in regs:
        chave = f"{r.data_estatistica} → {r.mes_alvo:%m/%Y} (base {r.base_calculo})"
        if _ausente(r.mediana):
            p.append(Problema("valor_ausente", chave, "Mediana ausente", True))
        if r.base_calculo not in (0, 1):
            p.append(Problema("base_calculo", chave, str(r.base_calculo), True))
        if r.mes_alvo.day != 1:
            p.append(Problema("frequencia", chave, "Mês-alvo fora do dia 1", True))
        if r.respondentes is not None and r.respondentes < 0:
            p.append(Problema("respondentes", chave, "Número negativo de respondentes", True))
        if None not in (r.minimo, r.mediana, r.maximo) and not r.minimo <= r.mediana <= r.maximo:
            p.append(Problema("estatisticas", chave, "Mediana fora do intervalo [mínimo, máximo]", True))
        if r.origem_disponibilidade not in ORIGENS_FOCUS:
            p.append(Problema("origem_invalida", chave, r.origem_disponibilidade, True))
        if r.disponivel_em is not None:
            if not r.entra_no_relatorio:
                p.append(Problema("disponibilidade_incoerente", chave, "Data de divulgação fora do relatório semanal", True))
            elif r.disponivel_em.date() <= r.data_estatistica:
                p.append(Problema("divulgado_antes_da_coleta", chave, "Divulgação não posterior à estatística", True))
    return p


def graves(problemas: list[Problema]) -> list[Problema]:
    return [x for x in problemas if x.grave]
