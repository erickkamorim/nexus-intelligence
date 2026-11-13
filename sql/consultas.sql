-- NEXUS Intelligence - consultas de análise

-- 1. Cobertura: quantos registros e qual período de cada indicador
SELECT indicador,
       COUNT(*)             AS total_registros,
       MIN(data_referencia) AS primeira_data,
       MAX(data_referencia) AS ultima_data
FROM indicadores
GROUP BY indicador
ORDER BY indicador;

-- 2. Último valor de cada indicador (base para os KPIs do dashboard)
SELECT DISTINCT ON (indicador)
       indicador, data_referencia, valor
FROM indicadores
ORDER BY indicador, data_referencia DESC;

-- 3. IPCA acumulado em 12 meses (juros compostos das variações mensais)
SELECT data_referencia,
       valor AS ipca_mes,
       ROUND(((EXP(SUM(LN(1 + valor / 100)) OVER janela) - 1) * 100)::numeric, 2) AS ipca_12m
FROM indicadores
WHERE indicador = 'ipca_mensal'
WINDOW janela AS (ORDER BY data_referencia ROWS BETWEEN 11 PRECEDING AND CURRENT ROW)
ORDER BY data_referencia DESC;

-- 4. Dólar: média, mínimo e máximo por mês
SELECT DATE_TRUNC('month', data_referencia)::date AS mes,
       ROUND(AVG(valor), 4) AS media,
       MIN(valor) AS minimo,
       MAX(valor) AS maximo
FROM indicadores
WHERE indicador = 'dolar_venda'
GROUP BY 1
ORDER BY 1 DESC;

-- 5. Mudanças na Selic meta (quando o Copom alterou a taxa)
SELECT data_referencia, valor AS selic, valor_anterior,
       valor - valor_anterior AS variacao_pp
FROM (
    SELECT data_referencia, valor,
           LAG(valor) OVER (ORDER BY data_referencia) AS valor_anterior
    FROM indicadores
    WHERE indicador = 'selic_meta'
) t
WHERE valor <> valor_anterior
ORDER BY data_referencia DESC;

-- 6. Juro real aproximado: Selic meta vs IPCA 12 meses (mês a mês)
WITH ipca AS (
    SELECT DATE_TRUNC('month', data_referencia)::date AS mes,
           (EXP(SUM(LN(1 + valor / 100)) OVER (ORDER BY data_referencia
                ROWS BETWEEN 11 PRECEDING AND CURRENT ROW)) - 1) * 100 AS ipca_12m
    FROM indicadores WHERE indicador = 'ipca_mensal'
),
selic AS (
    SELECT DISTINCT ON (DATE_TRUNC('month', data_referencia))
           DATE_TRUNC('month', data_referencia)::date AS mes, valor AS selic
    FROM indicadores WHERE indicador = 'selic_meta'
    ORDER BY DATE_TRUNC('month', data_referencia), data_referencia DESC
)
SELECT s.mes, s.selic, ROUND(i.ipca_12m::numeric, 2) AS ipca_12m,
       ROUND((((1 + s.selic / 100) / (1 + i.ipca_12m / 100) - 1) * 100)::numeric, 2) AS juro_real
FROM selic s JOIN ipca i USING (mes)
ORDER BY s.mes DESC;

-- 7. Auditoria: últimas execuções da carga
SELECT id, iniciado_em, finalizado_em, status,
       registros_lidos, registros_inseridos, registros_atualizados, mensagem
FROM execucoes
ORDER BY iniciado_em DESC
LIMIT 10;
