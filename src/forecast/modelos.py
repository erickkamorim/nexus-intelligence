"""Modelos de referência (baselines).

Cada modelo define UMA função: previsao(y, h) -> Series f, em que f[t] é a
previsão de y[t+h] feita com dados até t (inclusive). Ela é construída só com
deslocamentos para trás (shift) e janelas que terminam em t, portanto nunca
olha o futuro: há um teste que altera os valores futuros e confere que f[t]
não muda.

A mesma função serve para:
  * a previsão na origem (último valor de f);
  * os erros históricos dentro do treino, que formam os intervalos empíricos
    (quantis dos erros de h passos), sem nenhuma hipótese de normalidade.

Escala: IPCA em pontos percentuais (erros aditivos); câmbio em log (erros
multiplicativos, convertidos de volta para R$).
"""

import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd


@dataclass
class Modelo:
    nome: str
    previsao: Callable[[pd.Series, int], pd.Series]
    escala: str = "nivel"            # "nivel" (aditivo) ou "log" (multiplicativo)
    descricao: str = ""
    tags: set = field(default_factory=set)


# ------------------------------------------------------------------ IPCA mensal
def _ingenuo(y: pd.Series, h: int) -> pd.Series:
    return y.copy()


def _sazonal_ingenuo(y: pd.Series, h: int) -> pd.Series:
    if h > 12:
        raise ValueError("sazonal ingênuo definido para h <= 12")
    # previsão de y[t+h] = y[t+h-12], que está em t - (12-h) <= t
    return y.shift(12 - h)


def _media_sazonal(anos: int):
    def prever(y: pd.Series, h: int) -> pd.Series:
        if h > 12:
            raise ValueError("média sazonal definida para h <= 12")
        # média de y[t+h-12k], k = 1..anos (todos <= t)
        return pd.concat([y.shift(12 * k - h) for k in range(1, anos + 1)], axis=1).mean(axis=1, skipna=False)
    return prever


MODELOS_IPCA = [
    Modelo("ingenuo", _ingenuo, "nivel", "Repete a variação do último mês conhecido", {"referencia"}),
    Modelo("sazonal_ingenuo", _sazonal_ingenuo, "nivel", "Repete o mesmo mês do ano anterior"),
    Modelo("media_sazonal_5a", _media_sazonal(5), "nivel", "Média do mesmo mês nos últimos 5 anos"),
]


# ------------------------------------------------------------------ Câmbio (dias úteis)
def _passeio_aleatorio(y: pd.Series, h: int) -> pd.Series:
    return y.copy()


def _passeio_com_tendencia(janela: int):
    def prever(y: pd.Series, h: int) -> pd.Series:
        retorno = np.log(y).diff()
        tendencia = retorno.rolling(janela, min_periods=janela).mean()  # termina em t
        return y * np.exp(h * tendencia)
    return prever


MODELOS_CAMBIO = [
    Modelo("passeio_aleatorio", _passeio_aleatorio, "log", "Cotação de amanhã = cotação de hoje", {"referencia"}),
    Modelo("passeio_aleatorio_tendencia", _passeio_com_tendencia(250), "log",
           "Passeio aleatório com a tendência média dos últimos 250 dias úteis"),
]


# ------------------------------------------------------------------ Previsão com intervalo empírico
def prever_com_intervalo(modelo: Modelo, y: pd.Series, h: int, n_erros: int,
                         niveis=(0.80, 0.95)) -> dict | None:
    """Previsão pontual na origem (último ponto de y) + intervalos pelos quantis
    dos últimos `n_erros` erros de h passos que o mesmo modelo cometeu no treino."""
    f = modelo.previsao(y, h)
    pontual = f.iloc[-1]
    if pd.isna(pontual):
        return None
    if modelo.escala == "log":
        erros = (np.log(y.shift(-h)) - np.log(f)).dropna().tail(n_erros)
    else:
        erros = (y.shift(-h) - f).dropna().tail(n_erros)
    saida = {"previsto": float(pontual), "n_erros_intervalo": int(len(erros))}
    for nivel in niveis:
        chave = int(round(nivel * 100))
        if len(erros) < 20:  # poucos erros: intervalo não informado
            saida[f"li{chave}"] = saida[f"ls{chave}"] = math.nan
            continue
        a = (1 - nivel) / 2
        q_baixo, q_alto = np.quantile(erros, [a, 1 - a])
        if modelo.escala == "log":
            saida[f"li{chave}"], saida[f"ls{chave}"] = pontual * math.exp(q_baixo), pontual * math.exp(q_alto)
        else:
            saida[f"li{chave}"], saida[f"ls{chave}"] = pontual + q_baixo, pontual + q_alto
    return saida
