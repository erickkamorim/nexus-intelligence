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


def executar(fonte, cfg: ConfigSerie, modelos: list[Modelo], origens: list[datetime],
             usar_focus: bool = False) -> pd.DataFrame:
    realizado = fonte.atual(cfg.serie)
    calendario = realizado.index
    linhas = []
    for origem in origens:
        hist = fonte.conhecida_em(cfg.serie, origem)
        tardios = hist.conhecido_desde[hist.conhecido_desde > origem]
        if len(tardios):
            raise VazamentoDeDados(f"{cfg.serie}: {len(tardios)} valor(es) conhecidos depois da origem {origem}")
        y = hist.valores
        if len(y) < cfg.minimo_historico:
            continue
        ultimo = y.index[-1]
        focus = fonte.focus_em(origem) if usar_focus else None

        for h in cfg.horizontes:
            alvo = _alvo(ultimo, h, cfg, calendario)
            if alvo is None or alvo not in realizado.index:
                continue
            base = {"serie": cfg.serie, "origem": origem, "ultimo_conhecido": ultimo,
                    "h": h, "alvo": alvo, "realizado": float(realizado[alvo])}
            for modelo in modelos:
                p = prever_com_intervalo(modelo, y, h, cfg.n_erros_intervalo)
                if p is not None:
                    linhas.append({**base, "modelo": modelo.nome, **p})
            if focus is not None and alvo in focus.index:
                linhas.append({**base, "modelo": "focus_mediana", "previsto": float(focus[alvo]),
                               "n_erros_intervalo": 0})
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
