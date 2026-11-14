"""Calibração conformal dos intervalos, feita em tempo real (sem olhar o futuro).

Problema medido no backtest: os intervalos do SARIMA para o IPCA cobriram ~84%
quando prometiam 95% (estreitos), e os do ARIMA no câmbio cobriram ~98%
(largos). A calibração corrige a largura com os próprios erros do passado.

Método (conformalized quantile regression, Romano et al., 2019), por modelo,
medida, horizonte e nível:
  * escore de cada previsão passada: s = max(li - y, y - ls)
    (positivo quando o valor real ficou fora da faixa; negativo quando sobrou folga);
  * na origem t, usa SÓ as previsões cujo valor real já era conhecido em t
    (alvo <= último mês/dia conhecido na origem t);
  * Q = quantil de ordem ceil((n + 1)(1 - alfa)) / n desses escores;
  * novo intervalo = [li - Q, ls + Q]. Q negativo estreita a faixa.
Com menos de `minimo` escores disponíveis, a origem fica sem intervalo calibrado.
"""

import math

import numpy as np
import pandas as pd


def _quantil_conformal(escores: np.ndarray, alfa: float) -> float:
    n = len(escores)
    k = math.ceil((n + 1) * (1 - alfa))
    if k > n:
        return math.inf
    return float(np.sort(escores)[k - 1])


def calibrar(df: pd.DataFrame, modelo: str, minimo: int = 24, sufixo: str = "_calibrado") -> pd.DataFrame:
    """Devolve novas linhas `<modelo>_calibrado` com intervalos ajustados.
    A previsão pontual não muda; só a largura dos intervalos."""
    base = df[df["modelo"] == modelo]
    if base.empty:
        return base.iloc[0:0]
    saida = []
    for (medida, h), g in base.groupby(["medida", "h"]):
        g = g.sort_values("origem")
        for _, linha in g.iterrows():
            # só previsões passadas cujo valor real já estava publicado nesta origem
            passado = g[(g["origem"] < linha["origem"]) & (g["alvo"] <= linha["ultimo_conhecido"])]
            nova = linha.copy()
            nova["modelo"] = modelo + sufixo
            nova["n_erros_intervalo"] = len(passado)
            for nivel in (80, 95):
                li, ls = f"li{nivel}", f"ls{nivel}"
                escores = np.maximum(passado[li] - passado["realizado"], passado["realizado"] - passado[ls]).dropna()
                if len(escores) < minimo or pd.isna(linha[li]):
                    nova[li] = nova[ls] = math.nan
                    continue
                q = _quantil_conformal(escores.to_numpy(float), 1 - nivel / 100)
                novo_li, novo_ls = linha[li] - q, linha[ls] + q
                # a faixa nunca encolhe além da previsão pontual
                nova[li] = min(novo_li, linha["previsto"])
                nova[ls] = max(novo_ls, linha["previsto"])
            if pd.notna(nova["li80"]) and pd.notna(nova["li95"]):
                nova["li95"] = min(nova["li95"], nova["li80"])
                nova["ls95"] = max(nova["ls95"], nova["ls80"])
            saida.append(nova)
    return pd.DataFrame(saida)


def ajuste_atual(passado: pd.DataFrame, nivel: int, minimo: int = 24) -> tuple[float | None, int]:
    """Ajuste conformal para a previsão de HOJE: usa todas as previsões do backtest
    (todas já têm valor realizado). Devolve (Q, n_escores); Q None se faltar amostra."""
    li, ls = f"li{nivel}", f"ls{nivel}"
    escores = np.maximum(passado[li] - passado["realizado"], passado["realizado"] - passado[ls]).dropna()
    if len(escores) < minimo:
        return None, len(escores)
    return _quantil_conformal(escores.to_numpy(float), 1 - nivel / 100), len(escores)


def aplicar_ajuste(previsto: float, li: float, ls: float, q: float) -> tuple[float, float]:
    return min(li - q, previsto), max(ls + q, previsto)
