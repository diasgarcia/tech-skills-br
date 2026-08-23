# Manual de Uso e Guia de Execução

Este documento é o guia operacional completo para a execução dos coletores, filtros, importação para o banco de dados e geração de relatórios estatísticos da pesquisa.

---

## 🚀 Trilha Padrão de Execução (Recomendada)

Para realizar uma rodada completa de coleta sem desperdiçar créditos de API e consolidar todas as informações no banco de dados SQLite, execute a trilha abaixo na ordem:

```mermaid
flowchart TD
    A["1. Coleta Gratuita Ilimitada<br><code>python main.py</code><br>(Gupy, LinkedIn, Vagas.com, ProgramaThor, Trampos)"] --> B["2. Coleta SerpApi Isolada<br><code>python main.py --sources serpapi --max-pages 1</code>"]
    B --> C["3. Coleta TheirStack Isolada<br><code>python main.py --sources theirstack --max-pages 1 --page-size 8</code>"]
    C --> D["4. Consolidação no SQLite<br><code>python scripts/import_csv.py</code>"]
    D --> E["5. Atualizar Snapshot Seed (GitHub)<br><code>python scripts/export_seed.py</code>"]
    E --> F["6. Relatório Consolidado do Banco<br><code>python scripts/report_db.py</code>"]
```

### Passo a Passo da Trilha:

#### 1. Coleta Geral Gratuita (Ilimitada)
Executa a busca com profundidade máxima nos 5 portais gratuitos (Gupy, LinkedIn, Vagas.com, ProgramaThor e Trampos.co), sem consumir nenhuma cota ou API paga:
```powershell
python main.py
```

#### 2. Coleta Complementar SerpApi (Google Jobs - Sob Controle)
Executa a SerpApi de forma isolada, consumindo exatamente ~13 consultas da sua cota mensal:
```powershell
python main.py --sources serpapi --max-pages 1
```

#### 3. Coleta Complementar TheirStack (Econômica e Calibrada)
Executa a TheirStack de forma isolada, coletando até 8 vagas ricas por termo de busca (consumindo ~80 a 100 créditos da sua cota):
```powershell
python main.py --sources theirstack --max-pages 1 --page-size 8
```

#### 4. Importação e Deduplicação no Banco de Dados
Lê os CSVs gerados em `output/`, resolve as datas de publicação, deduplica e insere/atualiza todas as vagas e tecnologias na base relacional SQLite (`data/vagas.db`):
```powershell
python scripts/import_csv.py
```

#### 5. Atualização do Snapshot Versionado (Seed)
Exporta todas as vagas consolidadas do banco de dados para `seed/vagas.csv`, deixando o snapshot pronto para versionamento no GitHub e deploy:
```powershell
python scripts/export_seed.py
```

#### 6. Emissão do Relatório Estatístico Consolidado
Varre o banco de dados inteiro acumulado até o momento, imprime o panorama geral no terminal e salva um relatório Markdown em `output/relatorio_banco_consolidado_AAAAMMDD.md`:
```powershell
python scripts/report_db.py
```



---

## 📖 Referência Detalhada de Comandos

### 1. `main.py` (Pipeline de Coleta e Mineração)

O `main.py` orquestra a coleta nos portais, o portão de relevância tecnológica, o filtro de senioridade, a extração de tecnologias, a classificação regional e a exportação dos arquivos.

```text
Uso: python main.py [OPÇÕES]
```

#### Parâmetros Disponíveis:

| Flag | Tipo | Padrão | Descrição |
| :--- | :--- | :--- | :--- |
| **`--sources`** | Lista | `gupy vagas programathor trampos linkedin` | Define quais portais consultar. Opções: `gupy`, `vagas`, `programathor`, `trampos`, `linkedin`, `theirstack`, `serpapi`. |
| **`--locations`** | Lista | `todos` | Filtra polos tecnológicos ou macrorregiões específicas. Ex: `--locations nordeste sul` ou `--locations "Recife" "Florianópolis" "São Paulo"`. |
| **`--start-page`** | Int | `1` | Página inicial da busca por portal. Permite pular direto para páginas mais profundas sem gastar requisições nas primeiras. |
| **`--max-pages`** | Int | `5` | Quantidade máxima de páginas/lotes navegados por termo em cada portal. |
| **`--page-size`** | Int | `100` | Limite de vagas por página (máximo 100 na Gupy; 25 na TheirStack). |
| **`--terms`** | Lista | 13 termos nativos | Sobrescreve os termos de busca padrão (definidos em `scraper/config.py`). |
| **`--delay`** | Float | `1.5` | Intervalo em segundos de espera entre requisições HTTP para respeito aos servidores. |
| **`--output`** | Caminho | `./output` | Diretório onde os arquivos CSV, relatórios e gráficos PNG são salvos. |
| **`--no-charts`** | Flag | `False` | Desativa a geração dos gráficos PNG pelo Matplotlib. |
| **`-v`, `--verbose`** | Flag | `False` | Habilita logs detalhados de depuração (nível `DEBUG`). |


#### Exemplos de Uso Avançado:

- **Coleta apenas no Nordeste e Sul:**
  ```powershell
  python main.py --locations nordeste sul
  ```

- **Coleta de teste rápida com 1 página e termos específicos:**
  ```powershell
  python main.py --terms "engenheiro de dados junior" "analista de dados junior" --max-pages 1
  ```

- **Coleta apenas na Gupy:**
  ```powershell
  python main.py --sources gupy
  ```

---

### 2. `scripts/import_csv.py` (Carga Idempotente no Banco de Dados)

Espelha os dados do CSV mais recente (ou de um CSV específico) para o banco de dados relacional.

```text
Uso: python scripts/import_csv.py [OPÇÕES]
```

#### Parâmetros Disponíveis:

| Flag | Tipo | Padrão | Descrição |
| :--- | :--- | :--- | :--- |
| **`--csv`** | Caminho | Último CSV em `output/` | Caminho do arquivo CSV que será importado. |
| **`--db`** | String | `data/vagas.db` | Caminho do arquivo SQLite local ou URL de conexão PostgreSQL (`postgresql://user:pass@host/db`). |
| **`--referencia`** | Data | Data do arquivo | Data âncora (`AAAA-MM-DD`) para cálculo de datas relativas (*"Há 3 dias"*, *"Ontem"*). |
| **`--recriar`** | Flag | `False` | **Atenção:** Apaga todas as tabelas e recria a base do zero antes de importar. |

#### Exemplos de Uso:

- **Importar o CSV mais recente com data fixa de auditoria:**
  ```powershell
  python scripts/import_csv.py --referencia 2026-08-12
  ```

- **Importar um CSV específico de uma quinzena passada:**
  ```powershell
  python scripts/import_csv.py --csv output/vagas_20260812_100000.csv
  ```

---

### 3. `scripts/report_db.py` (Relatório Estatístico Consolidado)

Analisa todas as vagas salvas no banco de dados SQLite/PostgreSQL e emite um relatório estatístico completo com percentuais, gráficos e tabelas.

```text
Uso: python scripts/report_db.py [OPÇÕES]
```

#### Parâmetros Disponíveis:

| Flag | Tipo | Padrão | Descrição |
| :--- | :--- | :--- | :--- |
| **`--db`** | String | `data/vagas.db` | Caminho do banco SQLite ou URL do PostgreSQL. |
| **`--no-export`** | Flag | `False` | Apenas exibe o resumo no terminal, sem salvar o arquivo `.md` em `output/`. |

#### Exemplo de Uso:
```powershell
python scripts/report_db.py
```

---

## 🗄️ Como Explorar os Dados no DBeaver

1. Abra o **DBeaver**.
2. Clique em **Nova Conexão $\rightarrow$ SQLite**.
3. No campo **Path**, selecione o arquivo:
   `c:\Users\rafael\Documents\vagas-tech-junior\data\vagas.db`
4. Clique em **Testar Conexão** e depois em **Concluir**.

### Consultas SQL Úteis para a Pesquisa:

#### A. Top 20 Tecnologias Mais Demandadas:
```sql
SELECT 
    t.nome AS tecnologia,
    t.categoria,
    COUNT(vt.vaga_id) AS total_vagas,
    ROUND(COUNT(vt.vaga_id) * 100.0 / (SELECT COUNT(*) FROM vagas), 1) AS percentual_vagas
FROM tecnologias t
JOIN vaga_tecnologia vt ON t.id = vt.tecnologia_id
GROUP BY t.nome, t.categoria
ORDER BY total_vagas DESC
LIMIT 20;
```

#### B. Distribuição de Vagas por Macrorregião e Modalidade:
```sql
SELECT 
    regiao,
    workplace_type AS modalidade,
    COUNT(*) AS total_vagas
FROM vagas
GROUP BY regiao, workplace_type
ORDER BY regiao, total_vagas DESC;
```

#### C. Tecnologias mais pedidas em vagas de Backend:
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

---

## 🌐 Executando a API REST Localmente

Para iniciar o servidor FastAPI e navegar pela documentação interativa (Swagger UI):

```powershell
uvicorn api.app:app --reload
```

Acesse no navegador: **[http://localhost:8000/docs](http://localhost:8000/docs)**.


---

## 🧪 Executando os Testes Automatizados

O projeto possui uma suíte com **mais de 260 testes unitários automatizados** cobrindo classificadores, coletores, expressões regulares e banco de dados:

```powershell
pytest
```

---

## 🤝 Créditos e Agradecimentos

Este projeto foi construído e expandido a partir da concepção original do repositório [**vagas-tech-junior**](https://github.com/EmidioLP/vagas-tech-junior), de autoria de **Emidio Lopes de Souza Neto** ([GitHub](https://github.com/EmidioLP) / [LinkedIn](https://www.linkedin.com/in/emidio-lopes/)).

