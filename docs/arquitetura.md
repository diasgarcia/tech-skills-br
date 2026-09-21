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
| Interface e montagem do Pages | `.github/web/`, `scripts/build_pages.py` |

Os scripts de importação e enriquecimento ainda coordenam parte das regras e da persistência. A separação é incremental; não foi criada uma camada genérica de serviços ou repositórios.

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

Os workflows que usam a release compartilham um grupo de concorrência e não cancelam a execução ativa. Esse grupo não é uma fila durável de todas as solicitações: o GitHub pode substituir uma execução pendente. Publicações locais precisam ser coordenadas separadamente.

O GitHub é publicado antes da réplica no Kaggle. Uma falha da réplica deixa aviso e permite nova tentativa sem coleta. A entrega compara o arquivo de uma versão específica; não aceita qualquer versão posterior como prova de sucesso.

## Métricas e interface

O gráfico mantém o histórico por **data de publicação**, por decisão do responsável. As colunas contam vagas publicadas nessa data; a linha conta as habilidades distintas atualmente relacionadas a essas vagas. Não é um registro de eventos de coleta ou extração. A atualização dos JSONs tem data de geração própria.

Valores ausentes não são convertidos em Júnior, Presencial ou Brasil. Denominador zero produz percentual zero sem alterar a contagem publicada.

No LinkedIn, uma cidade informa localização, não modalidade. O projeto usa o rótulo
do portal quando ele aparece no HTML e aceita texto explícito no título ou na
descrição. Sem esses sinais, a modalidade fica como `Não informado`.

O frontend usa texto do DOM para conteúdo dos anúncios e aceita apenas links HTTP(S). HTML, CSS e JavaScript ficam separados, sem framework novo. Os testes executam o JavaScript em um DOM simulado; a aparência em navegadores reais ainda requer conferência visual.

## Validação

Testes de falha usam clientes simulados e SQLite temporário. Há cenários de rollback, retomada, confirmação de publicação, categorias e nulos no Parquet, além de execução das células do notebook com dados pequenos. As instruções estão no [guia local](execucao-rapida.md).

A coleta automática também verifica fonte zerada, queda em relação às rodadas
anteriores, modalidade inválida, URL inválida, data futura, excesso de fallback e
empresa ausente. Um alerta alto impede a publicação daquele snapshot. A comparação
histórica começa depois de três coletas completas registradas.
Abler e Recrutei ficam fora das regras de zero e queda: elas consultam uma janela
móvel de 24 horas, portanto a redução pode ser normal mesmo sem falha do portal.

Testes locais não demonstram disponibilidade dos portais nem sucesso de uma publicação real. Não execute coleta, migração na base de trabalho ou publicação como efeito colateral de uma revisão.
