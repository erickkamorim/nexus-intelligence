"""Acesso aos dados "como eram conhecidos" em cada momento.

O backtest só conversa com uma Fonte. Há duas implementações com a mesma regra:
  * FonteBanco: chama as funções SQL serie_conhecida_em / focus_conhecido_em
    (a única porta de entrada definida na Fase 1);
  * FonteMemoria: mesma regra em pandas, para testes sem banco.

Toda consulta devolve também `conhecido_desde`, para que o motor de backtest
possa conferir, a cada origem, que nada do futuro entrou (defesa em profundidade).
"""

from dataclasses import dataclass
from datetime import datetime

import pandas as pd


@dataclass
class Historico:
    valores: pd.Series          # índice: data de referência (Timestamp), ordenado
    conhecido_desde: pd.Series  # mesmo índice: quando cada valor ficou conhecido


class FonteMemoria:
    """versoes: DataFrame com serie, data_referencia, valor, versao, conhecido_desde.
    focus: DataFrame com mes_alvo, mediana, data_estatistica, disponivel_em (opcional)."""

    def __init__(self, versoes: pd.DataFrame, focus: pd.DataFrame | None = None):
        self.versoes = versoes.assign(data_referencia=pd.to_datetime(versoes["data_referencia"]))
        self.focus = focus

    def conhecida_em(self, serie: str, momento: datetime) -> Historico:
        v = self.versoes
        v = v[(v["serie"] == serie) & v["conhecido_desde"].notna() & (v["conhecido_desde"] <= momento)]
        v = v.sort_values(["data_referencia", "versao"]).drop_duplicates("data_referencia", keep="last")
        v = v.set_index("data_referencia").sort_index()
        return Historico(v["valor"].astype(float), v["conhecido_desde"])

    def atual(self, serie: str) -> pd.Series:
        v = self.versoes[self.versoes["serie"] == serie]
        v = v.sort_values(["data_referencia", "versao"]).drop_duplicates("data_referencia", keep="last")
        return v.set_index("data_referencia")["valor"].astype(float).sort_index()

    def focus_em(self, momento: datetime) -> pd.Series:
        if self.focus is None:
            return pd.Series(dtype=float)
        f = self.focus[self.focus["disponivel_em"] <= momento]
        f = f.sort_values("data_estatistica").drop_duplicates("mes_alvo", keep="last")
        return pd.Series(f["mediana"].astype(float).values, index=pd.to_datetime(f["mes_alvo"])).sort_index()


class FonteBanco:
    """Lê do PostgreSQL. `reconectar` (opcional) abre uma conexão nova: num banco
    gerenciado que suspende por inatividade (Neon), uma pausa longa entre consultas
    derruba a conexão; nesse caso a consulta é refeita uma vez numa conexão nova."""

    def __init__(self, conn, reconectar=None):
        self.conn = conn
        self.reconectar = reconectar

    def _consultar(self, sql: str, parametros: tuple = ()) -> list:
        try:
            return self.conn.execute(sql, parametros).fetchall()
        except Exception as erro:
            if self.reconectar is None or type(erro).__name__ not in ("OperationalError", "InterfaceError"):
                raise
            self.conn = self.reconectar()
            return self.conn.execute(sql, parametros).fetchall()

    def conhecida_em(self, serie: str, momento: datetime) -> Historico:
        linhas = self._consultar(
            "SELECT data_referencia, valor, conhecido_desde FROM serie_conhecida_em(%s, %s) ORDER BY 1",
            (serie, momento))
        indice = pd.to_datetime([l[0] for l in linhas])
        return Historico(pd.Series([float(l[1]) for l in linhas], index=indice),
                         pd.Series([l[2] for l in linhas], index=indice))

    def atual(self, serie: str) -> pd.Series:
        linhas = self._consultar(
            "SELECT data_referencia, valor FROM serie_atual WHERE serie = %s ORDER BY 1", (serie,))
        return pd.Series([float(l[1]) for l in linhas], index=pd.to_datetime([l[0] for l in linhas]))

    def focus_em(self, momento: datetime) -> pd.Series:
        linhas = self._consultar(
            "SELECT mes_alvo, mediana FROM focus_conhecido_em(%s, 0::smallint) ORDER BY 1", (momento,))
        return pd.Series([float(l[1]) for l in linhas], index=pd.to_datetime([l[0] for l in linhas]))

    def divulgacoes_ipca(self) -> list[datetime]:
        return [l[0] for l in self._consultar(
            "SELECT divulgado_em FROM divulgacoes WHERE serie = 'ipca_mensal' ORDER BY 1")]
