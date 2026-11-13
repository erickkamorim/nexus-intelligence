"""SARIMA (IPCA) e ARIMA no log (câmbio), com intervalos por simulação.

Regras:
  * a ordem é escolhida por AIC numa grade pequena, usando SÓ a série recebida
    (os dados conhecidos na origem). A seleção é refeita a cada
    `reselecionar_a_cada` origens; os parâmetros são reestimados em toda origem;
  * os intervalos vêm de `n_caminhos` caminhos simulados a partir do último
    dado conhecido. Eles refletem a incerteza dos choques futuros, mas não a
    incerteza na estimação dos parâmetros (limitação documentada);
  * no câmbio o modelo trabalha em log: a previsão pontual é exp(média do log),
    ou seja, a mediana em R$, e os quantis são convertidos com exp;
  * o backend de estimação é injetável: em produção usa o statsmodels; nos
    testes, um backend simples em numpy, para verificar toda a lógica em volta.
"""

import logging
import math
import os
import warnings
from dataclasses import dataclass
from itertools import product

import numpy as np
import pandas as pd

log = logging.getLogger("nexus.forecast")


@dataclass(frozen=True)
class Especificacao:
    ordem: tuple[int, int, int]
    sazonal: tuple[int, int, int, int] = (0, 0, 0, 0)
    tendencia: str = "c"   # 'c' constante (d=0) | 't' tendência linear = deriva quando d=1 | 'n' nenhuma

    def __str__(self):
        p, d, q = self.ordem
        P, D, Q, s = self.sazonal
        texto = f"ARIMA({p},{d},{q})"
        if s:
            texto = f"SARIMA({p},{d},{q})({P},{D},{Q}){s}"
        return f"{texto} tend={self.tendencia}"


def grade_ipca() -> list[Especificacao]:
    return [Especificacao((p, 0, q), (P, 0, Q, 12), "c")
            for p, q, P, Q in product(range(3), range(3), range(2), range(2))]


def grade_cambio() -> list[Especificacao]:
    return [Especificacao((p, 1, q), (0, 0, 0, 0), t) for p, q, t in product(range(3), range(3), ("n", "t"))]


def _ajustar_statsmodels(z: np.ndarray, espec: Especificacao, maxiter: int, inicio=None):
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        modelo = SARIMAX(z, order=espec.ordem, seasonal_order=espec.sazonal, trend=espec.tendencia,
                         enforce_stationarity=True, enforce_invertibility=True)
        # cov_type="none": não calcula a covariância dos parâmetros (erros-padrão),
        # que não é usada aqui e custava a maior parte do tempo de cada ajuste.
        return modelo.fit(disp=False, maxiter=maxiter, cov_type="none", start_params=inicio)


def _aic_statsmodels(argumentos) -> float:
    """Executado em processos paralelos durante a seleção de ordem."""
    z, espec, maxiter = argumentos
    try:
        return float(_ajustar_statsmodels(z, espec, maxiter).aic)
    except Exception:
        return math.inf


class BackendStatsmodels:
    """Ajuste com statsmodels.SARIMAX (importado só quando usado)."""

    def __init__(self, maxiter: int = 200, processos: int | None = None):
        self.maxiter = maxiter
        # Cada processo carrega statsmodels/pandas (centenas de MB). Padrão conservador: 2.
        # Ajustável pela variável de ambiente NEXUS_PROCESSOS (1 = sem paralelismo).
        if processos is None:
            processos = int(os.getenv("NEXUS_PROCESSOS", "2"))
        self.processos = max(1, min(processos, os.cpu_count() or 1))
        self._executor = None
        self._ultimos_parametros: dict[Especificacao, np.ndarray] = {}

    def ajustar(self, z: np.ndarray, espec: Especificacao):
        inicio = self._ultimos_parametros.get(espec)
        try:
            resultado = _ajustar_statsmodels(z, espec, self.maxiter, inicio)
        except Exception:
            if inicio is None:
                raise
            resultado = _ajustar_statsmodels(z, espec, self.maxiter)  # sem ponto de partida
        # os parâmetros desta origem são o ponto de partida da próxima (convergência mais rápida)
        self._ultimos_parametros[espec] = np.asarray(resultado.params)
        return _AjusteStatsmodels(resultado)

    def aics(self, z: np.ndarray, grade: list[Especificacao]) -> list[float]:
        """AIC de cada especificação, em paralelo quando houver mais de um núcleo."""
        tarefas = [(z, e, self.maxiter) for e in grade]
        if self.processos <= 1:
            return [_aic_statsmodels(t) for t in tarefas]
        # Um único conjunto de processos, reaproveitado em todas as seleções
        # (criar e destruir processos a cada seleção custa memória e tempo).
        if self._executor is None:
            from concurrent.futures import ProcessPoolExecutor
            self._executor = ProcessPoolExecutor(max_workers=self.processos)
        return list(self._executor.map(_aic_statsmodels, tarefas))

    def encerrar(self) -> None:
        if self._executor is not None:
            self._executor.shutdown()
            self._executor = None


class _AjusteStatsmodels:
    def __init__(self, resultado):
        self.resultado = resultado
        self.aic = float(resultado.aic)

    def prever(self, horizonte: int) -> np.ndarray:
        return np.asarray(self.resultado.forecast(horizonte), float)

    def simular(self, horizonte: int, n: int, semente: int) -> np.ndarray:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                sim = self.resultado.simulate(horizonte, repetitions=n, anchor="end", random_state=semente)
            except TypeError:  # versões antigas sem random_state
                np.random.seed(semente)
                sim = self.resultado.simulate(horizonte, repetitions=n, anchor="end")
        return np.asarray(sim, float).reshape(horizonte, n)


class ModeloSarima:
    """Modelo ajustável: o motor chama prever_varios() uma vez por origem, em ordem cronológica."""

    ajustavel = True

    def __init__(self, nome: str, grade: list[Especificacao], escala: str, reselecionar_a_cada: int,
                 backend=None, n_caminhos: int = 1000, semente: int = 2026, minimo: int = 60):
        self.nome, self.grade, self.escala = nome, grade, escala
        self.reselecionar_a_cada, self.n_caminhos, self.semente, self.minimo = reselecionar_a_cada, n_caminhos, semente, minimo
        self.backend = backend or BackendStatsmodels()
        self.especificacao: Especificacao | None = None
        self.origens_desde_selecao = 0
        self.selecoes: list[dict] = []   # histórico das escolhas, para transparência
        self.falhas = 0

    def _transformar(self, y: pd.Series) -> np.ndarray:
        valores = y.to_numpy(float)
        return np.log(valores) if self.escala == "log" else valores

    def _selecionar(self, z: np.ndarray, quando) -> None:
        candidatos = []
        if hasattr(self.backend, "aics"):
            candidatos = list(zip(self.backend.aics(z, self.grade), self.grade))
        else:
            for espec in self.grade:
                try:
                    candidatos.append((self.backend.ajustar(z, espec).aic, espec))
                except Exception as erro:  # combinação que não converge é descartada
                    log.debug("%s falhou na seleção: %s", espec, erro)
        candidatos = [c for c in candidatos if math.isfinite(c[0])]
        if not candidatos:
            raise RuntimeError("Nenhuma especificação pôde ser ajustada")
        aic, self.especificacao = min(candidatos, key=lambda c: c[0])
        self.origens_desde_selecao = 0
        self.selecoes.append({"origem": quando, "n_obs": len(z), "especificacao": str(self.especificacao),
                              "aic": aic, "candidatos_validos": len(candidatos)})

    def prever_varios(self, y: pd.Series, horizontes: list[int], origem=None) -> dict | None:
        if len(y) < self.minimo:
            return None
        z = self._transformar(y)
        try:
            if self.especificacao is None or self.origens_desde_selecao >= self.reselecionar_a_cada:
                self._selecionar(z, origem)
            ajuste = self.backend.ajustar(z, self.especificacao)
            H = max(horizontes)
            media = ajuste.prever(H)
            caminhos = ajuste.simular(H, self.n_caminhos, self.semente)
        except Exception as erro:
            self.falhas += 1
            log.warning("%s: falha na origem %s (%s)", self.nome, origem, erro)
            return None
        finally:
            self.origens_desde_selecao += 1

        if self.escala == "log":
            media, caminhos = np.exp(media), np.exp(caminhos)
        por_h = {}
        for h in horizontes:
            linha = caminhos[h - 1]
            q = np.quantile(linha, [0.025, 0.10, 0.90, 0.975])
            pontual = float(media[h - 1])
            por_h[h] = {"previsto": pontual, "li95": float(min(q[0], pontual)), "li80": float(min(q[1], pontual)),
                        "ls80": float(max(q[2], pontual)), "ls95": float(max(q[3], pontual)),
                        "n_erros_intervalo": 0, "detalhe": str(self.especificacao)}
        return {"por_h": por_h, "caminhos": caminhos}
