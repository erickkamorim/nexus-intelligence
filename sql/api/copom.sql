-- Histórico de mudanças da Selic meta (decisões do Copom)
SELECT COALESCE(json_agg(json_build_object(
           'data', data_referencia,
           'selic', ROUND(valor, 2),
           'anterior', ROUND(anterior, 2),
           'variacao', ROUND(valor - anterior, 2)
       ) ORDER BY data_referencia DESC), '[]'::json)
FROM (
    SELECT data_referencia, valor,
           LAG(valor) OVER (ORDER BY data_referencia) AS anterior
    FROM indicadores
    WHERE indicador = 'selic_meta'
) t
WHERE valor <> anterior;
