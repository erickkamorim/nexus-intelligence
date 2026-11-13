-- Testes do esquema de versões. Rode em um banco vazio:
--   psql -d nexus_teste -v ON_ERROR_STOP=1 -f sql/forecast_schema.sql -f tests/sql/test_versoes.sql
-- Qualquer falha interrompe com uma mensagem "FALHOU: ...".

BEGIN;

INSERT INTO coleta_execucoes (fonte) VALUES ('teste');

-- 1) Carga histórica: IPCA de jan/2024 publicado em 08/02/2024
INSERT INTO stg_serie VALUES
  ('ipca_mensal', '2024-01-01', 0.42, '2024-02-08 09:00-03', 'ibge_calendario', 'teste'),
  ('ipca_mensal', '2024-02-01', 0.83, NULL, 'nao_verificavel', 'teste');
SELECT registrar_versoes(1, TRUE);

DO $$ BEGIN
  IF (SELECT COUNT(*) FROM serie_versoes) <> 2 THEN RAISE EXCEPTION 'FALHOU: carga inicial deveria gravar 2 versões'; END IF;
  IF (SELECT tipo_versao FROM serie_versoes WHERE data_referencia = '2024-01-01') <> 'carga_historica' THEN
    RAISE EXCEPTION 'FALHOU: primeira carga deveria ser carga_historica'; END IF;
END $$;

-- 2) Sem vazamento: antes da divulgação o valor não existe para o backtest
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM serie_conhecida_em('ipca_mensal', '2024-02-07 23:59-03')) THEN
    RAISE EXCEPTION 'FALHOU: valor apareceu antes de ser divulgado'; END IF;
  IF (SELECT valor FROM serie_conhecida_em('ipca_mensal', '2024-02-08 09:00-03')) <> 0.42 THEN
    RAISE EXCEPTION 'FALHOU: valor deveria aparecer no momento da divulgação'; END IF;
END $$;

-- 3) Data não verificável nunca entra no backtest
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM serie_conhecida_em('ipca_mensal', '2099-01-01')
             WHERE data_referencia = '2024-02-01') THEN
    RAISE EXCEPTION 'FALHOU: observação sem data comprovada entrou no backtest'; END IF;
END $$;

-- 4) Repetir a mesma coleta não cria versões
INSERT INTO stg_serie VALUES ('ipca_mensal', '2024-01-01', 0.42, '2024-02-08 09:00-03', 'ibge_calendario', 'teste');
SELECT registrar_versoes(1, FALSE);
DO $$ BEGIN
  IF (SELECT COUNT(*) FROM serie_versoes WHERE data_referencia = '2024-01-01') <> 1 THEN
    RAISE EXCEPTION 'FALHOU: coleta repetida criou versão duplicada'; END IF;
END $$;

-- 5) Revisão: nova versão, antiga preservada, backtest antigo não enxerga a revisão
INSERT INTO stg_serie VALUES ('ipca_mensal', '2024-01-01', 0.45, '2024-02-08 09:00-03', 'ibge_calendario', 'teste');
SELECT registrar_versoes(1, FALSE);
DO $$ BEGIN
  IF (SELECT COUNT(*) FROM serie_versoes WHERE data_referencia = '2024-01-01') <> 2 THEN
    RAISE EXCEPTION 'FALHOU: revisão deveria criar a versão 2'; END IF;
  IF (SELECT valor FROM serie_conhecida_em('ipca_mensal', '2024-03-01')) <> 0.42 THEN
    RAISE EXCEPTION 'FALHOU: backtest de 2024 enxergou uma revisão feita depois'; END IF;
  IF (SELECT valor FROM serie_conhecida_em('ipca_mensal', NOW() + INTERVAL '1 second')) <> 0.45 THEN
    RAISE EXCEPTION 'FALHOU: valor revisado deveria valer a partir da coleta'; END IF;
  IF (SELECT valor FROM serie_atual WHERE data_referencia = '2024-01-01') <> 0.45 THEN
    RAISE EXCEPTION 'FALHOU: serie_atual deveria mostrar a versão mais recente'; END IF;
  IF (SELECT COUNT(*) FROM serie_revisoes) <> 2 THEN
    RAISE EXCEPTION 'FALHOU: serie_revisoes deveria listar as duas versões'; END IF;
END $$;

-- 6) Data de divulgação descoberta depois passa a valer para a mesma versão
INSERT INTO stg_serie VALUES ('ipca_mensal', '2024-02-01', 0.83, '2024-03-12 09:00-03', 'ibge_calendario', 'teste');
SELECT registrar_versoes(1, FALSE);
DO $$ BEGIN
  IF (SELECT COUNT(*) FROM serie_versoes WHERE data_referencia = '2024-02-01') <> 1 THEN
    RAISE EXCEPTION 'FALHOU: preencher a data de divulgação não pode criar versão'; END IF;
  IF (SELECT valor FROM serie_conhecida_em('ipca_mensal', '2024-03-12 10:00-03') WHERE data_referencia = '2024-02-01') <> 0.83 THEN
    RAISE EXCEPTION 'FALHOU: observação com data comprovada deveria entrar no backtest'; END IF;
END $$;

-- 7) Restrições de integridade
DO $$ BEGIN
  BEGIN
    INSERT INTO serie_versoes (serie, data_referencia, valor, versao, disponivel_em, origem_disponibilidade, tipo_versao, fonte)
    VALUES ('ipca_mensal', '2024-01-01', 1, 1, NULL, 'nao_verificavel', 'carga_historica', 'x');
    RAISE EXCEPTION 'FALHOU: versão duplicada foi aceita';
  EXCEPTION WHEN unique_violation THEN NULL; END;
  BEGIN
    INSERT INTO serie_versoes (serie, data_referencia, valor, versao, disponivel_em, origem_disponibilidade, tipo_versao, fonte)
    VALUES ('ptax_venda', '2024-01-02', 4.9, 1, NULL, 'ptax_datahora_cotacao', 'carga_historica', 'x');
    RAISE EXCEPTION 'FALHOU: origem verificável sem data foi aceita';
  EXCEPTION WHEN check_violation THEN NULL; END;
END $$;

-- 8) Focus: só a estatística semanal, só depois de divulgada
INSERT INTO focus_ipca_mensal (data_estatistica, mes_alvo, base_calculo, mediana, entra_no_relatorio, disponivel_em, origem_disponibilidade)
VALUES ('2024-03-07', '2024-04-01', 0, 0.30, FALSE, NULL, 'nao_verificavel'),
       ('2024-03-08', '2024-04-01', 0, 0.32, TRUE, '2024-03-11 08:00-03', 'focus_relatorio_semanal');
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM focus_conhecido_em('2024-03-10 23:00-03')) THEN
    RAISE EXCEPTION 'FALHOU: Focus apareceu antes da divulgação do relatório'; END IF;
  IF (SELECT mediana FROM focus_conhecido_em('2024-03-11 08:00-03')) <> 0.32 THEN
    RAISE EXCEPTION 'FALHOU: Focus deveria usar a estatística do relatório semanal'; END IF;
END $$;

ROLLBACK;
SELECT 'OK: todos os testes de versões passaram' AS resultado;
