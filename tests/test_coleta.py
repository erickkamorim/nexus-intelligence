"""Testes da Fase 1 (sem internet: as respostas das APIs são simuladas).

Rode na raiz do projeto:  python -m pytest -q
"""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from coleta import focus, ibge, ptax, sgs  # noqa: E402
from coleta.modelos import BRASILIA, Observacao  # noqa: E402
from coleta.validacao import graves, validar_focus, validar_serie  # noqa: E402

HOJE = date(2026, 11, 13)


# ---------------------------------------------------------------- SGS
def test_janelas_cobrem_o_periodo_sem_sobrepor_e_com_menos_de_10_anos():
    j = sgs.janelas(date(2004, 1, 1), date(2026, 11, 13))
    assert j[0][0] == date(2004, 1, 1) and j[-1][1] == date(2026, 11, 13)
    for (a_ini, a_fim), (b_ini, _) in zip(j, j[1:]):
        assert b_ini == a_fim + timedelta(days=1)
    for ini, fim in j:
        assert fim < ini.replace(year=ini.year + 10)


def test_janelas_com_29_de_fevereiro():
    assert sgs.janelas(date(2016, 2, 29), date(2030, 1, 1))[0][1] == date(2026, 2, 27)


def test_ipca_recebe_data_do_calendario_ou_fica_nao_verificavel():
    resposta = [{"data": "01/01/2024", "valor": "0.42"}, {"data": "01/02/2024", "valor": "0.83"}]
    divulgacoes = {date(2024, 1, 1): datetime(2024, 2, 8, 9, tzinfo=BRASILIA)}
    obs = sgs.coletar_ipca(date(2024, 1, 1), date(2024, 2, 29), divulgacoes, obter=lambda url: resposta)
    jan, fev = obs
    assert jan.origem_disponibilidade == "ibge_calendario" and jan.disponivel_em.day == 8
    assert fev.origem_disponibilidade == "nao_verificavel" and fev.disponivel_em is None


def test_sgs_valor_invalido_vira_ausente_e_a_validacao_bloqueia():
    obs = sgs.interpretar([{"data": "01/01/2024", "valor": "abc"}], "ipca_mensal", "sgs_433", mensal=True)
    assert obs[0].valor is None
    assert any(p.regra == "valor_ausente" for p in graves(validar_serie(obs, "mensal", (-3, 5), HOJE)))


# ---------------------------------------------------------------- PTAX
def test_ptax_usa_o_horario_do_boletim_como_divulgacao():
    obs = ptax.interpretar([{"cotacaoVenda": 4.8916, "dataHoraCotacao": "2024-01-02 13:03:28.733"}])[0]
    assert obs.data_referencia == date(2024, 1, 2)
    assert obs.disponivel_em == datetime(2024, 1, 2, 13, 3, 28, 733000, tzinfo=BRASILIA)
    assert obs.origem_disponibilidade == "ptax_datahora_cotacao"


def test_ptax_divide_em_janelas_anuais():
    j = ptax.janelas_anuais(date(2016, 6, 1), date(2018, 3, 1))
    assert j == [(date(2016, 6, 1), date(2016, 12, 31)), (date(2017, 1, 1), date(2017, 12, 31)),
                 (date(2018, 1, 1), date(2018, 3, 1))]


# ---------------------------------------------------------------- Focus
CALENDARIO = [date(2024, 3, d) for d in (4, 5, 6, 7, 8, 11, 12, 13, 14, 15, 18)]


def _focus(dia, alvo="04/2024", mediana=0.30, base=0):
    return {"Indicador": "IPCA", "Data": dia, "DataReferencia": alvo, "Mediana": mediana, "Media": mediana,
            "DesvioPadrao": 0.05, "Minimo": 0.1, "Maximo": 0.5, "numeroRespondentes": 80, "baseCalculo": base}


def test_focus_so_o_fechamento_semanal_entra_e_fica_disponivel_no_dia_util_seguinte():
    regs = focus.interpretar([_focus("2024-03-07"), _focus("2024-03-08")], CALENDARIO, HOJE)
    quinta, sexta = regs
    assert not quinta.entra_no_relatorio and quinta.disponivel_em is None
    assert sexta.entra_no_relatorio
    assert sexta.disponivel_em == datetime(2024, 3, 11, 9, 0, tzinfo=BRASILIA)  # segunda-feira


def test_focus_semana_em_andamento_ainda_nao_tem_relatorio():
    regs = focus.interpretar([_focus("2026-11-12")], CALENDARIO, HOJE)
    assert not regs[0].entra_no_relatorio


def test_focus_feriado_na_segunda_desloca_a_divulgacao():
    calendario = [date(2024, 3, 8), date(2024, 3, 12)]  # 11/03 sem expediente
    assert focus.proximo_dia_util(date(2024, 3, 8), calendario) == date(2024, 3, 12)


def test_focus_paginacao_busca_todas_as_paginas(monkeypatch):
    monkeypatch.setattr(focus, "PAGINA", 2)
    paginas = iter([{"value": [1, 2]}, {"value": [3, 2]}, {"value": [5]}])
    assert focus.baixar(date(2024, 1, 1), obter=lambda url: next(paginas)) == [1, 2, 3, 2, 5]


def test_focus_validacao_detecta_duplicidade_e_mediana_incoerente():
    regs = focus.interpretar([_focus("2024-03-08"), _focus("2024-03-08"), _focus("2024-03-05", mediana=0.9)],
                             CALENDARIO, HOJE)
    regras = {p.regra for p in graves(validar_focus(regs))}
    assert {"duplicidade", "estatisticas"} <= regras


# ---------------------------------------------------------------- IBGE
def test_ibge_ignora_ipca15_e_ipcae_e_le_a_referencia():
    itens = [
        {"titulo": "IPCA - Índice Nacional de Preços ao Consumidor Amplo", "referencia": "1/2024",
         "data_divulgacao": "08/02/2024 09:00:00"},
        {"titulo": "IPCA-15 - Índice Nacional de Preços ao Consumidor Amplo 15", "referencia": "2/2024",
         "data_divulgacao": "27/02/2024 09:00:00"},
        {"titulo": "IPCA-E", "referencia": "1/2024 a 3/2024", "data_divulgacao": "26/03/2024 09:00:00"},
    ]
    assert ibge.interpretar(itens) == {date(2024, 1, 1): datetime(2024, 2, 8, 9, tzinfo=BRASILIA)}


def test_ibge_recusa_divulgacao_antes_do_fim_do_mes():
    with pytest.raises(ValueError):
        ibge.interpretar([{"titulo": "IPCA", "referencia": "2/2024", "data_divulgacao": "10/02/2024 09:00:00"}])


def test_ibge_formato_desconhecido_falha_em_vez_de_adivinhar():
    with pytest.raises(ValueError):
        ibge.interpretar([{"titulo": "IPCA", "quando": "amanhã"}])


# ---------------------------------------------------------------- Validação de séries
def _mensal(meses, divulgado=None):
    return [Observacao("ipca_mensal", m, 0.3, divulgado, "ibge_calendario" if divulgado else "nao_verificavel", "t")
            for m in meses]


def test_lacuna_mensal_e_grave():
    obs = _mensal([date(2024, 1, 1), date(2024, 3, 1)])
    assert any(p.regra == "lacuna" for p in graves(validar_serie(obs, "mensal", (-3, 5), HOJE)))


def test_divulgacao_antes_do_fim_do_periodo_e_grave():
    obs = _mensal([date(2024, 1, 1)], datetime(2024, 1, 20, tzinfo=BRASILIA))
    assert any(p.regra == "divulgado_antes_do_periodo" for p in graves(validar_serie(obs, "mensal", (-3, 5), HOJE)))


def test_duplicidade_conflitante_e_grave_e_identica_e_aviso():
    a = Observacao("ptax_venda", date(2024, 1, 2), 4.9, datetime(2024, 1, 2, 13, tzinfo=BRASILIA), "ptax_datahora_cotacao", "t")
    b = Observacao("ptax_venda", date(2024, 1, 2), 5.1, datetime(2024, 1, 2, 13, tzinfo=BRASILIA), "ptax_datahora_cotacao", "t")
    assert graves(validar_serie([a, b], "diaria", (1, 15), HOJE))
    assert not graves(validar_serie([a, a], "diaria", (1, 15), HOJE))


def test_cotacao_em_fim_de_semana_e_grave():
    sab = Observacao("ptax_venda", date(2024, 1, 6), 4.9, datetime(2024, 1, 6, 13, tzinfo=BRASILIA), "ptax_datahora_cotacao", "t")
    assert any(p.regra == "frequencia" for p in graves(validar_serie([sab], "diaria", (1, 15), HOJE)))


def test_origem_e_data_incoerentes_sao_graves():
    obs = [Observacao("ipca_mensal", date(2024, 1, 1), 0.4, None, "ibge_calendario", "t")]
    assert any(p.regra == "disponibilidade_incoerente" for p in graves(validar_serie(obs, "mensal", (-3, 5), HOJE)))
