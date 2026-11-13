"""Estruturas de dados compartilhadas pelos coletores."""

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

BRASILIA = ZoneInfo("America/Sao_Paulo")

ORIGENS_SERIE = {"ptax_datahora_cotacao", "ibge_calendario", "nao_verificavel"}
ORIGENS_FOCUS = {"focus_relatorio_semanal", "nao_verificavel"}


@dataclass(frozen=True)
class Observacao:
    serie: str
    data_referencia: date
    valor: float | None
    disponivel_em: datetime | None
    origem_disponibilidade: str
    fonte: str


@dataclass(frozen=True)
class ExpectativaFocus:
    data_estatistica: date
    mes_alvo: date
    base_calculo: int
    mediana: float | None
    media: float | None
    desvio_padrao: float | None
    minimo: float | None
    maximo: float | None
    respondentes: int | None
    entra_no_relatorio: bool
    disponivel_em: datetime | None
    origem_disponibilidade: str
