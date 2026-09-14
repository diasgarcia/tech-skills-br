"""Contratos de conexao sem acesso ao banco operacional."""

from contextlib import closing
import importlib
import sqlite3

import pytest
from sqlalchemy import text

from api.database import connect_sqlite, init_db, make_engine, read_session, resolve_sqlite_path


def test_engine_nao_cria_diretorio_antes_de_conectar(tmp_path):
    path = tmp_path / "nao-criado" / "vagas.db"

    engine = make_engine(path)
    engine.dispose()

    assert not path.parent.exists()


def test_cli_importacao_nao_exporta_outro_banco(tmp_path, csv_vagas_minimo, monkeypatch):
    from scripts import export_pages_data, import_csv

    path = tmp_path / "selecionada.db"
    configured = tmp_path / "nao-tocar.db"
    monkeypatch.setenv("DATABASE_URL", str(configured))

    def nao_exportar(*args, **kwargs):
        pytest.fail("Importacao nao deve exportar JSON por efeito colateral.")

    monkeypatch.setattr(export_pages_data, "export_all_pages_data", nao_exportar)

    result = import_csv.main(["--csv", str(csv_vagas_minimo), "--db", str(path)])

    assert result == 0
    assert path.exists()
    assert not configured.exists()


def test_import_reextract_nao_cria_base(monkeypatch, tmp_path):
    path = tmp_path / "ausente" / "vagas.db"
    monkeypatch.setenv("DATABASE_URL", str(path))

    importlib.import_module("scripts.reextract_all_skills")

    assert not path.parent.exists()


def test_connect_nao_cria_base_ausente(tmp_path):
    path = tmp_path / "ausente.db"

    with pytest.raises(sqlite3.OperationalError):
        connect_sqlite(path)

    assert not path.exists()


def test_destino_explicito_vence_ambiente_nos_dois_clientes(monkeypatch, tmp_path):
    configured, selected = tmp_path / "env.db", tmp_path / "selected.db"
    monkeypatch.setenv("DATABASE_URL", str(configured))
    init_db(db_path=selected)

    with closing(connect_sqlite(selected)) as conn:
        conn.execute("INSERT INTO tecnologias(nome, grupo) VALUES ('Exemplo', 'teste')")
        conn.commit()

    assert resolve_sqlite_path(selected) == selected
    assert not configured.exists()


def test_conexoes_habilitam_fk_e_exclusao_em_cascata(tmp_path):
    path = tmp_path / "vagas.db"
    init_db(db_path=path)
    with closing(connect_sqlite(path)) as conn, conn:
        conn.execute("INSERT INTO tecnologias(id, nome, grupo) VALUES (1, 'SQL', 'linguagens')")
        conn.execute(
            "INSERT INTO vagas(id, source, external_id, title, area, enrich_encerrada) "
            "VALUES (1, 'teste', '001', 'Dev', 'Backend', 0)"
        )
        conn.execute("INSERT INTO vaga_tecnologia VALUES (1, 1)")
    engine = make_engine(path)

    try:
        with engine.begin() as conn:
            assert conn.scalar(text("PRAGMA foreign_keys")) == 1
            conn.execute(text("DELETE FROM vagas WHERE id = 1"))
        with closing(connect_sqlite(path)) as conn:
            links = conn.execute("SELECT * FROM vaga_tecnologia").fetchall()
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        engine.dispose()

    assert links == []
    assert violations == []


def test_conexao_leitura_recusa_gravacao(tmp_path):
    path = tmp_path / "vagas com #.db"
    init_db(db_path=path)

    with closing(connect_sqlite(path, read_only=True)) as conn:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DELETE FROM vagas")


def test_resolucao_recusa_outro_backend():
    with pytest.raises(ValueError, match="SQLite"):
        resolve_sqlite_path("postgresql://localhost/vagas")


def test_sessao_leitura_recusa_escrita_e_libera_arquivo(tmp_path):
    from sqlalchemy.exc import OperationalError

    path = tmp_path / "leitura.db"
    init_db(db_path=path)

    with pytest.raises(OperationalError, match="readonly"):
        with read_session(path) as session:
            session.execute(text("DELETE FROM vagas"))
    path.unlink()

    assert not path.exists()


@pytest.mark.parametrize("exporter", ["pages", "charts", "report", "seed", "parquet"])
def test_exportadores_nao_criam_banco_inexistente(tmp_path, exporter):
    from sqlalchemy.exc import OperationalError
    from scripts.export_pages_data import export_all_pages_data
    from scripts.export_readme_charts import load_chart_jobs
    from scripts.export_seed import exportar_seed
    from scripts.export_kaggle import exportar
    from scripts.report_db import generate_db_report

    path = tmp_path / "ausente" / "vagas.db"
    operations = {
        "pages": lambda: export_all_pages_data(tmp_path / "json", path),
        "charts": lambda: load_chart_jobs(path),
        "report": lambda: generate_db_report(path, export_md=False),
        "seed": lambda: exportar_seed(path, tmp_path / "vagas.csv"),
        "parquet": lambda: exportar(path, tmp_path / "kaggle"),
    }

    with pytest.raises((OperationalError, sqlite3.OperationalError)):
        operations[exporter]()

    assert not path.exists()
    assert not path.parent.exists()
