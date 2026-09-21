from datetime import datetime, timedelta, timezone
import json
import sqlite3

from api.database import init_db
from scripts.collection_health import check, freshness, record


def _metrics(path, *, collected_at=None, full_scope=True):
    payload = {
        "schema_version": 1,
        "collected_at": collected_at or datetime.now(timezone.utc).isoformat(),
        "full_scope": full_scope,
        "raw_jobs": 100,
        "eligible_jobs": 70,
        "requests": 12,
        "source_stats": [
            {"source": "gupy", "raw_jobs": 100, "requests": 12, "errors": []}
        ],
        "alerts": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_registro_e_idempotente_e_alimenta_frescor(tmp_path, monkeypatch):
    db_path = tmp_path / "vagas.db"
    metrics_path = _metrics(tmp_path / "metrics.json")
    init_db(db_path=db_path)
    monkeypatch.setenv("GITHUB_RUN_ID", "123")

    check(metrics_path, db_path)
    record(metrics_path, db_path)
    record(metrics_path, db_path)
    status = freshness(db_path)

    with sqlite3.connect(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM coleta_execucoes").fetchone()[0]
    assert total == 1
    assert status["state"] == "current"


def test_frescor_detecta_ultima_coleta_atrasada(tmp_path):
    db_path = tmp_path / "vagas.db"
    old = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    metrics_path = _metrics(tmp_path / "metrics.json", collected_at=old)
    init_db(db_path=db_path)
    record(metrics_path, db_path)

    status = freshness(db_path, max_age_hours=24)

    assert status["state"] == "stale"
    assert status["age_hours"] >= 29


def test_coleta_parcial_nao_renova_frescor_global(tmp_path):
    db_path = tmp_path / "vagas.db"
    metrics_path = _metrics(tmp_path / "metrics.json", full_scope=False)
    init_db(db_path=db_path)
    record(metrics_path, db_path)

    status = freshness(db_path)

    assert status["state"] == "no_history"
