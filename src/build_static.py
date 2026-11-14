"""
NEXUS Intelligence - Gera a versão estática do dashboard (para o GitHub Pages).

Executa as mesmas consultas da API (sql/api/*.sql) e salva o resultado em
arquivos JSON, junto com a página. Assim o dashboard funciona online sem
precisar de servidor nem banco de dados.

Uso (depois do extract.py e do load.py):
    python src/build_static.py

Gera a pasta site/ pronta para publicar.
"""

import json
import os
import shutil
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import psycopg

RAIZ = Path(__file__).resolve().parent.parent
PASTA_SQL = RAIZ / "sql" / "api"
PASTA_WEB = RAIZ / "web"
PASTA_SITE = RAIZ / "site"
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/nexus_db")
CONSULTAS = ["resumo", "series", "copom", "qualidade"]


def serializar(valor):
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    raise TypeError(f"Tipo não suportado: {type(valor)}")


def montar_agenda() -> dict:
    """Calendários oficiais guardados no repositório (data/referencia): divulgações do IPCA
    (IBGE) e reuniões do Copom (Banco Central). A página escolhe os próximos eventos pela
    data de hoje, então a agenda continua certa entre uma atualização e outra."""
    ref = RAIZ / "data" / "referencia"
    ibge = json.loads((ref / "calendario_ibge_ipca.json").read_text(encoding="utf-8"))
    ipca = sorted(
        ({"mes_referencia": f"{i['ano_referencia_inicio']}-{i['mes_referencia_inicio']:02d}-01",
          "divulgacao": datetime.strptime(i["data_divulgacao"][:10], "%d/%m/%Y").date().isoformat()}
         for i in ibge["itens"]),
        key=lambda x: x["divulgacao"])
    copom = json.loads((ref / "calendario_copom.json").read_text(encoding="utf-8"))
    return {
        "ipca": [x for x in ipca if x["divulgacao"] >= "2026-01-01"],
        "copom": [{"inicio": a, "decisao": b} for a, b in copom["reunioes"]],
        "fontes": {"ipca": ibge["fonte"], "copom": copom["fonte"]},
        # o workflow atualizar-dashboard.yml roda em dias úteis às 22h UTC (19h em Brasília)
        "atualizacao": {"dias_uteis": True, "hora_brasilia": "19:00"},
    }


def main():
    if PASTA_SITE.exists():
        shutil.rmtree(PASTA_SITE)
    (PASTA_SITE / "api").mkdir(parents=True)

    with psycopg.connect(DATABASE_URL) as conn:
        consultas = list(CONSULTAS)
        # Previsões só existem depois que o Forecast roda neste banco
        if conn.execute("SELECT to_regclass('previsoes_publicadas') IS NOT NULL").fetchone()[0]:
            consultas += ["previsoes", "placar"]
        if conn.execute("SELECT to_regclass('cotacoes_moedas') IS NOT NULL").fetchone()[0]:
            consultas.append("moedas")
        for nome in consultas:
            sql = (PASTA_SQL / f"{nome}.sql").read_text(encoding="utf-8")
            linha = conn.execute(sql).fetchone()
            if linha is None:
                print(f"api/{nome}: sem dados, ignorado")
                continue
            resultado = linha[0]
            # Sem extensão, para a página usar o mesmo caminho da API local (api/resumo)
            destino = PASTA_SITE / "api" / nome
            destino.write_text(json.dumps(resultado, default=serializar, ensure_ascii=False), encoding="utf-8")
            print(f"api/{nome}: {destino.stat().st_size:,} bytes")

    agenda = montar_agenda()
    (PASTA_SITE / "api" / "agenda").write_text(json.dumps(agenda, ensure_ascii=False), encoding="utf-8")
    print(f"api/agenda: {len(agenda['ipca'])} divulgações do IPCA e {len(agenda['copom'])} reuniões do Copom")

    for pagina in PASTA_WEB.glob("*.html"):
        shutil.copy(pagina, PASTA_SITE / pagina.name)
    (PASTA_SITE / ".nojekyll").touch()  # o GitHub Pages serve os arquivos como estão
    print(f"Site gerado em {PASTA_SITE}")


if __name__ == "__main__":
    main()
