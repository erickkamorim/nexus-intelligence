import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import moedas  # noqa: E402


def test_moedas_usa_so_o_boletim_de_fechamento_um_por_dia():
    registros = [
        {"cotacaoCompra": 6.40, "cotacaoVenda": 6.41, "dataHoraCotacao": "2026-11-12 10:08:30.000", "tipoBoletim": "Abertura"},
        {"cotacaoCompra": 6.50, "cotacaoVenda": 6.51, "dataHoraCotacao": "2026-11-12 13:09:01.000", "tipoBoletim": "Fechamento"},
        {"cotacaoCompra": 6.55, "cotacaoVenda": 6.56, "dataHoraCotacao": "2026-11-13 13:05:00.000", "tipoBoletim": "Fechamento"},
        {"cotacaoCompra": 6.57, "cotacaoVenda": 6.58, "dataHoraCotacao": "2026-11-13 13:20:00.000", "tipoBoletim": "Fechamento"},
        {"cotacaoCompra": None, "cotacaoVenda": None, "dataHoraCotacao": "2026-11-14 13:00:00.000", "tipoBoletim": "Fechamento"},
    ]
    linhas = moedas.interpretar("EUR", registros)
    assert [l[1] for l in linhas] == [date(2026, 11, 12), date(2026, 11, 13)]
    assert linhas[0][3] == 6.51
    assert linhas[1][3] == 6.58  # boletim republicado no mesmo dia: vale o mais recente
