"""
NEXUS Forecast · Fase 1 · Coleta com versões e datas de divulgação comprovadas.

Uso (na raiz do projeto, com DATABASE_URL configurada):
    python src/coletar_forecast.py --sondar   # só baixa amostras para conferir os formatos
    python src/coletar_forecast.py            # coleta, valida e grava

Ordem da coleta:
    1. PTAX (dólar)          -> também fornece o calendário de dias úteis do BCB
    2. Calendário do IBGE    -> datas de divulgação do IPCA
    3. IPCA (SGS 433)        -> com a data de divulgação do passo 2
    4. Focus (IPCA mensal)   -> disponível no dia útil seguinte ao fechamento semanal

Cada fonte é validada antes de gravar. Um problema grave impede a gravação
daquela fonte inteira e a execução termina com erro.
"""

import argparse
from collections import Counter
import json
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from coleta import focus, ibge, ptax, sgs  # noqa: E402
from coleta.http import obter_json  # noqa: E402
from coleta.modelos import BRASILIA  # noqa: E402
from coleta.validacao import consolidar_duplicadas, graves, validar_focus, validar_serie  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/nexus_db")
log = logging.getLogger("nexus.coleta")


def cobertura_calendario_ipca() -> dict:
    """Primeira e última divulgação do IPCA que o calendário do IBGE conhece."""
    agora = datetime.now(BRASILIA)
    divulgacoes = ibge.coletar(date(2000, 1, 1), date.today(), agora)
    meses = sorted(divulgacoes)
    return {"meses_com_data": len(meses),
            "primeiro_mes": f"{meses[0]:%m/%Y}" if meses else None,
            "ultimo_mes": f"{meses[-1]:%m/%Y}" if meses else None,
            "primeira_divulgacao": f"{divulgacoes[meses[0]]:%d/%m/%Y %H:%M}" if meses else None}


def sondar(pasta: Path) -> None:
    """Baixa uma amostra pequena de cada fonte e salva o JSON bruto."""
    pasta.mkdir(parents=True, exist_ok=True)
    hoje = date.today()
    amostras = {
        "ptax": lambda: obter_json(ptax.montar_url(ptax.URL, {
            "@dataInicial": "'01-02-2024'", "@dataFinalCotacao": "'01-10-2024'", "$format": "json"})),
        "ibge_calendario": lambda: obter_json(ibge.montar_url(ibge.URL, {
            "busca": "IPCA", "de": "01-01-2015", "ate": f"{hoje:%m-%d-%Y}", "tipo": 1, "qtd": 20, "page": 1})),
        "ibge_calendario_antigo": lambda: obter_json(ibge.montar_url(ibge.URL, {
            "busca": "IPCA", "de": "01-01-2004", "ate": "12-31-2006", "tipo": 1, "qtd": 20, "page": 1})),
        "ibge_cobertura_ipca": lambda: cobertura_calendario_ipca(),
        "sgs_433": lambda: obter_json(sgs.montar_url(sgs.URL.format(codigo=433), {
            "formato": "json", "dataInicial": "01/01/2024", "dataFinal": "31/03/2024"})),
        "focus": lambda: obter_json(focus.montar_url(focus.URL, {
            "$filter": "Indicador eq 'IPCA' and Data ge '2024-03-04' and Data le '2024-03-15'",
            "$top": 50, "$format": "json"})),
    }
    for nome, baixar in amostras.items():
        try:
            dados = baixar()
            (pasta / f"{nome}.json").write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"OK    {nome}")
        except Exception as erro:  # a sondagem registra e segue
            print(f"ERRO  {nome}: {erro}")
    print(f"\nAmostras salvas em {pasta}")


def relatar(nome: str, problemas: list) -> None:
    for p in problemas:
        (log.error if p.grave else log.warning)("%s | %s | %s | %s", nome, p.regra, p.chave, p.detalhe)
    if problemas:
        log.info("%s: %s problema(s), %s grave(s)", nome, len(problemas), len(graves(problemas)))


def coletar(args) -> int:
    import psycopg

    from coleta import armazenamento as arm

    hoje = date.today()
    falhas = []
    with psycopg.connect(DATABASE_URL) as conn:
        arm.preparar_esquema(conn)

        def etapa(fonte, executar):
            execucao = arm.iniciar_execucao(conn, fonte)
            try:
                lidos, novas, problemas = executar(execucao)
                status = "falha" if graves(problemas) else "sucesso"
                arm.finalizar_execucao(conn, execucao, status, lidos, novas, len(problemas),
                                       "Problemas graves na validação: nada foi gravado" if status == "falha" else None)
                if status == "falha":
                    falhas.append(fonte)
            except Exception as erro:
                conn.rollback()
                log.exception("%s falhou", fonte)
                arm.finalizar_execucao(conn, execucao, "falha", 0, None, 0, str(erro))
                falhas.append(fonte)

        # 1. PTAX
        cotacoes = []

        def etapa_ptax(execucao):
            cotacoes.extend(ptax.coletar(args.inicio_ptax, hoje))
            problemas = validar_serie(cotacoes, "diaria", (1.0, 15.0), hoje)
            relatar("ptax", problemas)
            novas = None if graves(problemas) else arm.gravar_serie(conn, execucao, consolidar_duplicadas(cotacoes))
            return len(cotacoes), novas, problemas
        etapa("ptax", etapa_ptax)
        calendario = ptax.dias_uteis(cotacoes)

        # 2. Calendário do IBGE
        divulgacoes = {}
        try:
            divulgacoes = ibge.coletar(args.inicio_ipca, hoje, datetime.now(BRASILIA))
            arm.gravar_divulgacoes(conn, divulgacoes)
        except Exception:
            log.exception("Calendário do IBGE indisponível: o IPCA ficará como 'nao_verificavel'")
            falhas.append("ibge_calendario")

        # 3. IPCA
        def etapa_ipca(execucao):
            obs = sgs.coletar_ipca(args.inicio_ipca, hoje, divulgacoes)
            problemas = validar_serie(obs, "mensal", (-3.0, 5.0), hoje)
            relatar("ipca", problemas)
            novas = None if graves(problemas) else arm.gravar_serie(conn, execucao, consolidar_duplicadas(obs))
            por_origem = Counter(o.origem_disponibilidade for o in obs)
            log.info("IPCA, origem da data de divulgação: %s", dict(por_origem))
            return len(obs), novas, problemas
        etapa("sgs_ipca", etapa_ipca)

        # 4. Focus
        def etapa_focus(execucao):
            if not calendario:
                raise RuntimeError("Sem calendário de dias úteis (PTAX): Focus não pode ser datado")
            regs = focus.coletar(args.inicio_focus, calendario, hoje)
            problemas = validar_focus(regs)
            relatar("focus", problemas)
            novas = None if graves(problemas) else arm.gravar_focus(conn, execucao, regs)
            return len(regs), novas, problemas
        etapa("focus", etapa_focus)

    if falhas:
        log.error("Fontes com falha: %s", ", ".join(falhas))
        return 1
    log.info("Coleta concluída sem falhas")
    return 0


def main():
    parser = argparse.ArgumentParser(description="NEXUS Forecast · coleta da Fase 1")
    parser.add_argument("--sondar", action="store_true", help="Só baixa amostras para conferir os formatos")
    parser.add_argument("--inicio-ipca", type=date.fromisoformat, default=date(2004, 1, 1))
    parser.add_argument("--inicio-ptax", type=date.fromisoformat, default=date(2016, 1, 1))
    parser.add_argument("--inicio-focus", type=date.fromisoformat, default=date(2010, 1, 1))
    args = parser.parse_args()

    (RAIZ / "logs").mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s",
                        handlers=[logging.FileHandler(RAIZ / "logs" / "coleta_forecast.log", encoding="utf-8"),
                                  logging.StreamHandler(sys.stdout)])
    if args.sondar:
        sondar(RAIZ / "data" / "amostras")
        return
    sys.exit(coletar(args))


if __name__ == "__main__":
    main()
