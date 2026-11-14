"""Gravação no PostgreSQL. Toda a regra de versionamento fica no banco
(função registrar_versoes), aqui só há o transporte dos dados."""

from pathlib import Path

from .modelos import ExpectativaFocus, Observacao

ESQUEMA = Path(__file__).resolve().parents[2] / "sql" / "forecast_schema.sql"


def preparar_esquema(conn) -> None:
    conn.execute(ESQUEMA.read_text(encoding="utf-8"))
    conn.commit()


TRAVA_COLETA = 742_001  # chave do advisory lock: uma coleta por vez no banco


def travar_coleta(conn) -> None:
    """A atualização diária e a recalibração podem rodar ao mesmo tempo e as duas
    coletam. A trava (pg_advisory_lock) faz a segunda esperar a primeira terminar;
    ela é liberada sozinha quando a conexão fecha."""
    conn.execute("SELECT pg_advisory_lock(%s)", (TRAVA_COLETA,))
    conn.commit()


def iniciar_execucao(conn, fonte: str) -> int:
    execucao = conn.execute("INSERT INTO coleta_execucoes (fonte) VALUES (%s) RETURNING id", (fonte,)).fetchone()[0]
    conn.commit()
    return execucao


def finalizar_execucao(conn, execucao: int, status: str, lidos: int, novas: int | None,
                       problemas: int, mensagem: str | None = None) -> None:
    conn.execute("""UPDATE coleta_execucoes
                       SET finalizado_em = NOW(), status = %s, registros_lidos = %s,
                           versoes_novas = %s, problemas_validacao = %s, mensagem = %s
                     WHERE id = %s""", (status, lidos, novas, problemas, mensagem, execucao))
    conn.commit()


def gravar_serie(conn, execucao: int, obs: list[Observacao]) -> int:
    """Grava em uma transação: tudo ou nada. Devolve o número de versões novas."""
    serie = obs[0].serie
    with conn.transaction():
        primeira_carga = conn.execute(
            "SELECT NOT EXISTS (SELECT 1 FROM serie_versoes WHERE serie = %s)", (serie,)).fetchone()[0]
        with conn.cursor().copy(
                "COPY stg_serie (serie, data_referencia, valor, disponivel_em, origem_disponibilidade, fonte) FROM STDIN") as copia:
            for o in obs:
                copia.write_row((o.serie, o.data_referencia, o.valor, o.disponivel_em, o.origem_disponibilidade, o.fonte))
        return conn.execute("SELECT registrar_versoes(%s, %s)", (execucao, primeira_carga)).fetchone()[0]


def gravar_divulgacoes(conn, divulgacoes: dict, fonte: str = "ibge_calendario_v3") -> None:
    with conn.transaction():
        conn.cursor().executemany(
            """INSERT INTO divulgacoes (serie, mes_referencia, divulgado_em, fonte)
               VALUES ('ipca_mensal', %s, %s, %s)
               ON CONFLICT (serie, mes_referencia) DO NOTHING""",
            [(mes, quando, fonte) for mes, quando in divulgacoes.items()])


def gravar_focus(conn, execucao: int, regs: list[ExpectativaFocus]) -> int:
    """Estatísticas do Focus de uma data não mudam: chaves já gravadas são ignoradas.
    Se a fonte devolver outro valor para uma chave existente, a carga falha."""
    with conn.transaction():
        cur = conn.cursor()
        cur.execute("CREATE TEMP TABLE stg_focus (LIKE focus_ipca_mensal INCLUDING DEFAULTS) ON COMMIT DROP")
        with cur.copy("""COPY stg_focus (data_estatistica, mes_alvo, base_calculo, mediana, media, desvio_padrao,
                         minimo, maximo, respondentes, entra_no_relatorio, disponivel_em,
                         origem_disponibilidade, execucao_id) FROM STDIN""") as copia:
            for r in regs:
                copia.write_row((r.data_estatistica, r.mes_alvo, r.base_calculo, r.mediana, r.media, r.desvio_padrao,
                                 r.minimo, r.maximo, r.respondentes, r.entra_no_relatorio, r.disponivel_em,
                                 r.origem_disponibilidade, execucao))
        divergentes = cur.execute("""
            SELECT COUNT(*) FROM stg_focus s JOIN focus_ipca_mensal f USING (data_estatistica, mes_alvo, base_calculo)
             WHERE f.mediana <> s.mediana""").fetchone()[0]
        if divergentes:
            raise ValueError(f"{divergentes} estatística(s) do Focus mudaram de valor desde a última coleta")
        # O fechamento semanal só é conhecido depois que a semana termina: atualiza a marcação
        cur.execute("""
            UPDATE focus_ipca_mensal f
               SET entra_no_relatorio = s.entra_no_relatorio, disponivel_em = s.disponivel_em,
                   origem_disponibilidade = s.origem_disponibilidade
              FROM stg_focus s
             WHERE (f.data_estatistica, f.mes_alvo, f.base_calculo) = (s.data_estatistica, s.mes_alvo, s.base_calculo)
               AND f.origem_disponibilidade = 'nao_verificavel' AND s.origem_disponibilidade <> 'nao_verificavel'""")
        cur.execute("""
            INSERT INTO focus_ipca_mensal SELECT * FROM stg_focus
            ON CONFLICT (data_estatistica, mes_alvo, base_calculo) DO NOTHING""")
        return cur.rowcount
