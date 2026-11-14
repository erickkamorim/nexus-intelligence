-- Placar ao vivo: as previsões que o NEXUS publicou de verdade, comparadas com o
-- dado oficial que saiu depois (e, no IPCA, com o Focus do mesmo momento).
--
-- O backtest mede o passado simulado; o placar mede o que foi publicado com data,
-- sem possibilidade de ajuste depois. Fonte: previsoes_publicadas (um retrato
-- JSON por execução do src/prever_atual.py).
--
-- Regras:
--   * IPCA: para cada mês-alvo e horizonte, vale a ÚLTIMA previsão publicada
--     antes do IBGE divulgar o dado (a "palavra final" do modelo naquele horizonte).
--   * Dólar: para cada cotação-base e horizonte, a última previsão publicada com
--     aquela base. O realizado é a PTAX do h-ésimo dia com boletim depois da base
--     (conta dias com PTAX publicada, então feriados não atrapalham).
WITH snap AS (
    SELECT id, gerado_em, conteudo FROM previsoes_publicadas
),
-- ---------------------------------------------------------------- IPCA
ipca_prev AS (
    SELECT DISTINCT ON ((p->>'alvo')::date, (p->>'h')::int)
           (p->>'alvo')::date        AS alvo,
           (p->>'h')::int            AS h,
           s.gerado_em               AS publicado_em,
           (p->>'previsto')::numeric AS previsto,
           (p->>'li80')::numeric AS li80, (p->>'ls80')::numeric AS ls80,
           (p->>'li95')::numeric AS li95, (p->>'ls95')::numeric AS ls95,
           (p->>'focus')::numeric    AS focus
    FROM snap s
    CROSS JOIN LATERAL jsonb_array_elements(s.conteudo->'ipca'->'previsoes') p
    LEFT JOIN divulgacoes d ON d.serie = 'ipca_mensal' AND d.mes_referencia = (p->>'alvo')::date
    WHERE d.divulgado_em IS NULL OR s.gerado_em < d.divulgado_em   -- nada publicado depois do dado
    ORDER BY (p->>'alvo')::date, (p->>'h')::int, s.gerado_em DESC
),
ipca AS (
    SELECT p.*, a.valor AS realizado, d.divulgado_em
    FROM ipca_prev p
    LEFT JOIN serie_atual a ON a.serie = 'ipca_mensal' AND a.data_referencia = p.alvo
    LEFT JOIN divulgacoes d ON d.serie = 'ipca_mensal' AND d.mes_referencia = p.alvo
),
-- ---------------------------------------------------------------- Dólar
ptax AS (
    SELECT data_referencia AS dia, valor, ROW_NUMBER() OVER (ORDER BY data_referencia) AS n
    FROM serie_atual WHERE serie = 'ptax_venda'
),
cambio_prev AS (
    SELECT DISTINCT ON ((s.conteudo->'cambio'->>'ultimo_conhecido')::date, (p->>'h')::int)
           (s.conteudo->'cambio'->>'ultimo_conhecido')::date AS base,
           (p->>'h')::int            AS h,
           s.gerado_em               AS publicado_em,
           (p->>'previsto')::numeric AS previsto,
           (p->>'li80')::numeric AS li80, (p->>'ls80')::numeric AS ls80,
           (p->>'li95')::numeric AS li95, (p->>'ls95')::numeric AS ls95,
           (p->>'alvo_aproximado')::date AS alvo_aproximado
    FROM snap s
    CROSS JOIN LATERAL jsonb_array_elements(s.conteudo->'cambio'->'previsoes') p
    ORDER BY (s.conteudo->'cambio'->>'ultimo_conhecido')::date, (p->>'h')::int, s.gerado_em DESC
),
cambio AS (
    SELECT c.*, alvo.dia AS alvo, alvo.valor AS realizado
    FROM cambio_prev c
    LEFT JOIN ptax b    ON b.dia = c.base
    LEFT JOIN ptax alvo ON alvo.n = b.n + c.h
)
SELECT json_build_object(
    'primeira_publicacao', (SELECT MIN(gerado_em) FROM snap),
    'ultima_publicacao',   (SELECT MAX(gerado_em) FROM snap),
    'publicacoes',         (SELECT COUNT(*) FROM snap),
    'dias_publicados',     (SELECT COUNT(DISTINCT (gerado_em AT TIME ZONE 'America/Sao_Paulo')::date) FROM snap),
    'ipca', json_build_object(
        'avaliadas', COALESCE((SELECT json_agg(json_build_object(
                'alvo', alvo, 'h', h, 'publicado_em', publicado_em, 'divulgado_em', divulgado_em,
                'previsto', ROUND(previsto, 2), 'li80', ROUND(li80, 2), 'ls80', ROUND(ls80, 2),
                'li95', ROUND(li95, 2), 'ls95', ROUND(ls95, 2), 'focus', focus, 'realizado', realizado)
                ORDER BY alvo DESC, h) FROM ipca WHERE realizado IS NOT NULL), '[]'),
        'em_aberto', (SELECT COUNT(*) FROM ipca WHERE realizado IS NULL),
        'proximo_alvo', (SELECT MIN(alvo) FROM ipca WHERE realizado IS NULL)
    ),
    'cambio', json_build_object(
        'avaliadas', COALESCE((SELECT json_agg(json_build_object(
                'base', base, 'h', h, 'alvo', alvo, 'publicado_em', publicado_em,
                'previsto', ROUND(previsto, 4), 'li80', ROUND(li80, 4), 'ls80', ROUND(ls80, 4),
                'li95', ROUND(li95, 4), 'ls95', ROUND(ls95, 4), 'realizado', realizado)
                ORDER BY alvo DESC, h) FROM cambio WHERE realizado IS NOT NULL), '[]'),
        'em_aberto', (SELECT COUNT(*) FROM cambio WHERE realizado IS NULL),
        'proximo_alvo', (SELECT MIN(alvo_aproximado) FROM cambio WHERE realizado IS NULL)
    )
);
