# Execução Rápida

O [Manual de Uso](https://github.com/diasgarcia/tech-skills-br/wiki/Manual-de-Uso) na wiki documenta todos os parâmetros e opções.

```powershell
# 0. Primeira execução: carrega o histórico versionado no SQLite local.
python scripts/import_csv.py --csv seed/vagas.csv

# 1. Coleta (Gupy, LinkedIn, Vagas.com, ProgramaThor, Trampos, Solides, GeekHunter):
python main.py

# 2. Consolida as coletas no SQLite:
python scripts/import_csv.py

# 3. Atualiza o snapshot versionado (seed/vagas.csv):
python scripts/export_seed.py

# 4. Gera o relatório estatístico consolidado:
python scripts/report_db.py
```
