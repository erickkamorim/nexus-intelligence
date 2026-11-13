"""Testes da Fase 2: modelos de referência, backtest sem vazamento, métricas e Diebold-Mariano.

Rode na raiz do projeto:  python -m pytest -q
"""

import math
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from coleta.modelos import BRASILIA  # noqa: E402
from forecast.backtest import ConfigSerie, VazamentoDeDados, executar, origens_semanais  # noqa: E402
from forecast.fontes import FonteMemoria, Historico  # noqa: E402
from forecast.metricas import diebold_mariano, resumo  # noqa: E402
from forecast.modelos import MODELOS_CAMBIO, MODELOS_IPCA, prever_com_intervalo  # noqa: E402

RNG = np.random.default_rng(42)


# ---------------------------------------------------------------- dados sintéticos
def ipca_sintetico(meses=150, inicio="2010-01-01"):
    idx = pd.date_range(inicio, periods=meses, freq="MS")
    sazonal = 0.15 * np.sin(2 * np.pi * idx.month / 12)
    valores = 0.4 + sazonal + RNG.normal(0, 0.12, meses)
    divulgado = [pd.Timestamp(d + pd.DateOffset(months=1, days=9), tz=BRASILIA).replace(hour=9) for d in idx]
    return pd.DataFrame({"serie": "ipca_mensal", "data_referencia": idx, "valor": valores, "versao": 1,
                         "conhecido_desde": divulgado})


def cambio_sintetico(dias=900):
    idx = pd.bdate_range("2020-01-01", periods=dias)
    valores = 5 * np.exp(np.cumsum(RNG.normal(0, 0.008, dias)))
    conhecido = [pd.Timestamp(d, tz=BRASILIA).replace(hour=13) for d in idx]
    return pd.DataFrame({"serie": "ptax_venda", "data_referencia": idx, "valor": valores, "versao": 1,
                         "conhecido_desde": conhecido})


IPCA = ConfigSerie("ipca_mensal", "mensal", [1, 3, 6], n_erros_intervalo=60, minimo_historico=72)
CAMBIO = ConfigSerie("ptax_venda", "diaria", [1, 5, 21], n_erros_intervalo=300, minimo_historico=300)


# ---------------------------------------------------------------- modelos
@pytest.mark.parametrize("modelo", MODELOS_IPCA + MODELOS_CAMBIO, ids=lambda m: m.nome)
@pytest.mark.parametrize("h", [1, 5])
def test_modelo_nunca_olha_o_futuro(modelo, h):
    y = pd.Series(np.exp(RNG.normal(0, 0.1, 400)) + 3)
    t = 300
    antes = modelo.previsao(y, h).iloc[: t + 1]
    alterada = y.copy()
    alterada.iloc[t + 1:] = 999.0  # muda tudo que vem depois de t
    depois = modelo.previsao(alterada, h).iloc[: t + 1]
    pd.testing.assert_series_equal(antes, depois)


def test_sazonal_ingenuo_e_media_sazonal_usam_os_meses_certos():
    y = pd.Series(np.arange(1, 81, dtype=float))  # y[t] = t + 1
    assert MODELOS_IPCA[1].previsao(y, 2).iloc[40] == y.iloc[40 + 2 - 12]
    media = MODELOS_IPCA[2].previsao(y, 2)
    # com 5 anos completos disponíveis: média de y[t+h-12k], k = 1..5
    assert media.iloc[70] == pytest.approx(np.mean([y.iloc[70 + 2 - 12 * k] for k in range(1, 6)]))
    # sem 5 anos de histórico: não inventa uma média parcial
    assert math.isnan(media.iloc[52])


def test_intervalos_ordenados_e_coerentes():
    y = pd.Series(5 * np.exp(np.cumsum(RNG.normal(0, 0.01, 800))))
    p = prever_com_intervalo(MODELOS_CAMBIO[0], y, 5, 300)
    assert p["li95"] <= p["li80"] <= p["previsto"] <= p["ls80"] <= p["ls95"]


def test_intervalo_nao_e_informado_com_poucos_erros():
    y = pd.Series(np.linspace(1, 2, 15))
    p = prever_com_intervalo(MODELOS_IPCA[0], y, 1, 60)
    assert math.isnan(p["li80"]) and p["n_erros_intervalo"] < 20


# ---------------------------------------------------------------- backtest sem vazamento
def test_origem_antes_da_divulgacao_nao_enxerga_o_mes():
    fonte = FonteMemoria(ipca_sintetico())
    mes = pd.Timestamp("2019-03-01")
    divulgacao = fonte.versoes.loc[fonte.versoes["data_referencia"] == mes, "conhecido_desde"].iloc[0]
    antes = executar(fonte, IPCA, MODELOS_IPCA[:1], [divulgacao - timedelta(minutes=1)])
    depois = executar(fonte, IPCA, MODELOS_IPCA[:1], [divulgacao + timedelta(minutes=1)])
    assert antes["ultimo_conhecido"].iloc[0] == mes - pd.DateOffset(months=1)
    assert depois["ultimo_conhecido"].iloc[0] == mes
    alvo_h3 = depois.loc[depois["h"] == 3, "alvo"].iloc[0]
    assert alvo_h3 == mes + pd.DateOffset(months=3)


def test_motor_interrompe_se_a_fonte_entregar_dado_do_futuro():
    class FonteComVazamento(FonteMemoria):
        def conhecida_em(self, serie, momento):
            h = super().conhecida_em(serie, momento + timedelta(days=60))  # bug proposital
            return Historico(h.valores, h.conhecido_desde)

    fonte = FonteComVazamento(ipca_sintetico())
    with pytest.raises(VazamentoDeDados):
        executar(fonte, IPCA, MODELOS_IPCA[:1], [datetime(2019, 6, 20, tzinfo=BRASILIA)])


def test_revisao_posterior_nao_entra_no_historico_mas_e_o_valor_realizado():
    versoes = ipca_sintetico()
    mes = pd.Timestamp("2019-01-01")
    original = versoes.loc[versoes["data_referencia"] == mes].iloc[0]
    revisao = original.copy()
    revisao["valor"], revisao["versao"] = 9.99, 2
    revisao["conhecido_desde"] = pd.Timestamp("2025-01-01", tz=BRASILIA)
    fonte = FonteMemoria(pd.concat([versoes, revisao.to_frame().T], ignore_index=True).astype({"valor": float, "versao": int}))
    hist = fonte.conhecida_em("ipca_mensal", datetime(2019, 6, 1, tzinfo=BRASILIA))
    assert hist.valores[mes] == pytest.approx(original["valor"])
    assert fonte.atual("ipca_mensal")[mes] == 9.99


def test_focus_so_e_usado_se_publicado_ate_a_origem_e_para_o_mesmo_mes_alvo():
    versoes = ipca_sintetico()
    origem = datetime(2019, 4, 10, 9, 1, tzinfo=BRASILIA)  # logo após o IPCA de mar/2019
    focus = pd.DataFrame({
        "mes_alvo": pd.to_datetime(["2019-04-01", "2019-04-01", "2019-06-01"]),
        "mediana": [0.30, 0.99, 0.25],
        "data_estatistica": pd.to_datetime(["2019-04-05", "2019-04-12", "2019-04-05"]),
        "disponivel_em": [pd.Timestamp("2019-04-08 09:00", tz=BRASILIA), pd.Timestamp("2019-04-15 09:00", tz=BRASILIA),
                          pd.Timestamp("2019-04-08 09:00", tz=BRASILIA)],
    })
    df = executar(FonteMemoria(versoes, focus), IPCA, MODELOS_IPCA[:1], [origem], usar_focus=True)
    f = df[df["modelo"] == "focus_mediana"].set_index("h")
    assert f.loc[1, "previsto"] == 0.30          # o relatório de 15/04 ainda não existia
    assert f.loc[3, "previsto"] == 0.25          # mês-alvo jun/2019 = 3 meses após mar/2019
    assert 6 not in f.index                      # sem expectativa para set/2019: não inventa


def test_origens_semanais_deixam_espaco_para_o_maior_horizonte():
    cal = pd.bdate_range("2020-01-01", periods=400)
    origens = origens_semanais(cal, 50, 21, 5)
    assert len(origens) == 50
    assert pd.Timestamp(origens[-1].date()) <= cal[-22]
    assert all((b - a).days >= 5 for a, b in zip(origens, origens[1:]))


def test_backtest_completo_do_cambio_cobertura_proxima_do_nominal():
    fonte = FonteMemoria(cambio_sintetico(1200))
    cal = fonte.atual("ptax_venda").index
    df = executar(fonte, CAMBIO, MODELOS_CAMBIO, origens_semanais(cal, 120, 21, 5))
    m = resumo(df, "passeio_aleatorio", passo=5)
    rw = m[(m["modelo"] == "passeio_aleatorio") & (m["h"] == 1)].iloc[0]
    assert 0.85 <= rw["cobertura95"] <= 1.0
    assert set(m["veredito"]) <= {"referência", "melhor que a referência", "pior que a referência",
                                  "sem diferença significativa", "amostra insuficiente"}


# ---------------------------------------------------------------- Diebold-Mariano
def test_dm_sinal_e_simetria():
    e_bom = RNG.normal(0, 1, 200)
    e_ruim = e_bom * 1.5 + RNG.normal(0, 0.3, 200)
    a = diebold_mariano(e_bom, e_ruim, h=1)
    b = diebold_mariano(e_ruim, e_bom, h=1)
    assert a["dm"] > 0 and a["p_modelo_melhor"] < 0.05
    assert b["dm"] == pytest.approx(-a["dm"])


def test_dm_previsoes_identicas_nao_produzem_conclusao():
    e = RNG.normal(0, 1, 100)
    assert math.isnan(diebold_mariano(e, e, h=1)["p_bilateral"])


def test_dm_defasagens_dependem_do_espacamento_das_origens():
    e1, e2 = RNG.normal(0, 1, 100), RNG.normal(0, 1, 100)
    assert diebold_mariano(e1, e2, h=6, passo=1)["defasagens"] == 5
    assert diebold_mariano(e1, e2, h=21, passo=5)["defasagens"] == 4
    assert diebold_mariano(e1, e2, h=1, passo=5)["defasagens"] == 0


def _erros_sobrepostos(T, h):
    """Erros MA(h-1): o que acontece com previsões de h passos em origens consecutivas."""
    choques = RNG.normal(0, 1, T + h)
    return np.array([choques[t:t + h].sum() for t in range(T)])


def test_dm_com_correcao_mantem_o_nivel_e_sem_correcao_rejeita_demais():
    """Simulação sob H0 (modelos igualmente bons) com h = 6 e T = 60.
    A correção para autocorrelação deve rejeitar perto de 5%; ignorar a
    sobreposição (h=1) deve rejeitar bem mais, mostrando por que ela é necessária."""
    T, h, simulacoes = 60, 6, 600
    rejeita_corrigido = rejeita_ingenuo = 0
    for _ in range(simulacoes):
        e1, e2 = _erros_sobrepostos(T, h), _erros_sobrepostos(T, h)
        rejeita_corrigido += diebold_mariano(e1, e2, h=h)["p_bilateral"] < 0.05
        rejeita_ingenuo += diebold_mariano(e1, e2, h=1)["p_bilateral"] < 0.05
    taxa_corrigida, taxa_ingenua = rejeita_corrigido / simulacoes, rejeita_ingenuo / simulacoes
    assert taxa_corrigida <= 0.12
    assert taxa_ingenua > taxa_corrigida + 0.05
