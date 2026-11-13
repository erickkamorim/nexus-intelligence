-- Séries históricas para os gráficos (o filtro de período é feito na página)
WITH ipca AS (
    SELECT data_referencia,
           valor AS mensal,
           CASE WHEN COUNT(*) OVER w = 12
                THEN (EXP(SUM(LN(1 + valor / 100)) OVER w) - 1) * 100 END AS acum_12m
    FROM indicadores
    WHERE indicador = 'ipca_mensal'
    WINDOW w AS (ORDER BY data_referencia ROWS BETWEEN 11 PRECEDING AND CURRENT ROW)
),
selic_mes AS (
    -- Selic em vigor no último dia disponível de cada mês
    SELECT DISTINCT ON (DATE_TRUNC('month', data_referencia))
           DATE_TRUNC('month', data_referencia)::date AS mes, valor AS selic
    FROM indicadores
    WHERE indicador = 'selic_meta'
    ORDER BY DATE_TRUNC('month', data_referencia), data_referencia DESC
)
SELECT json_build_object(
    'selic', (SELECT json_agg(json_build_array(data_referencia, ROUND(valor, 2)) ORDER BY data_referencia)
              FROM indicadores WHERE indicador = 'selic_meta'),
    'dolar', (SELECT json_agg(json_build_array(data_referencia, ROUND(valor, 4)) ORDER BY data_referencia)
              FROM indicadores WHERE indicador = 'dolar_venda'),
    'ipca', (SELECT json_agg(json_build_array(data_referencia, ROUND(mensal, 2),
                                              ROUND(acum_12m::numeric, 2)) ORDER BY data_referencia)
             FROM ipca),
    'juro_real', (SELECT json_agg(json_build_array(
                         s.mes,
                         ROUND((((1 + s.selic / 100) / (1 + i.acum_12m / 100) - 1) * 100)::numeric, 2))
                         ORDER BY s.mes)
                  FROM selic_mes s
                  JOIN ipca i ON i.data_referencia = s.mes
                  WHERE i.acum_12m IS NOT NULL)
);
