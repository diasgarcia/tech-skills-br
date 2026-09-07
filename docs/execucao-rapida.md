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

## Atualizar o repo local (puxar a base nova do GitHub)

O banco **não fica no git** — ele vive na release. Então `git pull` traz código e relatórios, mas não a base. Para deixar o repo local igual ao do GitHub:

```powershell
# 1. Primeira vez só: logar no GitHub CLI.
gh auth login

# 2. Traz código, scripts e relatórios novos:
git pull origin main

# 3. Baixa o banco operacional mais recente da release:
gh release download latest --pattern vagas.db --dir data --clobber

# 4. Confere se veio a base atualizada (total de vagas e maior id):
python -c "import sqlite3; c = sqlite3.connect('data/vagas.db'); print(c.execute('SELECT COUNT(*), MAX(id) FROM vagas').fetchone())"
```

Dica: compare o `MAX(id)` impresso com o da release no GitHub; se for igual, a base local está atualizada. A partir daí, `python main.py` coleta por cima dessa base, e os passos 2–6 da seção anterior seguem valendo.
