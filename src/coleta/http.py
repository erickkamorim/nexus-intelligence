"""Acesso HTTP com novas tentativas e identificação do cliente."""

import logging
import time
from urllib.parse import quote, urlencode

import requests

CABECALHOS = {
    "User-Agent": "NEXUS-Intelligence/1.0 (+https://github.com/erickkamorim/nexus-intelligence)",
    "Accept": "application/json",
}

SEGUROS = "$,'=()@"

log = logging.getLogger("nexus.coleta")


def montar_url(base: str, params: dict) -> str:
    """Monta a URL com espaços como %20 (o OData do BCB não aceita '+')."""
    if not params:
        return base
    return base + "?" + urlencode(params, quote_via=quote, safe=SEGUROS)


def obter_json(url: str, tentativas: int = 3, pausa: float = 2.0, timeout: int = 60):
    for tentativa in range(1, tentativas + 1):
        try:
            resp = requests.get(url, headers=CABECALHOS, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as erro:
            log.warning("Tentativa %s/%s falhou: %s (%s)", tentativa, tentativas, erro, url[:120])
            if tentativa == tentativas:
                raise
            time.sleep(pausa * tentativa)
