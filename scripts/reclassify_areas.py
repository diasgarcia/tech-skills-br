"""Reclassifica a area das vagas usando as regras mais recentes.

Dois modos, para evitar trabalho inutil:

- padrao (sem --todas): reclassifica apenas as vagas que ainda podem
  melhorar -- area vazia, invalida ou "Outros/TI Geral" -- e que tenham
  descricao. E o que roda no fluxo diario, DEPOIS do enriquecimento:
  vagas do LinkedIn classificadas so pelo titulo ganham a area correta
  na mesma run, sem esperar a rodada seguinte.

- --todas: reclassifica TODAS as vagas com descricao, atualizando apenas
  as que mudarem (sem UPDATE desnecessario). Uso manual, quando as
  regras de areas.yml mudam.

    python scripts/reclassify_areas.py
    python scripts/reclassify_areas.py --todas
"""

from __future__ import annotations

import argparse
from contextlib import closing
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.classifier import default_classifier  # noqa: E402
from api.database import connect_sqlite, resolve_sqlite_path  # noqa: E402

logger = logging.getLogger("reclassify_areas")


def reclassificar(db_path: Path | str | None = None, todas: bool = False) -> dict:
    clf = default_classifier()
    validas = set(clf.areas)

    mudadas = 0
    analisadas = 0
    with closing(connect_sqlite(db_path)) as conn, conn:
        params = []
        query = (
            "SELECT id, title, area, area_score, area_matches, description "
            "FROM vagas WHERE LENGTH(TRIM(COALESCE(description, ''))) > 0"
        )
        if not todas:
            params = sorted(validas)
            placeholders = ",".join("?" for _ in params)
            query += (
                " AND (area IS NULL OR area = '' OR area = 'Outros/TI Geral'"
                f" OR area NOT IN ({placeholders}))"
            )
        for vid, title, area, score, matches, desc in conn.execute(query, params).fetchall():
            analisadas += 1
            resultado = clf.classify(title, desc)
            if resultado.area == (area or ""):
                continue
            conn.execute(
                "UPDATE vagas SET area = ?, area_score = ?, area_matches = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (resultado.area, resultado.score, ", ".join(resultado.matches[:12]), vid),
            )
            mudadas += 1
    logger.info("Reclassificacao: %d analisadas, %d mudadas.",
                analisadas, mudadas)
    return {"analisadas": analisadas, "mudadas": mudadas, "validas": sorted(validas)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reclassifica areas com as regras atuais de areas.yml."
    )
    parser.add_argument(
        "--todas", action="store_true",
        help="Reclassifica todas as vagas com descricao (padrao: so pendentes).",
    )
    parser.add_argument(
        "--db", default=None,
        help="Caminho do SQLite (padrao: data/vagas.db).",
    )
    args = parser.parse_args(argv)

    db = resolve_sqlite_path(args.db)
    logger.info("Banco: %s", db)
    resultado = reclassificar(db, todas=args.todas)
    print(f"Analisadas: {resultado['analisadas']} | Mudadas: {resultado['mudadas']}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    raise SystemExit(main())
