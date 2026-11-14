"""Previsões de HOJE, com a mesma metodologia validada no backtest.

  * IPCA: SARIMA (ordem escolhida por AIC com todos os dados conhecidos agora),
    intervalos por simulação e calibrados com TODOS os erros do backtest
    (todos já têm valor realizado); acumulado em 12 meses por caminhos;
    mediana do Focus para os mesmos meses-alvo.
  * Câmbio: passeio aleatório com intervalos empíricos (a referência que nenhum
    modelo superou no backtest).
  * Mensagens de veredito geradas a partir das métricas do último backtest,
    para que o texto do dashboard nunca diga mais do que os testes mostraram.
"""

from datetime import datetime

import numpy as np
import pandas as pd

from .acumulado import acumulado_12m, acumulado_12m_caminhos
from .calibracao import ajuste_atual, aplicar_ajuste
from .modelos import MODELOS_CAMBIO, prever_com_intervalo
from .sarima import ModeloSarima, grade_ipca

HORIZONTES_IPCA = [1, 2, 3, 4, 5, 6]
HORIZONTES_CAMBIO = [1, 5, 10, 21]


def _r(v, casas=4):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), casas)


def _calibrar(previsto, li, ls, passado: pd.DataFrame, nivel: int):
    q, n = ajuste_atual(passado, nivel) if passado is not None and len(passado) else (None, 0)
    if q is None:
        return None, None, n
    novo_li, novo_ls = aplicar_ajuste(previsto, li, ls, q)
    return novo_li, novo_ls, n


def previsao_ipca(fonte, agora: datetime, backtest: pd.DataFrame | None, backend=None) -> dict:
    hist = fonte.conhecida_em("ipca_mensal", agora)
    y = hist.valores
    ultimo = y.index[-1]
    modelo = ModeloSarima("sarima", grade_ipca(), "nivel", reselecionar_a_cada=1, backend=backend, minimo=72)
    r = modelo.prever_varios(y, HORIZONTES_IPCA, agora)
    if r is None:
        raise RuntimeError("SARIMA não pôde ser ajustado com os dados atuais")
    focus = fonte.focus_em(agora)
    bt = backtest[backtest["modelo"] == "sarima"] if backtest is not None and len(backtest) else None

    def passado(medida, h):
        return None if bt is None else bt[(bt["medida"] == medida) & (bt["h"] == h)]

    mensal, acumulado = [], []
    for h in HORIZONTES_IPCA:
        alvo = ultimo + pd.DateOffset(months=h)
        p = r["por_h"][h]
        item = {"h": h, "alvo": alvo.strftime("%Y-%m-%d"), "previsto": _r(p["previsto"]),
                "focus": _r(focus.get(alvo)) if alvo in focus.index else None}
        for nivel in (80, 95):
            li, ls, n = _calibrar(p["previsto"], p[f"li{nivel}"], p[f"ls{nivel}"], passado("variacao", h), nivel)
            item[f"li{nivel}"], item[f"ls{nivel}"] = _r(li), _r(ls)
            item["n_escores_calibracao"] = n
        mensal.append(item)

        caminhos = acumulado_12m_caminhos(y, r["caminhos"], h)
        pontual = acumulado_12m(y, [r["por_h"][k]["previsto"] for k in range(1, h + 1)], h)
        q = np.quantile(caminhos, [0.025, 0.10, 0.90, 0.975])
        brutos = {80: (min(q[1], pontual), max(q[2], pontual)), 95: (min(q[0], pontual), max(q[3], pontual))}
        meses_focus = [focus.get(ultimo + pd.DateOffset(months=k)) for k in range(1, h + 1)]
        item12 = {"h": h, "alvo": alvo.strftime("%Y-%m-%d"), "previsto": _r(pontual, 2),
                  "focus": _r(acumulado_12m(y, meses_focus, h), 2) if all(m is not None for m in meses_focus) else None}
        for nivel in (80, 95):
            li, ls, _ = _calibrar(pontual, *brutos[nivel], passado("acumulado_12m", h), nivel)
            item12[f"li{nivel}"], item12[f"ls{nivel}"] = _r(li, 2), _r(ls, 2)
        acumulado.append(item12)

    return {
        "ultimo_conhecido": ultimo.strftime("%Y-%m-%d"),
        "especificacao": str(modelo.especificacao),
        "historico": [[d.strftime("%Y-%m-%d"), _r(v)] for d, v in y.iloc[-36:].items()],
        "previsoes": mensal,
        "acumulado_12m": acumulado,
    }


def previsao_cambio(fonte, agora: datetime) -> dict:
    y = fonte.conhecida_em("ptax_venda", agora).valores
    ultimo = y.index[-1]
    passeio = MODELOS_CAMBIO[0]
    itens = []
    for h in HORIZONTES_CAMBIO:
        p = prever_com_intervalo(passeio, y, h, 500)
        itens.append({"h": h, "alvo_aproximado": (ultimo + pd.offsets.BDay(h)).strftime("%Y-%m-%d"),
                      "previsto": _r(p["previsto"]), "li80": _r(p["li80"]), "ls80": _r(p["ls80"]),
                      "li95": _r(p["li95"]), "ls95": _r(p["ls95"])})
    return {"ultimo_conhecido": ultimo.strftime("%Y-%m-%d"), "modelo": "passeio_aleatorio",
            "historico": [[d.strftime("%Y-%m-%d"), _r(v)] for d, v in y.iloc[-130:].items()],
            "previsoes": itens}


def _lista(numeros: list[int]) -> str:
    """[1] -> '1 mês'; [1, 2] -> '1 e 2 meses'; [1, 2, 3] -> '1, 2 e 3 meses'."""
    texto = str(numeros[0]) if len(numeros) == 1 else ", ".join(map(str, numeros[:-1])) + f" e {numeros[-1]}"
    return f"{texto} {'mês' if numeros == [1] else 'meses'}"


def tabela_desempenho(metricas: pd.DataFrame) -> dict:
    """Linhas por horizonte para o dashboard, a partir de backtest_metricas."""
    def linha(df, comparacao, modelo, h):
        x = df[(df["comparacao"] == comparacao) & (df["modelo"] == modelo) & (df["h"] == h)]
        return None if x.empty else x.iloc[0]

    saida = {"ipca": [], "cambio": []}
    ipca = metricas[metricas["serie"] == "ipca_mensal"]
    ipca = ipca[ipca["medida"] == "variacao"]
    for h in HORIZONTES_IPCA:
        vf, vm = linha(ipca, "focus_mediana", "sarima", h), linha(ipca, "media_sazonal_5a", "sarima", h)
        cal = linha(ipca, "focus_mediana", "sarima_calibrado", h)
        if vf is None:
            continue
        saida["ipca"].append({
            "h": h, "rmse_relativo_focus": _r(vf["rmse_relativo"], 3), "veredito_focus": vf["veredito"],
            "rmse_relativo_media": _r(vm["rmse_relativo"], 3) if vm is not None else None,
            "veredito_media": vm["veredito"] if vm is not None else None,
            "cobertura80": _r(cal["cobertura80"], 3) if cal is not None else None,
            "cobertura95": _r(cal["cobertura95"], 3) if cal is not None else None,
            "origens": int(vf["n"])})
    cambio = metricas[metricas["serie"] == "ptax_venda"]
    for h in HORIZONTES_CAMBIO:
        rw, ar = linha(cambio, "passeio_aleatorio", "passeio_aleatorio", h), linha(cambio, "passeio_aleatorio", "arima_log", h)
        if rw is None:
            continue
        saida["cambio"].append({
            "h": h, "rmse_rw": _r(rw["rmse"]), "cobertura80": _r(rw["cobertura80"], 3), "cobertura95": _r(rw["cobertura95"], 3),
            "rmse_relativo_arima": _r(ar["rmse_relativo"], 3) if ar is not None else None,
            "veredito_arima": ar["veredito"] if ar is not None else None, "origens": int(rw["n"])})
    return saida


def mensagens(desempenho: dict) -> dict:
    """Texto do veredito, derivado só dos testes (nunca mais forte que eles)."""
    ipca, cambio = desempenho["ipca"], desempenho["cambio"]
    msg = {}
    empate = [d["h"] for d in ipca if d["veredito_focus"] == "sem diferença significativa"]
    # menor h a partir do qual TODOS os horizontes seguintes empatam com o Focus
    a_partir = next((h for h in sorted(empate) if all(x["veredito_focus"] != "pior que a referência"
                                                       for x in ipca if x["h"] >= h)), None)
    melhor_media = [d["h"] for d in ipca if d["veredito_media"] == "melhor que a referência"]
    partes = []
    if a_partir is not None:
        partes.append(f"A partir de {a_partir} {'mês' if a_partir == 1 else 'meses'} à frente, o modelo não se distingue "
                      "estatisticamente do Boletim Focus.")
    pior = [d["h"] for d in ipca if d["veredito_focus"] == "pior que a referência"]
    if pior:
        partes.append(f"Em {_lista(pior)} à frente, o mercado erra menos.")
    if melhor_media:
        partes.append(f"Supera o melhor modelo simples (média sazonal) em {_lista(melhor_media)} à frente.")
    msg["ipca"] = " ".join(partes) or "Sem conclusões estatisticamente significativas no backtest."
    if cambio and not any(d["veredito_arima"] == "melhor que a referência" for d in cambio):
        msg["cambio"] = ("Nenhum modelo testado superou o passeio aleatório: a melhor previsão disponível para o dólar "
                         "é a cotação atual. A faixa mostra a incerteza esperada.")
    else:
        msg["cambio"] = "Um modelo superou o passeio aleatório em parte dos horizontes; veja a tabela."
    return msg
