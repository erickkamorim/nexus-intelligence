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
| IPCA mensal | SGS 433 (BCB) | API de calendário de divulgações do IBGE (v3) | Calendário oficial do IBGE |
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

1. Rodar `python src/coletar_forecast.py --sondar` e conferir as amostras reais,
   principalmente o formato do calendário do IBGE e até que ano ele cobre.
2. Ajustar o leitor do calendário do IBGE ao formato real, se necessário.
3. Rodar a coleta completa e registrar a cobertura: quantos meses de IPCA têm data de
   divulgação comprovada.
