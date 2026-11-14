"""
NEXUS Intelligence - API de dados + dashboard web.

Uso (na raiz do projeto, com o ambiente ativado):
    python src/api.py

Depois abra http://localhost:8000 no navegador.
Documentação automática da API: http://localhost:8000/docs

As consultas ficam em sql/api/*.sql e já devolvem JSON pronto do PostgreSQL.
"""

import os
import webbrowser
from pathlib import Path

import psycopg
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

RAIZ = Path(__file__).resolve().parent.parent
PASTA_SQL = RAIZ / "sql" / "api"
PASTA_WEB = RAIZ / "web"
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/nexus_db")

app = FastAPI(
    title="NEXUS Intelligence API",
    description="Indicadores econômicos oficiais do Banco Central do Brasil (SGS).",
    version="0.1.0",
)


def consultar(nome: str):
    """Executa sql/api/<nome>.sql e devolve o JSON gerado pelo PostgreSQL."""
    sql = (PASTA_SQL / f"{nome}.sql").read_text(encoding="utf-8")
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=5) as conn:
            linha = conn.execute(sql).fetchone()
            return None if linha is None else linha[0]
    except psycopg.OperationalError as erro:
        raise HTTPException(status_code=503, detail=f"Banco de dados indisponível: {erro}") from erro


@app.get("/api/resumo", summary="KPIs atuais: Selic, IPCA 12m, dólar, juro real e última carga")
def resumo():
    return consultar("resumo")


@app.get("/api/series", summary="Séries históricas para os gráficos")
def series():
    return consultar("series")


@app.get("/api/copom", summary="Mudanças da Selic meta (decisões do Copom)")
def copom():
    return consultar("copom")


@app.get("/api/qualidade", summary="Cobertura dos dados e histórico de cargas")
def qualidade():
    return consultar("qualidade")


@app.get("/api/previsoes", summary="Previsões publicadas: IPCA (SARIMA calibrado e Focus) e câmbio")
def previsoes():
    try:
        conteudo = consultar("previsoes")
    except HTTPException:
        raise
    except Exception as erro:  # tabela ainda não existe neste banco
        raise HTTPException(status_code=404, detail=f"Previsões indisponíveis: {erro}") from erro
    if conteudo is None:
        raise HTTPException(status_code=404, detail="Nenhuma previsão publicada ainda (rode src/prever_atual.py)")
    return conteudo


# O dashboard (web/index.html) é servido na raiz do site
app.mount("/", StaticFiles(directory=PASTA_WEB, html=True), name="web")


if __name__ == "__main__":
    endereco = "http://localhost:8000"
    print(f"NEXUS Intelligence rodando em {endereco}  (Ctrl+C para parar)")
    webbrowser.open(endereco)
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
