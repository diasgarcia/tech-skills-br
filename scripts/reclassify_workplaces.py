"""Reavalia modalidades do LinkedIn com as regras atuais."""

from __future__ import annotations

import argparse
from contextlib import closing
import logging
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from api.database import connect_sqlite, resolve_sqlite_path  # noqa: E402
from api.migrations import migrate_connection  # noqa: E402
from scraper.config import workplace_override  # noqa: E402
from scraper.geo import default_geo_classifier  # noqa: E402
from scraper.models import infer_linkedin_workplace  # noqa: E402

logger = logging.getLogger("reclassify_workplaces")


def reclassify_linkedin_workplaces(db_path: str | Path | None = None) -> dict:
    geo = default_geo_classifier()
    analyzed = 0
    changed = 0

    with closing(connect_sqlite(db_path)) as conn:
        migrate_connection(conn)
        rows = conn.execute(
            "SELECT id, external_id, title, location, workplace_type, "
            "workplace_declared, description "
            "FROM vagas WHERE source = 'linkedin'"
        ).fetchall()
        with conn:
            for (
                db_id, external_id, title, location, current, declared, description
            ) in rows:
                analyzed += 1
                curated_workplace = workplace_override("linkedin", external_id)
                workplace = curated_workplace or infer_linkedin_workplace(
                    current, bool(declared), location=location,
                    title=title, description=description,
                )
                new_declared = bool(declared) or bool(curated_workplace)
                if workplace == (current or "") and new_declared == bool(declared):
                    continue
                polo, region = geo.classify(location, workplace)
                conn.execute(
                    "UPDATE vagas SET workplace_type = ?, polo = ?, regiao = ?, "
                    "workplace_declared = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (workplace, polo, region, new_declared, db_id),
                )
                changed += 1

    logger.info("Modalidades do LinkedIn: %d analisadas, %d alteradas.", analyzed, changed)
    return {"analyzed": analyzed, "changed": changed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args(argv)
    result = reclassify_linkedin_workplaces(resolve_sqlite_path(args.db))
    print(f"Analisadas: {result['analyzed']} | Alteradas: {result['changed']}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    raise SystemExit(main())
