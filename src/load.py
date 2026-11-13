"""
NEXUS Intelligence - Carga do CSV no PostgreSQL.

Uso (na raiz do projeto, depois do extract.py):
    python src/load.py

Conexão: variável de ambiente DATABASE_URL, por exemplo
    postgresql://postgres:SUA_SENHA@localhost:5432/nexus_db

Insere registros novos e atualiza os que mudaram (INSERT ... ON CONFLICT),
então pode rodar quantas vezes quiser sem duplicar dados.
Cada execução fica registrada na tabela `execucoes`.
"""

import os
import sys
from pathlib import Path

import pandas as pd
import psycopg

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO = RAIZ / "data" / "indicadores.csv"
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/nexus_db")

UPSERT = """
INSERT INTO indicadores (indicador, codigo_sgs, data_referencia, valor)
VALUES (%s, %s, %s, %s)
ON CONFLICT (indicador, data_referencia) DO UPDATE
    SET valor = EXCLUDED.valor,
        atualizado_em = NOW()
    WHERE indicadores.valor IS DISTINCT FROM EXCLUDED.valor
RETURNING (xmax = 0) AS inserido
"""


def main():
    if not ARQUIVO.exists():
        print(f"Arquivo não encontrado: {ARQUIVO}. Rode antes: python src/extract.py")
        sys.exit(1)

    df = pd.read_csv(ARQUIVO, parse_dates=["data_referencia"])
    linhas = [
        (r.indicador, int(r.codigo_sgs), r.data_referencia.date(), float(r.valor))
        for r in df.itertuples(index=False)
    ]

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO execucoes (registros_lidos) VALUES (%s) RETURNING id", (len(linhas),))
            execucao_id = cur.fetchone()[0]
        conn.commit()

        try:
            inseridos = atualizados = 0
            with conn.cursor() as cur:
                for linha in linhas:
                    cur.execute(UPSERT, linha)
                    resultado = cur.fetchone()  # None = já existia com o mesmo valor
                    if resultado is not None:
                        if resultado[0]:
                            inseridos += 1
                        else:
                            atualizados += 1
                cur.execute(
                    """UPDATE execucoes
                       SET finalizado_em = NOW(), status = 'sucesso',
                           registros_inseridos = %s, registros_atualizados = %s
                       WHERE id = %s""",
                    (inseridos, atualizados, execucao_id),
                )
            conn.commit()
            print(f"Carga concluída: {len(linhas)} lidos, {inseridos} novos, {atualizados} atualizados.")
        except Exception as erro:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE execucoes SET finalizado_em = NOW(), status = 'falha', mensagem = %s WHERE id = %s",
                    (str(erro), execucao_id),
                )
            conn.commit()
            print(f"Falha na carga: {erro}")
            sys.exit(1)


if __name__ == "__main__":
    main()
