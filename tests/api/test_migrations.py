import sqlite3
from contextlib import closing

import pytest

from api.enrichment_state import EnrichmentStatus, record_attempt
from api.migrations import migrate_connection


@pytest.fixture
def legacy():
    with closing(sqlite3.connect(":memory:")) as conn:
        conn.execute("CREATE TABLE vagas (id INTEGER PRIMARY KEY, enrich_encerrada INTEGER)")
        conn.executemany("INSERT INTO vagas VALUES (?, ?)", [(1, 1), (2, 0)])
        conn.commit()
        yield conn


def test_migracao_preserva_legado_sem_inventar_expiracao(legacy):
    migrate_connection(legacy)

    rows = legacy.execute(
        "SELECT id, enrich_encerrada, enrichment_status, advertisement_status, enrichment_attempted_at "
        "FROM vagas ORDER BY id"
    ).fetchall()

    assert rows == [(1, 1, "legacy_resolved", "unknown", None), (2, 0, "pending", "unknown", None)]


def test_tentativas_nao_se_confundem_com_disponibilidade_e_migracao_e_idempotente(legacy):
    migrate_connection(legacy)
    with legacy:
        record_attempt(legacy, 1, EnrichmentStatus.UNAVAILABLE, "http_404")
        record_attempt(legacy, 2, EnrichmentStatus.SUCCEEDED)
        record_attempt(legacy, 1, EnrichmentStatus.FAILED, "http_500")
    before = legacy.execute("SELECT * FROM vagas").fetchall()

    migrate_connection(legacy)

    assert legacy.execute("SELECT * FROM vagas").fetchall() == before
    assert legacy.execute(
        "SELECT enrichment_status, advertisement_status FROM vagas ORDER BY id"
    ).fetchall() == [("failed", "unavailable"), ("succeeded", "available")]


def test_migracao_recusa_esquema_futuro_sem_modificar(legacy):
    legacy.execute("PRAGMA user_version = 99")

    with pytest.raises(ValueError, match="mais nova"):
        migrate_connection(legacy)

    assert [row[1] for row in legacy.execute("PRAGMA table_info(vagas)")] == ["id", "enrich_encerrada"]


def test_falha_na_migracao_desfaz_colunas_e_preserva_dados(legacy, monkeypatch):
    from api import migrations
    monkeypatch.setattr(migrations, "ADDITIONAL_COLUMNS", {"campo": "TEXT", "invalido": "?!"})

    with pytest.raises(sqlite3.OperationalError):
        migrate_connection(legacy)

    assert [row[1] for row in legacy.execute("PRAGMA table_info(vagas)")] == ["id", "enrich_encerrada"]
    assert legacy.execute("SELECT * FROM vagas ORDER BY id").fetchall() == [(1, 1), (2, 0)]
