"""Gera os SVGs do README a partir do banco consolidado."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from api.database import init_db, make_engine
from api.models import Tecnologia, Vaga, vaga_tecnologia
from scraper.charts import ChartJob, export_readme_charts


def load_chart_jobs(db_path: str | Path | None = None) -> list[ChartJob]:
    """Carrega apenas os campos usados pelos graficos."""
    engine = make_engine(db_path)
    init_db(engine)

    with Session(engine) as session:
        vacancy_rows = session.execute(
            select(Vaga.id, Vaga.published_date, Vaga.area)
        ).all()
        skill_rows = session.execute(
            select(vaga_tecnologia.c.vaga_id, Tecnologia.nome).join(
                Tecnologia,
                Tecnologia.id == vaga_tecnologia.c.tecnologia_id,
            )
        ).all()

    skills_by_job: dict[int, list[str]] = defaultdict(list)
    for job_id, skill in skill_rows:
        skills_by_job[job_id].append(skill)

    return [
        ChartJob(
            published_date=published_date,
            area=area,
            skills=tuple(skills_by_job[job_id]),
        )
        for job_id, published_date, area in vacancy_rows
    ]


def export_pages_charts(
    output_dir: Path, db_path: str | Path | None = None
) -> dict[str, Path]:
    """Exporta os dois SVGs estaveis usados pelo README."""
    jobs = load_chart_jobs(db_path)
    files = export_readme_charts(jobs, output_dir)
    if not files:
        raise ValueError("O banco nao contem vagas para gerar os graficos.")
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gera os graficos SVG publicados no README."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Diretorio que recebera os SVGs.",
    )
    parser.add_argument("--db", type=Path, default=None, help="Caminho do SQLite.")
    args = parser.parse_args(argv)

    files = export_pages_charts(args.output_dir, args.db)
    for path in files.values():
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
