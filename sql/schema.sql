-- NEXUS Intelligence - estrutura do banco (PostgreSQL)
-- Execute uma vez no banco nexus_db:  psql -U postgres -d nexus_db -f sql/schema.sql

-- Histórico dos indicadores (uma linha por indicador e data)
CREATE TABLE IF NOT EXISTS indicadores (
    id               BIGSERIAL PRIMARY KEY,
    indicador        VARCHAR(50)    NOT NULL,
    codigo_sgs       INTEGER        NOT NULL,
    data_referencia  DATE           NOT NULL,
    valor            NUMERIC(18,6)  NOT NULL,
    coletado_em      TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    atualizado_em    TIMESTAMPTZ    NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_indicador_data UNIQUE (indicador, data_referencia)
);

CREATE INDEX IF NOT EXISTS idx_indicadores_consulta
    ON indicadores (indicador, data_referencia DESC);

-- Auditoria: cada carga registra quando rodou, quanto entrou e se falhou
CREATE TABLE IF NOT EXISTS execucoes (
    id                 BIGSERIAL PRIMARY KEY,
    iniciado_em        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    finalizado_em      TIMESTAMPTZ,
    status             VARCHAR(20)  NOT NULL DEFAULT 'em_andamento',  -- sucesso | falha
    registros_lidos    INTEGER,
    registros_inseridos INTEGER,
    registros_atualizados INTEGER,
    mensagem           TEXT
);

-- Cotações PTAX de fechamento de outras moedas (faixa de moedas no topo do dashboard)
CREATE TABLE IF NOT EXISTS cotacoes_moedas (
    moeda          CHAR(3)        NOT NULL,   -- código ISO (USD, EUR...)
    data           DATE           NOT NULL,
    compra         NUMERIC(18,6)  NOT NULL,   -- R$ por 1 unidade da moeda
    venda          NUMERIC(18,6)  NOT NULL,
    boletim_em     TIMESTAMPTZ    NOT NULL,   -- dataHoraCotacao do boletim de fechamento
    coletado_em    TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    PRIMARY KEY (moeda, data)
);
