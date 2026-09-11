import csv
import sys
from pathlib import Path

import pytest

# Permite rodar `pytest` a partir da raiz do projeto sem instalar o pacote.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def csv_vagas_minimo(tmp_path):
    path = tmp_path / "vagas_20260731_174407.csv"
    fields = [
        "area",
        "seniority",
        "title",
        "company",
        "source",
        "location",
        "workplace_type",
        "published_date",
        "url",
        "skills",
        "area_score",
        "area_matches",
        "search_term",
        "external_id",
        "description",
    ]
    row = {field: "" for field in fields}
    row.update(
        {
            "area": "Data",
            "seniority": "Júnior",
            "title": "Analista de Dados Jr",
            "company": "ACME",
            "source": "gupy",
            "location": "São Paulo, SP",
            "workplace_type": "Híbrido",
            "published_date": "2026-07-20",
            "url": "https://example.com/jobs/1",
            "skills": "Python, SQL",
            "area_score": "12.0",
            "area_matches": "analista de dados(t)",
            "search_term": "analista de dados junior",
            "external_id": "1",
            "description": "Analisar dados com Python e SQL.",
        }
    )
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerow(row)
    return path
