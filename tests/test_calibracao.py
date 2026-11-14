"""Testes da calibração conformal: corrige a cobertura e não usa o futuro."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from forecast.calibracao import calibrar  # noqa: E402
from forecast.metricas import resumo  # noqa: E402


def _backtest(n=200, largura=0.5, h=1, semente=0):
    """Previsões com erro N(0,1) e intervalos estreitos demais (meia-largura 0.5)."""
    rng = np.random.default_rng(semente)
    datas = pd.date_range("2010-01-01", periods=n, freq="MS")
    realizado = rng.normal(0, 1, n)
    return pd.DataFrame({
        "medida": "variacao", "modelo": "sarima", "h": h,
        "origem": datas, "ultimo_conhecido": datas, "alvo": datas + pd.DateOffset(months=h),
        "previsto": 0.0, "realizado": realizado,
        "li80": -largura, "ls80": largura, "li95": -largura * 1.5, "ls95": largura * 1.5,
    }).assign(erro=lambda d: d["realizado"] - d["previsto"])


def _cobertura(df, nivel):
    ok = df[f"li{nivel}"].notna()
    d = df[ok]
    return ((d["realizado"] >= d[f"li{nivel}"]) & (d["realizado"] <= d[f"ls{nivel}"])).mean()


def test_calibracao_corrige_intervalos_estreitos():
    df = _backtest(400)
    assert _cobertura(df, 95) < 0.7
    cal = calibrar(df, "sarima")
    assert 0.90 <= _cobertura(cal, 95) <= 0.99
    assert 0.72 <= _cobertura(cal, 80) <= 0.88


def test_calibracao_estreita_intervalos_largos():
    df = _backtest(400, largura=3.0)
    assert _cobertura(df, 80) > 0.95
    cal = calibrar(df, "sarima")
    assert _cobertura(cal, 80) < 0.90
    larg_original = (df["ls80"] - df["li80"]).mean()
    assert (cal["ls80"] - cal["li80"]).mean() < larg_original


def test_calibracao_nao_usa_valores_ainda_nao_publicados():
    """Alterar valores realizados de previsões cujo alvo ainda não era conhecido
    na origem não pode mudar o intervalo calibrado daquela origem."""
    df = _backtest(120, h=6)
    cal = calibrar(df, "sarima").set_index("origem")
    origem = df["origem"].iloc[80]
    alterado = df.copy()
    nao_publicados = alterado["alvo"] > alterado.loc[alterado["origem"] == origem, "ultimo_conhecido"].iloc[0]
    alterado.loc[nao_publicados, "realizado"] = 999.0
    cal2 = calibrar(alterado, "sarima").set_index("origem")
    assert cal.loc[origem, "li95"] == cal2.loc[origem, "li95"]
    assert cal.loc[origem, "ls80"] == cal2.loc[origem, "ls80"]


def test_sem_escores_suficientes_nao_ha_intervalo():
    cal = calibrar(_backtest(30), "sarima", minimo=24)
    assert cal["li95"].iloc[:24].isna().all()
    assert cal["li95"].iloc[-1:].notna().all()


def test_previsao_pontual_nao_muda_e_intervalos_ficam_ordenados():
    df = _backtest(200)
    cal = calibrar(df, "sarima").dropna(subset=["li95"])
    assert (cal["previsto"] == 0.0).all()
    assert ((cal["li95"] <= cal["li80"]) & (cal["li80"] <= cal["previsto"]) &
            (cal["previsto"] <= cal["ls80"]) & (cal["ls80"] <= cal["ls95"])).all()
    assert set(cal["modelo"]) == {"sarima_calibrado"}


def test_resumo_aceita_o_modelo_calibrado():
    df = _backtest(200)
    df = pd.concat([df, df.assign(modelo="ingenuo"), calibrar(df, "sarima")], ignore_index=True)
    m = resumo(df, "ingenuo")
    assert "sarima_calibrado" in set(m["modelo"])
