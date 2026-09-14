from contextlib import closing
from unittest.mock import Mock

import pytest

from api.database import connect_sqlite, init_db
from scripts import reextract_all_skills as module


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "vagas.db"
    init_db(db_path=path)
    monkeypatch.setattr(module, "technologies", lambda: {"SQL": "linguagens", "Python": "linguagens"})
    with closing(connect_sqlite(path)) as conn, conn:
        conn.execute("INSERT INTO tecnologias(id, nome, grupo) VALUES (1, 'SQL', 'antigo')")
        conn.execute(
            "INSERT INTO vagas(id, source, external_id, title, area, description, enrich_encerrada, updated_at) "
            "VALUES (1, 'teste', '001', 'Dev Python', 'Backend', 'Python', 0, '2020-01-01')"
        )
        conn.execute("INSERT INTO vaga_tecnologia VALUES (1, 1)")
    return path


def snapshot(path):
    with closing(connect_sqlite(path, read_only=True)) as conn:
        return {
            name: conn.execute(f"SELECT * FROM {name}").fetchall()
            for name in ("vagas", "tecnologias", "vaga_tecnologia")
        }


def test_reextracao_seleciona_base_sincroniza_e_e_idempotente(db, monkeypatch, tmp_path):
    other = tmp_path / "outro.db"
    init_db(db_path=other)
    monkeypatch.setenv("DATABASE_URL", str(other))
    original_other = snapshot(other)

    result = module.reextract_all_skills(db)
    after_first = snapshot(db)
    repeated = module.reextract_all_skills(db)

    assert result.adicionados == result.removidos == result.vagas_alteradas == 1
    assert repeated.adicionados == repeated.removidos == repeated.vagas_alteradas == 0
    assert snapshot(db) == after_first
    assert snapshot(other) == original_other


def test_dry_run_desfaz_links_vocabulario_e_timestamps(db):
    before = snapshot(db)

    result = module.reextract_all_skills(db, dry_run=True)

    assert result.dry_run
    assert result.adicionados == 1
    assert snapshot(db) == before


def test_falha_extracao_desfaz_inclusive_vocabulario(db, monkeypatch):
    before = snapshot(db)
    extractor = Mock()
    extractor.extract.side_effect = RuntimeError("falha simulada")
    monkeypatch.setattr(module, "default_extractor", lambda: extractor)

    with pytest.raises(RuntimeError, match="simulada"):
        module.reextract_all_skills(db)

    assert snapshot(db) == before


def test_falha_de_gravacao_desfaz_remocao_dos_links(db):
    with closing(connect_sqlite(db)) as conn:
        conn.execute("CREATE TRIGGER falha BEFORE INSERT ON vaga_tecnologia BEGIN SELECT RAISE(ABORT, 'simulada'); END")
    before = snapshot(db)

    with pytest.raises(Exception, match="simulada"):
        module.reextract_all_skills(db)

    assert snapshot(db) == before
