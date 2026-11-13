"""Motor de backtest com origem móvel e janela crescente.

Em cada origem:
  1. pede à Fonte o histórico conhecido naquele momento;
  2. CONFERE que todo valor recebido tinha conhecido_desde <= origem
     (se não tiver, interrompe: é um vazamento, não um aviso);
  3. cada modelo prevê h passos à frente do último dado conhecido;
  4. a previsão é comparada com o valor que de fato aconteceu (versão atual).

O alvo de h passos é definido pela frequência:
  * mensal: o mês h meses depois do último mês conhecido;
  * diária: a h-ésima data útil depois da última cotação conhecida (calendário
    das cotações realizadas).
"""

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

from coleta.modelos import BRASILIA

from .modelos import Modelo, prever_com_intervalo


class VazamentoDeDados(AssertionError):
    pass


@dataclass
class ConfigSerie:
    serie: str
    frequencia: str            # "mensal" ou "diaria"
    horizontes: list[int]
    n_erros_intervalo: int     # quantos erros passados formam o intervalo empírico
    minimo_historico: int      # observações mínimas para prever


def _alvo(ultimo: pd.Timestamp, h: int, cfg: ConfigSerie, calendario: pd.DatetimeIndex) -> pd.Timestamp | None:
    if cfg.frequencia == "mensal":
        return ultimo + pd.DateOffset(months=h)
    posicao = calendario.searchsorted(ultimo, side="right") + h - 1
    return calendario[posicao] if posicao < len(calendario) else None


def _previsoes_na_origem(modelo, y: pd.Series, cfg: ConfigSerie, origem) -> dict | None:
    """Padroniza a saída: {"por_h": {h: {...}}, "caminhos": matriz ou None}."""
    if getattr(modelo, "ajustavel", False):
        return modelo.prever_varios(y, cfg.horizontes, origem)
    por_h = {}
    for h in cfg.horizontes:
        p = prever_com_intervalo(modelo, y, h, cfg.n_erros_intervalo)
        if p is not None:
            por_h[h] = p
    return {"por_h": por_h, "caminhos": None}


def executar(fonte, cfg: ConfigSerie, modelos: list, origens: list[datetime],
             usar_focus: bool = False, acumulado_12m: bool = False, ao_avancar=None) -> pd.DataFrame:
    """Uma linha por (medida, modelo, origem, h).

    medida = 'variacao' (a própria série) ou 'acumulado_12m' (IPCA: meses observados
    na origem + meses previstos; intervalo só para modelos com caminhos simulados)."""
    from .acumulado import acumulado_12m as compor, acumulado_12m_caminhos, realizado_12m

    realizado = fonte.atual(cfg.serie)
    calendario = realizado.index
    linhas = []
    ordenadas = sorted(origens)
    for i, origem in enumerate(ordenadas, start=1):
        if ao_avancar:
            ao_avancar(i, len(ordenadas), origem)
        hist = fonte.conhecida_em(cfg.serie, origem)
        tardios = hist.conhecido_desde[hist.conhecido_desde > origem]
        if len(tardios):
            raise VazamentoDeDados(f"{cfg.serie}: {len(tardios)} valor(es) conhecidos depois da origem {origem}")
        y = hist.valores
        if len(y) < cfg.minimo_historico:
            continue
        ultimo = y.index[-1]
        alvos = {h: _alvo(ultimo, h, cfg, calendario) for h in cfg.horizontes}

        resultados = {}
        for modelo in modelos:
            r = _previsoes_na_origem(modelo, y, cfg, origem)
            if r:
                resultados[modelo.nome] = r
        if usar_focus:
            focus = fonte.focus_em(origem)
            por_h = {h: {"previsto": float(focus[a]), "n_erros_intervalo": 0}
                     for h, a in alvos.items() if a is not None and a in focus.index}
            resultados["focus_mediana"] = {"por_h": por_h, "caminhos": None}

        for nome, r in resultados.items():
            for h, p in r["por_h"].items():
                alvo = alvos[h]
                base = {"serie": cfg.serie, "origem": origem, "ultimo_conhecido": ultimo, "h": h, "alvo": alvo,
                        "modelo": nome}
                if alvo is not None and alvo in realizado.index:
                    linhas.append({**base, "medida": "variacao", "realizado": float(realizado[alvo]), **p})

                if not acumulado_12m or alvo is None:
                    continue
                anteriores = [r["por_h"].get(k) for k in range(1, h + 1)]
                if any(a is None for a in anteriores):
                    continue  # precisa de todos os meses 1..h previstos
                verdade = realizado_12m(realizado, alvo)
                if verdade is None:
                    continue
                linha = {**base, "medida": "acumulado_12m", "realizado": verdade, "n_erros_intervalo": 0,
                         "previsto": compor(y, [a["previsto"] for a in anteriores], h)}
                if r["caminhos"] is not None:
                    acum = acumulado_12m_caminhos(y, r["caminhos"], h)
                    q = np.quantile(acum, [0.025, 0.10, 0.90, 0.975])
                    pt = linha["previsto"]
                    linha.update(li95=min(q[0], pt), li80=min(q[1], pt), ls80=max(q[2], pt), ls95=max(q[3], pt),
                                 detalhe=p.get("detalhe"))
                linhas.append(linha)
    df = pd.DataFrame(linhas)
    if not df.empty:
        df["erro"] = df["realizado"] - df["previsto"]
    return df


def origens_semanais(calendario: pd.DatetimeIndex, quantidade: int, maior_h: int, passo: int = 5,
                     hora: int = 18) -> list[datetime]:
    """Origens a cada `passo` dias úteis, terminando cedo o bastante para que o
    maior horizonte já tenha acontecido. Hora 18h de Brasília (com fuso explícito,
    para o banco não interpretar no fuso do servidor): depois do boletim PTAX do dia."""
    utilizaveis = calendario[: len(calendario) - maior_h]
    escolhidas = utilizaveis[::-passo][:quantidade][::-1]
    return [d.to_pydatetime().replace(hour=hora, tzinfo=BRASILIA) for d in escolhidas]
