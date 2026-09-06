# Execução Rápida

O [Manual de Uso](https://github.com/diasgarcia/tech-skills-br/wiki/Manual-de-Uso) na wiki documenta todos os parâmetros e opções.

```powershell
# 0. Primeira execução: baixa o banco mais recente da release do GitHub.
gh release download latest --pattern vagas.db --dir data --clobber

# 1. Coleta (Gupy, LinkedIn, Vagas.com, Trampos, Solides, GeekHunter, InfoJobs, Abler, Recrutei):
python main.py

# 2. Consolida as coletas no SQLite:
python scripts/import_csv.py

# 3. Gera o snapshot CSV (seed/vagas.csv):
python scripts/export_seed.py

# 4. Gera o relatório estatístico consolidado:
python scripts/report_db.py

# 5. Publica o banco e o CSV novos na release (opcional, quando quiser devolver o estado):
gh release upload latest data/vagas.db seed/vagas.csv --clobber

# 6. Envia o snapshot novo para o Kaggle (precisa do KAGGLE_API_TOKEN no ambiente):
python scripts/export_kaggle.py
```

O estado operacional vive na release `latest` (`vagas.db` + `vagas.csv`). O histórico versionado fica no Kaggle: <https://www.kaggle.com/datasets/rafaeldiasgarcia/tech-skills-br>
