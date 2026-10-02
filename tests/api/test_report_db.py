"""Testes do gerador de relatorio consolidado do banco (scripts/report_db.py)."""

import argparse
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path

from api.database import connect_sqlite, init_db
from scripts import report_db
from scripts.import_csv import importar
from scripts.report_db import generate_db_report
from scripts.resumo_commit import resumir


def _banco(tmp_path, timestamps):
    db_file = tmp_path / "vagas.db"
    init_db(db_path=db_file)
    with closing(connect_sqlite(db_file)) as conn, conn:
        conn.executemany(
            "INSERT INTO vagas (source, external_id, title, area, enrich_encerrada, "
            "created_at, updated_at, published_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "linkedin", str(index), "Desenvolvedor Junior", "Backend", 0,
                    timestamp, "2026-10-01 23:00:00", "2026-09-30",
                )
                for index, timestamp in enumerate(timestamps, 1)
            ],
        )
    return db_file


def test_generate_db_report_empty_db(tmp_path: Path):
    db_file = tmp_path / "vazio.db"
    init_db(db_path=db_file)

    out = generate_db_report(db_path=db_file, export_md=False)

    assert out == ""


def test_generate_db_report_with_data(tmp_path: Path, csv_vagas_minimo):
    db_file = tmp_path / "teste.db"
    importar(csv_vagas_minimo, db_path=db_file)

    md_text = generate_db_report(db_path=db_file, export_md=False)

    assert "# Relatório Consolidado da Base de Vagas" in md_text
    assert "Ranking de Áreas de Tecnologia" in md_text


def test_relatorio_e_commit_contam_todas_as_rodadas_do_mesmo_dia(tmp_path):
    db_file = _banco(tmp_path, [
        "2026-10-01 02:59:59",
        "2026-10-01 03:00:00",
        "2026-10-01 12:16:05",
        "2026-10-01 17:16:05",
        "2026-10-01 22:16:05",
        "2026-10-02 02:59:59",
        "2026-10-02 03:00:00",
    ])
    dia = date(2026, 10, 1)
    args = argparse.Namespace(
        db=db_file, dia=dia, brutas=100, elegiveis=10, novas=1, atualizadas=9,
        log=None, summary_json=None,
    )
    before = db_file.read_bytes()

    md_text = generate_db_report(db_path=db_file, export_md=False, dia=dia)
    commit_text = resumir(args)

    assert "**Vagas novas no dia (01/10/2026, Brasília):** 5" in md_text
    assert "**Total de vagas consolidadas:** 7" in md_text
    assert "- Novas no dia (01/10/2026, Brasilia): 5 vagas" in commit_text
    assert "- Importacao da ultima rodada: 1 novas | 9 atualizadas" in commit_text
    assert db_file.read_bytes() == before


def test_relatorio_mostra_zero_sem_contar_atualizacoes_de_vagas_antigas(tmp_path):
    db_file = _banco(tmp_path, ["2026-09-30 12:00:00"])

    md_text = generate_db_report(db_path=db_file, export_md=False, dia=date(2026, 10, 1))

    assert "**Vagas novas no dia (01/10/2026, Brasília):** 0" in md_text
    assert "**Total de vagas consolidadas:** 1" in md_text


def test_relatorio_exporta_total_diario_nos_dois_arquivos_em_brasilia(tmp_path, monkeypatch):
    db_file = _banco(tmp_path, ["2026-10-01 22:16:05", "2026-10-02 03:00:00"])
    output_dir = tmp_path / "output"
    project_root = tmp_path / "projeto"

    class DataFixa(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 2, 2, 30, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(report_db, "datetime", DataFixa)
    monkeypatch.setattr(report_db, "DEFAULT_OUTPUT_DIR", output_dir)
    monkeypatch.setattr(report_db, "PROJECT_ROOT", project_root)

    md_text = generate_db_report(db_path=db_file)

    assert "**Data de geração:** 01/10/2026 23:30 (Brasília)" in md_text
    assert "**Vagas novas no dia (01/10/2026, Brasília):** 1" in md_text
    assert (output_dir / "relatorio_banco_consolidado_20261001_233000.md").read_text(
        encoding="utf-8"
    ) == md_text
    assert (project_root / "docs/relatorios/relatorio_banco_consolidado.md").read_text(
        encoding="utf-8"
    ) == md_text


def test_cli_relatorio_recebe_dia_do_workflow(tmp_path, capsys):
    db_file = _banco(tmp_path, ["2026-10-01 12:00:00", "2026-10-02 12:00:00"])

    exit_code = report_db.main(["--db", str(db_file), "--dia", "2026-10-01", "--no-export"])

    assert exit_code == 0
    assert "Novas no dia (01/10/2026, Brasília): 1" in capsys.readouterr().out
