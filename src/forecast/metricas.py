"""Métricas de avaliação e teste de Diebold-Mariano.

Diebold-Mariano (DM) compara a perda de dois modelos nas MESMAS origens.
Quando o horizonte é maior que o espaçamento entre origens, as previsões se
sobrepõem e os erros ficam autocorrelacionados: a variância comum subestima a
incerteza e o teste rejeita demais. Por isso:

  * variância de longo prazo com q defasagens, q = ceil(h / passo) - 1
    (passo = espaçamento entre origens, nas mesmas unidades de h);
  * núcleo retangular, como no artigo original; se a variância sair
    não positiva, usa o núcleo de Bartlett (Newey-West), sempre positivo;
  * correção de Harvey, Leybourne e Newbold (1997) para amostras pequenas,
    com valor-p pela distribuição t com T-1 graus de liberdade.
"""

import math

import numpy as np
import pandas as pd
from scipy import stats


def _autocov(d: np.ndarray, k: int) -> float:
    dc = d - d.mean()
    return float(np.dot(dc[k:], dc[: len(d) - k]) / len(d))


def variancia_longo_prazo(d: np.ndarray, q: int) -> tuple[float, str]:
    gamas = [_autocov(d, k) for k in range(q + 1)]
    retangular = gamas[0] + 2 * sum(gamas[1:])
    if retangular > 0:
        return retangular, "retangular"
    bartlett = gamas[0] + 2 * sum((1 - k / (q + 1)) * gamas[k] for k in range(1, q + 1))
    return bartlett, "bartlett"


def diebold_mariano(erro_modelo, erro_referencia, h: int, passo: int = 1, perda: str = "quadratica") -> dict:
    """d_t = perda(referência) - perda(modelo): positivo quando o modelo erra menos.

    Retorna estatística HLN, valor-p bilateral e valor-p unilateral para
    "o modelo é melhor que a referência"."""
    e1, e2 = np.asarray(erro_modelo, float), np.asarray(erro_referencia, float)
    if e1.shape != e2.shape:
        raise ValueError("Os erros precisam estar alinhados nas mesmas origens")
    f = (lambda e: e ** 2) if perda == "quadratica" else np.abs
    d = f(e2) - f(e1)
    T = len(d)
    q = max(0, math.ceil(h / passo) - 1)
    resultado = {"n": T, "defasagens": q, "dm": math.nan, "p_bilateral": math.nan,
                 "p_modelo_melhor": math.nan, "nucleo": None}
    if T < 10 or np.allclose(d, 0):
        return resultado
    var, nucleo = variancia_longo_prazo(d, q)
    if var <= 0:
        return resultado
    dm = d.mean() / math.sqrt(var / T)
    # correção HLN; o termo usa o número de períodos sobrepostos (q + 1)
    k = q + 1
    ajuste = math.sqrt(max((T + 1 - 2 * k + k * (k - 1) / T) / T, 1e-12))
    hln = dm * ajuste
    resultado.update(dm=hln, nucleo=nucleo,
                     p_bilateral=float(2 * stats.t.sf(abs(hln), T - 1)),
                     p_modelo_melhor=float(stats.t.sf(hln, T - 1)))
    return resultado


def resumo(df: pd.DataFrame, referencia: str, passo: int = 1, alfa: float = 0.05) -> pd.DataFrame:
    """Uma linha por modelo e horizonte, sempre nas origens comuns ao modelo e à referência."""
    linhas = []
    for (modelo, h), g in df.groupby(["modelo", "h"]):
        ref = df[(df["modelo"] == referencia) & (df["h"] == h)].set_index("origem")["erro"]
        comum = g.set_index("origem")["erro"].to_frame("modelo").join(ref.rename("ref"), how="inner").dropna()
        linha = {"modelo": modelo, "h": h, "n": len(g),
                 "mae": g["erro"].abs().mean(), "rmse": math.sqrt((g["erro"] ** 2).mean())}
        for nivel in (80, 95):
            li, ls = f"li{nivel}", f"ls{nivel}"
            if li in g and g[li].notna().any():
                ok = g[li].notna()
                linha[f"cobertura{nivel}"] = ((g.loc[ok, "realizado"] >= g.loc[ok, li]) &
                                              (g.loc[ok, "realizado"] <= g.loc[ok, ls])).mean()
            else:
                linha[f"cobertura{nivel}"] = math.nan
        if modelo != referencia and len(comum):
            linha["rmse_relativo"] = math.sqrt((comum["modelo"] ** 2).mean()) / math.sqrt((comum["ref"] ** 2).mean())
            dm = diebold_mariano(comum["modelo"], comum["ref"], h, passo)
            linha.update(n_comum=dm["n"], dm=dm["dm"], p_valor=dm["p_bilateral"], p_melhor=dm["p_modelo_melhor"])
            if math.isnan(dm["p_modelo_melhor"]):
                veredito = "amostra insuficiente"
            elif dm["p_modelo_melhor"] < alfa:
                veredito = "melhor que a referência"
            elif dm["p_bilateral"] < alfa:
                veredito = "pior que a referência"
            else:
                veredito = "sem diferença significativa"
            linha["veredito"] = veredito
        else:
            linha.update(rmse_relativo=1.0 if modelo == referencia else math.nan, veredito="referência"
                         if modelo == referencia else "sem origens em comum")
        linhas.append(linha)
    return pd.DataFrame(linhas).sort_values(["h", "rmse"]).reset_index(drop=True)
