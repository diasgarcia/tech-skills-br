# Mapeamento de Skills em Tecnologia no Brasil (projeto)

## Resumo

Projeto de dados (projeto de dados) que coleta e extrai as habilidades técnicas demandadas pelo mercado de tecnologia no Brasil. Esses dados serão posteriormente confrontados com as referências públicas e os referências técnicas.

| Item                             | Descrição                                                                                                                                      |
| :------------------------------- | :----------------------------------------------------------------------------------------------------------------------------------------------- |
| **Linguagem**              | Python 3.12+                                                                                                                                     |
| **Banco de dados**         | SQLite (SQLAlchemy 2.0)                                                                                                                          |
| **Documentação**         | [Wiki](https://github.com/diasgarcia/tech-skills-br/wiki) — Manual de Uso, Arquitetura, Pipeline, Modelo de Dados, Classificação e Automação |
| **Integração contínua** | [GitHub Actions](https://github.com/diasgarcia/tech-skills-br/actions/workflows/ci.yml)                                                           |

## Objetivo do Projeto

> **O projeto organiza dados sobre habilidades citadas em anúncios de vagas de entrada em tecnologia no Brasil.**

Para produzir esses dados com evidências quantitativas e reprodutíveis, o projeto executa um pipeline de coleta multi-fonte, extração de tecnologias por taxonomia curada, deduplicação e análise estatística. A metodologia completa está documentada na [wiki](https://github.com/diasgarcia/tech-skills-br/wiki).

## Execução Rápida

Os comandos essenciais estão em [docs/execucao-rapida](docs/execucao-rapida.md).

## Site Público e API JSON Estática (GitHub Pages)

O projeto publica um painel web minimalista e uma API JSON estática com CORS liberado no GitHub Pages:

**Base URL:** [diasgarcia.github.io/tech-skills-br](https://diasgarcia.github.io/tech-skills-br/)

```http
GET /api/resumo.json HTTP/1.1

GET /api/areas.json HTTP/1.1

GET /api/tecnologias.json HTTP/1.1

GET /api/vagas.json HTTP/1.1
```

## Dataset no Kaggle

A base tambem fica no Kaggle.
O dataset tem snapshots diarios em Parquet.
Acesse: [kaggle.com/datasets/rafaeldiasgarcia/tech-skills-br](https://www.kaggle.com/datasets/rafaeldiasgarcia/tech-skills-br)
