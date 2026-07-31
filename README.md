# vagas-tech-junior

Raspagem de vagas de emprego para responder, **com dados reais**, uma pergunta:
qual área de tecnologia (Backend, Frontend, Data, Mobile, DevOps, QA, Fullstack,
Suporte/Infra, Segurança) tem mais vagas para desenvolvedores júnior no Brasil em 2026?

O projeto coleta vagas em portais públicos, filtra apenas nível de entrada
(júnior/estágio/trainee/aprendiz), classifica cada vaga em uma área de tecnologia
por palavras-chave, remove duplicatas e gera CSVs + um relatório em Markdown com
o ranking.

---

## Fontes de dados

| Portal | Como é acessado | Status |
|--------|-----------------|--------|
| **Gupy** (`portal.gupy.io`) | Endpoint JSON público que o front do portal usa: `GET https://employability-portal.gupy.io/api/v1/jobs?jobName=<termo>&limit=<n>&offset=<n>` | Funcionando, sem autenticação |
| **Vagas.com.br** | HTML da busca (`/vagas-de-<termo>?pagina=<n>`), renderizado no servidor | Funcionando, sem Selenium |
| **Catho** | — | **Bloqueado** (ver abaixo) |

### Sobre a Gupy

O endpoint acima **não** é a API oficial `api.gupy.io` (essa exige token de
empresa). É o mesmo JSON que o navegador chama ao usar a busca do portal,
descoberto inspecionando a aba Network em `portal.gupy.io/job-search/term=...`.
É público e não pede login.

Dois detalhes descobertos testando o endpoint ao vivo, e que o código trata:

- `limit` máximo é **100** — acima disso a API responde `HTTP 400`.
- `pagination.total` **não é confiável**: vem limitado ao tamanho da página
  (com `limit=100` ele responde `total=100` mesmo havendo centenas de vagas).
  Por isso a paginação vai até receber uma página vazia, e não até bater o `total`.

### Sobre o Vagas.com.br

Ao contrário do que se costuma supor, a listagem de busca do Vagas.com é
renderizada no servidor — os cards já vêm no HTML. **Não é preciso
Selenium/Playwright**; `requests` + BeautifulSoup bastam. Isso foi verificado
ao vivo antes de escrever o parser.

Ponto de atenção: o Vagas.com devolve apenas um *trecho* da descrição (texto de
marketing), enquanto a Gupy devolve a descrição completa. O classificador leva
isso em conta (veja "Portão de relevância" abaixo).

### Sobre a Catho — bloqueada

A Catho não é acessível por cliente HTTP simples: qualquer requisição sem
navegador real recebe `HTTP 404` com a página "Operação Inválida!" — inclusive
a home do site, não só a busca. Não é uma questão de renderização de JavaScript
que Selenium resolveria sozinho.

**Nenhum dado da Catho é simulado neste projeto.** Por isso a fonte ficou de
fora, e o caminho recomendado é trocar por outra fonte pública: **LinkedIn Jobs**
(guest API), **Indeed BR**, **Programathor**, **Trampos.co** ou **Remotar** — a
estrutura de `scraper/sources/` foi feita para receber uma fonte nova em um
arquivo só.

---

## Instalação

Requer Python 3.10+.

```bash
git clone <url-do-seu-repo> vagas-tech-junior
cd vagas-tech-junior
python -m venv venv
```

Ative o ambiente virtual:

```bash
venv\Scripts\activate
```

No Linux/macOS use `source venv/bin/activate`. Depois instale as dependências:

```bash
pip install -r requirements.txt
```

## Como rodar

Coleta completa (Gupy + Vagas.com, 13 termos de busca):

```bash
python main.py
```

Outros exemplos:

```bash
python main.py --sources gupy
```

```bash
python main.py --terms "engenheiro de dados junior" "estagio dados" --max-pages 3
```

```bash
python main.py --strict --delay 3
```

### Opções

| Flag | Efeito |
|------|--------|
| `--sources gupy vagas` | Quais portais consultar |
| `--terms "..." "..."` | Substitui a lista padrão de termos |
| `--max-pages N` | Máximo de páginas por termo, por portal (padrão 5) |
| `--page-size N` | Vagas por página (a Gupy limita a 100) |
| `--delay S` | Segundos entre requests (padrão 1.5) |
| `--output DIR` | Diretório de saída (padrão `./output`) |
| `--strict` | Descarta títulos mistos como "Desenvolvedor Júnior/Pleno" |
| `--all-levels` | Não filtra por senioridade |
| `--keep-non-tech` | Mantém vagas fora de tecnologia que a busca solta devolve |
| `--no-charts` | Não gera os gráficos PNG |
| `-v` | Log detalhado |

## Saídas

Gravadas em `output/` (ignorado pelo git), com timestamp no nome:

- `vagas_<timestamp>.csv` — todas as vagas classificadas, uma por linha, com
  área, senioridade, empresa, local, URL, tecnologias citadas (coluna `skills`)
  e quais keywords dispararam a classificação (coluna `area_matches`, útil para
  depurar as regras).
- `ranking_areas_<timestamp>.csv` — ranking de áreas por quantidade de vagas.
- `skills_por_area_<timestamp>.csv` — tecnologias mais pedidas em cada área,
  em formato longo (`area, posicao, tecnologia, vagas`).
- `relatorio_<timestamp>.md` — relatório legível: ranking, distribuição por
  senioridade e portal, tecnologias mais pedidas, top empresas e amostra de
  vagas por área.
- `grafico_areas_<timestamp>.png` — distribuição das vagas por área.
- `grafico_skills_<timestamp>.png` — tecnologias mais pedidas por área.

Os gráficos saem em PNG (200 dpi). Use `--no-charts` para pular essa etapa.

Os CSVs saem em `utf-8-sig`, então abrem direto no Excel com acentuação correta.

---

## Como funciona

```
coleta (por portal, por termo)
   ↓
filtro de senioridade      → mantém júnior / estágio / trainee / aprendiz
   ↓
deduplicação               → por ID do portal, depois por título+empresa
   ↓
portão de relevância tech  → descarta "Analista Contábil Jr" e afins
   ↓
classificação por área     → keywords ponderadas
   ↓
extração de tecnologias    → quais linguagens/ferramentas a vaga cita
   ↓
exportação                 → 3 CSVs + relatório .md + 2 gráficos PNG
```

### Portão de relevância ("é vaga de tech?")

A busca dos portais é solta e devolve muita coisa que não é tecnologia
(`Analista Contábil Jr`, `Analista Fiscal Jr`, `Analista de Ouvidoria Junior`).
Se essas vagas ficassem no dataset, o ranking mediria a população errada — na
primeira execução deste projeto elas representavam **48%** do total.

O **título** é o sinal confiável; a descrição nem sempre é (o Vagas.com só
devolve um trecho de marketing, cheio de palavra genérica como "sistemas" ou
"aplicação", que apareceria até numa vaga administrativa). Por isso o portão tem
listas com rigor diferente, em `tech_gate` no `areas.yml`:

1. título casa `tech_gate.titulo` (sinais amplos), **ou**
2. título casa uma keyword `peso_alto` de qualquer área, **ou**
3. descrição casa `tech_gate.descricao` (sinais estritos) ou uma `peso_alto`.

E `tech_gate.excluir` derruba contextos onde as palavras acima não significam
tecnologia: "Pesquisa e Desenvolvimento" (P&D industrial), "Odontologia Digital",
"Segurança do Trabalho", "Tecnologia Educacional".

### Classificação por área

Cada área tem keywords em duas faixas de peso (`peso_alto` = 4.0,
`peso_medio` = 1.0). Keyword encontrada no **título** vale 3× o que vale na
descrição (`title_boost`), porque o título é muito mais confiável.

Duas regras evitam classificação por evidência frágil:

- **Título dominante** — se alguma área foi sinalizada pelo título, só essas
  áreas disputam. Sem isso, uma descrição longa da Gupy que cita "dados" de
  passagem ("proteção de dados", "dados cadastrais") transformava uma vaga de
  *Governança de TI* em vaga de *Data*.
- **`min_score` = 3.0** (o valor de uma keyword `peso_medio` no título) — abaixo
  disso a vaga cai em "Outros/TI Geral". Um único "dados" solto numa descrição
  não basta para definir a área.

O efeito é que "Outros/TI Geral" fica com ~23% das vagas — títulos como
"Estágio em TI", "Estágio em Desenvolvimento" ou "Desenvolvedor de Software Jr",
dos quais realmente **não dá** para inferir a área. Preferi deixá-los explícitos
a distribuí-los por chute.

As keywords são casadas como palavra/frase inteira sobre o texto normalizado
(minúsculas, sem acento, pontuação virando espaço). Isso evita que "go" case
dentro de "Goiânia" ou "java" dentro de "javascript".

### Extração de tecnologias

Cada vaga é varrida atrás das tecnologias listadas em
`scraper/rules/skills.yml` (linguagens, frameworks, bancos, cloud, ferramentas
de dados/QA/suporte e práticas como Scrum e Inglês). O resultado alimenta a
coluna `skills` do CSV e o segundo gráfico.

A extração roda **antes** da exportação de propósito: o CSV trunca a descrição
em 500 caracteres, e a Gupy devolve descrições longas onde a maior parte das
tecnologias é citada.

Aqui o texto passa por uma normalização própria que **preserva `#` e `+`** — com
a normalização padrão do projeto, `C#` viraria `c` e casaria com qualquer letra
"c" solta no texto.

### Gráficos

Duas decisões de forma, ambas visíveis em `scraper/charts.py`:

- **Uma cor só, não um degradê por valor.** Áreas de tecnologia são categorias
  *nominais* (não têm ordem natural). Pintar a barra maior mais escura gastaria
  o canal de cor repetindo o que o comprimento da barra já diz.
- **Small multiples para as tecnologias** — um painel por área, em vez de 8 cores
  disputando a mesma figura. A pergunta é "quais techs nesta área?", e cada
  painel responde isso sozinho.

O raio do canto arredondado é calculado em **pixels** e convertido para unidades
de dado de cada painel. O caminho óbvio no matplotlib (raio fixo em unidades de
dado) deforma o canto quando os eixos têm escalas diferentes: num painel cujo
eixo x vai só até 3, o raio vira uma "pílula" horizontal.

### Editando as regras

Toda a lógica de negócio está em três YAMLs comentados — **você não precisa
mexer em Python para ajustar**:

- **`scraper/rules/areas.yml`** — áreas, keywords, pesos e o portão de relevância.
- **`scraper/rules/seniority.yml`** — o que conta como nível de entrada e o que
  é nível acima.
- **`scraper/rules/skills.yml`** — tecnologias procuradas e seus apelidos.

Duas armadilhas já documentadas lá dentro, aprendidas rodando com dados reais:

- não coloque `data` como keyword de Data: em português casa com "**data** de
  admissão";
- não coloque `seguranca` sozinho na área Segurança: casa com "normas de
  **segurança**" no boilerplate de qualquer vaga de suporte, e com "**Segurança**
  do Trabalho". Isso inflou a área de 4 para 45 vagas na primeira execução.

### Educação com o servidor

- User-Agent identificável (não finge ser navegador).
- Delay de 1.5 s entre requests, com jitter, configurável via `--delay`.
- Retry com backoff exponencial em 429/5xx e erros de conexão, respeitando
  `Retry-After`.
- Falha em um termo ou portal não derruba a coleta inteira — o erro é registrado
  e reportado no fim.
- Paginação para assim que uma página vem vazia ou repetida.

---

## Estrutura

```
vagas-tech-junior/
├── main.py                  # CLI
├── requirements.txt
├── README.md
├── .gitignore
├── scraper/
│   ├── config.py            # termos de busca, delays, caminhos
│   ├── models.py            # dataclass Job, normalização de texto
│   ├── http_client.py       # sessão educada: delay + retry + UA
│   ├── seniority.py         # filtro júnior/estágio/trainee
│   ├── classifier.py        # portão de tech + classificação por área
│   ├── skills.py            # extração de tecnologias citadas
│   ├── dedupe.py            # remoção de duplicatas
│   ├── export.py            # CSVs e relatório .md
│   ├── charts.py            # gráficos PNG
│   ├── pipeline.py          # orquestração
│   ├── rules/
│   │   ├── areas.yml        # ← regras de área (edite aqui)
│   │   ├── seniority.yml    # ← regras de senioridade (edite aqui)
│   │   └── skills.yml       # ← tecnologias procuradas (edite aqui)
│   └── sources/
│       ├── base.py          # contrato JobSource
│       ├── gupy.py
│       └── vagas_com.py
└── tests/                   # 84 testes, sem rede
```

### Adicionando um portal novo

1. Crie `scraper/sources/meu_portal.py` com uma classe que herda de `JobSource`
   e implementa `fetch_term(term) -> list[Job]`.
2. Registre em `scraper/sources/__init__.py`, no `SOURCE_REGISTRY`.

Pronto — ele passa a aceitar `--sources meu_portal` e reaproveita filtro,
classificação, dedupe e exportação.

## Testes

```bash
python -m pytest -q
```

São 84 testes e nenhum acessa a rede: os parsers são testados contra respostas
reais capturadas dos portais e fixadas em `tests/test_sources.py`.

---

## Limitações honestas

- **É uma amostra, não o mercado inteiro.** O resultado depende dos termos de
  busca em `config.py` e dos portais consultados. Termos diferentes mudam o
  ranking.
- **Viés de portal.** Gupy e Vagas.com têm perfis de empresa diferentes; nenhum
  representa o mercado brasileiro todo.
- **Vagas replicadas por cidade** (uma mesma posição anunciada em 20 comarcas)
  contam como 20 vagas, porque são de fato 20 posições abertas — mas isso pesa
  no ranking. Olhe a coluna `company` no CSV se um número parecer estranho.
- **Classificação por keyword erra em casos ambíguos.** A coluna `area_matches`
  mostra exatamente o que disparou cada classificação, para você auditar e
  ajustar o YAML.
- **Áreas pequenas dão contagens de tecnologia instáveis.** Com 9 vagas em
  DevOps, uma tecnologia citada em 2 delas já entra no top 8 — o gráfico de
  skills é confiável para Suporte/Infra, Backend e Data, e apenas indicativo
  para as áreas com menos de ~15 vagas.
- **A extração de tecnologias mede menção, não exigência.** Uma vaga que diz
  "diferencial: Python" conta igual a uma que exige Python.
- **Os portais mudam.** Se a Gupy alterar o endpoint ou o Vagas.com mudar as
  classes do HTML, o coletor correspondente para de trazer resultados (e avisa
  no log, sem inventar dados).
