"""Testes do gerador de relatorio consolidado do banco (scripts/report_db.py)."""

from pathlib import Path
from scripts.report_db import generate_db_report


def test_generate_db_report_empty_db(tmp_path: Path):
    db_file = tmp_path / "vazio.db"
    out = generate_db_report(db_path=db_file, export_md=False)
    assert out == ""


def test_generate_db_report_with_data(tmp_path: Path):
    from scripts.import_csv import importar

    db_file = tmp_path / "teste.db"
    csv_file = Path(__file__).resolve().parent.parent / "seed" / "vagas.csv"
    if csv_file.exists():
        importar(csv_file, db_path=db_file)
        md_text = generate_db_report(db_path=db_file, export_md=False)
        assert "# Relatório Consolidado da Base de Vagas" in md_text
        assert "Ranking de Áreas de Tecnologia" in md_text
