# 📡 NEXUS Intelligence | Inteligência Econômica do Brasil

<p align="center">
  <img src="docs/dashboard.png" width="100%">
</p>

<p align="center">

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-336791?style=for-the-badge&logo=postgresql&logoColor=white)
![SQL](https://img.shields.io/badge/SQL-003B57?style=for-the-badge)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white)
![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?style=for-the-badge&logo=javascript&logoColor=black)
![statsmodels](https://img.shields.io/badge/statsmodels-4B8BBE?style=for-the-badge)
![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-2088FF?style=for-the-badge&logo=githubactions&logoColor=white)

</p>

<p align="center">
  <a href="https://erickkamorim.github.io/nexus-intelligence/"><b>🔗 Acessar o dashboard online</b></a>
  &nbsp;·&nbsp;
  <a href="https://erickkamorim.github.io/nexus-intelligence/metodologia.html"><b>📐 Metodologia das previsões</b></a>
</p>

> **Plataforma de inteligência econômica que coleta automaticamente indicadores oficiais do Banco Central do Brasil, valida a qualidade dos dados, armazena o histórico em PostgreSQL e apresenta as análises em um dashboard web interativo.**

---

# 📌 Objetivo

Construir um produto de dados completo, da coleta à interpretação, capaz de responder perguntas como:

- Qual é a taxa Selic hoje e como o Copom vem conduzindo os juros?
- A inflação está acelerando ou desacelerando?
- Quanto a Selic rende acima da inflação (juro real)?
- Como o dólar se comportou em um determinado período?
- Os dados estão atualizados e confiáveis?
- Um modelo estatístico consegue prever a inflação e o dólar melhor do que referências simples e do que o mercado (Boletim Focus)?

Diferente de um dashboard construído sobre uma planilha estática, o NEXUS busca os dados direto da fonte oficial, garante que não haja duplicidade ou valores inválidos e pode ser atualizado a qualquer momento com um único comando.

---

# 📊 Sobre o Projeto

Os dados vêm da **API SGS (Sistema Gerenciador de Séries Temporais) do Banco Central do Brasil**, uma fonte pública e oficial que não exige chave de acesso.

O projeto cobre todas as etapas de um fluxo de dados:

1. **Extração** automatizada via API, com novas tentativas em caso de falha
2. **Validação** de datas, valores, duplicidades e faixas plausíveis
3. **Carga** incremental no PostgreSQL, sem duplicar registros
4. **Auditoria** de cada execução (quando rodou, quantos registros, se falhou)
5. **Análise** com SQL usando funções de janela
6. **Disponibilização** dos dados por uma API REST
7. **Visualização** em um dashboard web desenvolvido do zero
8. **Previsão** do IPCA e do dólar validada com backtest honesto (NEXUS Forecast)

---

# 🛠️ Tecnologias Utilizadas

| Ferramenta | Utilização |
|------------|------------|
| 🐍 Python | Extração, validação e carga dos dados (ETL) |
| 🐼 Pandas | Transformação e tratamento das séries |
| 🗄️ PostgreSQL | Armazenamento do histórico e tabela de auditoria |
| 🧮 SQL | Indicadores derivados com funções de janela (`LAG`, `SUM OVER`, `DISTINCT ON`) |
| ⚡ FastAPI | API REST que entrega os dados ao dashboard |
| 🎨 HTML, CSS e JavaScript | Dashboard web com gráficos SVG feitos sem bibliotecas externas |
| 📐 statsmodels e SciPy | SARIMA/ARIMA, teste de Diebold-Mariano e intervalos de previsão |
| ☁️ Neon | PostgreSQL gerenciado na nuvem, usado pela automação |
| ⚙️ GitHub Actions | Testes, atualização diária, recalibração dos modelos e publicação no GitHub Pages |

---

# 📈 Indicadores

| Indicador | Código SGS | Frequência | Unidade |
|-----------|-----------|------------|---------|
| Selic meta | 432 | Diária | % ao ano |
| IPCA | 433 | Mensal | Variação % no mês |
| Dólar americano (venda) | 1 | Dias úteis | R$ por US$ |

**Indicadores calculados no banco a partir das séries oficiais:**

- 📊 IPCA acumulado em 12 meses (juros compostos das variações mensais)
- ⚖️ Juro real ex-post (Selic descontada do IPCA 12 meses)
- 🏛️ Decisões do Copom (cada mudança da Selic meta e sua variação em p.p.)
- 🔁 Ciclo atual do Copom (cortes ou altas consecutivos e variação acumulada)
- 💵 Média móvel de 21 dias úteis e volatilidade anualizada do dólar

---

# 💡 Principais Insights

> Período analisado: janeiro de 2023 a novembro de 2026, com dados atualizados até 13/11/2026.

### 🏛️ Juros

- O Copom alterou a Selic meta **19 vezes** no período, passando por **três ciclos completos**.
- **Ciclo de cortes (ago/2023 a mai/2024):** a taxa caiu de 13,75% para 10,50% ao ano.
- **Ciclo de altas (set/2024 a jun/2025):** sete altas seguidas levaram a Selic de 10,50% a **15,00% ao ano**, o pico do período. No auge do aperto, o Copom subiu **1 p.p. em três reuniões consecutivas** (dez/2024, jan/2025 e mar/2025).
- **Novo ciclo de cortes (desde mar/2026):** cinco reduções de 0,25 p.p. trouxeram a taxa para **13,75%**, uma queda acumulada de 1,25 p.p.
- Com o IPCA em 4,63% em 12 meses, o **juro real está em 8,72% ao ano**. Ele chegou a passar de 10% no início de 2026, quando a Selic estava no pico e a inflação desacelerava.

### 🛒 Inflação

- O IPCA acumulou **19,04%** entre janeiro de 2023 e outubro de 2026, com média de **0,38% ao mês**.
- A maior variação mensal foi em **fevereiro de 2025 (1,31%)**.
- Houve meses de **deflação**, como **agosto de 2026 (-0,32%)**, a menor taxa do período.
- O acumulado em 12 meses está em **4,63%** (outubro de 2026).

### 💵 Câmbio

- O dólar oscilou entre a mínima de **R$ 4,7202 (27/07/2023)** e a máxima de **R$ 6,2086 (02/01/2025)**.
- Depois do pico no início de 2025, a moeda recuou por mais de um ano, até voltar à faixa de R$ 5,00 em meados de 2026.
- Em novembro de 2026 houve uma **alta de 12,0% em 30 dias**, levando a cotação a **R$ 5,6518**.
- A volatilidade anualizada no período foi de **12,0%**.

---

# ⚙️ Funcionalidades

✅ Extração automática dos dados oficiais do Banco Central

✅ Validação de qualidade com registro em log

✅ Carga incremental sem duplicidade (`INSERT ... ON CONFLICT`)

✅ Auditoria de todas as cargas na tabela `execucoes`

✅ API REST com documentação automática (Swagger)

✅ Resumo da conjuntura gerado automaticamente a partir dos dados

✅ Decisões do Copom marcadas no gráfico da Selic

✅ Filtro de período (6 meses, 1 ano, 2 anos ou tudo)

✅ Tooltips interativos em todos os gráficos

✅ Painel de qualidade dos dados

✅ Layout responsivo com tema escuro

✅ Dashboard online com atualização diária automática (GitHub Actions + GitHub Pages)

---

# 🏗️ Arquitetura

```
┌──────────────────────┐
│  Banco Central (SGS) │  API pública, formato JSON
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│  src/extract.py      │  Extração + validação + log
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│  src/load.py         │  Carga incremental + auditoria
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│  PostgreSQL          │  indicadores + execucoes
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│  src/api.py          │  FastAPI, consultas em sql/api/
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│  web/index.html      │  Dashboard interativo
└──────────────────────┘
```

---

# 🚀 Processo de Desenvolvimento

## 🔌 1. Extração dos Dados

O script `src/extract.py` consulta a API SGS para cada indicador e converte o JSON da API (datas em `dd/mm/aaaa` e valores em texto) para os tipos corretos.

Em caso de instabilidade da API, a extração faz até **3 tentativas** com intervalo crescente. Se uma série falhar, as outras continuam sendo processadas e a falha fica registrada em log.

---

## 🧹 2. Validação e Qualidade

Antes de qualquer dado chegar ao banco, são aplicadas regras de qualidade:

- ❌ Datas ou valores inválidos são removidos e registrados
- 🔁 Datas duplicadas são removidas
- 📅 Registros com data futura geram alerta
- 📏 Valores fora de uma faixa plausível geram alerta, sem apagar o dado, pois pode ser um evento real

Todas as ocorrências ficam em `logs/extract.log`.

---

## 🗄️ 3. Modelagem e Carga no PostgreSQL

```sql
CREATE TABLE indicadores (
    id               BIGSERIAL PRIMARY KEY,
    indicador        VARCHAR(50)    NOT NULL,
    codigo_sgs       INTEGER        NOT NULL,
    data_referencia  DATE           NOT NULL,
    valor            NUMERIC(18,6)  NOT NULL,
    coletado_em      TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    atualizado_em    TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_indicador_data UNIQUE (indicador, data_referencia)
);
```

A restrição `UNIQUE` impede que o mesmo indicador tenha dois valores na mesma data. A carga usa `INSERT ... ON CONFLICT`, então pode ser executada quantas vezes for necessário: registros novos são inseridos, valores revisados pelo Banco Central são atualizados e o restante é ignorado.

Cada execução é registrada na tabela `execucoes` com horário, status, quantidade de registros novos e atualizados e a mensagem de erro, se houver.


---

## 🧮 4. Análise com SQL

Os indicadores derivados são calculados diretamente no banco. Alguns destaques:

**IPCA acumulado em 12 meses**: o produto das variações mensais é calculado com a soma de logaritmos em uma janela de 12 linhas.

```sql
SELECT data_referencia,
       ROUND(((EXP(SUM(LN(1 + valor / 100)) OVER janela) - 1) * 100)::numeric, 2) AS ipca_12m
FROM indicadores
WHERE indicador = 'ipca_mensal'
WINDOW janela AS (ORDER BY data_referencia ROWS BETWEEN 11 PRECEDING AND CURRENT ROW);
```

**Decisões do Copom**: compara cada dia com o anterior usando `LAG` e mantém apenas os dias em que a Selic mudou.

```sql
SELECT data_referencia, valor AS selic, valor - valor_anterior AS variacao_pp
FROM (
    SELECT data_referencia, valor,
           LAG(valor) OVER (ORDER BY data_referencia) AS valor_anterior
    FROM indicadores
    WHERE indicador = 'selic_meta'
) t
WHERE valor <> valor_anterior;
```

Resultado no pgAdmin: as 19 decisões do Copom no período, com a taxa anterior e a variação em pontos percentuais.

<p align="center">
<img src="docs/pgadmin.png" width="80%">
</p>

Outras consultas em [`sql/consultas.sql`](sql/consultas.sql): último valor de cada indicador, dólar médio por mês, juro real mês a mês e histórico de cargas.

---

## ⚡ 5. API de Dados

A API em FastAPI expõe os dados para o dashboard. As consultas ficam em arquivos `.sql` separados (`sql/api/`) e já retornam JSON pronto do PostgreSQL.

| Endpoint | Retorno |
|----------|---------|
| `GET /api/resumo` | Valores atuais, variações, juro real, última decisão do Copom e última carga |
| `GET /api/series` | Séries históricas para os gráficos |
| `GET /api/copom` | Histórico de decisões do Copom |
| `GET /api/qualidade` | Cobertura de cada série e histórico de cargas |

A documentação interativa fica disponível em `http://localhost:8000/docs`.


---

## 📊 6. Dashboard Web

O dashboard foi desenvolvido do zero em HTML, CSS e JavaScript, com gráficos em SVG criados sem bibliotecas de visualização.

### 🏠 Visão Geral

No topo, uma **faixa com a PTAX de fechamento** de sete moedas (dólar, euro, libra, iene, franco suíço, dólar canadense e australiano) e a variação sobre o dia útil anterior. É a taxa de referência diária do Banco Central, não uma cotação em tempo real, e a faixa mostra a data do boletim.

Cinco cartões com os indicadores do momento (Selic, IPCA 12 meses, dólar, juro real e ciclo do Copom) e, logo abaixo, um **resumo da conjuntura escrito automaticamente** a partir dos dados: última decisão do Copom, ciclo atual, inflação, juro real e variação do dólar.

<p align="center">
<img src="docs/visao-geral.png" width="90%">
</p>

### 🏛️ Juros

Selic, IPCA 12 meses e juro real no mesmo gráfico, com **cada decisão do Copom marcada na linha** (verde para corte, vermelho para alta) e uma linha do tempo agrupada por ciclo.

<p align="center">
<img src="docs/juros.png" width="90%">
</p>

### 🛒 Inflação

IPCA mês a mês, com o mês mais recente em destaque, linha da média do período e estatísticas de acumulado, média, maior e menor taxa.

<p align="center">
<img src="docs/inflacao.png" width="90%">
</p>

### 💵 Câmbio

Cotação diária do dólar com média móvel de 21 dias úteis, mínima, máxima, variação e volatilidade anualizada no período.

<p align="center">
<img src="docs/cambio.png" width="90%">
</p>

### 🔮 Previsões

Previsão do IPCA para os próximos 6 meses e do dólar para 21 dias úteis, com faixas de 80% e 95%, a expectativa do Boletim Focus no mesmo gráfico e um aviso em texto simples dizendo onde o modelo ganha, empata ou perde para as referências. Detalhes na seção 8.

<p align="center">
<img src="docs/previsoes.png" width="90%">
</p>

### ✅ Qualidade dos Dados

Cobertura de cada série, dias desde a última atualização e histórico das cargas com status de sucesso ou falha.

<p align="center">
<img src="docs/qualidade.png" width="90%">
</p>

---

## 🌐 7. Publicação e Atualização Automática

O dashboard fica disponível online pelo **GitHub Pages**:

🔗 **https://erickkamorim.github.io/nexus-intelligence/**

O banco de produção é um **PostgreSQL gerenciado no Neon** (região São Paulo). A conexão fica em um segredo do GitHub (`DATABASE_URL`), nunca no código. Cada tarefa roda na sua cadência:

| Cadência | Workflow | O que faz |
|----------|----------|-----------|
| Todo dia útil, 19h | `atualizar-dashboard.yml` | Testes → coleta do BCB, IBGE e Focus → previsão do dia → publicação |
| Todo sábado | `recalibrar-modelos.yml` | Backtest completo do câmbio |
| Todo dia 15 | `recalibrar-modelos.yml` | Backtest do IPCA e do SARIMA, depois da divulgação do IBGE |
| Mudança nos modelos, na coleta ou no calendário do IBGE | `recalibrar-modelos.yml` | Backtest das duas séries |

Garantias da automação:

- **Nada é publicado sem os testes passarem** (74 testes em Python e testes SQL do versionamento, num PostgreSQL temporário).
- **Se a extração do BCB falhar**, a publicação é interrompida e a versão anterior continua no ar.
- **Se só o Forecast falhar**, o painel é publicado com a última previsão válida e o GitHub mostra um aviso.
- **Uma coleta por vez no banco:** a atualização diária e a recalibração podem rodar juntas, e uma trava no PostgreSQL (`pg_advisory_lock`) faz a segunda coleta esperar a primeira.
- Os resultados de cada backtest ficam guardados em CSV por 90 dias (artefatos do Actions).

---

## 🔮 8. NEXUS Forecast: previsões com validação honesta

Previsão do **IPCA** (1 a 6 meses e acumulado em 12 meses) e do **dólar** (1 a 21 dias úteis). A regra do projeto: **todo modelo precisa provar, em dados que não viu, que é melhor do que uma referência simples**. Se não for, o painel diz isso. A explicação completa está na [página de Metodologia](https://erickkamorim.github.io/nexus-intelligence/metodologia.html).

<p align="center">
<img src="docs/metodologia.png" width="85%">
</p>

**Dados como eram conhecidos em cada data**

- Cada valor guarda **quando ficou público**: o IPCA usa a data de divulgação do calendário oficial do IBGE, o dólar usa a hora da cotação PTAX e o Focus fica disponível no dia útil seguinte ao fechamento da semana.
- **Revisões viram versões novas**, sem apagar a anterior (tabela `serie_versoes`, só inserção). A função `serie_conhecida_em(série, momento)` devolve o histórico exatamente como estava naquele momento.
- Valores sem data verificável ficam fora do backtest em vez de receber uma data estimada.
- A API do IBGE não responde a servidores fora do Brasil (como os do GitHub Actions). A automação usa uma cópia do calendário oficial guardada no repositório (`data/referencia/calendario_ibge_ipca.json`), exportada no Brasil com `src/exportar_calendario_ibge.py` uma vez por ano. Uma data agendada só passa a valer depois que acontece.

**Backtest com origem móvel**

- IPCA: uma origem logo após cada divulgação desde 2017. Câmbio: 250 origens semanais.
- Em cada origem o modelo só enxerga o que já tinha sido publicado. Um verificador interrompe o backtest se algum dado do futuro aparecer.
- **As ordens do SARIMA são escolhidas de novo usando só os dados de cada origem**, não com a série inteira.
- Comparação com o **Boletim Focus** na mesma data, mesmo mês-alvo e mesmo horizonte.
- **Teste de Diebold-Mariano com correção para sobreposição** (horizontes maiores que o intervalo entre origens geram erros autocorrelacionados). Em simulação, o teste sem correção rejeitava a hipótese nula em ~34% das vezes, quando deveria rejeitar em 5%. Com a correção, 5,6% a 7,8%.
- Intervalos de 80% e 95% com **cobertura medida** e calibrados apenas com erros passados já conhecidos em cada origem.

**Resultados (backtest de 14/11/2026)**

| Comparação | Resultado |
|------------|-----------|
| IPCA · SARIMA × média sazonal | **SARIMA melhor** em 1 e 2 meses (RMSE 16% e 10% menor, significativo); empate de 3 a 6 meses |
| IPCA · SARIMA × Boletim Focus | **Focus melhor** em 1 mês (RMSE do SARIMA 32% maior); empate estatístico de 2 a 6 meses |
| IPCA · cobertura dos intervalos | 82–85% (meta 80%) e 95–98% (meta 95%) depois da calibração |
| Dólar · ARIMA × passeio aleatório | **Sem diferença significativa** em nenhum horizonte; o painel usa o passeio aleatório e informa isso |
| Dólar · cobertura do passeio aleatório | 82% (meta 80%) e 96% (meta 95%) |

O que esses números dizem: o mercado tem informação que um modelo só com o histórico do IPCA não tem (preços de combustível, energia, alimentos da semana), e isso aparece no horizonte de 1 mês. No dólar, nenhum modelo simples supera o passeio aleatório, resultado clássico da literatura (Meese e Rogoff). Mostrar isso com teste estatístico é parte do produto.

---

# 💻 Como Executar

**Pré-requisitos:** Python 3.11+ e PostgreSQL instalados.

```powershell
# 1. Clonar o repositório
git clone https://github.com/erickkamorim/nexus-intelligence.git
cd nexus-intelligence

# 2. Criar o ambiente e instalar as dependências
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3. Configurar a conexão com o banco
$env:DATABASE_URL = "postgresql://postgres:SUA_SENHA@localhost:5432/nexus_db"

# 4. Criar o banco e as tabelas
python -c "import psycopg; c=psycopg.connect('postgresql://postgres:SUA_SENHA@localhost:5432/postgres', autocommit=True); c.execute('CREATE DATABASE nexus_db')"
python -c "import psycopg, os, pathlib; c=psycopg.connect(os.environ['DATABASE_URL'], autocommit=True); c.execute(pathlib.Path('sql/schema.sql').read_text(encoding='utf-8'))"

# 5. Extrair e carregar os dados
python src/extract.py
python src/load.py

# 6. (Opcional) Forecast: coleta com datas de divulgação, backtest e previsão do dia
python src/coletar_forecast.py
python src/rodar_backtest.py      # leva alguns minutos (SARIMA)
python src/prever_atual.py

# 7. Abrir o dashboard (http://localhost:8000)
python src/api.py
```

---

# 📁 Estrutura do Projeto

```
nexus-intelligence/
├── src/
│   ├── extract.py        # Extração e validação (API SGS)
│   ├── load.py           # Carga incremental e auditoria
│   ├── api.py            # API FastAPI + servidor do dashboard
│   ├── build_static.py   # Versão estática para o GitHub Pages
│   ├── coleta/           # Forecast: coletores BCB, IBGE e Focus com datas de divulgação
│   ├── forecast/         # Forecast: modelos, backtest, Diebold-Mariano, calibração
│   ├── coletar_forecast.py
│   ├── rodar_backtest.py
│   └── prever_atual.py
├── sql/
│   ├── schema.sql        # Tabelas indicadores e execucoes
│   ├── forecast_schema.sql  # Versões, divulgações, Focus e backtests
│   ├── consultas.sql     # Consultas de análise
│   └── api/              # Consultas usadas pela API
├── web/
│   ├── index.html        # Dashboard
│   └── metodologia.html  # Metodologia das previsões
├── tests/                # Testes Python e SQL
├── docs/                 # Imagens do README
├── .github/workflows/    # Atualização diária, recalibração e publicação
├── requirements.txt
└── README.md
```

---

# 🗺️ Próximos Passos

- [x] Atualização automática agendada com GitHub Actions
- [x] Publicação do dashboard na web (GitHub Pages)
- [x] Previsão do IPCA e do dólar com backtest, comparação com o Focus e intervalos calibrados
- [x] Banco gerenciado na nuvem (Neon) e cadências separadas de coleta e recalibração
- [ ] Novos indicadores: IGP-M, CDI, PIB e taxa de desemprego
- [ ] Detecção estatística de anomalias nas séries
- [ ] Análises explicativas geradas com inteligência artificial
- [ ] Relatório complementar em Power BI

---

# 📂 Fonte dos Dados

Os dados utilizados neste projeto são obtidos da API pública do Sistema Gerenciador de Séries Temporais (SGS) do Banco Central do Brasil.

🔗 https://dadosabertos.bcb.gov.br

O NEXUS Forecast também usa a PTAX e as expectativas do Boletim Focus (APIs Olinda do Banco Central) e o calendário de divulgações do IBGE, para saber quando cada IPCA ficou público.

🔗 https://servicodados.ibge.gov.br/api/docs/calendario

---

# 👨‍💻 Autor

## Erick Amorim

Data Analytics | Python | SQL | Business Intelligence

🔗 **LinkedIn**

https://www.linkedin.com/in/erickkamorim

💻 **GitHub**

https://github.com/erickkamorim

---

⭐ Se este projeto foi interessante para você, considere deixar uma estrela no repositório.
