-- KPIs do topo do dashboard: último valor de cada indicador e comparações
WITH ultimo AS (
    SELECT DISTINCT ON (indicador) indicador, data_referencia, valor
    FROM indicadores
    ORDER BY indicador, data_referencia DESC
),
ha_30_dias AS (
    -- último valor disponível até 30 dias antes da data mais recente
    SELECT u.indicador,
           (SELECT i.valor
              FROM indicadores i
             WHERE i.indicador = u.indicador
               AND i.data_referencia <= u.data_referencia - 30
             ORDER BY i.data_referencia DESC
             LIMIT 1) AS valor
    FROM ultimo u
),
ipca AS (
    SELECT data_referencia,
           valor AS mensal,
           CASE WHEN COUNT(*) OVER w = 12
                THEN (EXP(SUM(LN(1 + valor / 100)) OVER w) - 1) * 100 END AS acum_12m
    FROM indicadores
    WHERE indicador = 'ipca_mensal'
    WINDOW w AS (ORDER BY data_referencia ROWS BETWEEN 11 PRECEDING AND CURRENT ROW)
),
ipca_ult AS (
    SELECT data_referencia, mensal, acum_12m,
           LAG(acum_12m) OVER (ORDER BY data_referencia) AS acum_12m_anterior
    FROM ipca
    ORDER BY data_referencia DESC
    LIMIT 1
),
copom AS (
    SELECT data_referencia, valor, valor - anterior AS variacao
    FROM (
        SELECT data_referencia, valor,
               LAG(valor) OVER (ORDER BY data_referencia) AS anterior
        FROM indicadores
        WHERE indicador = 'selic_meta'
    ) t
    WHERE valor <> anterior
    ORDER BY data_referencia DESC
    LIMIT 1
),
execucao AS (
    SELECT status, iniciado_em, finalizado_em, registros_inseridos, registros_atualizados, mensagem
    FROM execucoes
    ORDER BY iniciado_em DESC
    LIMIT 1
)
SELECT json_build_object(
    'selic', (SELECT json_build_object(
                'valor', ROUND(u.valor, 2), 'data', u.data_referencia,
                'valor_30d', ROUND(h.valor, 2))
              FROM ultimo u JOIN ha_30_dias h USING (indicador)
              WHERE indicador = 'selic_meta'),
    'dolar', (SELECT json_build_object(
                'valor', ROUND(u.valor, 4), 'data', u.data_referencia,
                'valor_30d', ROUND(h.valor, 4))
              FROM ultimo u JOIN ha_30_dias h USING (indicador)
              WHERE indicador = 'dolar_venda'),
    'ipca', (SELECT json_build_object(
                'mensal', ROUND(mensal, 2), 'data', data_referencia,
                'acum_12m', ROUND(acum_12m::numeric, 2),
                'acum_12m_anterior', ROUND(acum_12m_anterior::numeric, 2))
             FROM ipca_ult),
    'juro_real', (SELECT ROUND((((1 + u.valor / 100) / (1 + i.acum_12m / 100) - 1) * 100)::numeric, 2)
                  FROM ultimo u, ipca_ult i
                  WHERE u.indicador = 'selic_meta'),
    'copom', (SELECT json_build_object('data', data_referencia, 'valor', ROUND(valor, 2),
                                       'variacao', ROUND(variacao, 2))
              FROM copom),
    'execucao', (SELECT row_to_json(execucao) FROM execucao)
);
