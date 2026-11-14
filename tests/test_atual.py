"""Testes da Fase 4: previsões de hoje e mensagens do dashboard."""

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from coleta.modelos import BRASILIA  # noqa: E402
from forecast.atual import mensagens, previsao_cambio, previsao_ipca, tabela_desempenho  # noqa: E402
from forecast.fontes import FonteMemoria  # noqa: E402
from test_forecast import cambio_sintetico, ipca_sintetico  # noqa: E402
from test_sarima import BackendFalso  # noqa: E402

AGORA = datetime(2022, 7, 20, 12, 0, tzinfo=BRASILIA)


def _fonte_com_focus():
    versoes = pd.concat([ipca_sintetico(meses=150), cambio_sintetico(700)], ignore_index=True)
    meses = pd.date_range("2022-06-01", periods=8, freq="MS")
    focus = pd.DataFrame({"mes_alvo": meses, "mediana": 0.35, "data_estatistica": pd.Timestamp("2022-07-15"),
                          "disponivel_em": pd.Timestamp("2022-07-18 09:00", tz=BRASILIA)})
    return FonteMemoria(versoes, focus)


def _backtest_estreito(n=60):
    """Backtest em que o SARIMA errava para fora da faixa: a calibração deve alargar."""
    rng = np.random.default_rng(1)
    linhas = []
    for medida in ("variacao", "acumulado_12m"):
        for h in range(1, 7):
            real = rng.normal(0, 1, n)
            linhas.append(pd.DataFrame({"medida": medida, "modelo": "sarima", "h": h, "previsto": 0.0,
                                        "li80": -0.1, "ls80": 0.1, "li95": -0.2, "ls95": 0.2, "realizado": real}))
    return pd.concat(linhas, ignore_index=True)


def test_previsao_ipca_estrutura_focus_e_calibracao():
    fonte = _fonte_com_focus()
    sem = previsao_ipca(fonte, AGORA, None, backend=BackendFalso())
    com = previsao_ipca(fonte, AGORA, _backtest_estreito(), backend=BackendFalso())
    assert sem["ultimo_conhecido"] == "2022-06-01"  # IPCA de jun/22 divulgado em 10/07/22
    assert [p["h"] for p in com["previsoes"]] == [1, 2, 3, 4, 5, 6]
    assert com["previsoes"][0]["alvo"] == "2022-07-01"
    assert com["previsoes"][0]["focus"] == 0.35
    assert sem["previsoes"][0]["li80"] is None          # sem backtest: não publica faixa não calibrada
    p = com["previsoes"][2]
    assert p["li95"] <= p["li80"] <= p["previsto"] <= p["ls80"] <= p["ls95"]
    assert p["ls95"] - p["li95"] > 1.0                  # alargada pela calibração
    a = com["acumulado_12m"][5]
    assert a["li80"] <= a["previsto"] <= a["ls80"] and a["focus"] is not None


def test_previsao_cambio_passeio_aleatorio():
    c = previsao_cambio(_fonte_com_focus(), AGORA)
    ultimo_valor = c["historico"][-1][1]
    assert [p["h"] for p in c["previsoes"]] == [1, 5, 10, 21]
    assert all(p["previsto"] == ultimo_valor for p in c["previsoes"])
    larguras = [p["ls80"] - p["li80"] for p in c["previsoes"]]
    assert larguras == sorted(larguras)                 # incerteza cresce com o horizonte


METRICAS_REAIS = pd.DataFrame(
    # resultados do backtest de 14/11/2026 (vs Focus e vs média sazonal)
    [("ipca_mensal", "variacao", "focus_mediana", "sarima", h, 118, 0.3, rf, None, None, vf) for h, rf, vf in [
        (1, 1.318, "pior que a referência"), (2, 1.047, "sem diferença significativa"),
        (3, 1.042, "sem diferença significativa"), (4, 1.033, "sem diferença significativa"),
        (5, 1.021, "sem diferença significativa"), (6, 0.995, "sem diferença significativa")]] +
    [("ipca_mensal", "variacao", "media_sazonal_5a", "sarima", h, 118, 0.3, rm, None, None, vm) for h, rm, vm in [
        (1, 0.840, "melhor que a referência"), (2, 0.901, "melhor que a referência"),
        (3, 0.936, "sem diferença significativa"), (4, 0.952, "sem diferença significativa"),
        (5, 0.956, "sem diferença significativa"), (6, 0.950, "sem diferença significativa")]] +
    [("ptax_venda", "variacao", "passeio_aleatorio", m, h, 250, 0.1, r, 0.82, 0.96, v) for h in (1, 5, 10, 21)
     for m, r, v in [("passeio_aleatorio", 1.0, "referência"), ("arima_log", 1.01, "sem diferença significativa")]],
    columns=["serie", "medida", "comparacao", "modelo", "h", "n", "rmse", "rmse_relativo", "cobertura80",
             "cobertura95", "veredito"])


def test_mensagens_refletem_exatamente_os_testes():
    msg = mensagens(tabela_desempenho(METRICAS_REAIS))
    assert "A partir de 2 meses" in msg["ipca"]
    assert "Em 1 mês à frente, o mercado erra menos" in msg["ipca"]
    assert "em 1 e 2 meses à frente" in msg["ipca"]
    assert "supera o Focus" not in msg["ipca"] and "bate" not in msg["ipca"]
    assert "Nenhum modelo testado superou o passeio aleatório" in msg["cambio"]


def test_mensagem_nao_afirma_empate_se_algum_horizonte_posterior_perde():
    m = METRICAS_REAIS.copy()
    m.loc[(m["comparacao"] == "focus_mediana") & (m["h"] == 5), "veredito"] = "pior que a referência"
    msg = mensagens(tabela_desempenho(m))
    assert "A partir de 6 meses" in msg["ipca"]
