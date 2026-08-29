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

### Pendências para o artigo

- Medir a contribuição marginal de cada fonte com o avaliador.
- Documentar a metodologia de deduplicação entre portais.
- Documentar o portão de relevância e o filtro de senioridade.
- Documentar a taxonomia de skills com mais de 200 tecnologias.
- Descrever a classificação por área com pesos.
- Descrever a estratificação geográfica por polos.
- Registrar as decisões metodológicas: fontes públicas, sem contorno de bloqueio.
