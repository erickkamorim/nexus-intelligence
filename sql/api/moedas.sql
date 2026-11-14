-- Faixa de moedas: última PTAX de fechamento de cada moeda e variação sobre o dia útil anterior
WITH ordenadas AS (
    SELECT moeda, data, venda,
           LAG(venda) OVER (PARTITION BY moeda ORDER BY data) AS anterior,
           ROW_NUMBER() OVER (PARTITION BY moeda ORDER BY data DESC) AS n
    FROM cotacoes_moedas
),
ultimas AS (
    SELECT * FROM ordenadas WHERE n = 1
)
SELECT json_build_object(
    'data', (SELECT MAX(data) FROM ultimas),
    'moedas', COALESCE(json_agg(json_build_object(
        'moeda', moeda,
        'data', data,
        'venda', venda,
        'anterior', anterior,
        'variacao_pct', CASE WHEN anterior > 0 THEN ROUND((venda / anterior - 1) * 100, 2) END
    ) ORDER BY array_position(ARRAY['USD','EUR','GBP','JPY','CHF','CAD','AUD']::bpchar[], moeda)), '[]'::json)
)
FROM ultimas;
