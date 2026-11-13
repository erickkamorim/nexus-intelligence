"""Testes da Fase 3 com um backend falso (AR por mínimos quadrados em numpy).

O objetivo aqui é verificar toda a lógica em volta do SARIMA (dados por origem,
seleção de ordem, simulação, acumulado em 12 meses, falhas) sem depender do
statsmodels. O ajuste real com statsmodels é validado rodando src/rodar_backtest.py.
"""

import math
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from forecast.acumulado import acumulado_12m, acumulado_12m_caminhos, realizado_12m  # noqa: E402
from forecast.backtest import ConfigSerie, executar  # noqa: E402
from forecast.fontes import FonteMemoria  # noqa: E402
from forecast.metricas import resumo  # noqa: E402
from forecast.modelos import MODELOS_IPCA  # noqa: E402
from forecast.sarima import Especificacao, ModeloSarima, grade_cambio, grade_ipca  # noqa: E402
from test_forecast import ipca_sintetico  # noqa: E402


class AjusteAR:
    def __init__(self, z, p):
        self.z, self.p = np.asarray(z, float), p
        X = np.column_stack([np.ones(len(z) - p)] + [self.z[p - k - 1: len(z) - k - 1] for k in range(p)])
        alvo = self.z[p:]
        self.beta, *_ = np.linalg.lstsq(X, alvo, rcond=None)
        resid = alvo - X @ self.beta
        self.sigma = float(np.std(resid, ddof=len(self.beta)))
        self.aic = len(alvo) * math.log(self.sigma ** 2) + 2 * (len(self.beta) + 1)

    def _passo(self, hist):
        return self.beta[0] + sum(self.beta[k + 1] * hist[-k - 1] for k in range(self.p))

    def prever(self, H):
        hist = list(self.z)
        for _ in range(H):
            hist.append(self._passo(hist))
        return np.array(hist[-H:])

    def simular(self, H, n, semente):
        rng = np.random.default_rng(semente)
        saida = np.empty((H, n))
        for j in range(n):
            hist = list(self.z[-max(self.p, 1):])
            for t in range(H):
                hist.append(self._passo(hist) + rng.normal(0, self.sigma))
                saida[t, j] = hist[-1]
        return saida


class BackendFalso:
    def __init__(self, falhar=False):
        self.chamadas, self.falhar = [], falhar

    def ajustar(self, z, espec: Especificacao):
        self.chamadas.append(len(z))
        if self.falhar:
            raise RuntimeError("não convergiu")
        return AjusteAR(z, espec.ordem[0])


GRADE = [Especificacao((p, 0, 0)) for p in range(3)]
IPCA = ConfigSerie("ipca_mensal", "mensal", [1, 2, 3, 4, 5, 6], n_erros_intervalo=60, minimo_historico=72)


def _origens(fonte, n, a_partir="2017-01-01"):
    datas = sorted(fonte.versoes["conhecido_desde"])
    return [d + timedelta(minutes=1) for d in datas if d >= pd.Timestamp(a_partir, tz=d.tz)][:n]


def _modelo(backend, **kw):
    return ModeloSarima("sarima", GRADE, "nivel", reselecionar_a_cada=12, backend=backend, n_caminhos=300, minimo=72, **kw)


# ---------------------------------------------------------------- grades
def test_grades_tem_o_tamanho_documentado():
    assert len(grade_ipca()) == 36 and len(grade_cambio()) == 18
    assert all(e.ordem[1] == 1 and e.tendencia in ("n", "t") for e in grade_cambio())


# ---------------------------------------------------------------- dados por origem e seleção
def test_sarima_so_recebe_os_dados_conhecidos_em_cada_origem():
    fonte = FonteMemoria(ipca_sintetico(meses=130))
    origens = _origens(fonte, 14)
    backend = BackendFalso()
    modelo = _modelo(backend)
    executar(fonte, IPCA, [modelo], origens)
    # a última chamada de cada origem é o ajuste final: tamanho = meses conhecidos na origem
    esperados = [len(fonte.conhecida_em("ipca_mensal", o).valores) for o in origens]
    finais = [backend.chamadas[i] for i in np.cumsum([len(GRADE) * (k % 12 == 0) + 1 for k in range(len(origens))]) - 1]
    assert finais == esperados


def test_ordem_e_reselecionada_a_cada_12_origens_so_com_dados_da_origem():
    fonte = FonteMemoria(ipca_sintetico(meses=140))
    origens = _origens(fonte, 30)
    modelo = _modelo(BackendFalso())
    executar(fonte, IPCA, [modelo], origens)
    assert len(modelo.selecoes) == 3                       # origens 1, 13 e 25
    for s, o in zip(modelo.selecoes, [origens[0], origens[12], origens[24]]):
        assert s["origem"] == o
        assert s["n_obs"] == len(fonte.conhecida_em("ipca_mensal", o).valores)


def test_falha_de_ajuste_nao_derruba_o_backtest():
    fonte = FonteMemoria(ipca_sintetico(meses=120))
    modelo = _modelo(BackendFalso(falhar=True))
    df = executar(fonte, IPCA, [modelo, MODELOS_IPCA[0]], _origens(fonte, 5))
    assert modelo.falhas == 5
    assert set(df["modelo"]) == {"ingenuo"}


def test_intervalos_do_sarima_ordenados_e_com_a_ordem_registrada():
    fonte = FonteMemoria(ipca_sintetico(meses=120))
    df = executar(fonte, IPCA, [_modelo(BackendFalso())], _origens(fonte, 6))
    s = df[df["medida"] == "variacao"]
    assert ((s["li95"] <= s["li80"]) & (s["li80"] <= s["previsto"]) & (s["previsto"] <= s["ls80"]) & (s["ls80"] <= s["ls95"])).all()
    assert s["detalhe"].str.startswith("ARIMA(").all()


def test_cobertura_proxima_do_nominal_quando_o_modelo_e_o_correto():
    """Dados gerados por um AR(1); o backend ajusta AR: a cobertura de 95% deve ficar perto de 95%."""
    rng = np.random.default_rng(3)
    n = 260
    y = np.empty(n)
    y[0] = 0.4
    for t in range(1, n):
        y[t] = 0.2 + 0.5 * y[t - 1] + rng.normal(0, 0.15)
    versoes = ipca_sintetico(meses=n).assign(valor=y)
    fonte = FonteMemoria(versoes)
    df = executar(fonte, IPCA, [_modelo(BackendFalso())], _origens(fonte, 120, "2019-01-01"))
    cob = resumo(df, "sarima").set_index("h")["cobertura95"]
    assert (cob > 0.85).all() and (cob <= 1.0).all()


# ---------------------------------------------------------------- acumulado em 12 meses
def _meses(valores, fim="2024-06-01"):
    return pd.Series(valores, index=pd.date_range(end=fim, periods=len(valores), freq="MS"))


def test_acumulado_combina_observados_e_previstos():
    obs = _meses([0.5] * 24)
    assert acumulado_12m(obs, [0.5], 1) == pytest.approx((1.005 ** 12 - 1) * 100)
    # h=3: 9 observados (0.5) + 3 previstos (1.0)
    assert acumulado_12m(obs, [1.0, 1.0, 1.0], 3) == pytest.approx((1.005 ** 9 * 1.01 ** 3 - 1) * 100)


def test_acumulado_recusa_meses_observados_com_lacuna():
    obs = _meses([0.5] * 24).drop(pd.Timestamp("2024-03-01"))
    with pytest.raises(ValueError):
        acumulado_12m(obs, [0.5], 1)


def test_acumulado_por_caminhos_usa_cada_caminho():
    obs = _meses([0.5] * 24)
    caminhos = np.array([[0.0, 1.0], [0.0, 1.0]])          # 2 meses, 2 caminhos
    r = acumulado_12m_caminhos(obs, caminhos, 2)
    assert r[0] == pytest.approx((1.005 ** 10 - 1) * 100)
    assert r[1] == pytest.approx((1.005 ** 10 * 1.01 ** 2 - 1) * 100)


def test_realizado_12m_exige_12_meses_continuos():
    s = _meses([0.5] * 12)
    assert realizado_12m(s, pd.Timestamp("2024-06-01")) == pytest.approx((1.005 ** 12 - 1) * 100)
    assert realizado_12m(s, pd.Timestamp("2024-05-01")) is None


def test_backtest_gera_acumulado_para_todos_e_intervalo_so_com_caminhos():
    versoes = ipca_sintetico(meses=130)
    fonte = FonteMemoria(versoes)
    df = executar(fonte, IPCA, [MODELOS_IPCA[0], _modelo(BackendFalso())], _origens(fonte, 4), acumulado_12m=True)
    a = df[df["medida"] == "acumulado_12m"]
    assert set(a["modelo"]) == {"ingenuo", "sarima"}
    assert a.loc[a["modelo"] == "ingenuo", "li95"].isna().all()
    assert a.loc[a["modelo"] == "sarima", "li95"].notna().all()
    atual = fonte.atual("ipca_mensal")
    for _, linha in a.iterrows():
        assert linha["realizado"] == pytest.approx(realizado_12m(atual, linha["alvo"]))
