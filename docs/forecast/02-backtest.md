# NEXUS Forecast · Fase 2 · Backtest, referências e métricas

## Modelos de referência

| Série | Modelo | Previsão de y[t+h] com dados até t |
|---|---|---|
| IPCA | `ingenuo` (**referência**) | Última variação mensal conhecida |
| IPCA | `sazonal_ingenuo` | Mesmo mês do ano anterior |
| IPCA | `media_sazonal_5a` | Média do mesmo mês nos últimos 5 anos (sem média parcial) |
| IPCA | `focus_mediana` | Mediana do Focus publicada até a origem, para o mesmo mês-alvo |
| Câmbio | `passeio_aleatorio` (**referência obrigatória**) | Última cotação conhecida |
| Câmbio | `passeio_aleatorio_tendencia` | Última cotação × tendência média de 250 dias úteis |

Cada modelo é uma única função `previsao(y, h)` construída só com deslocamentos para trás,
o que garante por construção que f[t] não usa dados posteriores a t. Um teste altera todos
os valores futuros e confere que as previsões passadas não mudam.

## Intervalos

Intervalos empíricos: quantis dos últimos erros de h passos que o próprio modelo cometeu
dentro do histórico de treino (60 erros no IPCA, 500 no câmbio). Não supõem normalidade.
Com menos de 20 erros disponíveis, o intervalo não é informado. No câmbio, os erros são
calculados em log e convertidos de volta para R$.

## Origens e alvos

- **IPCA:** uma origem um minuto após cada divulgação com data exata no calendário do IBGE
  (a partir de 11/01/2017). O horizonte h é contado a partir do último mês conhecido.
- **Câmbio:** 250 origens, uma a cada 5 dias úteis, às 18h de Brasília (depois do boletim
  PTAX), terminando cedo o bastante para que o maior horizonte (21 dias úteis) já tenha
  acontecido.
- **Valor realizado:** a versão atual da série. As versões conhecidas na origem são usadas
  só para treinar.

## Defesa contra vazamento

1. A Fonte só devolve valores com `conhecido_desde <= origem` (função SQL da Fase 1).
2. O motor confere isso de novo a cada origem e interrompe com `VazamentoDeDados` se
   receber qualquer valor do futuro.
3. O banco recusa uma previsão cujo último dado conhecido seja posterior à data da origem
   (`ck_ultimo_antes_da_origem`).

## Métricas

Por modelo e horizonte, sempre nas origens comuns ao modelo e à referência: MAE, RMSE,
RMSE relativo (RMSE do modelo ÷ RMSE da referência; abaixo de 1, o modelo errou menos),
cobertura dos intervalos de 80% e 95% e o teste de Diebold-Mariano.

## Diebold-Mariano com sobreposição

Quando o horizonte é maior que o espaçamento entre origens, previsões vizinhas compartilham
choques e os erros ficam autocorrelacionados. A implementação usa:

- defasagens q = ceil(h / passo) − 1, em que passo é o espaçamento entre origens
  (IPCA: passo 1 mês; câmbio: passo 5 dias úteis, então h = 21 dá q = 4);
- variância de longo prazo com núcleo retangular, trocando para Bartlett (Newey-West)
  se a variância sair não positiva;
- correção de Harvey, Leybourne e Newbold (1997) e valor-p pela t com T−1 graus de liberdade.

**Evidência por simulação** (H0 verdadeira, erros sobrepostos com h = 6, 2.000 repetições,
nível nominal de 5%):

| Tamanho da amostra | Com a correção | Ignorando a sobreposição |
|---|---|---|
| T = 60 | 7,8% | 34,2% |
| T = 120 | 5,6% | 34,8% |

Ignorar a sobreposição faria o teste "encontrar" diferenças inexistentes em cerca de um
terço das vezes. Com a correção, a taxa fica próxima de 5% e converge conforme T cresce.
Esse comportamento é verificado em `tests/test_forecast.py`.

## Veredito exibido

| Condição (5%) | Veredito |
|---|---|
| p unilateral (modelo melhor) < 0,05 | melhor que a referência |
| p bilateral < 0,05 e modelo pior | pior que a referência |
| caso contrário | sem diferença significativa |
| menos de 10 origens comuns | amostra insuficiente |

## Reprodutibilidade

Cada execução grava em `backtest_execucoes` os parâmetros (JSON) e a versão do código
(hash do Git); `backtest_previsoes` guarda cada previsão com origem, alvo, intervalo e valor
realizado; `backtest_metricas` guarda a tabela de resultados.
