# Tech Skills Brasil

Dados sobre as habilidades exigidas em vagas de entrada no mercado brasileiro de tecnologia.

[Explorar o painel](https://diasgarcia.github.io/tech-skills-br/) · [Analisar no Kaggle](https://www.kaggle.com/code/rafaeldiasgarcia/tech-skills-brasil-an-lise-di-ria) · [Baixar o dataset](https://www.kaggle.com/datasets/rafaeldiasgarcia/tech-skills-br) · [Consultar a metodologia](https://github.com/diasgarcia/tech-skills-br/wiki)

O projeto acompanha anúncios de estágio, aprendiz, trainee e nível júnior. A coleta consulta nove portais três vezes por dia. O processo organiza as vagas por área e identifica as habilidades citadas em cada anúncio.

## Visão atual da pesquisa

[![Gráfico de vagas coletadas e habilidades distintas identificadas nos últimos 30 dias](https://diasgarcia.github.io/tech-skills-br/assets/vagas-habilidades-30d.svg)](https://diasgarcia.github.io/tech-skills-br/)

[![Mapa de calor das seis maiores áreas e das seis habilidades mais citadas](https://diasgarcia.github.io/tech-skills-br/assets/areas-habilidades.svg)](https://www.kaggle.com/code/rafaeldiasgarcia/tech-skills-brasil-an-lise-di-ria)

Os gráficos são gerados com o banco consolidado. Eles mudam automaticamente quando uma área ou habilidade altera sua posição no ranking.

## Pergunta da pesquisa

> Em que medida as diretrizes curriculares do MEC e os referenciais da Sociedade Brasileira de Computação preparam os estudantes para as habilidades exigidas pelo mercado de trabalho brasileiro?

Os dados oferecem evidências quantitativas para comparar a formação em Computação com as demandas encontradas nos anúncios.

## Como os dados são produzidos

1. A coleta localiza vagas de entrada em nove portais.
2. Os filtros removem duplicidades e anúncios fora do escopo.
3. Cada vaga recebe uma área técnica, uma modalidade e uma região.
4. Uma taxonomia curada identifica as habilidades presentes na descrição.
5. O projeto publica o banco consolidado, a API, o painel e o dataset.

Detalhes sobre fontes, critérios, limitações e decisões estão na [wiki do projeto](https://github.com/diasgarcia/tech-skills-br/wiki).

## Acesse os resultados

| Recurso | Conteúdo |
|---|---|
| [Painel público](https://diasgarcia.github.io/tech-skills-br/) | Visão geral, rankings e exploradores de vagas e áreas |
| [Notebook no Kaggle](https://www.kaggle.com/code/rafaeldiasgarcia/tech-skills-brasil-an-lise-di-ria) | Análise atualizada da base |
| [Dataset no Kaggle](https://www.kaggle.com/datasets/rafaeldiasgarcia/tech-skills-br) | Snapshot em Parquet para análise e reutilização |
| [API JSON](https://diasgarcia.github.io/tech-skills-br/api/resumo.json) | Dados estáticos usados pelo painel |
| [Relatório consolidado](docs/relatorios/relatorio_banco_consolidado.md) | Resumo textual mais recente |

## Escopo

- A amostra contém vagas encontradas durante o período da pesquisa. Ela não representa todas as vagas de tecnologia do Brasil.
- Os resultados mudam conforme novos anúncios entram na base.
- O projeto não é um portal de empregos e não participa de processos seletivos.
- Os links das vagas identificam a origem das informações.

## Execução local

O guia de [execução rápida](docs/execucao-rapida.md) contém os comandos necessários para preparar o ambiente e consultar a base.

## Pesquisa e licença

Este projeto de iniciação científica é desenvolvido no Centro Universitário das Faculdades Integradas de Ourinhos. A professora Jessica Antonio Delgado orienta a pesquisa.

O código é distribuído sob a [licença MIT](LICENSE).
