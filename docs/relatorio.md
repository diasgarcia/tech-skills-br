### 20/08/2026

Comecei a trabalhar no projeto a partir da base existente. Criei o mapeamento de 14 polos tecnológicos e 5 macrorregiões. Implementei a inferência de modalidade de trabalho no modelo Job. Melhorei a sessão HTTP com suporte a POST e GET JSON.

---

### 21/08/2026

Implementei o coletor SerpApi para busca estruturada no Google Jobs. Implementei o coletor TheirStack com enriquecimento de tecnologias. Refinei a detecção de modalidade do LinkedIn. Expandi a taxonomia de skills para 217 tecnologias.

---

### 22/08/2026

Desacoplei as fontes com cota da execução padrão. Adicionei a opção --start-page. Integrei novas opções de linha de comando. Criei gráficos analíticos estratificados. Adicionei os campos regiao e polo ao modelo ORM. Enriqueci a importação idempotente. Adicionei o relatório estatístico da base consolidada.

---

### 23/08/2026

Criei o exportador de snapshot versionado. A base consolidada chegou a 1540 vagas. Atualizei os metadados da API para a pesquisa PIBIC. Reescrevi o README com foco acadêmico. Criei o manual de uso detalhado. Criei a especificação técnica da arquitetura.

---

### 24/08/2026

Alinhei a identificação do projeto para tech-skills-br. Removi dados legados. Ajustei as licenças. Adicionei CI no GitHub Actions. Organizei relatórios e gráficos em docs/relatorios.

---

### 25/08/2026

Adicionei a automação de coleta diária no GitHub Actions. Refinei a taxonomia de senioridade. Desmembrei as áreas de Suporte, Infraestrutura e Engenharia de Software. Aumentei a paginação padrão de 5 para 15 páginas por termo. Expandi o catálogo geográfico para 27 capitais. Expandi a taxonomia para 14 áreas. Adicionei deduplicação por URL canônica. Implementei o site minimalista e a API JSON estática. Defini a data de corte em 01/01/2026. Eliminei vagas inativas legadas. Criei o workflow de deploy no GitHub Pages.

Tentei várias abordagens contra o Cloudflare do ProgramaThor: User-Agent atualizado, curl_cffi com impersonate do Chrome, Playwright Chromium headless. Criei a busca de descrição completa do LinkedIn. Expandi os termos de busca. Desmembrei Service Desk, Hardware e Segurança da Informação em subáreas. Criei a área de Inteligência Artificial separada de Data. Adicionei Copilots e LLMs à taxonomia. A base chegou a 2057 vagas.

---

### 26/08/2026

Adicionei aliases case-sensitive às skills. Mantive a descrição completa no CSV. Melhorei o enriquecimento do LinkedIn com retry. Configurei 3 rodadas diárias com enriquecimento só de pendentes.

---

### 27/08/2026

Adicionei a janela de 30 dias ao enriquecimento. Recuperei descrições truncadas da Gupy. Cobri http_client, pipeline, paginação e config com testes. Corrigi a modalidade do LinkedIn usando o título. Sincronizei o push do bot com retry. Troquei os crons nativos por gatilho externo via API de dispatch. Criei o enriquecimento de Vagas.com, Trampos e ProgramaThor. Recuperei 5 descrições truncadas da Gupy. Removi 98 vagas da Gupy de vez.

---

### 28/08/2026

Corrigi o import: linha sem descrição não rebaixa a área. Marquei vaga com 404 como encerrada. Criei a regra de ignorar seções de benefícios na extração de skills. Criei a reclassificação retroativa de áreas. Removi 28 vagas fora do escopo. Reclassifiquei 170 áreas. Removi a API REST FastAPI, os containers e o deploy dedicado. O projeto ficou só com JSON estáticos. Fiz a limpeza de comentários do código. Revisei o README e os documentos. Mudei o site para a pasta site/ na raiz. Depois mudei para api/web e .github/web. Removi o SerpApi e o TheirStack. O projeto ficou só com fontes públicas. Adicionei meu nome à licença.

---

### 29/08/2026

Corrigi o campo enrich_encerrada para booleano. Achei um bug: o import marcava todas as vagas como encerradas. Corrigi. Travei as dependências nas versões do Python 3.12. O CI passou a testar só no 3.12. Adicionei o workflow manual de enriquecimento. Expandi a taxonomia: GPO, Fortigate, Antivírus, Bitdefender, Ubiquiti, Backup, Hyper-V, Windows Server, Power Automate e Word.

Implementei o coletor Solides via endpoint público do portal. Usei os filtros nativos de nível. A fonte trouxe 84% de vagas inéditas no piloto. Implementei o coletor GeekHunter via SSR público. O enriquecimento extrai empresa e data do JSON-LD. Criei o avaliador de contribuição marginal de fonte. Mudei o Trampos para varredura completa. Adicionei o filtro de aprendiz na Solides. Separei estagio de estagiario. Movi os filtros de coleta para o YAML. Removi o ProgramaThor e o Playwright. A fonte bloqueava o runner e rendia pouco.

Também fiz correções e melhorias na interface web do projeto.

---

### 30/08/2026

Melhorei a busca do explorador de vagas: detecção automática de cidade/polo/região na query, termos combinados com E lógico e casamento por prefixo enquanto se digita (ex.: "sao p" já filtra São Paulo). Numerei os commits do bot por rodada (09h16 - 1, 14h16 - 2, 19h16 - 3, fora disso - manual N) usando a hora de início do job.

Descobri e corrigi três bugs ao re-verificar 50% da base (1355 vagas ao vivo + 44 lidas na mão): seções de "Benefícios" no meio do texto cortavam os requisitos (vaga da Camisaria FMW perdia Hardware/Windows); a janela de 30 dias deixava 35 vagas do LinkedIn órfãs de descrição para sempre; o snippet do Vagas.com (313-400 chars, com "...") ficava fora do gate de enriquecimento. Ainda: o enrich da GeekHunter gravava data antiga do JSON-LD furando o corte de 2026, e o cliente HTTP respeitava Retry-After sem teto — o Cloudflare mandou 429 com 23h e a coleta dormiria tudo.

Adicionei o modo navegador ao PoliteSession via curl_cffi (impersonate do Chrome), que passou no bot-check do Cloudflare onde o requests puro tomava ban. O enriquecimento do Vagas.com passou a parar no primeiro 429 e a persistir o progresso a cada 10 preenchimentos. A base caiu de 2795 para 2787 vagas ao cortar 8 zumbis de 2025 que o enriquecimento re-injetava.

### 31/08/2026

Achei mais um bug sério na importação: linha sem skills sobrescrevia as tecnologias do banco com lista vazia — o CSV da coleta roda com --no-enrich e o LinkedIn re-coletado chegava sem skills, apagando a cada rodada o que o enriquecimento tinha acumulado (os vínculos caíram de 14896 para 9603). Corrigi para preservar quando a linha vem vazia e re-extraí a base inteira (14833 vínculos, 2387 vagas com skills).

Corrigi o stop do primeiro 429 para parar de verdade (as futures já enfileiradas martelavam o IP banido). Rodei uma coleta manual do GitHub para validar. Criei o board Tech Skills BR no GitHub Projects com as pendências em issues. Restam 58 descrições truncadas do Vagas.com, que as rodadas noturnas preenchem em lotes por causa do rate limit do Cloudflare.

---

### 01/09/2026

Rodei as três coletas automáticas do dia e um enriquecimento manual. Sem mudanças de código.

---

### 02/09/2026

Corrigi os ids instáveis das vagas entre as runs do CI. O seed passou a exportar a coluna db_id. O import restaura o id original. O vagas.json parou de mudar inteiro a cada coleta. Simulei duas runs com banco do zero: zero ids diferentes nas 3067 vagas.

Melhorei a classificação por área. Título específico vence o genérico. Suporte disfarçado de "Analista de Sistemas" vira Suporte Técnico. Movi 26 vagas e revisei uma a uma. Removi psycopg e httpx. O projeto ficou SQLite-only.

Corrigi o import. Snippet novo não regride descrição enriquecida. A fila de pendentes drenou de verdade. O enriquecimento passou a parar o lote da fonte no primeiro 429. O LinkedIn ganhou a proteção que não tinha. Os commits de dados ganharam resumo da rodada no corpo. O rótulo do commit veio dos inputs do dispatch. Removi o critério "500 caracteres exatos" da fila do LinkedIn. Busca com sucesso marca a vaga como resolvida. Silenciei avisos repetidos do matplotlib no runner.

---

### 03/09/2026

Corrigi as URLs do Solides. O redirectLink antigo usava subdomínios que não resolvem mais em DNS. O coletor passou a gravar a URL canônica do portal. Corrigi 678 URLs na base.

Criei o portão novo. Vagas de campo, vendas, call center e loja saem da base. Medido: 61 vagas não-tech a menos. Mudei a classificação. Suporte Técnico virou área genérica. Título específico vence. "Analista de Suporte N1" vai para Service Desk. "Técnico Suporte Volante" vai para Field Service. Reclassifiquei 139 vagas. Removi 6 não-tech.

Testei dois experimentos contra o 429 do Cloudflare no Vagas.com: fingerprint Safari e warm-up de sessão. Nenhum mudou o resultado. O limite é por IP. Reverti o Safari. Os logs da coleta e do enriquecimento passaram a aparecer ao vivo no runner.

Corrigi a senioridade. "N1.5" é tier de suporte, não nível de entrada. Três vagas pleno/sênior saíram da base. Criei contextos de descarte para "eletrônica" como adjetivo. Dois falsos positivos saíram. Corrigi a empresa da Gupy em páginas compartilhadas. O nome vem do subdomínio, não do careerPageName. Adicionei ferramentas de suporte ao vocabulário: Suporte Remoto, Clonezilla, VirtualBox, SharePoint, Microsoft Teams e ITSM. Re-extraí as skills na base inteira. Revalidei 59 empresas do GeekHunter com o JSON-LD. A busca do dashboard ganhou filtro por fonte. A cidade vence o polo regional no display. Limpei comentários redundantes do código.

---

### 04/09/2026

Implementei o coletor do InfoJobs. A busca pública é renderizada no servidor. Júnior entra pela busca textual. Estágio, trainee e aprendiz entram pelos filtros nativos de contrato. A primeira coleta completa trouxe 378 vagas novas. A fonte virou a quarta maior da base.

O enriquecimento do InfoJobs busca a descrição completa no detalhe da vaga. O teaser da listagem tem 153 caracteres fixos. Vaga encerrada vira 404. O bloqueio suave não marca vaga como encerrada.

Revisei 38 vagas do InfoJobs uma a uma. Corrigi aliases que não casavam. Adicionei Pacote Office, ServiceNow, Storage, Google Sheets, DAX, AutoCAD, PABX e Robótica ao vocabulário. Fibra óptica virou alias de Redes de Computadores. A cobertura subiu de 55% para 99%.

Canonicalizei a senioridade: "Estagiário" virou "Estágio" no import e 10 vagas da base foram re-rotuladas. Canonicalizei nomes de empresa: variantes de "Confidencial" e sufixos societários ("ltda", "sa", "holding"...) deixaram de criar empresas duplicadas. Normalizei as empresas da base e corrigi 62 slugs do GeekHunter.

Adicionei o CITATION.cff (formato 1.2.0) no main e na branch do congresso. Alinhei o README ao Python 3.12 e registrei o InfoJobs no execucao-rapida. Os gráficos e o relatório consolidado passaram a ser gerados só na rodada das 09h16 (as outras duas só coletam, importam e enriquecem).

Implementei o coletor da Abler via sitemap público com checkpoint incremental (rodada interrompida retoma sem refazer GET). A primeira coleta trouxe 96 vagas novas. Implementei o coletor do Recrutei: sitemap com lastmod (janela de 24h) ou varredura completa da listagem SSR. O detalhe traz JSON-LD com descrição integral, então a fonte não entra na fila de enriquecimento. A primeira coleta trouxe 56 vagas novas.

Comecei o experimento de paralelismo: coleta das 9 fontes ao mesmo tempo com delay por fonte (--parallel-sources e --source-delay), LinkedIn com 100 páginas por termo (--max-pages 100) e inputs de dispatch no workflow para controlar o experimento sem mexer no código.

---

### 05/09/2026

Rodei a coleta manual do experimento de paralelismo: 43.743 vagas brutas em 1h15, todas as fontes ao mesmo tempo. O LinkedIn entregou 37.210 vagas (3.733 requests a 1.0s) sem um único bloqueio — 1.000 vagas por termo confirmado nos 40 termos. Nenhuma outra fonte bloqueou. A Solides ficou fora: a API responde 500 desde o dia 03 (outage do lado deles, não rate limit nosso).

Medi o throttle suave do LinkedIn no meu IP: depois de ~330 requests acumulados as páginas voltam vazias sem 429 — limite por volume e por IP, não por ritmo; o IP do Actions passou com 3.700+ requests em linha reta.

A deduplicação comeu quase tudo: das 37 mil brutas do LinkedIn sobraram 2.207 elegíveis e apenas 356 novas na base. O ganho do 1000/termo é largura de cobertura, não explosão da base — que foi de 3.864 para 4.213 vagas, com o LinkedIn em 57,9%. Verifiquei as datas: nenhuma vaga pré-2026 no banco (o import descarta silenciosamente, sem contador no log), mas 65 vagas sem data passam pelo portão — 63 da GeekHunter. O enriquecimento do LinkedIn drenou 335 pendentes em 6,5 minutos, sem bloqueio.

Corrigi a modalidade do Recrutei: o JSON-LD do detalhe não traz address para vagas remotas e a modalidade fica no bloco do header da página. Regra em três camadas com proteção contra falsos positivos — "Auxílio Home Office" é benefício e "suporte remoto a clientes" é atividade, não modalidade. Re-parseei as 56 vagas ao vivo e corrigi 9 no snapshot. Regeneirei a API estática localmente e o deploy saiu só pelo push (deploy_pages.yml), sem rodada de coleta.

Adicionei o resumo colapsável na coleta paralela: o Actions não suporta TUI, então o log abre um grupo novo a cada 45s com as contagens por fonte no título (::group::), e cada fonte reporta o progresso por hook. Criei as issues #21 (medir os limites de cada fonte, coleta e enriquecimento, um por um) e #22 (página da wiki com limites e bloqueios das fontes).

---

### Pendências para o artigo

- Medir a contribuição marginal de cada fonte com o avaliador.
- Documentar a metodologia de deduplicação entre portais.
- Documentar o portão de relevância e o filtro de senioridade.
- Documentar a taxonomia de skills com mais de 200 tecnologias.
- Descrever a classificação por área com pesos.
- Descrever a estratificação geográfica por polos.
- Registrar as decisões metodológicas: fontes públicas, sem contorno de bloqueio.
- Medir os limites e bloqueios de cada fonte, coleta e enriquecimento, um por um (issue #21).
- Criar a página da wiki "Limites e Bloqueios das Fontes" com o que for medido (issue #22).
