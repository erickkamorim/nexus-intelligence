-- Testes do placar ao vivo (sql/api/placar.sql). Rode em um banco vazio:
--   psql -d nexus_teste -v ON_ERROR_STOP=1 -f sql/forecast_schema.sql -f tests/sql/test_placar.sql
-- Qualquer falha interrompe com uma mensagem "FALHOU: ...".

BEGIN;

INSERT INTO coleta_execucoes (fonte) VALUES ('teste_placar');

-- Dados oficiais: PTAX de 5 dias úteis (15/11 é domingo) e dois meses de IPCA
INSERT INTO stg_serie VALUES
  ('ptax_venda', '2026-11-11', 5.62, '2026-11-11 13:10-03', 'ptax_datahora_cotacao', 'teste'),
  ('ptax_venda', '2026-11-12', 5.65, '2026-11-12 13:10-03', 'ptax_datahora_cotacao', 'teste'),
  ('ptax_venda', '2026-11-13', 5.65, '2026-11-13 13:10-03', 'ptax_datahora_cotacao', 'teste'),
  ('ptax_venda', '2026-11-16', 5.70, '2026-11-16 13:10-03', 'ptax_datahora_cotacao', 'teste'),
  ('ipca_mensal', '2026-09-01', 0.82, '2026-10-09 09:00-03', 'ibge_calendario', 'teste'),
  ('ipca_mensal', '2026-10-01', 0.14, '2026-11-12 09:00-03', 'ibge_calendario', 'teste');
SELECT registrar_versoes((SELECT MAX(id) FROM coleta_execucoes), TRUE);
INSERT INTO divulgacoes (serie, mes_referencia, divulgado_em, fonte) VALUES
  ('ipca_mensal', '2026-09-01', '2026-10-09 09:00-03', 'teste'),
  ('ipca_mensal', '2026-10-01', '2026-11-12 09:00-03', 'teste');

-- Retratos publicados
INSERT INTO previsoes_publicadas (gerado_em, conteudo) VALUES
  -- antes do IPCA de outubro sair: esta é a palavra final para out/26 em h=1
  ('2026-11-05 19:00-03', '{"ipca": {"previsoes": [
      {"h": 1, "alvo": "2026-10-01", "previsto": 0.20, "li80": 0.0, "ls80": 0.4, "li95": -0.1, "ls95": 0.5, "focus": 0.18},
      {"h": 2, "alvo": "2026-11-01", "previsto": 0.30, "li80": 0.0, "ls80": 0.6, "li95": -0.2, "ls95": 0.8, "focus": 0.35}]},
    "cambio": {"ultimo_conhecido": "2026-11-11", "previsoes": [
      {"h": 1, "previsto": 5.62, "li80": 5.58, "ls80": 5.66, "li95": 5.55, "ls95": 5.69, "alvo_aproximado": "2026-11-12"}]}}'),
  -- depois da divulgação: não pode entrar no placar de out/26
  ('2026-11-12 19:00-03', '{"ipca": {"previsoes": [
      {"h": 1, "alvo": "2026-10-01", "previsto": 0.99, "li80": 0.9, "ls80": 1.1, "li95": 0.8, "ls95": 1.2, "focus": 0.14},
      {"h": 1, "alvo": "2026-11-01", "previsto": 0.27, "li80": -0.2, "ls80": 0.7, "li95": -0.5, "ls95": 1.0, "focus": 0.35}]},
    "cambio": {"ultimo_conhecido": "2026-11-12", "previsoes": [
      {"h": 1, "previsto": 5.64, "li80": 5.60, "ls80": 5.68, "li95": 5.57, "ls95": 5.71, "alvo_aproximado": "2026-11-13"},
      {"h": 5, "previsto": 5.64, "li80": 5.50, "ls80": 5.78, "li95": 5.45, "ls95": 5.83, "alvo_aproximado": "2026-11-19"}]}}'),
  -- mesma base de câmbio, publicada mais tarde no mesmo dia: substitui a anterior
  ('2026-11-12 21:00-03', '{"ipca": {"previsoes": []},
    "cambio": {"ultimo_conhecido": "2026-11-12", "previsoes": [
      {"h": 1, "previsto": 5.65, "li80": 5.61, "ls80": 5.69, "li95": 5.58, "ls95": 5.72, "alvo_aproximado": "2026-11-13"}]}}'),
  ('2026-11-13 19:00-03', '{"ipca": {"previsoes": []},
    "cambio": {"ultimo_conhecido": "2026-11-13", "previsoes": [
      {"h": 1, "previsto": 5.65, "li80": 5.61, "ls80": 5.69, "li95": 5.58, "ls95": 5.72, "alvo_aproximado": "2026-11-16"}]}}');

-- roda a consulta do placar exatamente como o site (sem o ";" final) e guarda o resultado
\set placar `sed 's/;[[:space:]]*$//' sql/api/placar.sql`
CREATE TEMP TABLE resultado AS :placar ;

DO $$
DECLARE r json := (SELECT json_build_object FROM resultado);
BEGIN
  -- IPCA: só out/26 tem dado; vale a previsão de 05/11 (0,20), não a publicada depois (0,99)
  IF json_array_length(r->'ipca'->'avaliadas') <> 1 THEN RAISE EXCEPTION 'FALHOU: IPCA deveria ter 1 previsão avaliada'; END IF;
  IF (r->'ipca'->'avaliadas'->0->>'previsto')::numeric <> 0.20 THEN
    RAISE EXCEPTION 'FALHOU: previsão publicada depois da divulgação entrou no placar'; END IF;
  IF (r->'ipca'->'avaliadas'->0->>'realizado')::numeric <> 0.14 THEN RAISE EXCEPTION 'FALHOU: IPCA realizado errado'; END IF;
  IF (r->'ipca'->'avaliadas'->0->>'focus')::numeric <> 0.18 THEN RAISE EXCEPTION 'FALHOU: Focus deveria ser o do mesmo retrato'; END IF;
  IF (r->'ipca'->>'em_aberto')::int <> 2 THEN RAISE EXCEPTION 'FALHOU: deveriam restar 2 previsões de IPCA em aberto'; END IF;
  IF (r->'ipca'->>'proximo_alvo')::date <> '2026-11-01' THEN RAISE EXCEPTION 'FALHOU: próximo alvo do IPCA'; END IF;

  -- Dólar: 3 avaliadas (bases 11, 12 e 13/11 em h=1); h=5 ainda em aberto
  IF json_array_length(r->'cambio'->'avaliadas') <> 3 THEN RAISE EXCEPTION 'FALHOU: dólar deveria ter 3 avaliadas'; END IF;
  -- a primeira da lista é a mais recente: base 13/11 (sexta) -> alvo 16/11 (segunda), pulando o fim de semana
  IF (r->'cambio'->'avaliadas'->0->>'alvo')::date <> '2026-11-16' THEN RAISE EXCEPTION 'FALHOU: alvo do dólar deveria pular o fim de semana'; END IF;
  IF (r->'cambio'->'avaliadas'->0->>'realizado')::numeric <> 5.70 THEN RAISE EXCEPTION 'FALHOU: dólar realizado errado'; END IF;
  -- base 12/11: vale a publicação das 21h (5,65), não a das 19h (5,64)
  IF (SELECT (e->>'previsto')::numeric FROM json_array_elements(r->'cambio'->'avaliadas') e
       WHERE e->>'base' = '2026-11-12') <> 5.65 THEN
    RAISE EXCEPTION 'FALHOU: deveria valer a última publicação de cada base'; END IF;
  IF (r->'cambio'->>'em_aberto')::int <> 1 THEN RAISE EXCEPTION 'FALHOU: deveria restar 1 previsão de dólar em aberto'; END IF;
  IF (r->>'publicacoes')::int <> 4 THEN RAISE EXCEPTION 'FALHOU: contagem de publicações'; END IF;
  RAISE NOTICE 'placar: todos os testes passaram';
END $$;

ROLLBACK;
