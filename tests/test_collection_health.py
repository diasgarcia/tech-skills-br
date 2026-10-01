from datetime import datetime, timedelta, timezone
import json
import sqlite3

import pytest

from api.database import init_db
from scripts.collection_health import check, freshness, main, record
from scraper.models import Job, SourceStats
from scraper.quality import build_metrics, write_metrics


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


def test_falha_de_fonte_registra_parcial_sem_perder_historico_completo(tmp_path, monkeypatch):
    db_path = tmp_path / "vagas.db"
    complete_at = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    metrics_path = _metrics(tmp_path / "metrics.json", collected_at=complete_at)
    init_db(db_path=db_path)
    record(metrics_path, db_path)
    metrics = build_metrics(
        [Job(source="linkedin", external_id="1", title="Desenvolvedor Junior")],
        [SourceStats("gupy", errors=["HTTP 404"]), SourceStats("linkedin", raw_jobs=1)],
        raw_jobs=1, requests=2, full_scope=True,
    )
    write_metrics(metrics, metrics_path)
    monkeypatch.setenv("GITHUB_RUN_ID", "partial-123")

    checked = check(metrics_path, db_path)
    record(metrics_path, db_path)
    status = freshness(db_path)

    with sqlite3.connect(db_path) as conn:
        partial = conn.execute(
            "SELECT status, escopo_completo FROM coleta_execucoes WHERE run_key = 'partial-123'"
        ).fetchone()
        total = conn.execute("SELECT COUNT(*) FROM coleta_execucoes").fetchone()[0]
    assert not any(alert["severity"] == "high" for alert in checked["alerts"])
    assert partial == ("warning", 0)
    assert total == 2
    assert status["state"] == "stale"
    assert status["last_collection"] == complete_at


def test_coleta_parcial_aparece_no_resumo_do_actions(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "vagas.db"
    summary_path = tmp_path / "summary.md"
    init_db(db_path=db_path)
    metrics = build_metrics(
        [Job(source="linkedin", external_id="1", title="Desenvolvedor Junior")],
        [SourceStats("gupy", errors=["HTTP 404"])],
        raw_jobs=1, requests=1, full_scope=True,
    )
    metrics_path = write_metrics(metrics, tmp_path / "metrics.json")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))

    check(metrics_path, db_path)

    assert "::warning title=Coleta parcial::" in capsys.readouterr().out
    assert "Coleta parcial: falha em gupy" in summary_path.read_text(encoding="utf-8")


def test_status_pode_avisar_sem_bloquear_snapshot_valido(tmp_path, capsys):
    db_path = tmp_path / "vagas.db"
    init_db(db_path=db_path)

    exit_code = main(["status", "--db", str(db_path), "--warn-only"])
    output = capsys.readouterr()

    assert exit_code == 0
    assert json.loads(output.out)["state"] == "no_history"
    assert "::warning title=Coleta completa atrasada::" in output.err


def test_status_apenas_aviso_nao_oculta_erro_operacional(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("Banco indisponivel")

    monkeypatch.setattr("scripts.collection_health.freshness", fail)

    with pytest.raises(RuntimeError, match="Banco indisponivel"):
        main(["status", "--db", str(tmp_path / "vagas.db"), "--warn-only"])
