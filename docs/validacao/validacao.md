# Validação da extração de habilidades

O extrator obteve **micro-F1 de 97,40%** na amostra de desenvolvimento de 370 vagas.

## Método

A amostra foi sorteada por fonte entre as 10.099 vagas da release `v2026.10.27`. O extrator e a referência usaram o título e a descrição salvos de cada vaga. As anotações de referência consideram menções explícitas, sinônimos e descrições equivalentes da mesma atividade.

O cálculo usa os 339 rótulos do catálogo da release. Cada par de vaga e habilidade conta uma vez.

| Vínculos de vaga e habilidade | Total |
| --- | ---: |
| Presentes na referência e na extração (VP) | 2.620 |
| Presentes apenas na extração (FP) | 68 |
| Presentes apenas na referência (FN) | 72 |
| Total na referência | 2.692 |
| Total na extração | 2.688 |

`Micro-F1 = 2 × VP / (2 × VP + FP + FN) = 5240 / 5380 ≈ 97,40%`

## Dados

- As listas por vaga, a origem das anotações, o catálogo, a identificação das regras e os metadados do sorteio estão nos [dados da medição](habilidades.json). O arquivo também registra as 1.078 marcações da referência que estão fora do catálogo.
- Cada ficha identifica uma vaga pela fonte e pelo ID no portal. [Lista das 370 vagas](amostra.csv)
- Os títulos e as descrições estão em `vagas.title` e `vagas.description`. Consulte a tabela pelo par `source` e `external_id`. [SQLite da release](https://github.com/diasgarcia/tech-skills-br/releases/download/v2026.10.27/vagas.db)

Para refazer a conta, restrinja as duas listas de cada ficha ao catálogo. Some as interseções e as diferenças das listas para obter VP, FP e FN.
