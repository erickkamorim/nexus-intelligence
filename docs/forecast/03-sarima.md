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

## Desempenho

A primeira execução real mostrou que a maior parte do tempo de cada ajuste ia para o cálculo
numérico da covariância dos parâmetros (erros-padrão), que não é usada aqui: os intervalos vêm
da simulação. Por isso:

- `cov_type="none"` no ajuste;
- os parâmetros da origem anterior são o ponto de partida da origem seguinte (mesma
  especificação), o que acelera a convergência; se esse ponto de partida falhar, o ajuste é
  refeito do zero;
- a seleção de ordem avalia as combinações em paralelo. Na primeira tentativa, um processo por
  núcleo esgotou a memória do computador (cada processo carrega statsmodels e pandas); o padrão
  passou a ser 2 processos, reaproveitados entre as seleções, ajustável por `NEXUS_PROCESSOS`.

Nenhuma dessas mudanças altera o que o modelo enxerga em cada origem.

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

## Resultados (backtest de 14/11/2026)

**IPCA, comparação com o Boletim Focus (RMSE relativo; > 1 = erro maior que o Focus):**

| h | SARIMA | Média sazonal 5 anos |
|---|---|---|
| 1 | 1,318 (pior, significativo) | 1,570 (pior) |
| 2 | 1,047 (sem diferença significativa) | 1,162 (pior) |
| 3 | 1,042 (sem diferença) | 1,113 (pior) |
| 4 | 1,033 (sem diferença) | 1,086 (sem diferença) |
| 5 | 1,021 (sem diferença) | 1,069 (sem diferença) |
| 6 | 0,995 (sem diferença) | 1,048 (sem diferença) |

A partir de 2 meses à frente, o SARIMA, que usa apenas o histórico do IPCA, não se distingue
estatisticamente do Boletim Focus. Não se afirma que o modelo supera o mercado: em h = 6 o erro
é 0,5% menor, sem significância.

**Ordens escolhidas** (10 seleções, nenhuma falha): SARIMA(1,0,0)(0,0,1)₁₂ de 2017 a 2019,
SARIMA(1,0,2)(1,0,1)₁₂ em 2020 e SARIMA(1,0,0)(1,0,1)₁₂ de 2021 a 2026. Estrutura estável:
persistência de curto prazo (AR 1) e padrão sazonal anual. Os valores de AIC não são comparáveis
entre anos, porque cada seleção usa uma amostra maior.

**Câmbio:** o ARIMA no log também não supera o passeio aleatório (RMSE relativo de 0,995 a
1,021, sem diferença significativa em nenhum horizonte).

**Cobertura dos intervalos (problema encontrado):**

| Modelo | Cobertura do intervalo de 80% | Cobertura do intervalo de 95% |
|---|---|---|
| SARIMA (IPCA) | — | 82% a 86% (estreito demais) |
| ARIMA (câmbio) | 89% a 91% (largo demais) | 97% a 98% (largo demais) |

No IPCA, o resultado confirma a limitação prevista (a simulação ignora a incerteza dos
parâmetros e as mudanças de regime). No câmbio aconteceu o contrário: o modelo estima uma
volatilidade constante com todo o histórico desde 2016, incluindo a turbulência de 2020, maior
que a volatilidade recente.

## Calibração conformal dos intervalos

Para que uma faixa chamada "95%" cubra de fato cerca de 95%, os intervalos são calibrados com
os erros do próprio backtest (`src/forecast/calibracao.py`, método CQR de Romano et al., 2019):

- escore de cada previsão passada: s = max(li − y, y − ls);
- na origem t, entram só as previsões cujo valor real **já estava publicado em t**;
- a faixa é deslocada pelo quantil conformal dos escores (alarga se o modelo errava para fora,
  estreita se sobrava folga);
- com menos de 24 escores disponíveis, não há intervalo calibrado naquela origem.

O resultado aparece como modelos `sarima_calibrado` e `arima_log_calibrado`, com a cobertura
medida fora da amostra. Os testes (`tests/test_calibracao.py`) verificam que a calibração corrige
intervalos estreitos e largos e que alterar valores ainda não publicados não muda o intervalo.

## Resultados após a calibração (backtest de 14/11/2026)

**IPCA, comparação com a média sazonal de 5 anos** (melhor modelo simples; RMSE relativo < 1 = erro menor):

| h | SARIMA | Focus | Cobertura SARIMA 80% / 95% | Cobertura calibrada 80% / 95% |
|---|---|---|---|---|
| 1 | 0,840 (melhor, significativo) | 0,637 (melhor) | 63% / 82% | 83% / 97% |
| 2 | 0,901 (melhor, significativo) | 0,860 (melhor) | 69% / 87% | 84% / 98% |
| 3 | 0,936 (sem diferença) | 0,899 (melhor) | 68% / 84% | 82% / 96% |
| 4 | 0,952 (sem diferença) | 0,921 (melhor) | 70% / 86% | 83% / 97% |
| 5 | 0,956 (sem diferença) | 0,936 (sem diferença) | 72% / 84% | 85% / 95% |
| 6 | 0,950 (sem diferença) | 0,954 (sem diferença) | 69% / 85% | 85% / 96% |

- O SARIMA supera de forma significativa o melhor modelo simples em 1 e 2 meses.
- A calibração conformal levou a cobertura do IPCA para perto do nominal (82% a 85% para 80%;
  95% a 98% para 95%), com leve excesso de cautela.

**Câmbio:** a calibração não corrigiu o excesso de largura do ARIMA (cobertura de 95% foi de
96%-98% para 97%-99%). Causas: poucos escores no início do backtest (com n = 24, o quantil de 95%
é praticamente o maior escore observado) e volatilidade que muda ao longo do tempo. Uma
calibração adaptativa com janela móvel é o caminho natural, mas não é necessária para o produto.

## Decisão para o dashboard

| Série | O que é exibido | Por quê |
|---|---|---|
| IPCA | SARIMA com intervalos calibrados, ao lado da mediana do Focus | Empata com o mercado a partir de 2 meses, supera o melhor modelo simples em 1 e 2 meses e tem intervalos calibrados |
| Câmbio | Passeio aleatório com intervalos empíricos | Nenhum modelo o superou; seus intervalos já estavam calibrados (82% / 96%) |
