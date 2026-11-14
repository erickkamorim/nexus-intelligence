-- Retrato mais recente das previsões publicadas (gerado por src/prever_atual.py)
SELECT conteudo FROM previsoes_publicadas ORDER BY id DESC LIMIT 1;
