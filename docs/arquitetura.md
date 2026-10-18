# Organização do código

O projeto usa funções para regras e transformações. Classes encapsulam conexões, clientes e estado de execução. Não há uma API HTTP neste repositório: `api/` contém persistência; o painel consome arquivos JSON estáticos.

| Responsabilidade | Local |
| --- | --- |
| Argumentos e configuração da coleta | `main.py`, `scraper/config.py` |
| Coletores e interpretação de páginas | `scraper/sources/` |
| Transporte, tentativas e contadores HTTP | `scraper/http_client.py` |
| Coordenação das fontes e progresso no terminal | `scraper/pipeline.py`, `scraper/progress.py` |
| Qualidade da coleta e frescor | `scraper/quality.py`, `scripts/collection_health.py` |
| Retomada após interrupção | `scraper/checkpoints.py` |
| Identidade e deduplicação de vagas | `scraper/dedupe.py` |
| Regras, classificação e extração | `scraper/rules/`, classificadores e `scraper/skills.py` |
| Política de descrição e nome da empresa | `scraper/consolidation.py` |
| Pendências e resultados de enriquecimento | `scraper/enrichment_queries.py`, `scraper/enrichment.py` |
| SQLite, modelos e migrações | `api/database.py`, `api/models.py`, `api/migrations.py` |
| Estados internos de enriquecimento | `api/enrichment_state.py` |
| Validação e entrega de snapshots | `api/snapshots.py`, `scripts/release_snapshot.py` |
| Exportação e publicação do Parquet | `scripts/export_kaggle.py` |
| Dados do site, relatório e gráficos | `scripts/export_pages_data.py`, `scripts/report_db.py`, `scripts/export_readme_charts.py` |
| Interface e montagem do Pages | `.github/web/`, `scripts/build_pages.py` |

Os scripts de importação e enriquecimento ainda coordenam parte das regras e da persistência. A separação é incremental; não foi criada uma camada genérica de serviços ou repositórios.

## Fontes e recortes

A rodada padrão consulta dez fontes: Gupy, LinkedIn, Vagas.com, trampos.co,
Sólides, GeekHunter, InfoJobs, Abler, Recrutei e Jobbol. Os termos e filtros
nativos ficam em `scraper/rules/coletores.yml`.

LinkedIn limita a busca às últimas 24 horas e pede ordem pelas mais recentes.
Sua lista `linkedin.termos_excluidos` omite `analista de integracoes junior`,
mantendo `analista de integracao junior`. A lista global das outras fontes não muda.
InfoJobs usa os últimos três dias. Abler e Recrutei usam a recência do sitemap
no modo diário. Essas janelas, os termos e os tetos de paginação limitam a
cobertura; não garantem observar todos os anúncios.

Jobbol usa uma listagem JSON e o JSON-LD das páginas públicas de detalhe.
A janela padrão é de três dias, com corte local antes de buscar a descrição.
A listagem pede ordem decrescente de data. Anúncios promovidos podem ficar
fora dessa ordem; uma vaga antiga não encerra a paginação. As quatro buscas
padrão cobrem TI, estágio, trainee e aprendiz. Requisitos técnicos da seção
Observações são preservados antes dos benefícios.

A lista `anunciantes_intermediarios`, em `coletores.yml`, vale para todas as
fontes. Ela compara nomes inteiros, sem distinguir caixa ou acentos. O fluxo
comum aplica o filtro antes do enriquecimento e da exportação. Uma menção ou
link de portal na descrição não causa exclusão.

O filtro mantém anúncios coletados na própria fonte. Só exclui republicações
quando a fonte própria também está selecionada. Por exemplo, uma vaga da Abler
na Jobbol é excluída quando Abler participa da rodada. Uma rodada apenas de
Jobbol mantém esse anúncio. A regra não remove o histórico nem garante cobertura
igual entre portais. Os logs e o relatório da coleta informam os descartes.

## Contratos de persistência

- Banco explícito tem precedência sobre a configuração do ambiente.
- Leitores e comandos de manutenção exigem base existente. Criar uma base é responsabilidade da inicialização/importação.
- Conexões habilitam chaves estrangeiras. Uma alteração por vaga no enriquecimento é confirmada inteira ou desfeita.
- Reextração global tem uma transação única, opção de prévia e sincronização por diferenças.
- Ausência de texto novo não autoriza apagar uma descrição válida. Skills são extraídas do texto preservado, incluindo o título conforme a regra atual.
- Checkpoints guardam registros completos e só são confirmados após a gravação durável da saída. Arquivos inválidos são preservados e geram erro.

## Deduplicação

A coleta usa evidências em ordem de força. Primeiro compara `source + external_id`,
URL exata e o identificador da vaga contido no link. A comparação textual é um
fallback conservador: ela só reúne fontes diferentes quando título e empresa são
compatíveis, a cidade é a mesma e as datas de publicação estão separadas por até
sete dias. Local ou data ausente não autoriza a fusão.

Marcas de duas letras, como MV, FI e EY, identificam empresas. Termos curtos
genéricos, como TI e RH, não identificam. IDs diferentes da mesma fonte nunca são
reunidos apenas por texto; isso preserva vagas distintas com o mesmo título em
cidades diferentes.

## Estados de enriquecimento

`enrich_encerrada` é um campo legado: indica que o fluxo deixou o item como resolvido. Pode ser verdadeiro tanto após sucesso quanto após indisponibilidade. **Não significa que a vaga deixou de aceitar candidaturas.** O contrato público do Parquet permanece com as mesmas 16 colunas.

O SQLite recebe quatro campos internos na migração de esquema:

| Campo | Significado |
| --- | --- |
| `enrichment_status` | `pending`, `legacy_resolved`, `succeeded`, `unavailable` ou `failed` |
| `enrichment_reason` | Motivo observado na tentativa |
| `enrichment_attempted_at` | Data da tentativa registrada |
| `advertisement_status` | Página de detalhes `unknown`, `available` ou `unavailable`; não mede candidaturas abertas |

Um registro antigo resolvido vira `legacy_resolved`, sem inventar motivo, data ou disponibilidade. Falha transitória preserva a última disponibilidade conhecida. A seleção de pendências mantém a política existente e o booleano legado; os campos novos ampliam o diagnóstico, não alteram silenciosamente a elegibilidade.

Migrações usam `PRAGMA user_version` e recusam versões de esquema desconhecidas. O banco da release preserva os campos internos. O CSV seed continua sendo uma exportação de compatibilidade; não substitui o SQLite para recuperar todo o histórico de tentativas.

`coleta_execucoes` guarda uma linha pequena por rodada válida. Ela contém contagens,
alertas e o resumo por fonte. Esse histórico permite detectar queda brusca de volume
e informar a data real da última coleta, sem duplicar vagas ou descrições.

## Publicação

O manifesto relaciona o hash da base anterior aos hashes do DB e CSV preparados. Os leitores recusam artefatos incompletos ou divergentes. A comparação antes do upload detecta uma base já desatualizada; ela **não é uma trava remota atômica**.

Os jobs que atualizam o banco, replicam o snapshot no Kaggle ou montam o site usam o grupo `vagas-snapshot-latest`, sem cancelar a execução ativa. A publicação no Pages usa outro grupo, `vagas-pages-deploy`, compartilhado pelos três workflows que publicam o site. Um novo deploy cancela o deploy anterior, sem cancelar a coleta, o enriquecimento ou a atualização do banco. Assim, uma espera no ambiente do Pages não mantém o banco bloqueado. Antes do deploy, o job compara o hash do artefato com o snapshot da release e ignora um artefato antigo se a base já mudou. Os grupos não são filas duráveis de todas as solicitações: o GitHub pode substituir uma execução pendente. Publicações locais precisam ser coordenadas separadamente.

O GitHub é publicado antes da réplica no Kaggle. Uma falha da réplica deixa aviso e permite nova tentativa sem coleta. A entrega compara o arquivo de uma versão específica; não aceita qualquer versão posterior como prova de sucesso.

## Métricas e interface

As localidades usam o normalizador comum na coleta, na importação e na exportação JSON. Quando o estado está explícito, o formato é `Cidade, UF`, inclusive para estados escritos por extenso. País redundante é removido somente quando a UF foi identificada. Sem UF, a cidade e o país informado são preservados. Não inferimos estado pelo nome da cidade ou pelo polo. Variações de local remoto viram `Remoto` e de abrangência nacional viram `Brasil`, sem mudar a classificação de modalidade.

O site carrega `.github/web/analytics.js`, incluído pelo build do Pages. O Google Analytics só é ativado no endereço publicado e após o aceite do visitante. O botão Privacidade permite rever a escolha. Os eventos próprios registram abas e cliques em links, sem enviar texto de buscas ou dados de anúncios. Localhost não envia estatísticas. A medição de acessos é separada do banco e das métricas de coleta.

O corpo do commit diário e o relatório Markdown destacam as vagas novas que ainda
estão na base e entraram naquele dia. Os dois recebem a mesma data do workflow.
A contagem usa `created_at`, convertido de UTC para
Brasília (UTC-3). Atualizações de vagas antigas não contam como novas. A data de
publicação do anúncio não define esse total. Coleta, importação e enriquecimento
da última rodada aparecem separados do acumulado diário.

O gráfico mantém o histórico por **data de publicação**, por decisão do responsável. As colunas contam vagas publicadas nessa data; a linha conta as habilidades distintas atualmente relacionadas a essas vagas. Não é um registro de eventos de coleta ou extração. A atualização dos JSONs tem data de geração própria.

O timestamp dos CSVs e a referência das datas relativas usam Brasília (UTC-3).
Datas explícitas dos portais são preservadas. O gráfico não avança além do dia
da rodada, mesmo quando algum anúncio informa uma data de publicação futura.

Senioridade e região ausentes não são convertidas em Júnior ou Brasil. A inferência de modalidade segue as regras por fonte descritas abaixo. Denominador zero produz percentual zero sem alterar a contagem publicada.

No LinkedIn, uma cidade informa localização, não modalidade. O projeto usa o rótulo
do portal quando ele aparece no HTML e aceita texto explícito no título ou na
descrição. Sem esses sinais, a modalidade fica como `Não informado`.

`workplace_declared` distingue o campo oficial de uma inferência. Correções
conferidas por vaga ficam em `workplace_overrides.yml`. O HTML público pode
omitir o rótulo que aparece na página autenticada. Atividades como suporte
remoto e presencial não definem o regime do trabalhador.

Esse tratamento conservador da cidade é específico do LinkedIn. Nas demais
fontes, o fallback geral ainda pode inferir Presencial a partir de uma cidade.
Essa inferência não equivale a uma confirmação do portal.

Avisos do Vagas.com sobre candidaturas de cidades próximas viram
`Cidade / UF e Região`. Um aviso de candidaturas nacionais não muda o local
de trabalho para Brasil nem define modalidade remota.

O frontend usa texto do DOM para conteúdo dos anúncios e aceita apenas links HTTP(S). HTML, CSS e JavaScript ficam separados, sem framework novo. Os testes executam o JavaScript em um DOM simulado; a aparência em navegadores reais ainda requer conferência visual.

### Detalhes dos anúncios

O explorador mostra anúncios dos últimos 30 dias pela data de publicação.
A busca combina termos com AND e considera título, empresa, área, habilidades,
modalidade, fonte e dados geográficos.

Um único `dialog` apresenta os dados da vaga. No computador, o hover abre um
painel sem X, posicionado sem cobrir o título. Clique, teclado ou toque abrem
um modal com X, Escape e fechamento pelo fundo. Os dados já estão no JSON;
abrir os detalhes não faz uma consulta ao portal.

O painel mostra metadados, habilidades e link de origem, não a descrição
completa. A seta de link direto permanece na última coluna, depois de
Local / Mod., inclusive no celular.

### Gráficos e percentuais

O mapa de calor usa as dez áreas com mais anúncios e as quinze habilidades
mais citadas em toda a base. Os rankings são recalculados automaticamente.
Cada célula divide os anúncios com a habilidade pelo total de anúncios da
área, inclusive os sem habilidades. Zero aparece como `0,0%`.

O SVG tem mais altura e fontes maiores para manter a leitura na largura
limitada do README. Aumentar apenas a largura do arquivo faz o GitHub reduzir
também os textos.

O terceiro gráfico seleciona as vinte habilidades mais citadas e ordena esse
conjunto pela presença média em todas as áreas. As colunas mostram essa média;
a linha mostra a quantidade de vagas com a habilidade. A base inclui vagas
sem habilidades e áreas sem menção entram com zero. Cada escala usa seu maior
valor, uma margem e divisões automáticas. O percentual não passa de 100%.

O ranking geral de habilidades usa anúncios com ao menos uma habilidade.
O explorador por área usa anúncios daquela área com habilidades. Esses
denominadores são diferentes do mapa de calor. Uma vaga pode ter vários
vínculos, então os percentuais de habilidades não precisam somar 100%.

O quadrinho **Skill com maior presença** usa outro indicador: calcula a média
dos percentuais de presença da habilidade em cada área. Todas as áreas têm
o mesmo peso. A base inclui vagas sem habilidades e áreas sem menção entram
com zero. Empates usam a quantidade de áreas com menção, depois o nome.
O texto mostra “Presença média por área: X,X%”, com uma casa decimal.
Não é o percentual da base inteira. A cobertura em quantidade de áreas fica
na explicação ao passar o ponteiro e no notebook, mas não é o critério principal
do ranking. O notebook preserva o ranking de citações e apresenta também o
ranking por presença entre áreas.

O notebook também calcula os três gráficos do README com o dataset vinculado
à execução. Mantém as tabelas e os gráficos anteriores; não carrega imagens
prontas do site.

### Calendário e formatos

As três rodadas publicadas atualizam o banco e os JSON. O dataset recebe nova
versão quando os dados mudam. Relatório e gráficos são atualizados na rodada 3,
às 19:16 de Brasília, ou em uma coleta tratada como manual.

O notebook automático é reenviado apenas na rodada 3 com origem cron e
dataset confirmado. A coleta manual não dispara esse notebook. Há um workflow
separado para publicá-lo. Seu código permanece versionado em
`notebooks/kaggle/`; não é editado a cada execução.

O Kaggle recebe um único `vagas.parquet`, com uma linha por anúncio e 16 colunas.
`skills` é texto separado por `; `, não uma lista aninhada. `published_date`
é data, `enrich_encerrada` é booleano e os vocabulários controlados usam
codificação de categorias. `external_id` continua texto para aceitar IDs
numéricos, UUIDs e outros códigos.

`gerado_em` informa a geração dos JSON; `ultima_coleta` informa a última
coleta completa válida registrada. Uma manutenção ou exportação não renova,
por si só, o frescor.

## Validação

Testes de falha usam clientes simulados e SQLite temporário. Há cenários de rollback, retomada, confirmação de publicação, categorias e nulos no Parquet, além de execução das células do notebook com dados pequenos. As instruções estão no [guia local](execucao-rapida.md).

Esses testes não medem a precisão da classificação em anúncios reais. Falta avaliar uma amostra independente com revisão humana. Termos fora do vocabulário e rótulos oficiais ausentes continuam sendo limites do processamento. A descrição obtida é salva sem truncamento; falhas de acesso podem impedir a recuperação do conteúdo completo da fonte. Os detalhes estão em [Escopo e Limitações](https://github.com/diasgarcia/tech-skills-br/wiki/Escopo-e-Limitacoes).

A coleta automática também verifica fonte zerada, queda em relação às rodadas
anteriores, modalidade inválida, URL inválida, data futura, excesso de fallback e
empresa ausente. Alertas altos de dados inválidos impedem a publicação daquele snapshot.
A queda de volume usa a última rodada anterior da mesma fonte e perfil, sem
erro de consulta nessa fonte. Menos de 10% do volume anterior gera alerta alto;
10% ou mais não gera alerta de queda. Não há média de várias rodadas.
Abler e Recrutei ficam fora das regras de zero e queda: elas consultam uma janela
móvel de 24 horas, portanto a redução pode ser normal mesmo sem falha do portal.

Uma falha registrada em uma fonte permite publicar os resultados válidos das
outras fontes como coleta parcial. O importador preserva as vagas anteriores da
fonte que falhou. O Actions mostra um aviso. Depois das etapas de publicação,
um job final encerra a rodada como falha. Esse erro não desfaz os dados salvos
nem as entregas concluídas. A rodada não renova o frescor da última coleta
completa. Fonte zerada sem erro e queda anormal de volume seguem o mesmo fluxo
parcial: o aviso informa a fonte e os valores observados, as publicações são
tentadas e o erro fica no job final. Esses alertas mantêm a severidade alta,
mas não são registradas como coleta completa. Resultados de fontes sem erro de
consulta podem servir de referência mesmo quando a rodada anterior foi parcial.
Coleta totalmente vazia, modalidade fora do vocabulário e outros alertas altos
continuam bloqueando a publicação antes da importação.

Testes locais não demonstram disponibilidade dos portais nem sucesso de uma publicação real. Não execute coleta, migração na base de trabalho ou publicação como efeito colateral de uma revisão.
