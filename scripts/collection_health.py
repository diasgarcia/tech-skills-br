"""Valida, registra e consulta a saude das coletas."""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from api.database import connect_sqlite, resolve_sqlite_path  # noqa: E402
from api.migrations import migrate_connection  # noqa: E402
from scraper.quality import assess_history, has_high_alerts  # noqa: E402


def load_metrics(path: Path) -> dict:
    metrics = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(metrics, dict) or metrics.get("schema_version") != 1:
        raise ValueError("Arquivo de metricas de coleta invalido.")
    return metrics


def load_history(conn, limit: int = 5) -> list[dict]:
    rows = conn.execute(
        "SELECT escopo_completo, fontes_json FROM coleta_execucoes "
        "WHERE status IN ('ok', 'warning') AND escopo_completo = 1 "
        "ORDER BY coletada_em DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {
            "full_scope": bool(full_scope),
            "source_stats": json.loads(source_stats),
        }
        for full_scope, source_stats in rows
    ]


def check(metrics_path: Path, db_path: str | Path | None = None) -> dict:
    metrics = load_metrics(metrics_path)
    with closing(connect_sqlite(db_path)) as conn:
        migrate_connection(conn)
        historical_alerts = assess_history(metrics, load_history(conn))

    existing = {
        (alert.get("rule"), alert.get("source"))
        for alert in metrics.get("alerts", [])
    }
    metrics.setdefault("alerts", []).extend(
        alert.__dict__
        for alert in historical_alerts
        if (alert.rule, alert.source) not in existing
    )
    metrics_path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print_alerts(metrics)
    return metrics


def print_alerts(metrics: dict) -> None:
    output_path = os.getenv("GITHUB_OUTPUT")
    if os.getenv("GITHUB_ACTIONS") == "true" and output_path:
        failed_sources = sorted({
            row["source"] for row in metrics.get("source_stats", []) if row.get("errors")
        })
        with Path(output_path).open("a", encoding="utf-8") as output:
            output.write(f"has_source_errors={str(bool(failed_sources)).lower()}\n")
            output.write(f"failed_sources={json.dumps(failed_sources, ensure_ascii=True)}\n")
    alerts = metrics.get("alerts", [])
    if not alerts:
        print("Qualidade da coleta: nenhuma anomalia detectada.")
        return
    for alert in alerts:
        level = "ERROR" if alert.get("severity") == "high" else "WARNING"
        print(f"{level}: {alert.get('message', 'Alerta de qualidade')}")
        if alert.get("rule") == "partial_collection" and os.getenv("GITHUB_ACTIONS") == "true":
            print(f"::warning title=Coleta parcial::{alert['message']}")
            summary_path = os.getenv("GITHUB_STEP_SUMMARY")
            if summary_path:
                with Path(summary_path).open("a", encoding="utf-8") as summary:
                    summary.write(f"\n## Coleta parcial\n\n{alert['message']}\n")


def record(metrics_path: Path, db_path: str | Path | None = None) -> None:
    metrics = load_metrics(metrics_path)
    if has_high_alerts(metrics):
        raise ValueError("Coleta com alerta alto nao pode ser registrada como valida.")

    collected = datetime.fromisoformat(metrics["collected_at"])
    if collected.tzinfo is None:
        raise ValueError("collected_at deve incluir fuso horario.")
    collected = collected.astimezone(timezone.utc).replace(tzinfo=None)
    run_key = os.getenv("GITHUB_RUN_ID") or metrics["collected_at"]
    status = "warning" if metrics.get("alerts") else "ok"

    with closing(connect_sqlite(db_path)) as conn:
        migrate_connection(conn)
        with conn:
            conn.execute(
                """
                INSERT INTO coleta_execucoes (
                    run_key, coletada_em, status, escopo_completo,
                    vagas_brutas, vagas_elegiveis, requisicoes,
                    fontes_json, alertas_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_key) DO UPDATE SET
                    coletada_em = excluded.coletada_em,
                    status = excluded.status,
                    escopo_completo = excluded.escopo_completo,
                    vagas_brutas = excluded.vagas_brutas,
                    vagas_elegiveis = excluded.vagas_elegiveis,
                    requisicoes = excluded.requisicoes,
                    fontes_json = excluded.fontes_json,
                    alertas_json = excluded.alertas_json
                """,
                (
                    run_key,
                    collected.isoformat(sep=" "),
                    status,
                    int(bool(metrics.get("full_scope"))),
                    int(metrics.get("raw_jobs", 0)),
                    int(metrics.get("eligible_jobs", 0)),
                    int(metrics.get("requests", 0)),
                    json.dumps(metrics.get("source_stats", []), ensure_ascii=False),
                    json.dumps(metrics.get("alerts", []), ensure_ascii=False),
                ),
            )
    print(f"Coleta registrada: {status} em {collected.isoformat()}Z")


def freshness(db_path: str | Path | None = None, *, max_age_hours: float = 24) -> dict:
    with closing(connect_sqlite(db_path, read_only=True)) as conn:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'coleta_execucoes'"
        ).fetchone()
        row = (
            conn.execute(
                "SELECT coletada_em, status FROM coleta_execucoes "
                "WHERE status IN ('ok', 'warning') AND escopo_completo = 1 "
                "ORDER BY coletada_em DESC LIMIT 1"
            ).fetchone()
            if table else None
        )
    if row is None:
        return {"state": "no_history", "last_collection": None, "age_hours": None}

    collected = datetime.fromisoformat(row[0]).replace(tzinfo=timezone.utc)
    age_hours = (datetime.now(timezone.utc) - collected).total_seconds() / 3600
    return {
        "state": "current" if age_hours <= max_age_hours else "stale",
        "last_collection": collected.isoformat(),
        "age_hours": round(age_hours, 1),
        "status": row[1],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "record", "status"))
    parser.add_argument("--metrics", type=Path, default=Path("output/collection_metrics.json"))
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--max-age-hours", type=float, default=24)
    parser.add_argument("--warn-only", action="store_true", help="Frescor atrasado gera aviso, sem erro de saida.")
    args = parser.parse_args(argv)
    db_path = resolve_sqlite_path(args.db)

    if args.command == "check":
        return int(has_high_alerts(check(args.metrics, db_path)))
    if args.command == "record":
        record(args.metrics, db_path)
        return 0

    result = freshness(db_path, max_age_hours=args.max_age_hours)
    print(json.dumps(result, ensure_ascii=False))
    if args.warn_only and result["state"] != "current":
        print(
            "::warning title=Coleta completa atrasada::O frescor global nao foi renovado. "
            "Veja os alertas de qualidade desta rodada.",
            file=sys.stderr,
        )
        return 0
    return int(result["state"] != "current")


if __name__ == "__main__":
    raise SystemExit(main())
