import sqlite3
import yaml
from pathlib import Path

import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.skills import SkillExtractor


with open(PROJECT_ROOT / "scraper" / "rules" / "skills.yml", encoding="utf-8") as fh:
    rules = yaml.safe_load(fh) or {}
extractor = SkillExtractor(rules)

conn = sqlite3.connect(PROJECT_ROOT / "data" / "vagas.db")
c = conn.cursor()

# Garante que todas as tecnologias de skills.yml existam na tabela
c.execute("SELECT nome FROM tecnologias")
existentes = {nome.lower() for (nome,) in c.fetchall()}
for group, entries in rules.items():
    for name in entries:
        if name.lower() not in existentes:
            c.execute("INSERT INTO tecnologias (nome, grupo) VALUES (?, ?)", (name, group))
conn.commit()

c.execute("SELECT id, nome FROM tecnologias")
tech_map = {nome.lower(): tid for tid, nome in c.fetchall()}

c.execute("DELETE FROM vaga_tecnologia")


c.execute("SELECT id, title, description FROM vagas")
rows = c.fetchall()

total_links = 0
for vid, title, desc in rows:
    text = f"{title} {desc or ''}"
    skills = extractor.extract(text)
    for s in skills:
        tid = tech_map.get(s.lower())
        if tid:
            c.execute("INSERT OR IGNORE INTO vaga_tecnologia (vaga_id, tecnologia_id) VALUES (?, ?)", (vid, tid))
            total_links += 1

conn.commit()
conn.close()
print(f"Sucesso: {total_links} vinculos de habilidades re-extraidos com precisao para {len(rows)} vagas!")
