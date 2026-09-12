# Validação da classificação

Este protocolo mede os acertos e os erros das regras em anúncios com rótulos humanos. A avaliação usa os textos salvos. Ela não consulta portais, não executa a coleta e não altera o banco.

**Estado atual:** a ferramenta está disponível para preparar a amostra e calcular as métricas. A anotação humana ainda está pendente. O projeto ainda não apresenta uma taxa de acerto medida por este protocolo. Testes unitários verificam o código; eles não substituem essa avaliação.

## O que será medido

| Componente | Referência humana | Resultado |
|---|---|---|
| Relevância técnica | O anúncio pertence à área de tecnologia? | Acurácia, precisão, recall, F1 por classe e matriz de confusão, apenas na amostra retida |
| Área | Área principal do anúncio | Acurácia, F1 macro, métricas por área e matriz de confusão, nos anúncios que o revisor considera técnicos |
| Senioridade no título | Nível de entrada explícito no título | Acurácia, F1 macro, métricas por classe e matriz de confusão |
| Skills | Habilidades técnicas citadas no título e na descrição | Precisão, recall e F1 micro e por skill; F1 macro; igualdade entre a lista prevista e a lista humana |

Cada skill conta no máximo uma vez por anúncio. A matriz de confusão usa a referência humana nas linhas e a previsão nas colunas. F1 macro dá o mesmo peso a cada classe presente na referência ou nas previsões. F1 micro reúne os acertos e erros antes do cálculo. Divisões por zero em precisão, recall e F1 recebem zero. Se não houver nenhuma skill humana ou prevista, o F1 macro de skills fica nulo; a igualdade entre listas ainda é calculada.

O banco contém anúncios que já passaram pelos filtros. Portanto, esta amostra não mede quantas vagas técnicas foram descartadas por engano nem o recall do processo de coleta. Para avaliar esses pontos, uma etapa posterior precisa preservar uma amostra anterior aos filtros, inclusive os descartados. A senioridade salva também pode vir do campo nativo do portal. Ela não é usada como verdade de referência: esta avaliação mede somente a regra aplicada ao título.

## Separação dos casos

A amostra inicial usa 300 anúncios, como piloto. Esse tamanho não garante precisão estatística para cada uma das áreas ou skills raras.

- `development`: cerca de 60%. Pode ser consultado para entender erros e ajustar regras.
- `validation`: cerca de 20%. Serve para comparar versões durante o desenvolvimento. O uso repetido influencia as escolhas; seu resultado não é a avaliação final.
- `test`: cerca de 20%. Fica reservado até o encerramento dos ajustes. Não deve orientar keywords, aliases, exclusões, pesos ou limiares.

A ferramenta agrupa anúncios com a mesma URL, descrições normalizadas iguais de pelo menos 100 caracteres, ou título igual com empresa compatível. As relações são transitivas. Ela sorteia um representante por grupo, sem preferir descrições longas. Os grupos reduzem a chance de cópias aparecerem em partições diferentes. Essa verificação não garante detectar toda paráfrase ou republicação.

Os [casos já conhecidos](validacao/casos-conhecidos.json) entram no desenvolvimento. A lista inicial vem de revisões anteriores e não é exaustiva. Acrescente outros IDs usados em ajustes antes de preparar a amostra. A correspondência por ID considera qualquer fonte, de forma conservadora. Os demais grupos são sorteados com semente fixa. O manifesto informa a composição por fonte e por partição. O sorteio é por grupos, sem estratificação ou ponderação por portal; os percentuais não estimam a população brasileira de anúncios.

Como parte do histórico já foi examinada, o teste histórico é **provisório**. Cada revisor deve informar se o caso foi usado em ajustes. Se houver contaminação, registre o ID como conhecido e prepare uma nova versão. Não apague o resultado anterior nem mude a partição no arquivo congelado. Para uma avaliação final mais forte, reserve anúncios de um período futuro antes de examinar seus erros.

Depois de abrir o teste, seus casos passam a ser conhecidos. Correções motivadas por eles exigem outro teste independente. A ferramenta pede `--final-test` e registra a abertura; ela não deve rodar no Actions diário.

## Preparar a amostra

Na raiz do repositório, com o banco local que será avaliado:

```powershell
python scripts/validate_classification.py prepare --db data/vagas.db --output output/validacao/piloto-01 --size 300 --seed 20260912
```

A pasta de saída precisa ser nova. A ferramenta salva:

- `cases-development.json`, `cases-validation.json` e `cases-test.json`: textos congelados, identificadores, fonte e partição; sem rótulos do algoritmo.
- `annotations-*.jsonl`: formulários vazios, um anúncio por linha.
- `labels.json`: nomes canônicos de áreas, níveis de entrada e skills.
- `manifest.json`: semente, composição da amostra, data, commit e hashes dos textos, do vocabulário, do código e das regras. O manifesto também informa se havia alterações locais.

Os arquivos ficam em `output/`, já ignorado pelo Git. Faça uma cópia preservada do pacote antes da anotação. Preserve também as versões dos formulários e dos resultados. O manifesto identifica os arquivos, mas não substitui o backup do código no Git e das alterações locais.

## Anotar sem consultar a previsão

Abra somente o arquivo de casos da partição em revisão. Localize o mesmo `case_id` no formulário correspondente. Leia o título e a descrição congelados. Não use a classificação atual do site, as skills do banco ou uma versão posterior do anúncio como resposta.

Preencha cada linha do formulário:

| Campo | Como preencher |
|---|---|
| `reviewer` | Nome ou identificador do revisor humano |
| `method` | `human`, somente após revisão humana |
| `seen_during_rule_tuning` | `true` se o caso foi usado para ajustar regras; `false` se não foi |
| `is_tech` | `true` ou `false`, conforme as atividades do cargo |
| `area` | Um nome de `labels.json`; texto vazio (`""`) quando `is_tech` for `false` |
| `seniority_title` | Nível de entrada explícito no título; caso contrário, `Não identificada no título` |
| `skills` | Lista de nomes canônicos identificados pelo revisor; `[]` quando não houver nenhum |
| `skills_outside_taxonomy` | Lista de habilidades técnicas presentes no anúncio, mas ausentes do vocabulário congelado |
| `notes` | Justificativa, trecho de evidência ou dúvida resolvida |

`null` significa pendente. `[]` significa revisão concluída sem skills daquela lista. Não confunda os dois estados. O cálculo recusa formulários incompletos, IDs ausentes ou repetidos, nomes inválidos e casos conhecidos em validação ou teste. Ele exige todos os casos da partição para evitar selecionar apenas os anúncios fáceis.

Avalie a atividade principal ao escolher a área. Use `Outros/TI Geral` se o anúncio for técnico e não sustentar uma área mais específica. Para senioridade, considere a informação explícita do título; um título que aceita júnior e pleno inclui o nível de entrada. Dúvidas precisam ser resolvidas e registradas antes do cálculo. Não adivinhe para completar o formulário.

Uma skill deve estar citada no trabalho, nos requisitos ou nos diferenciais do anúncio. Não infira JavaScript a partir de React nem considere tecnologias citadas apenas na apresentação da empresa ou nos benefícios. Use o nome canônico para sinônimos. Registre também habilidades fora do vocabulário: elas contam como omissões do extrator. A avaliação mede o texto disponível; uma descrição vazia não prova que a vaga não exige habilidades.

Idealmente, dois revisores anotam cópias separadas e depois resolvem as divergências. Esta primeira ferramenta aceita uma referência humana final e registra seus revisores; ela ainda não calcula concordância interavaliador. Anotações de IA, se usadas como apoio, precisam passar por revisão humana e não constituem um segundo avaliador independente.

## Calcular as métricas

Depois de concluir todas as anotações de desenvolvimento:

```powershell
python scripts/validate_classification.py evaluate --pack output/validacao/piloto-01 --annotations output/validacao/piloto-01/annotations-development.jsonl --split development --output output/validacao/piloto-01/result-development-v1.json
```

Para comparar uma versão das regras na validação:

```powershell
python scripts/validate_classification.py evaluate --pack output/validacao/piloto-01 --annotations output/validacao/piloto-01/annotations-validation.jsonl --split validation --output output/validacao/piloto-01/result-validation-v1.json
```

Somente após encerrar as decisões, abra o teste uma vez:

```powershell
python scripts/validate_classification.py evaluate --pack output/validacao/piloto-01 --annotations output/validacao/piloto-01/annotations-test.jsonl --split test --final-test --output output/validacao/piloto-01/result-test-v1.json
```

O resultado contém métricas, previsões, hashes das anotações, versão atual das regras e limitações. A avaliação usa as regras atuais nos textos congelados. O vocabulário do formulário permanece o do início da amostra; novas skills podem ser previstas e comparadas com `skills_outside_taxonomy`. Preserve a grafia canônica ao consolidar a referência humana. A abertura final também salva uma cópia completa em `test-opened.json`. Não sobrescreva resultados anteriores.

Publique números somente depois da revisão. Identifique tamanho, fonte, período, partição e versão das regras. Os parâmetros atualmente configurados são `title_boost = 3` e `min_score = 3`; ainda não há justificativa empírica para considerá-los ótimos. Qualquer comparação de parâmetros deve usar desenvolvimento e validação, antes de abrir o teste.

## Interpretação dos rankings públicos

O projeto mede menções identificadas em anúncios coletados. Ele não mede diretamente contratações, proficiência, quantidade de postos por anúncio nem todas as necessidades do mercado.

Nos rankings de skills do painel e do notebook, a frequência é o número de anúncios com a skill dividido pelo número de anúncios com ao menos uma skill identificada. No explorador por área, ambos os números são restritos à área. Uma vaga pode citar várias skills; os percentuais não precisam somar 100%. O mapa de calor do README usa o total de anúncios de cada área, conforme sua legenda. Mantenha a base de cálculo explícita em cada apresentação.

## Referências do protocolo

- [Separação entre desenvolvimento e teste](https://scikit-learn.org/stable/modules/cross_validation.html).
- [Vazamento de informação e boas práticas](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage).
- [Definições das métricas](https://scikit-learn.org/stable/modules/model_evaluation.html#classification-metrics).
