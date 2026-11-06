---
language:
- pt
license: mit
pretty_name: Tech Skills Brasil
tags:
- brazil
- jobs
- labor-market
configs:
- config_name: default
  data_files:
  - split: vagas
    path: vagas.parquet
---

# Tech Skills Brasil

Esta base reúne anúncios de vagas de entrada em tecnologia no Brasil. Inclui vagas de estágio, aprendiz, trainee e nível júnior. Cada linha representa um anúncio. A coluna `skills` lista as habilidades identificadas no texto do anúncio.

A coleta consulta portais públicos de emprego. O projeto consolida os anúncios, classifica a área e extrai habilidades com um vocabulário de termos técnicos. A coleta roda três vezes por dia. A branch `main` mostra o snapshot mais recente. Tags com data preservam versões específicas.

Os dados descrevem os anúncios coletados. A cobertura varia por fonte, e alguns anúncios têm descrição incompleta ou modalidade ausente. O projeto documenta o escopo e os critérios de coleta na wiki.

- [Código e releases](https://github.com/diasgarcia/tech-skills-br)
- [Metodologia e limitações](https://github.com/diasgarcia/tech-skills-br/wiki)
- [Dataset no Kaggle](https://www.kaggle.com/datasets/rafaeldiasgarcia/tech-skills-br)
- [Painel](https://diasgarcia.github.io/tech-skills-br/)
