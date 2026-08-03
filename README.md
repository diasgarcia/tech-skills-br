# vagas-tech-junior

Raspagem de vagas de emprego para responder, **com dados reais**, uma pergunta:
qual área de tecnologia (Backend, Frontend, Data, Mobile, DevOps, QA, Fullstack,
Suporte/Infra, Segurança) tem mais vagas para desenvolvedores júnior no Brasil em 2026?

O projeto coleta vagas em portais públicos, filtra apenas nível de entrada
(júnior/estágio/trainee/aprendiz), classifica cada vaga em uma área de tecnologia
por palavras-chave, remove duplicatas e gera CSVs, gráficos e um relatório em
Markdown com o ranking.

### 🔗 API no ar: **[vagas-tech-junior-api.onrender.com/docs](https://vagas-tech-junior-api.onrender.com/docs)**

Documentação interativa — dá para filtrar as vagas pelo navegador, sem instalar
nada. Alguns exemplos diretos:

- [Vagas de Backend remotas](https://vagas-tech-junior-api.onrender.com/vagas?area=Backend&modalidade=Remoto)
- [Ranking das áreas](https://vagas-tech-junior-api.onrender.com/areas)
- [Tecnologias mais pedidas](https://vagas-tech-junior-api.onrender.com/tecnologias?com_vagas=true)

> Hospedada no plano gratuito do Render, que hiberna após 15 minutos sem uso —
> **o primeiro acesso pode levar cerca de 1 minuto**. Os seguintes são imediatos.

---

# Resultados

> **Coleta de 31/07/2026** — 940 vagas brutas da Gupy e do Vagas.com.br, das
> quais **182** sobraram após filtrar nível de entrada, remover duplicatas e
> descartar vagas fora de tecnologia. Os números abaixo são um retrato dessa
> data; rodar `python main.py` gera um novo.

## Qual área mais contrata júnior

![Vagas júnior de tecnologia por área](docs/grafico-areas.png)

| # | Área | Vagas | % |
|---|------|-------|---|
| 1 | Suporte/Infra | 54 | 29,7% |
| 2 | Outros/TI Geral | 43 | 23,6% |
| 3 | Backend | 29 | 15,9% |
| 4 | Data | 15 | 8,2% |
| 5 | Frontend | 9 | 4,9% |
| 6 | DevOps | 9 | 4,9% |
| 7 | Fullstack | 8 | 4,4% |
| 8 | Mobile | 6 | 3,3% |
| 9 | Segurança | 5 | 2,7% |
| 10 | QA | 4 | 2,2% |

**Suporte/Infra é quase um terço das vagas de entrada** — bem à frente de
qualquer área de desenvolvimento. É a porta mais larga para quem está começando,
e não costuma ser a primeira escolha de quem entra na área.

"Outros/TI Geral" com 23,6% não é falha de classificação: são títulos como
"Estágio em TI" ou "Desenvolvedor de Software Jr", dos quais realmente não dá
para inferir a área. Preferi deixá-los explícitos a distribuí-los por chute e
inflar alguma área artificialmente.

## Remoto, híbrido ou presencial

![Vagas júnior por modalidade de trabalho](docs/grafico-modalidade.png)

| Modalidade | Vagas | % |
|---|---|---|
| Presencial | 103 | 56,6% |
| Não informado | 31 | 17,0% |
| Híbrido | 30 | 16,5% |
| Remoto | 18 | 9,9% |

**Só 1 em cada 10 vagas júnior é remota.** Somando remoto e híbrido chega-se a
26,4% — a maioria exige presença física.

A distribuição por área é mais reveladora que o total: **Backend concentra 8 das
18 vagas remotas**, enquanto **Data não tem nenhuma** (7 híbridas, 5 presenciais,
3 sem informação). Quem busca trabalho remoto júnior está, na prática, olhando
para Backend.

A fatia "Não informado" é quase toda do Vagas.com, cujo card de listagem não
distingue híbrido de presencial — está detalhado em
[Modalidade de trabalho](#modalidade-de-trabalho).

## Tecnologias mais pedidas

![Tecnologias mais pedidas por área](docs/grafico-skills.png)

| Tecnologia | Vagas | | Tecnologia | Vagas |
|---|---|---|---|---|
| Inglês | 59 | | Metodologias Ágeis | 27 |
| SQL | 40 | | Java | 23 |
| Git | 38 | | Redes/TCP-IP | 23 |
| Windows | 37 | | Excel | 23 |
| Python | 32 | | JavaScript | 21 |
| ITIL | 32 | | API REST | 21 |

**SQL aparece no topo de Data, Backend e Suporte/Infra** — é a habilidade mais
transferível entre as três áreas com mais vagas. **Inglês** lidera o geral e
aparece em praticamente toda área.

Para quem mira Data, o dado desconfortável: o topo da área é **Excel e Power BI**
(9 vagas cada, de 15), seguidos de SQL e Python. Airflow, Spark e dbt não
aparecem no top 8. O que o mercado brasileiro chama de "Data júnior" hoje é
majoritariamente perfil de BI/analista, não de engenharia de dados.

## Como esses números foram apurados

Três decisões afetaram o resultado mais que qualquer ajuste de código, e todas
vieram de rodar contra dados reais:

- **48% das vagas coletadas não eram de tecnologia** ("Analista Contábil Jr",
  "Analista Fiscal Jr"). Sem um portão de relevância, o ranking mediria a
  população errada.
- **A área Segurança apareceu com 45 vagas, todas falso positivo**: a palavra
  `segurança` casava com "normas de segurança" no boilerplate de vagas de
  suporte. Depois da correção, são 5 — o número real.
- **`data` não pode ser keyword de Data em português**: casa com "**data** de
  admissão".

As regras estão em três YAMLs comentados, e o CSV traz uma coluna `area_matches`
com as keywords que dispararam cada classificação, para auditoria.

Limitações conhecidas estão em [Limitações honestas](#limitações-honestas).

---

## Fontes de dados

| Portal | Como é acessado | Status |
|--------|-----------------|--------|
| **Gupy** (`portal.gupy.io`) | Endpoint JSON público que o front do portal usa: `GET https://employability-portal.gupy.io/api/v1/jobs?jobName=<termo>&limit=<n>&offset=<n>` | Funcionando, sem autenticação |
| **Vagas.com.br** | HTML da busca (`/vagas-de-<termo>?pagina=<n>`), renderizado no servidor | Funcionando, sem Selenium |
| **ProgramaThor** | HTML da listagem (`/jobs?expertise=<nível>&page=<n>`), renderizado no servidor | Funcionando, volume pequeno |
| **Trampos.co** | API JSON pública que a SPA consome: `GET https://trampos.co/api/v2/opportunities?tr=<termo>&page=<n>` | Funcionando, volume pequeno |
| **Catho** | — | **Bloqueado** (ver abaixo) |
| **Indeed BR** | — | **Bloqueado** (ver abaixo) |

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

### Sobre a ProgramaThor

Portal 100% de tecnologia, com listagem renderizada no servidor. Duas
particularidades mudam a forma de integrar:

- **O parâmetro `?search=` é ignorado.** Buscar `?search=python` devolve
  exatamente o mesmo conjunto de vagas que a listagem sem filtro — conferido
  comparando os ids retornados. Já `?expertise=` e `?page=` funcionam. Por isso
  esta fonte não percorre os 13 termos de busca do projeto: usa os filtros
  nativos de nível de entrada (`expertise=Júnior`, `contract_type=Estágio`) e
  faz duas consultas em vez de treze inúteis.
- **Vagas expiradas continuam na listagem**, marcadas com um selo "Vencida". São
  descartadas, e são a maioria: das 75 vagas "Júnior" nas 5 primeiras páginas,
  **68 estavam vencidas (91%)**, e as de estágio estavam 100% expiradas. As
  ativas ficam nas primeiras páginas — da página 6 em diante não há nenhuma.

O volume real é pequeno (**7 vagas júnior abertas** na coleta de 03/08/2026),
mas o card traz **senioridade e tecnologias declaradas pelo próprio portal**, o
que serve para conferir a classificação por keywords do projeto contra uma
categorização nativa. A senioridade declarada é respeitada em vez do regex de
título: "Programador(a) PHP" não tem marca de nível nenhuma, mas o portal a
classifica como Júnior.

### Sobre o Trampos.co

O site é uma SPA em Ember: o HTML entregue traz só um `<noscript>` de fallback,
sem link nem id por vaga. O que serve é a API JSON que o app consome, pública e
sem autenticação, descoberta na aba Network.

Os nomes dos parâmetros não são óbvios e foram mapeados por tentativa contra a
API: **`tr` é a busca textual** (cobre título e descrição) e `lc` é localização.
`q`, `s`, `category` e afins são silenciosamente ignorados.

Dois pontos que o código trata:

- O portal é **misto** — publica vagas de Comunicação e de TI no mesmo lugar. A
  categoria nativa entra na descrição para o portão de relevância decidir. Numa
  coleta real, das 12 vagas de nível de entrada encontradas, **11 eram de
  Administrativo, Comercial, Mídia e Publicidade** e só 1 era de tecnologia.
- A listagem **não traz a descrição da vaga**. Existe uma `company.description`,
  mas ela descreve a *empresa* — usá-la para classificar faria qualquer vaga de
  uma empresa de tecnologia parecer vaga de tecnologia. Só entram fatos da
  própria vaga.

A modalidade vem de flags nativas (`home_office`, `hybrid`). Vale registrar que
a fama de portal remoto **não se confirmou no recorte júnior**: das 12 vagas de
entrada, 3 remotas, 3 híbridas e 6 presenciais.

### Sobre a Catho — bloqueada

A Catho não é acessível por cliente HTTP simples: qualquer requisição sem
navegador real recebe `HTTP 404` com a página "Operação Inválida!" — inclusive
a home do site, não só a busca. Não é uma questão de renderização de JavaScript
que Selenium resolveria sozinho.

**Nenhum dado da Catho é simulado neste projeto.** Por isso a fonte ficou de
fora. A estrutura de `scraper/sources/` foi feita para receber uma fonte nova
em um arquivo só — **Remotar** e **Gupy Vagas** são candidatos ainda não
avaliados.

### Sobre o Indeed BR — bloqueado

O Indeed responde **HTTP 403 do Cloudflare** com o cabeçalho
`Cf-Mitigated: challenge`, tanto com o User-Agent do projeto quanto com um de
navegador. É um desafio de bot no edge, não uma questão de renderização.

Assim como na Catho, **nenhum dado do Indeed é simulado**: a fonte foi avaliada,
documentada e deixada de fora.

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
- `grafico_modalidade_<timestamp>.png` — distribuição por remoto / híbrido / presencial.
- `grafico_skills_<timestamp>.png` — tecnologias mais pedidas por área.

Os gráficos saem em PNG (200 dpi). Use `--no-charts` para pular essa etapa.

Os CSVs saem em `utf-8-sig`, então abrem direto no Excel com acentuação correta.

---

## API REST (opcional)

Há uma API **somente leitura** sobre os dados coletados. Ela não substitui o
pipeline: as vagas continuam entrando pelo scraper, e a API só as expõe por HTTP.

**No ar em [vagas-tech-junior-api.onrender.com/docs](https://vagas-tech-junior-api.onrender.com/docs)**
(primeiro acesso pode levar ~1 min — o plano gratuito hiberna).

Para rodar na sua máquina:

```bash
pip install -r requirements.txt
```

```bash
python scripts/import_csv.py
```

```bash
uvicorn api.app:app --reload
```

Documentação interativa em **http://127.0.0.1:8000/docs** (`127.0.0.1` é a sua
própria máquina).

### Endpoints

| Método | Rota | O que faz |
|---|---|---|
| GET | `/vagas` | Lista vagas. Filtros: `area`, `tecnologia`, `modalidade`, `fonte`, `q` (título), `limit`, `offset` |
| GET | `/vagas/{id}` | Detalhe da vaga, com descrição completa |
| GET | `/areas` | As 10 áreas com contagem e percentual |
| GET | `/areas/{nome}` | Uma área |
| GET | `/tecnologias` | As 114 tecnologias com contagem de menções. Filtros: `grupo`, `com_vagas` |
| GET | `/tecnologias/{nome}` | Uma tecnologia |

Exemplos, contra a instância pública:

```bash
curl "https://vagas-tech-junior-api.onrender.com/vagas?area=Backend&modalidade=Remoto&limit=5"
```

```bash
curl "https://vagas-tech-junior-api.onrender.com/tecnologias?grupo=linguagens&com_vagas=true"
```

**Não há `POST`, `PUT` nem `DELETE`** — os dados vêm da raspagem, e escrever por
HTTP criaria um estado que a próxima importação sobrescreveria. Esses verbos
respondem `405`.

Erros: `404` para vaga/área/tecnologia inexistente, `422` para parâmetro fora do
vocabulário (`?area=Inexistente`), sempre no formato `{"detail": "..."}`.

### Banco

SQLite em `data/vagas.db` (ignorado pelo git — é reconstruível a partir do CSV).
`scripts/import_csv.py` pega o CSV mais recente de `output/`, ou um específico
com `--csv`; `--recriar` zera as tabelas antes.

A importação é **idempotente**: a identidade da vaga é o par
`(source, external_id)`, então rodar de novo atualiza em vez de duplicar.

Duas decisões de modelagem que valem menção:

- **`skills` vira relação.** A string `"Excel, Python, SQL"` do CSV é
  normalizada numa tabela `tecnologias` + associação muitos-para-muitos. Sem
  isso não dá para filtrar nem contar direito.
- **`/areas` e `/tecnologias` são calculados da tabela de vagas**, nunca lidos
  de `ranking_areas.csv` ou `skills_por_area.csv`. Esses CSVs são recortes já
  agregados — o de skills é truncado no top-15 de cada área, então serviria
  números errados.

### Datas

O CSV traz três formatos: ISO (`2026-06-26`, Gupy), `dd/mm/aaaa` (Vagas.com) e
relativo (`"Ontem"`, `"Há 3 dias"`, Vagas.com). O importador converte tudo para
um único campo `DATE`.

As expressões relativas são resolvidas contra a **data de geração do CSV**
(extraída do timestamp no nome do arquivo), não contra a data de hoje — assim
importar um CSV de duas semanas atrás produz as mesmas datas que produziria no
dia da coleta.

Fora da máquina que coletou, o nome do arquivo pode não ter o timestamp e o
`mtime` deixa de ser confiável (num deploy, o clone do git carimba a data do
deploy). Por isso o snapshot é importado com a data fixa:

```bash
python scripts/import_csv.py --csv seed/vagas.csv --referencia 2026-07-31
```

### Deploy

`render.yaml` sobe a API no [Render](https://render.com) — basta apontar o
serviço para o repositório.

O disco do plano free é efêmero, então **o banco não é persistido**: ele é
reconstruído do snapshot em `seed/vagas.csv` toda vez que o serviço sobe (182
linhas, ~1s). O build usa `requirements-api.txt`, sem matplotlib, que a API
nunca importa.

O scraper **não roda no servidor**, de propósito: portais de vaga costumam
bloquear IP de nuvem. O deploy serve um snapshot datado. Para atualizar, rode
a coleta na sua máquina e faça commit de um novo `seed/vagas.csv`, ajustando
`--referencia` no `render.yaml`.

No plano free o serviço hiberna após 15 minutos parado, e o primeiro acesso
depois disso leva ~50s para responder.

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

### Modalidade de trabalho

As vagas são classificadas em **Remoto**, **Híbrido**, **Presencial** e
**Não informado**, com origens diferentes por portal:

- **Gupy** expõe a modalidade explicitamente no campo `workplaceType`
  (`remote` / `hybrid` / `on-site`) — é dado afirmado pelo portal.
- **Vagas.com** classifica as vagas em três modalidades ("Na empresa",
  "Na empresa e Home Office", "100% Home Office"), mas **o card da listagem só
  mostra "100% Home Office" ou o nome da cidade** — um card híbrido e um
  presencial são indistinguíveis ali. Por isso só o remoto é afirmado; o resto
  fica como "Não informado" em vez de ser adivinhado como presencial.

As três modalidades existem como filtro de busca no Vagas.com, mas os resultados
filtrados não reconciliam com a paginação da busca normal (para alguns termos o
filtro "Na empresa" sozinho já devolve a página inteira), então esse caminho foi
descartado.

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
├── main.py                  # CLI do scraper
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
│       ├── vagas_com.py
│       ├── programathor.py
│       └── trampos.py
├── api/                     # API REST somente leitura (opcional)
│   ├── app.py               # FastAPI, /docs, handlers de erro
│   ├── database.py          # engine e sessão SQLAlchemy
│   ├── models.py            # tabelas: vagas, tecnologias, associação
│   ├── schemas.py           # Pydantic (respostas)
│   ├── crud.py              # consultas e filtros
│   ├── dates.py             # normalização das datas para DATE
│   ├── vocabulary.py        # áreas e tecnologias, lidas dos YAMLs
│   └── routers/
├── scripts/
│   └── import_csv.py        # CSV → SQLite, idempotente
└── tests/                   # 192 testes, sem rede
    └── api/                 # testes da API (pulados sem FastAPI)
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

São 192 testes e nenhum acessa a rede: os parsers são testados contra respostas
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
- **A fatia "Não informado" da modalidade é quase toda do Vagas.com**, pelo
  motivo explicado acima. Entre as vagas em que o portal afirma a modalidade
  (as da Gupy), não há indefinição — se quiser só o dado afirmado, filtre o CSV
  por `source = gupy`.
- **Os portais mudam.** Se a Gupy alterar o endpoint ou o Vagas.com mudar as
  classes do HTML, o coletor correspondente para de trazer resultados (e avisa
  no log, sem inventar dados).
