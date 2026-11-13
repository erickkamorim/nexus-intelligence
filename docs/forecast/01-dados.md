# NEXUS Forecast · Fase 1 · Dados, datas de divulgação e versões

Este documento registra as decisões sobre os dados que alimentam os modelos e as
limitações conhecidas. Ele é a base da página de Metodologia.

## Princípio

Um backtest só é honesto se cada previsão usar **apenas o que estava publicado na
data em que ela teria sido feita**. Para isso, cada valor guarda duas datas:

| Campo | Significado |
|---|---|
| `data_referencia` | Período a que o valor se refere (ex.: IPCA de março) |
| `conhecido_desde` | Momento a partir do qual o valor podia ser conhecido |

Os modelos nunca leem as tabelas diretamente: tudo passa pelas funções
`serie_conhecida_em(serie, momento)` e `focus_conhecido_em(momento)`.

## De onde vem cada data de divulgação

| Série | Fonte do valor | Fonte da data de divulgação | Tipo de prova |
|---|---|---|---|
| Dólar (PTAX venda) | API PTAX do BCB (Olinda) | Campo `dataHoraCotacao` de cada boletim | Registro da própria fonte |
| IPCA mensal | SGS 433 (BCB) | API de calendário de divulgações do IBGE (v3) | Calendário oficial do IBGE ou limite superior comprovado (ver abaixo) |
| Focus · IPCA mensal | API de Expectativas do BCB (Olinda) | Primeiro dia útil após o fechamento semanal | Regra oficial de divulgação do Relatório Focus |

Observações:

- **Dólar:** o Forecast usa a PTAX da API Olinda e não a série 1 do SGS, porque só a
  API Olinda informa o horário de publicação de cada cotação.
- **Dias úteis:** o calendário de dias úteis usado para datar o Focus é o conjunto de
  dias em que houve boletim PTAX, ou seja, os dias de funcionamento do próprio BCB.
- **Focus:** a API publica estatísticas diárias, mas só a do último dia útil de cada
  semana compõe o Relatório Focus. As demais ficam gravadas, mas não entram na
  comparação. Por convenção conservadora, o relatório é considerado disponível a
  partir das 09h do dia útil seguinte.
- **Sem prova, fora do backtest:** quando não há data de divulgação comprovada (por
  exemplo, um mês de IPCA que não aparece no calendário do IBGE), o valor é gravado com
  origem `nao_verificavel` e **não entra** em nenhum treino ou comparação histórica.
  A quantidade de meses nessa situação é registrada em cada execução.

## IPCA: calendário do IBGE e limite superior comprovado

O formato do calendário foi conferido com uma amostra real (13/11/2026):

- a API devolve todas as pesquisas do IBGE; o IPCA é identificado pelo `produto_id` 9256
  (o IPCA-15, 9260, e o INPC, 9258, ficam de fora);
- o mês de referência vem nos campos `ano_referencia_inicio` e `mes_referencia_inicio`;
- `data_divulgacao` vem sem fuso horário. É interpretada como horário de Brasília, a leitura
  mais tardia possível, portanto a mais conservadora;
- divulgações agendadas para o futuro não contam como prova;
- **o calendário não cobre o início do histórico** (a consulta de 2004 a 2006 voltou vazia).

Para os meses anteriores ao início do calendário, a data usada é um **limite superior
comprovado**: o IBGE publica o IPCA em ordem cronológica, então um mês antigo já estava
publicado quando saiu o primeiro mês posterior que consta no calendário. Essa data pode ser
mais tardia que a publicação real, mas nunca mais cedo, por isso não cria vazamento.

Consequência prática: nenhum backtest pode ter data de origem anterior à primeira divulgação
registrada no calendário. Depois dela, todo o histórico anterior fica disponível para treino.
Quando o calendário trouxer a data exata de um mês, ela substitui o limite superior
(o contrário nunca acontece).

| Origem | Significado |
|---|---|
| `ibge_calendario` | Data exata do calendário oficial |
| `ibge_limite_superior` | Data da primeira divulgação posterior registrada no calendário |
| `nao_verificavel` | Mês posterior a tudo o que o calendário registra: fora dos backtests |

## Versões (vintages)

As APIs usadas não guardam versões antigas: devolvem apenas o valor vigente hoje.
Por isso o NEXUS guarda as versões a partir do momento em que começou a coletar.

- `serie_versoes` é append-only para valores: uma revisão gera **uma nova linha**
  (`versao` 2, 3, …) e a versão anterior é preservada.
- A primeira carga de cada série é marcada como `carga_historica`. Ela representa o
  valor vigente no dia da coleta, **não necessariamente a primeira publicação**.
- As versões capturadas pelas execuções diárias são marcadas como `observada` e só
  valem para o backtest a partir do momento em que foram coletadas.
- A view `serie_revisoes` lista toda observação que já teve mais de uma versão.

### Limitação dos históricos anteriores ao início da coleta

Para o período anterior à primeira coleta, o NEXUS assume que o valor vigente é igual
ao valor publicado originalmente. Essa premissa:

- é **verificável daqui em diante**: se uma revisão acontecer, ela aparece em
  `serie_revisoes`;
- **não é verificável para o passado** com as fontes usadas, e por isso é declarada
  como limitação na Metodologia;
- tem impacto esperado pequeno para as séries escolhidas (índice de preços
  ao consumidor e cotação de câmbio publicada em boletim), mas isso deve ser
  confirmado na documentação de cada fonte antes de ser afirmado como fato.

## Validações antes de gravar

Problemas **graves** impedem a gravação da fonte inteira (não existe carga parcial):
valor ausente, data futura, duplicidade com valores diferentes, lacuna na série
mensal, cotação em fim de semana, divulgação anterior ao fim do período de referência,
origem incoerente com a data de divulgação, mediana do Focus fora do intervalo
[mínimo, máximo] e estatística do Focus que mudou de valor desde a última coleta.

**Avisos** são registrados no log, sem bloquear: valores fora da faixa plausível,
duplicidades idênticas e lacunas de até alguns dias no câmbio (feriados).

## Testes

- `tests/sql/test_versoes.sql`: versionamento, revisões e ausência de vazamento no banco.
- `tests/test_coleta.py`: janelas de consulta, paginação, datas de divulgação, regras do
  Focus e validações, com respostas das APIs simuladas.

## Pendências antes da integração

1. ~~Conferir as amostras reais das APIs~~ (feito em 13/11/2026: PTAX, SGS e Focus no formato
   esperado; leitor do IBGE refeito para o formato real).
2. Registrar a cobertura do calendário do IBGE: primeiro mês com data exata.
3. Rodar a coleta completa e registrar quantos meses de IPCA ficaram em cada origem.
