# NEXUS Forecast · Fase 3 · SARIMA, ARIMA e intervalos por simulação

## Comparabilidade com a Fase 2

Mesmas origens, mesmos horizontes, mesmos valores realizados e mesmas métricas. O SARIMA
entra como mais um modelo no mesmo motor de backtest, com a mesma defesa contra vazamento.

## Especificação

| Série | Modelo | Grade de busca (AIC) | Seleção da ordem | Parâmetros |
|---|---|---|---|---|
| IPCA (variação mensal) | SARIMA(p,0,q)(P,0,Q)₁₂ com constante | p, q ∈ {0,1,2}; P, Q ∈ {0,1} — 36 combinações | A cada 12 origens (~1 ano) | Reestimados em toda origem |
| Câmbio (log da PTAX) | ARIMA(p,1,q) com ou sem deriva | p, q ∈ {0,1,2}; deriva sim/não — 18 combinações | A cada 52 origens (~1 ano) | Reestimados em toda origem |

- A seleção usa **apenas os dados conhecidos na origem** em que acontece. A ordem escolhida
  fica registrada em cada previsão (coluna `detalhe`) e no histórico de seleções da execução.
- Refazer a seleção em toda origem custaria mais de 4.000 ajustes no IPCA. A cadência anual
  imita um processo em produção (recalibração periódica) sem usar dados futuros.
- Com d = 1, a deriva do câmbio é especificada como tendência linear no nível (`trend='t'`),
  que equivale a uma constante na série diferenciada.
- Uma combinação que não converge é descartada. Se nenhuma convergir, a origem fica sem
  previsão desse modelo e a falha é contada (`falhas_sarima` nos parâmetros da execução).

## Intervalos por simulação

- 1.000 caminhos simulados a partir do último dado conhecido; quantis de 2,5%, 10%, 90% e
  97,5% formam os intervalos de 95% e 80%.
- **Câmbio:** o modelo trabalha em log. A previsão pontual é exp(média do log), isto é, a
  mediana em R$, e os quantis são convertidos com exp.
- **Limitação:** os caminhos refletem a incerteza dos choques futuros, mas não a incerteza
  na estimação dos parâmetros. Isso tende a produzir intervalos um pouco estreitos,
  e é exatamente o que a cobertura empírica mede.

## IPCA acumulado em 12 meses

Para o mês-alvo (último conhecido + h), o acumulado combina os 12 − h últimos meses
observados na origem com os h meses previstos, por juros compostos. No SARIMA, o acumulado
é calculado em **cada caminho simulado**, o que preserva a correlação entre os meses
previstos; os intervalos do acumulado vêm desses caminhos. Para os modelos sem caminhos
(referências e Focus), o acumulado é avaliado só na previsão pontual.

## Validação

- `tests/test_sarima.py` verifica, com um backend falso em numpy: que o modelo recebe só os
  dados de cada origem, a cadência de seleção, a tolerância a falhas, a ordem dos intervalos,
  a composição do acumulado (inclusive por caminhos) e a cobertura próxima do nominal quando
  o modelo é o correto.
- O ajuste real com statsmodels é validado rodando `python src/rodar_backtest.py`.
