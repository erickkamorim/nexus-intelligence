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
from coleta.validacao import consolidar_duplicadas, graves, validar_focus, validar_serie  # noqa: E402

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
# Itens copiados da amostra real do calendário (13/11/2026), campos essenciais
def _item(id_, produto_id, titulo, ano, mes, quando):
    return {"id": id_, "titulo": titulo, "data_divulgacao": quando, "produto_id": produto_id,
            "ano_referencia_inicio": ano, "mes_referencia_inicio": mes,
            "ano_referencia_fim": 0, "mes_referencia_fim": 0}


AGORA = datetime(2026, 11, 13, 16, 0, tzinfo=BRASILIA)
CALENDARIO_REAL = [
    _item(4321, 9256, "Índice Nacional de Preços ao Consumidor Amplo", 2026, 10, "12/11/2026 12:00:00"),
    _item(4320, 9258, "Índice Nacional de Preços ao Consumidor", 2026, 10, "12/11/2026 12:00:00"),
    _item(4314, 9260, "Índice Nacional de Preços ao Consumidor Amplo 15", 2026, 10, "23/10/2026 12:00:00"),
    _item(4323, 9227, "Pesquisa Mensal de Comércio", 2026, 9, "13/11/2026 12:00:00"),
]


def test_ibge_filtra_o_ipca_pelo_produto_id():
    assert ibge.interpretar(CALENDARIO_REAL, AGORA) == {
        date(2026, 10, 1): datetime(2026, 11, 12, 12, 0, tzinfo=BRASILIA)}


def test_ibge_ignora_divulgacao_agendada_para_o_futuro():
    futuro = [_item(1, 9256, "IPCA", 2026, 11, "10/12/2026 12:00:00")]
    assert ibge.interpretar(futuro, AGORA) == {}


def test_ibge_recusa_divulgacao_antes_do_fim_do_mes():
    with pytest.raises(ValueError):
        ibge.interpretar([_item(1, 9256, "IPCA", 2026, 10, "10/10/2026 12:00:00")], AGORA)


def test_ibge_formato_desconhecido_falha_em_vez_de_adivinhar():
    with pytest.raises(ValueError):
        ibge.interpretar([{"titulo": "IPCA", "quando": "amanhã"}], AGORA)


def test_ibge_paginacao_le_todas_as_paginas():
    paginas = iter([{"totalPages": 2, "items": [1, 2]}, {"totalPages": 2, "items": [3]}])
    assert ibge.baixar(date(2015, 1, 1), date(2026, 1, 1), obter=lambda url: next(paginas)) == [1, 2, 3]


# ---------------------------------------------------------------- Limite superior comprovado
def test_mes_fora_do_calendario_usa_a_primeira_divulgacao_posterior():
    divulgacoes = {date(2017, 1, 1): datetime(2017, 2, 8, 12, tzinfo=BRASILIA),
                   date(2017, 2, 1): datetime(2017, 3, 10, 12, tzinfo=BRASILIA)}
    obs = [Observacao("ipca_mensal", date(2010, 5, 1), 0.4, None, "nao_verificavel", "t"),
           Observacao("ipca_mensal", date(2017, 1, 1), 0.3, None, "nao_verificavel", "t")]
    antigo, exato = sgs.anexar_divulgacao(obs, divulgacoes)
    assert antigo.origem_disponibilidade == "ibge_limite_superior"
    assert antigo.disponivel_em == datetime(2017, 2, 8, 12, tzinfo=BRASILIA)
    assert exato.origem_disponibilidade == "ibge_calendario"


def test_limite_superior_nunca_e_anterior_a_divulgacao_real():
    """Propriedade: o limite vem de um mês posterior, logo é >= à divulgação real."""
    divulgacoes = {date(2020, m, 1): datetime(2020, m + 1, 10, 12, tzinfo=BRASILIA) for m in range(3, 12)}
    obs = [Observacao("ipca_mensal", date(2020, m, 1), 0.2, None, "nao_verificavel", "t") for m in (1, 2)]
    for o in sgs.anexar_divulgacao(obs, divulgacoes):
        assert o.disponivel_em.date() > o.data_referencia.replace(day=28)
        assert o.disponivel_em == datetime(2020, 4, 10, 12, tzinfo=BRASILIA)


def test_mes_posterior_a_todo_o_calendario_fica_nao_verificavel():
    divulgacoes = {date(2020, 1, 1): datetime(2020, 2, 7, 12, tzinfo=BRASILIA)}
    obs = [Observacao("ipca_mensal", date(2020, 2, 1), 0.2, None, "nao_verificavel", "t")]
    assert sgs.anexar_divulgacao(obs, divulgacoes)[0].origem_disponibilidade == "nao_verificavel"


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


def test_duplicidade_identica_e_consolidada_com_a_divulgacao_mais_antiga():
    """Caso real: a PTAX devolveu 23/04/2025 duas vezes com o mesmo valor."""
    cedo = Observacao("ptax_venda", date(2025, 4, 23), 5.71, datetime(2025, 4, 23, 13, 5, tzinfo=BRASILIA), "ptax_datahora_cotacao", "t")
    tarde = Observacao("ptax_venda", date(2025, 4, 23), 5.71, datetime(2025, 4, 23, 13, 9, tzinfo=BRASILIA), "ptax_datahora_cotacao", "t")
    outro = Observacao("ptax_venda", date(2025, 4, 24), 5.68, datetime(2025, 4, 24, 13, 4, tzinfo=BRASILIA), "ptax_datahora_cotacao", "t")
    assert not graves(validar_serie([tarde, cedo, outro], "diaria", (1, 15), HOJE))
    assert consolidar_duplicadas([tarde, cedo, outro]) == [cedo, outro]


def test_consolidar_recusa_valores_diferentes():
    a = Observacao("ptax_venda", date(2025, 4, 23), 5.71, None, "nao_verificavel", "t")
    b = Observacao("ptax_venda", date(2025, 4, 23), 5.80, None, "nao_verificavel", "t")
    with pytest.raises(ValueError):
        consolidar_duplicadas([a, b])


def test_copia_do_calendario_ibge_guarda_so_o_ipca_e_respeita_datas_futuras(tmp_path):
    from datetime import datetime

    from coleta import ibge
    from coleta.modelos import BRASILIA

    itens = [
        {"produto_id": 9256, "ano_referencia_inicio": 2026, "mes_referencia_inicio": 9,
         "data_divulgacao": "09/10/2026 09:00:00", "titulo": "IPCA"},
        {"produto_id": 9256, "ano_referencia_inicio": 2026, "mes_referencia_inicio": 10,
         "data_divulgacao": "10/11/2026 09:00:00"},
        {"produto_id": 9256, "ano_referencia_inicio": 2026, "mes_referencia_inicio": 11,
         "data_divulgacao": "10/12/2026 09:00:00"},
        {"produto_id": 9260, "ano_referencia_inicio": 2026, "mes_referencia_inicio": 10,
         "data_divulgacao": "27/10/2026 09:00:00"},
    ]
    caminho = tmp_path / "calendario.json"
    exportado = datetime(2026, 11, 14, 9, 0, tzinfo=BRASILIA)
    ibge.salvar_copia(itens, caminho, exportado)

    lidos, quando = ibge.ler_copia(caminho)
    assert quando == exportado
    assert len(lidos) == 3 and all(i["produto_id"] == 9256 for i in lidos)
    assert ibge.ultima_data_agendada(lidos) == datetime(2026, 12, 10, 9, 0, tzinfo=BRASILIA)

    # Em 14/11 a divulgação de novembro (agendada para 10/12) ainda não vale
    em_novembro = ibge.interpretar(lidos, exportado)
    assert sorted(m.month for m in em_novembro) == [9, 10]
    # Depois de 10/12 ela passa a valer, pela mesma regra
    em_dezembro = ibge.interpretar(lidos, datetime(2026, 12, 10, 10, 0, tzinfo=BRASILIA))
    assert sorted(m.month for m in em_dezembro) == [9, 10, 11]
