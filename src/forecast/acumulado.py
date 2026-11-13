"""IPCA acumulado em 12 meses a partir de meses observados e previstos.

O acumulado que termina no mês-alvo (último conhecido + h) combina:
  * os 12 - h últimos meses OBSERVADOS (como eram conhecidos na origem);
  * os h meses PREVISTOS.
Composição por juros compostos: prod(1 + v/100) - 1.

Com caminhos simulados, o acumulado é calculado em CADA caminho, o que
preserva a correlação entre os meses previstos. Somar intervalos mensais
seria errado.
"""

import numpy as np
import pandas as pd


def _observados_necessarios(observados: pd.Series, h: int) -> np.ndarray:
    n = 12 - h
    if n <= 0:
        return np.array([])
    ultimos = observados.iloc[-n:]
    esperado = pd.date_range(end=observados.index[-1], periods=n, freq="MS")
    if len(ultimos) < n or not ultimos.index.equals(esperado):
        raise ValueError(f"Faltam meses observados contínuos para compor o acumulado com h={h}")
    return ultimos.to_numpy(float)


def acumulado_12m(observados: pd.Series, previstos: list[float], h: int) -> float:
    if h < 1 or h > 12 or len(previstos) < h:
        raise ValueError("Informe as previsões dos meses 1..h (h entre 1 e 12)")
    fatores = np.concatenate([_observados_necessarios(observados, h), np.asarray(previstos[:h], float)])
    return float((np.prod(1 + fatores / 100) - 1) * 100)


def acumulado_12m_caminhos(observados: pd.Series, caminhos: np.ndarray, h: int) -> np.ndarray:
    """caminhos: matriz (horizonte, n_caminhos) com variações mensais simuladas."""
    base = np.prod(1 + _observados_necessarios(observados, h) / 100)
    return (base * np.prod(1 + caminhos[:h, :] / 100, axis=0) - 1) * 100


def realizado_12m(serie: pd.Series, alvo: pd.Timestamp) -> float | None:
    janela = serie.loc[:alvo].iloc[-12:]
    esperado = pd.date_range(end=alvo, periods=12, freq="MS")
    if len(janela) < 12 or not janela.index.equals(esperado):
        return None
    return float((np.prod(1 + janela.to_numpy(float) / 100) - 1) * 100)
