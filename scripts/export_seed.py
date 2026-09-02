"""Exporta o estado consolidado do banco de dados para seed/vagas.csv.

Gera o snapshot oficial versionavel para reproducao e deploy na nuvem.
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.database import database_url, make_engine, url_sem_senha  # noqa: E402
from api.models import Vaga  # noqa: E402
from scraper.config import PROJECT_ROOT  # noqa: E402

logger = logging.getLogger("export_seed")

COLUNAS_EXPORTACAO = [
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
    "regiao",
    "polo",
    "enrich_encerrada",
    # O id interno do banco, persistido para que a identidade numerica
    # sobreviva entre as runs: o runner do CI recria o banco do zero a
    # cada rodada, e sem esta coluna os ids mudariam para quase todas as
    # vagas a cada coleta.
    "db_id",
]


def exportar_seed(
    db_path: Path | str | None = None,
    output_csv: Path | str | None = None,
) -> dict:
    """Extrai todas as vagas do banco e grava em seed/vagas.csv."""
    dest_path = (
        Path(output_csv)
        if output_csv
        else (PROJECT_ROOT / "seed" / "vagas.csv")
    )
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    engine = make_engine(database_url(db_path))
    try:
        with Session(engine) as db:
            vagas = db.scalars(select(Vaga).order_by(Vaga.id.asc())).all()

            with open(dest_path, "w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=COLUNAS_EXPORTACAO)
                writer.writeheader()

                for v in vagas:
                    skills_str = ", ".join(
                        sorted(t.nome for t in v.tecnologias if t.nome)
                    )
                    pub_date = (
                        v.published_date.isoformat()
                        if v.published_date
                        else ""
                    )

                    row = {
                        "area": v.area or "Outros/TI Geral",
                        "seniority": v.seniority or "",
                        "title": v.title or "",
                        "company": v.company or "",
                        "source": v.source or "",
                        "location": v.location or "",
                        "workplace_type": v.workplace_type or "Não informado",
                        "published_date": pub_date,
                        "url": v.url or "",
                        "skills": skills_str,
                        "area_score": str(v.area_score) if v.area_score is not None else "",
                        "area_matches": v.area_matches or "",
                        "search_term": v.search_term or "",
                        "external_id": v.external_id or "",
                        "description": v.description or "",
                        "regiao": v.regiao or "",
                        "polo": v.polo or "",
                        "enrich_encerrada": "1" if v.enrich_encerrada else "0",
                        "db_id": str(v.id),
                    }
                    writer.writerow(row)
    finally:
        engine.dispose()


    logger.info("Snapshot exportado com sucesso: %d vagas em %s", len(vagas), dest_path)

    return {
        "total_vagas": len(vagas),
        "arquivo": str(dest_path),
        "db": url_sem_senha(database_url(db_path)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Exporta a base de dados consolidada para seed/vagas.csv.",
    )
    parser.add_argument(
        "--db", default=None,
        help="Caminho do banco SQLite ou URL de conexao PostgreSQL.",
    )
    parser.add_argument(
        "--output", default=None,
        help="Caminho do CSV de destino (padrao: seed/vagas.csv).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)-7s %(message)s",
        stream=sys.stdout,
    )

    resultado = exportar_seed(args.db, args.output)

    print("\n" + "=" * 55)
    print("  SNAPSHOT DE DADOS ATUALIZADO COM SUCESSO!")
    print("=" * 55)
    print(f"  Vagas exportadas .. {resultado['total_vagas']}")
    print(f"  Destino ........... {resultado['arquivo']}")
    print(f"  Origem ............ {resultado['db']}")
    print("=" * 55 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
