"""
NEXUS Forecast · Exporta o calendário de divulgações do IPCA (IBGE) para o repositório.

A API do IBGE não responde a servidores fora do Brasil, como os do GitHub Actions.
Rode este script num computador no Brasil (uma vez por ano, quando o IBGE publicar
o calendário do ano seguinte) e envie o arquivo gerado para o repositório:

    python src/exportar_calendario_ibge.py

Gera data/referencia/calendario_ibge_ipca.json com as divulgações já ocorridas e as
agendadas até o fim do ano que vem. Cada data agendada só passa a valer na coleta
depois que acontece.
"""

import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from coleta import ibge  # noqa: E402
from coleta.modelos import BRASILIA  # noqa: E402

DESTINO = Path(__file__).resolve().parent.parent / "data" / "referencia" / "calendario_ibge_ipca.json"


def main():
    agora = datetime.now(BRASILIA)
    print("Baixando o calendário do IBGE...")
    itens = ibge.baixar(date(2000, 1, 1), date(agora.year + 1, 12, 31))
    ja_ocorridas = ibge.interpretar(itens, agora)  # mesma validação de formato da coleta
    ipca = ibge.salvar_copia(itens, DESTINO, agora)
    ultima = ibge.ultima_data_agendada(ipca)
    meses = sorted(ja_ocorridas)
    print(f"Divulgações do IPCA no arquivo: {len(ipca)}")
    print(f"  já ocorridas: {len(meses)} (de {meses[0]:%m/%Y} a {meses[-1]:%m/%Y})" if meses else "  já ocorridas: 0")
    print(f"  agendada mais distante: {ultima:%d/%m/%Y}" if ultima else "")
    print(f"\nArquivo gerado: {DESTINO}")


if __name__ == "__main__":
    main()
