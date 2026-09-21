"""Checagens de plausibilidade para uma execucao de coleta."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import json
from pathlib import Path
from statistics import median

from .models import NAO_INFORMADO, WORKPLACE_ORDER, Job, SourceStats

VOLATILE_SOURCES = frozenset({"abler", "recrutei"})


@dataclass(frozen=True)
class QualityAlert:
    rule: str
    severity: str
    message: str
    source: str | None = None
    value: int | float | str | None = None
    limit: int | float | str | None = None


def assess_current(
    jobs: list[Job],
    stats: list[SourceStats],
    *,
    full_scope: bool,
    today: date | None = None,
) -> list[QualityAlert]:
    alerts: list[QualityAlert] = []
    today = today or datetime.now(timezone.utc).date()

    if full_scope and not jobs:
        alerts.append(QualityAlert(
            "collection_empty", "high", "A coleta completa nao produziu vagas.",
            value=0, limit="> 0",
        ))

    if full_scope:
        for stat in stats:
            if (
                stat.source not in VOLATILE_SOURCES
                and stat.raw_jobs == 0
                and not stat.errors
            ):
                alerts.append(QualityAlert(
                    "source_empty", "high",
                    f"{stat.source}: a fonte retornou zero vagas sem registrar erro.",
                    source=stat.source, value=0, limit="> 0",
                ))

    for stat in stats:
        if stat.errors:
            alerts.append(QualityAlert(
                "source_errors", "warning",
                f"{stat.source}: {len(stat.errors)} erro(s) durante a coleta.",
                source=stat.source, value=len(stat.errors), limit=0,
            ))

    valid_workplaces = set(WORKPLACE_ORDER)
    invalid_workplaces = [
        job for job in jobs
        if (job.workplace_type or NAO_INFORMADO) not in valid_workplaces
    ]
    if invalid_workplaces:
        alerts.append(QualityAlert(
            "invalid_workplace", "high",
            f"{len(invalid_workplaces)} vaga(s) usam modalidade fora do vocabulario.",
            value=len(invalid_workplaces), limit=0,
        ))

    invalid_urls = [
        job for job in jobs
        if job.url and not job.url.lower().startswith(("http://", "https://"))
    ]
    if invalid_urls:
        alerts.append(QualityAlert(
            "invalid_url", "warning",
            f"{len(invalid_urls)} vaga(s) possuem URL invalida.",
            value=len(invalid_urls), limit=0,
        ))

    future_dates = []
    for job in jobs:
        try:
            published = date.fromisoformat(job.published_date[:10]) if job.published_date else None
        except ValueError:
            continue
        if published and published > today:
            future_dates.append(job)
    if future_dates:
        alerts.append(QualityAlert(
            "future_date", "warning",
            f"{len(future_dates)} vaga(s) possuem data de publicacao futura.",
            value=len(future_dates), limit=0,
        ))

    if len(jobs) >= 50:
        fallback_count = sum(job.area == "Outros/TI Geral" for job in jobs)
        fallback_share = fallback_count / len(jobs)
        if fallback_share > 0.55:
            alerts.append(QualityAlert(
                "degenerated_classification", "warning",
                f"{fallback_share:.0%} das vagas ficaram em Outros/TI Geral.",
                value=round(fallback_share, 3), limit=0.55,
            ))

    by_source = Counter(job.source for job in jobs)
    missing_company = Counter(job.source for job in jobs if not job.company.strip())
    for source, total in by_source.items():
        if total < 20:
            continue
        share = missing_company[source] / total
        if share > 0.20:
            alerts.append(QualityAlert(
                "missing_company", "warning",
                f"{source}: {share:.0%} das vagas nao informam empresa.",
                source=source, value=round(share, 3), limit=0.20,
            ))

    return alerts


def assess_history(metrics: dict, history: list[dict]) -> list[QualityAlert]:
    if not metrics.get("full_scope"):
        return []

    alerts: list[QualityAlert] = []
    current = {
        row["source"]: int(row.get("raw_jobs", 0))
        for row in metrics.get("source_stats", [])
    }
    previous: dict[str, list[int]] = {}
    for run in history[:5]:
        if not run.get("full_scope"):
            continue
        for row in run.get("source_stats", []):
            previous.setdefault(row["source"], []).append(int(row.get("raw_jobs", 0)))

    for source, value in current.items():
        if source in VOLATILE_SOURCES:
            continue
        samples = previous.get(source, [])
        if len(samples) < 3:
            continue
        reference = median(samples)
        limit = reference * 0.30
        if reference >= 30 and value < limit:
            alerts.append(QualityAlert(
                "sharp_drop", "high",
                f"{source}: {value} vagas brutas; referencia recente {reference:g}.",
                source=source, value=value, limit=round(limit),
            ))
    return alerts


def build_metrics(
    jobs: list[Job],
    stats: list[SourceStats],
    *,
    raw_jobs: int,
    requests: int,
    full_scope: bool,
) -> dict:
    alerts = assess_current(jobs, stats, full_scope=full_scope)
    return {
        "schema_version": 1,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "full_scope": full_scope,
        "raw_jobs": raw_jobs,
        "eligible_jobs": len(jobs),
        "requests": requests,
        "source_stats": [
            {
                "source": stat.source,
                "raw_jobs": stat.raw_jobs,
                "requests": stat.requests_made,
                "errors": list(stat.errors),
            }
            for stat in stats
        ],
        "alerts": [asdict(alert) for alert in alerts],
    }


def write_metrics(metrics: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def has_high_alerts(metrics: dict) -> bool:
    return any(alert.get("severity") == "high" for alert in metrics.get("alerts", []))
