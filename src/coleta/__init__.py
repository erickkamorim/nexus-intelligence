"""Coletores do NEXUS Forecast (Fase 1).

Cada coletor devolve objetos Observacao/ExpectativaFocus já com a data de
divulgação comprovada (ou marcados como 'nao_verificavel'). Nenhum coletor
grava no banco: a validação e o armazenamento ficam em módulos separados.
"""
