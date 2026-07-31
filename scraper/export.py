"""Exportacao: CSV completo de vagas, CSV de ranking e relatorio em Markdown."""

from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime
from pathlib import Path

from .models import WORKPLACE_ORDER, Job

JOB_COLUMNS = [
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

RANKING_COLUMNS = ["posicao", "area", "vagas", "percentual"]


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def export_jobs_csv(jobs: list[Job], output_dir: Path, stamp: str | None = None) -> Path:
    stamp = stamp or _timestamp()
    path = output_dir / f"vagas_{stamp}.csv"
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=JOB_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for job in sorted(jobs, key=lambda j: (j.area, j.title)):
            writer.writerow(job.to_row())
    return path


def build_ranking(jobs: list[Job]) -> list[dict]:
    """Ranking de areas por quantidade de vagas."""
    counts = Counter(job.area for job in jobs)
    total = sum(counts.values()) or 1
    ranking = []
    for position, (area, count) in enumerate(counts.most_common(), start=1):
        ranking.append(
            {
                "posicao": position,
                "area": area,
                "vagas": count,
                "percentual": round(100 * count / total, 1),
            }
        )
    return ranking


def build_workplace_ranking(jobs: list[Job]) -> list[dict]:
    """Distribuicao das vagas por modalidade, na ordem Remoto/Híbrido/Presencial."""
    counts = Counter(job.workplace_type or WORKPLACE_ORDER[-1] for job in jobs)
    total = sum(counts.values()) or 1
    ordered = [m for m in WORKPLACE_ORDER if counts.get(m)]
    ordered += [m for m in counts if m not in WORKPLACE_ORDER]
    return [
        {
            "modalidade": modality,
            "vagas": counts[modality],
            "percentual": round(100 * counts[modality] / total, 1),
        }
        for modality in ordered
    ]


def export_ranking_csv(ranking: list[dict], output_dir: Path,
                       stamp: str | None = None) -> Path:
    stamp = stamp or _timestamp()
    path = output_dir / f"ranking_areas_{stamp}.csv"
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=RANKING_COLUMNS)
        writer.writeheader()
        writer.writerows(ranking)
    return path


def _bar(percent: float, width: int = 30) -> str:
    filled = round(percent / 100 * width)
    return "#" * filled + "." * (width - filled)


def export_report_md(
    jobs: list[Job],
    ranking: list[dict],
    output_dir: Path,
    meta: dict,
    stamp: str | None = None,
) -> Path:
    stamp = stamp or _timestamp()
    path = output_dir / f"relatorio_{stamp}.md"
    total = len(jobs)

    lines: list[str] = []
    lines.append("# Vagas tech junior no Brasil - ranking por area")
    lines.append("")
    lines.append(f"Coleta em **{datetime.now().strftime('%d/%m/%Y %H:%M')}**.")
    lines.append("")
    lines.append(f"- Vagas de nivel de entrada encontradas: **{total}**")
    lines.append(f"- Portais consultados: {', '.join(meta.get('sources', []))}")
    lines.append(f"- Termos de busca: {meta.get('terms_count', 0)}")
    lines.append(f"- Vagas brutas coletadas: {meta.get('raw_jobs', 0)}")
    lines.append(f"- Descartadas por senioridade: {meta.get('dropped_seniority', 0)}")
    lines.append(f"- Descartadas por nao serem de tecnologia: "
                 f"{meta.get('dropped_non_tech', 0)}")
    lines.append(f"- Duplicatas removidas: {meta.get('duplicates', 0)}")
    lines.append(f"- Requests HTTP: {meta.get('requests', 0)}")
    lines.append("")

    lines.append("## Ranking de areas")
    lines.append("")
    lines.append("| # | Area | Vagas | % | |")
    lines.append("|---|------|-------|---|---|")
    for row in ranking:
        lines.append(
            f"| {row['posicao']} | {row['area']} | {row['vagas']} | "
            f"{row['percentual']}% | `{_bar(row['percentual'])}` |"
        )
    lines.append("")

    lines.append("## Distribuicao por senioridade")
    lines.append("")
    seniority_counts = Counter(job.seniority for job in jobs)
    lines.append("| Nivel | Vagas |")
    lines.append("|-------|-------|")
    for label, count in seniority_counts.most_common():
        lines.append(f"| {label} | {count} |")
    lines.append("")

    lines.append("## Modalidade de trabalho")
    lines.append("")
    lines.append("| Modalidade | Vagas | % |")
    lines.append("|------------|-------|---|")
    for row in build_workplace_ranking(jobs):
        lines.append(f"| {row['modalidade']} | {row['vagas']} | {row['percentual']}% |")
    lines.append("")

    lines.append("### Modalidade por área")
    lines.append("")
    modalities = [m for m in WORKPLACE_ORDER
                  if any(j.workplace_type == m for j in jobs)]
    lines.append("| Área | " + " | ".join(modalities) + " |")
    lines.append("|------|" + "|".join(["---"] * len(modalities)) + "|")
    for row in ranking:
        area_jobs = [j for j in jobs if j.area == row["area"]]
        cells = [str(sum(1 for j in area_jobs if j.workplace_type == m))
                 for m in modalities]
        lines.append(f"| {row['area']} | " + " | ".join(cells) + " |")
    lines.append("")

    lines.append("## Vagas por portal")
    lines.append("")
    source_counts = Counter(job.source for job in jobs)
    lines.append("| Portal | Vagas |")
    lines.append("|--------|-------|")
    for label, count in source_counts.most_common():
        lines.append(f"| {label} | {count} |")
    lines.append("")

    lines.append("## Tecnologias mais pedidas")
    lines.append("")
    from .skills import overall_skill_counts

    lines.append("| Tecnologia | Vagas |")
    lines.append("|------------|-------|")
    for skill, count in overall_skill_counts(jobs, top_n=20):
        lines.append(f"| {skill} | {count} |")
    lines.append("")

    lines.append("## Top empresas contratando junior")
    lines.append("")
    company_counts = Counter(job.company for job in jobs if job.company)
    lines.append("| Empresa | Vagas |")
    lines.append("|---------|-------|")
    for label, count in company_counts.most_common(15):
        lines.append(f"| {label} | {count} |")
    lines.append("")

    lines.append("## Amostra de vagas por area")
    lines.append("")
    for row in ranking:
        area = row["area"]
        lines.append(f"### {area} ({row['vagas']} vagas)")
        lines.append("")
        sample = [j for j in jobs if j.area == area][:5]
        for job in sample:
            company = f" - {job.company}" if job.company else ""
            lines.append(f"- [{job.title}]({job.url}){company}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def export_skills_csv(jobs: list[Job], output_dir: Path,
                      stamp: str | None = None, top_n: int = 15) -> Path:
    """Ranking de tecnologias por area, em formato longo (area, tech, vagas)."""
    from .skills import skills_by_area

    stamp = stamp or _timestamp()
    path = output_dir / f"skills_por_area_{stamp}.csv"
    per_area = skills_by_area(jobs, top_n=top_n)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["area", "posicao", "tecnologia", "vagas"])
        for area in sorted(per_area):
            for position, (skill, count) in enumerate(per_area[area], start=1):
                writer.writerow([area, position, skill, count])
    return path


def export_all(jobs: list[Job], output_dir: Path, meta: dict,
               with_charts: bool = True) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = _timestamp()
    ranking = build_ranking(jobs)
    files = {
        "jobs_csv": export_jobs_csv(jobs, output_dir, stamp),
        "ranking_csv": export_ranking_csv(ranking, output_dir, stamp),
        "skills_csv": export_skills_csv(jobs, output_dir, stamp),
        "report_md": export_report_md(jobs, ranking, output_dir, meta, stamp),
    }

    if with_charts:
        from .charts import export_charts

        subtitle = (
            f"{len(jobs)} vagas de nível de entrada · "
            f"{' e '.join(meta.get('sources', []))} · "
            f"coleta em {datetime.now().strftime('%d/%m/%Y')}"
        )
        files.update(export_charts(jobs, output_dir, stamp, subtitle=subtitle))

    return files
