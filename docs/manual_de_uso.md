# Manual de Uso e Guia de Execução

Este documento descreve os comandos do projeto: coleta, importação no banco, relatórios e consumo dos dados.

## Trilha Padrão de Execução

Para uma rodada completa de coleta, sem desperdício de créditos de API, execute os passos abaixo na ordem.

```mermaid
flowchart TD
    A["1. Coleta Gratuita<br><code>python main.py</code><br>(Gupy, LinkedIn, Vagas.com, ProgramaThor, Trampos)"] --> B["2. Coleta SerpApi<br><code>python main.py --sources serpapi --max-pages 1</code>"]
    B --> C["3. Coleta TheirStack<br><code>python main.py --sources theirstack --max-pages 1 --page-size 8</code>"]
    C --> D["4. Consolidação no SQLite<br><code>python scripts/import_csv.py</code>"]
    D --> E["5. Snapshot Seed<br><code>python scripts/export_seed.py</code>"]
    E --> F["6. Relatório Consolidado<br><code>python scripts/report_db.py</code>"]
```

### 1. Coleta Gratuita (Ilimitada)

Executa a busca nos 5 portais gratuitos (Gupy, LinkedIn, Vagas.com, ProgramaThor e Trampos.co), sem consumir cota de API paga:

```powershell
python main.py
```

### 2. Coleta Complementar SerpApi

Executa a SerpApi (Google Jobs) de forma isolada. Consome cerca de 13 consultas da cota mensal:

```powershell
python main.py --sources serpapi --max-pages 1
```

### 3. Coleta Complementar TheirStack

Executa a TheirStack de forma isolada. Coleta até 8 vagas por termo e consome de 80 a 100 créditos da cota:

```powershell
python main.py --sources theirstack --max-pages 1 --page-size 8
```

### 4. Importação e Deduplicação no Banco de Dados

Lê os CSVs gerados em `output/`, resolve as datas de publicação, deduplica e insere ou atualiza as vagas no SQLite (`data/vagas.db`):

```powershell
python scripts/import_csv.py
```

### 5. Atualização do Snapshot Versionado

Exporta todas as vagas consolidadas do banco para `seed/vagas.csv`, que fica pronto para versionamento no GitHub:

```powershell
python scripts/export_seed.py
```

### 6. Relatório Estatístico Consolidado

Imprime o panorama geral no terminal e salva um relatório Markdown em `output/relatorio_banco_consolidado_AAAAMMDD_HHMMSS.md`:

```powershell
python scripts/report_db.py
```

## Coleta Diária Automatizada

O cron-job.org dispara o workflow `daily_scraper.yml` três vezes ao dia (09:16, 14:16 e 19:16, horário de Brasília). Cada execução:

1. Coleta as novas vagas dos portais gratuitos.
2. Importa o histórico (`seed/vagas.csv`) e as novas vagas no SQLite do runner.
3. Enriquece as descrições pendentes (outras fontes primeiro, depois LinkedIn).
4. Reclassifica as áreas das vagas pendentes.
5. Exporta o snapshot e os JSON estáticos e publica o dashboard no Pages.

O dashboard e a API estática são atualizados a cada execução.

## Referência Detalhada de Comandos

### 1. `main.py` (Coleta e Mineração)

O `main.py` orquestra a coleta, o portão de relevância, o filtro de senioridade, a extração de tecnologias, a classificação por área e a exportação dos arquivos.

```text
Uso: python main.py [OPÇÕES]
```

| Flag | Tipo | Padrão | Descrição |
| :--- | :--- | :--- | :--- |
| **`--sources`** | Lista | `gupy vagas programathor trampos linkedin` | Portais a consultar. Opções: `gupy`, `vagas`, `programathor`, `trampos`, `linkedin`, `theirstack`, `serpapi`. |
| **`--locations`** | Lista | `todos` | Polos ou macrorregiões a consultar. Ex: `--locations nordeste sul` ou `--locations "Recife" "Florianópolis"`. |
| **`--terms`** | Lista | 40 termos nativos | Sobrescreve os termos de busca padrão (definidos em `scraper/config.py`). |
| **`--start-page`** | Int | `1` | Página inicial da busca por portal. Permite retomar coletas interrompidas. |
| **`--max-pages`** | Int | `15` | Máximo de páginas navegadas por termo, por portal. |
| **`--page-size`** | Int | `100` | Vagas por página. A Gupy aceita no máximo 100. |
| **`--delay`** | Float | `1.5` | Segundos de espera entre requisições HTTP. |
| **`--output`** | Caminho | `./output` | Diretório dos arquivos CSV, relatórios e gráficos PNG. |
| **`--strict`** | Flag | `False` | Descarta títulos mistos como "Desenvolvedor Junior/Pleno". |
| **`--all-levels`** | Flag | `False` | Desativa o filtro de senioridade e coleta todos os níveis. |
| **`--keep-non-tech`** | Flag | `False` | Mantém vagas fora de tecnologia que o portão descartaria. |
| **`--no-charts`** | Flag | `False` | Não gera os gráficos PNG do Matplotlib. |
| **`--no-enrich`** | Flag | `False` | Não busca descrições do LinkedIn durante a coleta. |
| **`-v`, `--verbose`** | Flag | `False` | Habilita logs de depuração (nível `DEBUG`). |

#### Exemplos

```powershell
# Coleta apenas no Nordeste e no Sul:
python main.py --locations nordeste sul

# Coleta de teste rápida, com 1 página e termos específicos:
python main.py --terms "engenheiro de dados junior" "analista de dados junior" --max-pages 1

# Coleta apenas na Gupy:
python main.py --sources gupy
```

### 2. `scripts/import_csv.py` (Carga Idempotente no Banco)

Espelha o CSV mais recente (ou um CSV específico) no banco de dados relacional.

Linhas que não passam no portão de relevância (`tech_gate` em `scraper/rules/areas.yml`) são ignoradas e contabilizadas como "Fora do escopo". Como o import é idempotente, reimportar o `seed/vagas.csv` com `--recriar` também remove do banco vagas antigas que deixaram de ser tech após um ajuste do portão.

```text
Uso: python scripts/import_csv.py [OPÇÕES]
```

| Flag | Tipo | Padrão | Descrição |
| :--- | :--- | :--- | :--- |
| **`--csv`** | Caminho | Último CSV em `output/` | CSV a importar. |
| **`--db`** | String | `data/vagas.db` | SQLite local ou URL PostgreSQL (`postgresql://user:pass@host/db`). |
| **`--referencia`** | Data | Data do arquivo | Data âncora (`AAAA-MM-DD`) para resolver datas relativas ("Há 3 dias", "Ontem"). |
| **`--recriar`** | Flag | `False` | **Atenção:** apaga todas as tabelas e recria a base do zero antes de importar. |

#### Exemplos

```powershell
# Importa o CSV mais recente com data fixa de auditoria:
python scripts/import_csv.py --referencia 2026-08-12

# Importa um CSV específico:
python scripts/import_csv.py --csv output/vagas_20260812_100000.csv
```

### 3. `scripts/report_db.py` (Relatório Estatístico Consolidado)

Analisa todas as vagas do banco e emite um relatório estatístico com percentuais, gráficos e tabelas.

```text
Uso: python scripts/report_db.py [OPÇÕES]
```

| Flag | Tipo | Padrão | Descrição |
| :--- | :--- | :--- | :--- |
| **`--db`** | String | `data/vagas.db` | SQLite local ou URL do PostgreSQL. |
| **`--no-export`** | Flag | `False` | Apenas exibe o resumo no terminal, sem salvar o arquivo `.md` em `output/`. |
| **`--no-charts`** | Flag | `False` | Não gera os gráficos PNG. |

```powershell
python scripts/report_db.py
```

### 4. `scripts/export_pages_data.py` (JSON Estáticos do Pages)

Gera os arquivos JSON públicos que alimentam o site e servem como endpoints HTTP no GitHub Pages:

```powershell
python scripts/export_pages_data.py
```

O `scripts/import_csv.py` e o `scripts/report_db.py` executam este comando automaticamente ao final.

## Consumo da API JSON Estática (GitHub Pages)

Os dados consolidados são servidos gratuitamente, com CORS liberado, em `https://diasgarcia.github.io/tech-skills-br/`.

| Endpoint | Conteúdo |
| :--- | :--- |
| **`/api/resumo.json`** | KPIs, metadados e distribuições |
| **`/api/areas.json`** | Ranking das áreas técnicas |
| **`/api/tecnologias.json`** | Ranking de tecnologias e grupos |
| **`/api/vagas.json`** | Base completa de vagas estruturadas |

### Exemplos de Consumo

```powershell
# cURL:
curl -s https://diasgarcia.github.io/tech-skills-br/api/areas.json
```

```python
# Python (requests):
import requests

res = requests.get("https://diasgarcia.github.io/tech-skills-br/api/resumo.json")
dados = res.json()
print(f"Total de Vagas: {dados['metadados']['total_vagas']}")
```

## Como Explorar os Dados no DBeaver

1. Abra o DBeaver.
2. Clique em **Nova Conexão -> SQLite**.
3. No campo **Path**, selecione o arquivo `data/vagas.db` do projeto.
4. Clique em **Testar Conexão** e depois em **Concluir**.

### Consultas SQL Úteis

#### A. Top 20 Tecnologias Mais Demandadas

```sql
SELECT
    t.nome AS tecnologia,
    t.grupo,
    COUNT(vt.vaga_id) AS total_vagas,
    ROUND(COUNT(vt.vaga_id) * 100.0 / (SELECT COUNT(*) FROM vagas), 1) AS percentual_vagas
FROM tecnologias t
JOIN vaga_tecnologia vt ON t.id = vt.tecnologia_id
GROUP BY t.nome, t.grupo
ORDER BY total_vagas DESC
LIMIT 20;
```

#### B. Distribuição de Vagas por Macrorregião e Modalidade

```sql
SELECT
    regiao,
    workplace_type AS modalidade,
    COUNT(*) AS total_vagas
FROM vagas
GROUP BY regiao, workplace_type
ORDER BY regiao, total_vagas DESC;
```

#### C. Tecnologias Mais Pedidas em Vagas de Backend

```sql
SELECT
    t.nome AS tecnologia,
    COUNT(v.id) AS total_vagas
FROM vagas v
JOIN vaga_tecnologia vt ON v.id = vt.vaga_id
JOIN tecnologias t ON t.id = vt.tecnologia_id
WHERE v.area = 'Backend'
GROUP BY t.nome
ORDER BY total_vagas DESC
LIMIT 15;
```

## Testes Automatizados

A suíte cobre classificadores, coletores, expressões regulares e banco de dados. Para executar:

```powershell
pytest
```

Para verificar a cobertura:

```powershell
pytest --cov=scraper --cov=api --cov-report=term-missing
```

## Créditos

Este projeto foi construído e expandido a partir da concepção original do repositório [vagas-tech-junior](https://github.com/EmidioLP/vagas-tech-junior), de autoria de **Emidio Lopes de Souza Neto** ([GitHub](https://github.com/EmidioLP) / [LinkedIn](https://www.linkedin.com/in/emidio-lopes/)).
