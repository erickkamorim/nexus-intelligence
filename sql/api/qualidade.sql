-- Saúde dos dados: cobertura por indicador e últimas cargas
SELECT json_build_object(
    'cobertura', (
        SELECT json_agg(json_build_object(
                   'indicador', indicador,
                   'registros', total,
                   'primeira_data', primeira,
                   'ultima_data', ultima,
                   'dias_sem_atualizar', CURRENT_DATE - ultima
               ) ORDER BY indicador)
        FROM (
            SELECT indicador, COUNT(*) AS total,
                   MIN(data_referencia) AS primeira, MAX(data_referencia) AS ultima
            FROM indicadores
            GROUP BY indicador
        ) c
    ),
    'execucoes', (
        SELECT COALESCE(json_agg(e ORDER BY e.iniciado_em DESC), '[]'::json)
        FROM (
            SELECT id, iniciado_em, finalizado_em, status,
                   registros_lidos, registros_inseridos, registros_atualizados, mensagem
            FROM execucoes
            ORDER BY iniciado_em DESC
            LIMIT 8
        ) e
    )
);
