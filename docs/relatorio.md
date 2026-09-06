### 20/08/2026

Comecei a trabalhar no projeto a partir da base existente. Criei o mapeamento de 14 polos e 5 macrorregiões. Implementei a inferência de modalidade de trabalho no modelo Job. Melhorei a sessão HTTP, que agora aceita POST e GET JSON.

---

### 21/08/2026

Implementei o coletor SerpApi para busca estruturada no Google Jobs. Implementei o coletor TheirStack com enriquecimento de tecnologias. Refinei a detecção de modalidade do LinkedIn. Expandi a taxonomia de skills para 217 tecnologias.

---

### 22/08/2026

Separei as fontes com cota da execução padrão. Adicionei a opção --start-page. Integrei novas opções de linha de comando. Criei gráficos analíticos estratificados. Adicionei os campos regiao e polo ao modelo ORM. Enriqueci a importação idempotente. Adicionei o relatório estatístico da base consolidada.

---

### 23/08/2026

Criei o exportador de snapshot versionado. A base consolidada chegou a 1540 vagas. Atualizei os metadados da API para a pesquisa PIBIC. Reescrevi o README com foco acadêmico. Criei o manual de uso detalhado. Criei a especificação técnica da arquitetura.

---

### 24/08/2026

Alinhei a identificação do projeto para tech-skills-br. Removi dados legados. Ajustei as licenças. Adicionei CI no GitHub Actions. Organizei relatórios e gráficos em docs/relatorios.

---

### 25/08/2026

Adicionei a automação de coleta diária no GitHub Actions. Refinei a taxonomia de senioridade. Desmembrei as áreas de Suporte, Infraestrutura e Engenharia de Software. Aumentei a paginação padrão de 5 para 15 páginas por termo. Expandi o catálogo geográfico para 27 capitais. Expandi a taxonomia para 14 áreas. Adicionei deduplicação por URL canônica. Implementei o site minimalista e a API JSON estática. Defini a data de corte em 01/01/2026. Eliminei vagas inativas legadas. Criei o workflow de deploy no GitHub Pages.

Testei várias abordagens contra o Cloudflare do ProgramaThor. Usei User-Agent atualizado, curl_cffi com impersonate do Chrome e Playwright Chromium headless. Criei a busca de descrição completa do LinkedIn. Expandi os termos de busca. Desmembrei Service Desk, Hardware e Segurança da Informação em subáreas. Criei a área de Inteligência Artificial, separada de Data. Adicionei Copilots e LLMs à taxonomia. A base chegou a 2057 vagas.

---

### 26/08/2026

Adicionei aliases case-sensitive às skills. Mantive a descrição completa no CSV. Melhorei o enriquecimento do LinkedIn com retry. Configurei 3 rodadas diárias com enriquecimento só de pendentes.

---

### 27/08/2026

Adicionei a janela de 30 dias ao enriquecimento. Recuperei descrições truncadas da Gupy. Cobri http_client, pipeline, paginação e config com testes. Corrigi a modalidade do LinkedIn usando o título. Sincronizei o push do bot com retry. Troquei os crons nativos por gatilho externo via API de dispatch. Criei o enriquecimento de Vagas.com, Trampos e ProgramaThor. Recuperei 5 descrições truncadas da Gupy. Removi 98 vagas da Gupy de vez.

---

### 28/08/2026

Corrigi o import: linha sem descrição não rebaixa a área. Marquei vaga com 404 como encerrada. Criei a regra de ignorar seções de benefícios na extração de skills. Criei a reclassificação retroativa de áreas. Removi 28 vagas fora do escopo. Reclassifiquei 170 áreas. Removi a API REST FastAPI, os containers e o deploy dedicado. O projeto ficou só com JSON estáticos. Fiz a limpeza de comentários do código. Revisei o README e os documentos. Mudei o site para a pasta site/, depois para api/web e .github/web. Removi o SerpApi e o TheirStack. O projeto ficou só com fontes públicas. Adicionei meu nome à licença.

---

### 29/08/2026

Corrigi o campo enrich_encerrada para booleano. Achei um bug: o import marcava todas as vagas como encerradas. Corrigi. Travei as dependências nas versões do Python 3.12. O CI passou a testar só no 3.12. Adicionei o workflow manual de enriquecimento. Expandi a taxonomia com GPO, Fortigate, Antivírus, Bitdefender, Ubiquiti, Backup, Hyper-V, Windows Server, Power Automate e Word.

Implementei o coletor Solides via endpoint público do portal. Usei os filtros nativos de nível. A fonte trouxe 84% de vagas inéditas no piloto. Implementei o coletor GeekHunter via SSR público. O enriquecimento extrai empresa e data do JSON-LD. Criei o avaliador de contribuição marginal de fonte. Mudei o Trampos para varredura completa. Adicionei o filtro de aprendiz na Solides. Separei estagio de estagiario. Movi os filtros de coleta para o YAML. Removi o ProgramaThor e o Playwright, pois a fonte bloqueava o runner e rendia pouco.

Também fiz correções e melhorias na interface web do projeto.

---

### 30/08/2026

Melhorei a busca do explorador de vagas. A busca detecta cidade, polo e região na query. Os termos combinam com E lógico. O casamento usa prefixo enquanto se digita; por exemplo, "sao p" já filtra São Paulo. Numerei os commits do bot por rodada: 09h16 - 1, 14h16 - 2, 19h16 - 3, e fora disso manual N, usando a hora de início do job.

Descobri e corrigi três bugs ao re-verificar 50% da base, com 1355 vagas ao vivo e 44 lidas na mão. Seções de "Benefícios" no meio do texto cortavam os requisitos: uma vaga da Camisaria FMW perdia Hardware e Windows. A janela de 30 dias deixava 35 vagas do LinkedIn órfãs de descrição. O snippet do Vagas.com ficava fora do gate de enriquecimento. O enrich da GeekHunter gravava data antiga do JSON-LD e furava o corte de 2026. O cliente HTTP respeitava Retry-After sem teto: o Cloudflare mandou 429 com 23h e a coleta dormiria tudo.

Adicionei o modo navegador ao PoliteSession via curl_cffi, com impersonate do Chrome. O modo passou no bot-check do Cloudflare, onde o requests puro tomava ban. O enriquecimento do Vagas.com passou a parar no primeiro 429 e a persistir o progresso a cada 10 preenchimentos. A base caiu de 2795 para 2787 vagas ao cortar 8 zumbis de 2025 que o enriquecimento re-injetava.

---

### 31/08/2026

Achei mais um bug sério na importação: linha sem skills sobrescrevia as tecnologias do banco com lista vazia. O CSV da coleta roda com --no-enrich, e o LinkedIn re-coletado chegava sem skills. A cada rodada o enriquecimento perdia o que acumulou: os vínculos caíram de 14896 para 9603. Corrigi para preservar quando a linha vem vazia. Re-extraí a base inteira: 14833 vínculos, 2387 vagas com skills.

Corrigi o stop do primeiro 429 para parar de verdade, pois as futures enfileiradas martelavam o IP banido. Rodei uma coleta manual do GitHub para validar. Criei o board Tech Skills BR no GitHub Projects com as pendências em issues. Restam 58 descrições truncadas do Vagas.com, que as rodadas noturnas preenchem em lotes por causa do rate limit do Cloudflare.

---

### 01/09/2026

Rodei as três coletas automáticas do dia e um enriquecimento manual. Sem mudanças de código.

---

### 02/09/2026

Corrigi os ids instáveis das vagas entre as runs do CI. O seed passou a exportar a coluna db_id, e o import restaura o id original. O vagas.json parou de mudar inteiro a cada coleta. Simulei duas runs com banco do zero: zero ids diferentes nas 3067 vagas.

Melhorei a classificação por área. Título específico vence o genérico. Suporte disfarçado de "Analista de Sistemas" vira Suporte Técnico. Movi 26 vagas e revisei uma a uma. Removi psycopg e httpx. O projeto ficou SQLite-only.

Corrigi o import: snippet novo não regride descrição enriquecida. A fila de pendentes drenou de verdade. O enriquecimento passou a parar o lote da fonte no primeiro 429. O LinkedIn ganhou a proteção que não tinha. Os commits de dados ganharam resumo da rodada no corpo, e o rótulo do commit veio dos inputs do dispatch. Removi o critério "500 caracteres exatos" da fila do LinkedIn. Busca com sucesso marca a vaga como resolvida. Silenciei avisos repetidos do matplotlib no runner.

---

### 03/09/2026

Corrigi as URLs do Solides. O redirectLink antigo usava subdomínios que não resolvem mais em DNS, então o coletor passou a gravar a URL canônica do portal. Corrigi 678 URLs na base.

Criei o portão novo. Vagas de campo, vendas, call center e loja saem da base; medido em 61 vagas não-tech a menos. Mudei a classificação: Suporte Técnico virou área genérica e título específico vence. "Analista de Suporte N1" vai para Service Desk, e "Técnico Suporte Volante" vai para Field Service. Reclassifiquei 139 vagas e removi 6 não-tech.

Testei dois experimentos contra o 429 do Cloudflare no Vagas.com: fingerprint Safari e warm-up de sessão. Nenhum mudou o resultado; o limite é por IP. Reverti o Safari. Os logs da coleta e do enriquecimento passaram a aparecer ao vivo no runner.

Corrigi a senioridade: "N1.5" é tier de suporte, não nível de entrada, e três vagas pleno/sênior saíram da base. Criei contextos de descarte para "eletrônica" como adjetivo, tirando dois falsos positivos. Corrigi a empresa da Gupy em páginas compartilhadas: o nome vem do subdomínio, não do careerPageName. Adicionei ferramentas de suporte ao vocabulário: Suporte Remoto, Clonezilla, VirtualBox, SharePoint, Microsoft Teams e ITSM. Re-extraí as skills na base inteira. Revalidei 59 empresas do GeekHunter com o JSON-LD. A busca do dashboard ganhou filtro por fonte, e a cidade vence o polo regional no display. Limpei comentários redundantes do código.

---

### 04/09/2026

Implementei o coletor do InfoJobs. A busca pública é renderizada no servidor. Júnior entra pela busca textual; estágio, trainee e aprendiz entram pelos filtros nativos de contrato. A primeira coleta completa trouxe 378 vagas novas, e a fonte virou a quarta maior da base.

O enriquecimento do InfoJobs busca a descrição completa no detalhe da vaga. O teaser da listagem tem 153 caracteres fixos. Vaga encerrada vira 404. O bloqueio suave não marca vaga como encerrada.

Revisei 38 vagas do InfoJobs uma a uma. Corrigi aliases que não casavam. Adicionei Pacote Office, ServiceNow, Storage, Google Sheets, DAX, AutoCAD, PABX e Robótica ao vocabulário. Fibra óptica virou alias de Redes de Computadores. A cobertura subiu de 55% para 99%.

Canonicalizei a senioridade: "Estagiário" virou "Estágio" no import, e dez vagas da base foram re-rotuladas. Canonicalizei nomes de empresa: variantes de "Confidencial" e sufixos societários deixaram de criar empresas duplicadas. Normalizei as empresas da base e corrigi 62 slugs do GeekHunter.

Adicionei o CITATION.cff (formato 1.2.0) no main e na branch do congresso. Alinhei o README ao Python 3.12 e registrei o InfoJobs no execucao-rapida. Os gráficos e o relatório consolidado passaram a ser gerados só na rodada das 09h16; as outras duas rodadas só coletam, importam e enriquecem.

Implementei o coletor da Abler via sitemap público com checkpoint incremental. Rodada interrompida retoma sem refazer GET. A primeira coleta trouxe 96 vagas novas. Implementei o coletor do Recrutei. Ele usa o sitemap com lastmod (janela de 24h) ou varredura completa da listagem SSR. O detalhe traz JSON-LD com descrição integral, então a fonte não entra na fila de enriquecimento. A primeira coleta trouxe 56 vagas novas.

Comecei o experimento de paralelismo. As 9 fontes coletam ao mesmo tempo, cada uma com delay próprio. O LinkedIn passou a 100 páginas por termo. O workflow ganhou inputs de dispatch para controlar o experimento sem mexer no código.

---

### 05/09/2026

Rodei a coleta manual do experimento de paralelismo. Resultado: 43.743 vagas brutas em 1h15, com as 9 fontes ao mesmo tempo. O LinkedIn entregou 37.210 vagas em 3.733 requests a 1.0s, sem um único bloqueio. O teto de 1.000 vagas por termo foi confirmado nos 40 termos. Nenhuma outra fonte bloqueou. A Solides ficou fora com 500 na API; à noite descobri que não era outage, e sim o endpoint renomeado (veja abaixo).

Medi o throttle suave do LinkedIn no meu IP. Depois de ~330 requests acumulados as páginas voltam vazias, sem 429. É limite por volume e por IP, não por ritmo. O IP do Actions passou com 3.700+ requests em linha reta.

A deduplicação comeu quase tudo. Das 37 mil brutas do LinkedIn sobraram 2.207 elegíveis, e apenas 356 viraram novas na base. O ganho do 1000/termo é largura de cobertura, não explosão da base, que foi de 3.864 para 4.213 vagas, com o LinkedIn em 57,9%. Verifiquei as datas: nenhuma vaga pré-2026 está no banco, pois o import descarta em silêncio, sem mostrar no log. 65 vagas sem data passam pelo portão, sendo 63 da GeekHunter. O enriquecimento do LinkedIn drenou 335 pendentes em 6,5 minutos, sem bloqueio.

Corrigi a modalidade do Recrutei. O JSON-LD do detalhe não traz address para vagas remotas, e a modalidade fica no bloco do header da página. A regra tem três camadas e protege contra falsos positivos: "Auxílio Home Office" é benefício e "suporte remoto a clientes" é atividade, não modalidade. Re-parseei as 56 vagas ao vivo e corrigi 9 no snapshot. Regeneirei a API estática localmente, e o deploy saiu só pelo push (deploy_pages.yml), sem rodada de coleta.

O paralelismo virou o padrão da rodada. As medições viraram a matriz de delays por fonte: LinkedIn 1.0s, InfoJobs 2.0s, Vagas.com 2.0s e Solides 2.0s; as demais 1.0s. Tudo ficou como default no código (config), sem flags na CLI nem no workflow. A tela de dispatch manual ficou só com origem e rodada, que é o que o cron-job.org usa.

Medi os limites de cada fonte (issue #21) e encontrei o piso seguro para todas. Recrutei, Abler, Trampos, Gupy, GeekHunter e Solides aguentaram 30 requests a 0.5s sem bloqueio. O LinkedIn tem 1.0s como ponto doce; a 0.5s a API segura as respostas e o ritmo cai de 50 para 33 req/min. O Vagas.com detalhe é o único ban real: ~16-20 requests por IP por dia, com ban de 24h. É limite por volume, não por ritmo. O bloqueio suave do InfoJobs não se reproduziu. Criei a página "Limites e Bloqueios" na wiki (#22) e fechei as issues #20, #21 e #22.

Caçando as 11 pendentes eternas do Vagas.com, descobri que eram vagas removidas. O portal responde 200 com uma página genérica ("Vagas de emprego para {id}") sem descrição, e o enriquecimento não marcava como encerrada. Corrigi: página genérica agora conta como 404, e a fila zerou.

Corrigi a Solides. Os 500 de três dias eram o endpoint renomeado: v3/portal-vacancies-new virou v3/portal-vacancies, e as variantes v4 exigem auth. Validei a coleta ao vivo.

O monitor da coleta paralela virou tabela de verdade. Tem cores por status, coluna de termo sem corte, status code nos erros e percentual geral de conclusão. Durante a coleta o log mostra só a tabela; o restante sai no log geral do fim.

---

### 06/09/2026

Tirei os dados do git. O plano #24 virou realidade. Os JSON do site e os gráficos saíram do histórico. O estado operacional passou a viver como asset da release `latest` no GitHub. Cada rodada baixa o `vagas.db` no início e sobe o novo no fim. O git guarda só código, regras e documentação.

O seed CSV também foi para a release. O commit da rodada ficou reduzido ao relatório em texto. O `deploy_pages.yml` passou a gerar os JSON a partir do banco da release.

Criei o dataset no Kaggle (`rafaeldiasgarcia/tech-skills-br`). Cada rodada envia uma versão em Parquet. A nota registra a data, a rodada e a quantidade de vagas. Versões vazias não sobem. O workflow usa o token novo da Kaggle.

Completei os metadados do dataset. A licença ficou MIT. A frequência ficou diária. A descrição ficou em um parágrafo no estilo STE. As colunas do Parquet foram reordenadas. A coluna skills ficou no início. O Data Explorer mostra as tecnologias na tabela padrão.

Limpei o histórico com `filter-repo`. Removi `seed/vagas.csv`, `api/web`, `docs/api`, `.github/pages`, `site/api` e todos os gráficos de todas as versões. O repositório caiu de 105 MB para menos de 1 MB. Guardei um backup espelho do histórico antigo.

Corrigi problemas que a mudança revelou. O runner não tinha o `gh` autenticado. Adicionei o `GH_TOKEN` explícito. A rodada das 14:16 quebrou no commit porque o relatório regenerado ficava fora do stage. O guard passou a olhar só o que foi staged.

Revalidei as empresas do GeekHunter. 62 vagas guardavam o slug da URL em vez do nome real. O JSON-LD do detalhe corrigiu 57. As outras 5 não tinham nome no detalhe. Usei o nome resolvido das vagas irmãs. Zero slugs restantes.

Achei churn nas vagas da GeekHunter. Sete vagas antigas de 2025 entram na base toda rodada e saem no corte de 2026 do enriquecimento. O total não muda. As mesmas sete entram e saem sempre.

Perdi e recuperei três vagas do LinkedIn no bootstrap da release. O banco local estava defasado. O merge do seed completo devolveu as três. A lição ficou no plano: conferir a contagem antes de subir o asset.

Atualizei a wiki. A Home ganhou o Kaggle e a release no diagrama de contexto. A Arquitetura ganhou a nova persistência. A página de Automação ganhou o fluxo novo. A jornada da vaga ganhou um diagrama vertical. Criei as issues #23, #24 e #25.

---

### Pendências para o artigo

- Medir a contribuição marginal de cada fonte com o avaliador.
- Documentar a metodologia de deduplicação entre portais.
- Documentar o portão de relevância e o filtro de senioridade.
- Documentar a taxonomia de skills com mais de 200 tecnologias.
- Descrever a classificação por área com pesos.
- Descrever a estratificação geográfica por polos.
- Registrar as decisões metodológicas: fontes públicas, sem contorno de bloqueio.
