-- =============================================================================
-- NEXUS Forecast · Fase 1 · Esquema de dados com versões (vintages)
--
-- Modelo bitemporal:
--   * data_referencia  -> a que período o valor se refere (tempo de validade)
--   * conhecido_desde  -> a partir de quando aquele valor podia ser conhecido
--                         (tempo de transação), usado pelos backtests
--
-- Regra de ouro: nenhuma consulta de treino ou comparação histórica lê
-- serie_versoes diretamente. Tudo passa por serie_conhecida_em(), que só devolve
-- o que estava publicado no momento informado.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Execuções da coleta (auditoria)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS coleta_execucoes (
    id             BIGSERIAL    PRIMARY KEY,
    iniciado_em    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    finalizado_em  TIMESTAMPTZ,
    fonte          VARCHAR(40)  NOT NULL,                 -- sgs, ptax, focus, ibge_calendario
    status         VARCHAR(20)  NOT NULL DEFAULT 'em_andamento'
                   CHECK (status IN ('em_andamento', 'sucesso', 'falha')),
    registros_lidos     INTEGER,
    versoes_novas       INTEGER,
    problemas_validacao INTEGER,
    mensagem       TEXT
);

-- -----------------------------------------------------------------------------
-- 2. Datas de divulgação verificáveis (calendário oficial do IBGE)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS divulgacoes (
    serie            VARCHAR(40)  NOT NULL,               -- ipca_mensal
    mes_referencia   DATE         NOT NULL CHECK (EXTRACT(DAY FROM mes_referencia) = 1),
    divulgado_em     TIMESTAMPTZ  NOT NULL,
    fonte            VARCHAR(60)  NOT NULL,               -- ibge_calendario_v3
    coletado_em      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (serie, mes_referencia)
);

-- -----------------------------------------------------------------------------
-- 3. Versões das observações: um valor gravado nunca é alterado nem apagado;
--    uma revisão vira uma nova linha. Só a data de divulgação pode ser
--    preenchida depois, quando a prova chega (ver registrar_versoes).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS serie_versoes (
    id                      BIGSERIAL     PRIMARY KEY,
    serie                   VARCHAR(40)   NOT NULL,       -- ipca_mensal, ptax_venda
    data_referencia         DATE          NOT NULL,
    valor                   NUMERIC(18,6) NOT NULL,
    versao                  SMALLINT      NOT NULL CHECK (versao >= 1),

    -- Quando a fonte publicou o valor (NULL quando não há comprovação)
    disponivel_em           TIMESTAMPTZ,
    origem_disponibilidade  VARCHAR(30)   NOT NULL CHECK (origem_disponibilidade IN (
                                'ptax_datahora_cotacao',   -- timestamp do boletim do BCB
                                'ibge_calendario',         -- calendário oficial do IBGE
                                'ibge_limite_superior',    -- divulgação de um mês posterior (publicação em ordem)
                                'nao_verificavel')),       -- sem prova: fica fora dos backtests

    -- Como o NEXUS obteve esta versão
    tipo_versao             VARCHAR(20)   NOT NULL CHECK (tipo_versao IN (
                                'carga_historica',          -- valor vigente quando a coleta começou
                                'observada')),              -- capturada por uma execução diária
    coletado_em             TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    execucao_id             BIGINT        REFERENCES coleta_execucoes(id),
    fonte                   VARCHAR(60)   NOT NULL,

    -- Momento a partir do qual o backtest pode usar esta versão:
    --   carga_historica -> disponivel_em (premissa documentada: sem revisão desde a publicação)
    --   observada       -> o mais tarde entre disponivel_em e coletado_em
    conhecido_desde         TIMESTAMPTZ GENERATED ALWAYS AS (
                                CASE
                                    WHEN origem_disponibilidade = 'nao_verificavel' THEN NULL
                                    WHEN tipo_versao = 'carga_historica' THEN disponivel_em
                                    ELSE GREATEST(disponivel_em, coletado_em)
                                END) STORED,

    CONSTRAINT uq_serie_versao UNIQUE (serie, data_referencia, versao),
    CONSTRAINT ck_versao_1_e_carga CHECK (versao = 1 OR tipo_versao = 'observada'),
    CONSTRAINT ck_disponibilidade_coerente CHECK (
        (origem_disponibilidade = 'nao_verificavel') = (disponivel_em IS NULL))
);

CREATE INDEX IF NOT EXISTS idx_versoes_busca
    ON serie_versoes (serie, data_referencia, conhecido_desde);

-- Versão mais recente de cada observação (o que o dashboard mostra)
CREATE OR REPLACE VIEW serie_atual AS
SELECT DISTINCT ON (serie, data_referencia)
       serie, data_referencia, valor, versao, disponivel_em, origem_disponibilidade, coletado_em
FROM serie_versoes
ORDER BY serie, data_referencia, versao DESC;

-- Revisões: observações com mais de uma versão
CREATE OR REPLACE VIEW serie_revisoes AS
SELECT v.serie, v.data_referencia, v.versao, v.valor,
       LAG(v.valor) OVER w AS valor_anterior,
       v.valor - LAG(v.valor) OVER w AS diferenca,
       v.coletado_em
FROM serie_versoes v
WHERE (v.serie, v.data_referencia) IN (
    SELECT serie, data_referencia FROM serie_versoes GROUP BY 1, 2 HAVING COUNT(*) > 1)
WINDOW w AS (PARTITION BY v.serie, v.data_referencia ORDER BY v.versao);

-- O que se sabia sobre uma série em um momento: a ÚNICA porta de entrada dos backtests
CREATE OR REPLACE FUNCTION serie_conhecida_em(p_serie VARCHAR, p_momento TIMESTAMPTZ)
RETURNS TABLE (data_referencia DATE, valor NUMERIC, versao SMALLINT, conhecido_desde TIMESTAMPTZ)
LANGUAGE sql STABLE AS $$
    SELECT DISTINCT ON (v.data_referencia)
           v.data_referencia, v.valor, v.versao, v.conhecido_desde
    FROM serie_versoes v
    WHERE v.serie = p_serie
      AND v.conhecido_desde IS NOT NULL
      AND v.conhecido_desde <= p_momento
    ORDER BY v.data_referencia, v.versao DESC;
$$;

-- -----------------------------------------------------------------------------
-- 4. Área de preparação: a coleta grava aqui e registrar_versoes() decide
--    o que é novo. Assim a regra de versionamento fica em um só lugar.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stg_serie (
    serie                   VARCHAR(40)   NOT NULL,
    data_referencia         DATE          NOT NULL,
    valor                   NUMERIC(18,6) NOT NULL,
    disponivel_em           TIMESTAMPTZ,
    origem_disponibilidade  VARCHAR(30)   NOT NULL,
    fonte                   VARCHAR(60)   NOT NULL,
    PRIMARY KEY (serie, data_referencia)
);

CREATE OR REPLACE FUNCTION registrar_versoes(p_execucao BIGINT, p_carga_historica BOOLEAN)
RETURNS INTEGER LANGUAGE plpgsql AS $$
DECLARE
    novas INTEGER;
BEGIN
    INSERT INTO serie_versoes (serie, data_referencia, valor, versao, disponivel_em,
                               origem_disponibilidade, tipo_versao, execucao_id, fonte)
    SELECT s.serie, s.data_referencia, s.valor,
           COALESCE(a.versao, 0) + 1,
           -- uma revisão herda a data de publicação comprovada da versão anterior
           COALESCE(s.disponivel_em, a.disponivel_em),
           CASE WHEN COALESCE(s.disponivel_em, a.disponivel_em) IS NULL
                THEN 'nao_verificavel'
                ELSE COALESCE(NULLIF(s.origem_disponibilidade, 'nao_verificavel'), a.origem_disponibilidade)
           END,
           CASE WHEN a.versao IS NULL AND p_carga_historica THEN 'carga_historica' ELSE 'observada' END,
           p_execucao, s.fonte
    FROM stg_serie s
    LEFT JOIN serie_atual a
           ON a.serie = s.serie AND a.data_referencia = s.data_referencia
    WHERE a.versao IS NULL            -- observação nova
       OR a.valor <> s.valor;         -- revisão: grava nova versão, mantém a antiga
    GET DIAGNOSTICS novas = ROW_COUNT;

    -- Data de divulgação descoberta depois (ex.: calendário do IBGE coletado
    -- após a série) é uma informação nova sobre a mesma versão, não um novo valor.
    -- Só melhora a prova: sem prova -> qualquer prova; limite superior -> data exata.
    UPDATE serie_versoes v
       SET disponivel_em = s.disponivel_em,
           origem_disponibilidade = s.origem_disponibilidade
      FROM stg_serie s
     WHERE v.serie = s.serie AND v.data_referencia = s.data_referencia
       AND s.origem_disponibilidade <> 'nao_verificavel'
       AND (v.origem_disponibilidade = 'nao_verificavel'
            OR (v.origem_disponibilidade = 'ibge_limite_superior' AND s.origem_disponibilidade = 'ibge_calendario'));

    TRUNCATE stg_serie;
    RETURN novas;
END;
$$;

-- -----------------------------------------------------------------------------
-- 5. Boletim Focus: expectativas mensais do IPCA
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS focus_ipca_mensal (
    data_estatistica        DATE          NOT NULL,       -- campo "Data" da API
    mes_alvo                DATE          NOT NULL CHECK (EXTRACT(DAY FROM mes_alvo) = 1),
    base_calculo            SMALLINT      NOT NULL CHECK (base_calculo IN (0, 1)),
    mediana                 NUMERIC(10,4) NOT NULL,
    media                   NUMERIC(10,4),
    desvio_padrao           NUMERIC(10,4),
    minimo                  NUMERIC(10,4),
    maximo                  NUMERIC(10,4),
    respondentes            INTEGER       CHECK (respondentes IS NULL OR respondentes >= 0),

    -- Só as estatísticas do fechamento semanal entram no Relatório Focus;
    -- para elas, disponivel_em = primeiro dia útil seguinte (regra do BCB).
    entra_no_relatorio      BOOLEAN       NOT NULL,
    disponivel_em           TIMESTAMPTZ,
    origem_disponibilidade  VARCHAR(30)   NOT NULL CHECK (origem_disponibilidade IN (
                                'focus_relatorio_semanal', 'nao_verificavel')),
    coletado_em             TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    execucao_id             BIGINT        REFERENCES coleta_execucoes(id),

    PRIMARY KEY (data_estatistica, mes_alvo, base_calculo),
    CONSTRAINT ck_focus_alvo_futuro CHECK (mes_alvo >= DATE_TRUNC('month', data_estatistica) - INTERVAL '1 month'),
    CONSTRAINT ck_focus_disponibilidade CHECK (
        (origem_disponibilidade = 'nao_verificavel') = (disponivel_em IS NULL))
);

-- Expectativa do mercado conhecida em um momento, para um mês-alvo
CREATE OR REPLACE FUNCTION focus_conhecido_em(p_momento TIMESTAMPTZ, p_base SMALLINT DEFAULT 0)
RETURNS TABLE (mes_alvo DATE, mediana NUMERIC, data_estatistica DATE, disponivel_em TIMESTAMPTZ)
LANGUAGE sql STABLE AS $$
    SELECT DISTINCT ON (f.mes_alvo)
           f.mes_alvo, f.mediana, f.data_estatistica, f.disponivel_em
    FROM focus_ipca_mensal f
    WHERE f.base_calculo = p_base
      AND f.entra_no_relatorio
      AND f.disponivel_em IS NOT NULL
      AND f.disponivel_em <= p_momento
    ORDER BY f.mes_alvo, f.data_estatistica DESC;
$$;

-- -----------------------------------------------------------------------------
-- 6. Backtests (Fase 2): cada execução guarda parâmetros e versão do código,
--    cada previsão guarda a origem, o alvo e o valor realizado.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS backtest_execucoes (
    id              BIGSERIAL    PRIMARY KEY,
    iniciado_em     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    serie           VARCHAR(40)  NOT NULL,
    referencia      VARCHAR(60)  NOT NULL,
    versao_codigo   VARCHAR(60),
    parametros      JSONB        NOT NULL
);

CREATE TABLE IF NOT EXISTS backtest_previsoes (
    execucao_id       BIGINT        NOT NULL REFERENCES backtest_execucoes(id) ON DELETE CASCADE,
    modelo            VARCHAR(60)   NOT NULL,
    origem            TIMESTAMPTZ   NOT NULL,
    ultimo_conhecido  DATE          NOT NULL,
    h                 SMALLINT      NOT NULL CHECK (h > 0),
    alvo              DATE          NOT NULL,
    previsto          NUMERIC(18,6) NOT NULL,
    li80              NUMERIC(18,6),
    ls80              NUMERIC(18,6),
    li95              NUMERIC(18,6),
    ls95              NUMERIC(18,6),
    realizado         NUMERIC(18,6) NOT NULL,
    PRIMARY KEY (execucao_id, modelo, origem, h),
    CONSTRAINT ck_alvo_futuro CHECK (alvo > ultimo_conhecido),
    CONSTRAINT ck_ultimo_antes_da_origem CHECK (ultimo_conhecido <= origem::date),
    CONSTRAINT ck_intervalos CHECK (li95 IS NULL OR (li95 <= li80 AND li80 <= previsto AND previsto <= ls80 AND ls80 <= ls95))
);

CREATE TABLE IF NOT EXISTS backtest_metricas (
    execucao_id    BIGINT        NOT NULL REFERENCES backtest_execucoes(id) ON DELETE CASCADE,
    comparacao     VARCHAR(60)   NOT NULL,   -- contra qual referência
    modelo         VARCHAR(60)   NOT NULL,
    h              SMALLINT      NOT NULL,
    n              INTEGER       NOT NULL,
    mae            NUMERIC(18,6),
    rmse           NUMERIC(18,6),
    rmse_relativo  NUMERIC(10,4),
    cobertura80    NUMERIC(6,4),
    cobertura95    NUMERIC(6,4),
    n_comum        INTEGER,
    dm             NUMERIC(10,4),
    p_valor        NUMERIC(10,6),
    p_melhor       NUMERIC(10,6),
    veredito       VARCHAR(40),
    PRIMARY KEY (execucao_id, comparacao, modelo, h)
);

-- -----------------------------------------------------------------------------
-- 7. Fase 3: medida (variação ou acumulado 12m) e detalhe do modelo
--    (ex.: ordem do SARIMA escolhida). Migração idempotente para bancos
--    criados na Fase 2.
-- -----------------------------------------------------------------------------
ALTER TABLE backtest_previsoes ADD COLUMN IF NOT EXISTS medida  VARCHAR(20) NOT NULL DEFAULT 'variacao';
ALTER TABLE backtest_previsoes ADD COLUMN IF NOT EXISTS detalhe VARCHAR(80);
ALTER TABLE backtest_metricas  ADD COLUMN IF NOT EXISTS medida  VARCHAR(20) NOT NULL DEFAULT 'variacao';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'pk_backtest_previsoes_medida') THEN
        ALTER TABLE backtest_previsoes DROP CONSTRAINT IF EXISTS backtest_previsoes_pkey;
        ALTER TABLE backtest_previsoes ADD CONSTRAINT pk_backtest_previsoes_medida
            PRIMARY KEY (execucao_id, medida, modelo, origem, h);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'pk_backtest_metricas_medida') THEN
        ALTER TABLE backtest_metricas DROP CONSTRAINT IF EXISTS backtest_metricas_pkey;
        ALTER TABLE backtest_metricas ADD CONSTRAINT pk_backtest_metricas_medida
            PRIMARY KEY (execucao_id, medida, comparacao, modelo, h);
    END IF;
END $$;
