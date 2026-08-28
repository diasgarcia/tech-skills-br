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
import logging
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.classifier import default_classifier  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
logger = logging.getLogger("reclassify_areas")


def reclassificar(db_path: Path, todas: bool = False) -> dict:
    clf = default_classifier()
    validas = set(clf.areas)

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    if todas:
        c.execute(
            "SELECT id, title, area, area_score, area_matches, description "
            "FROM vagas WHERE description IS NOT NULL AND description != ''"
        )
    else:
        c.execute(
            "SELECT id, title, area, area_score, area_matches, description "
            "FROM vagas "
            "WHERE (area IS NULL OR area = '' OR area = 'Outros/TI Geral') "
            "  AND description IS NOT NULL AND description != ''"
        )

    mudadas = 0
    analisadas = 0
    for vid, title, area, score, matches, desc in c.fetchall():
        analisadas += 1
        pendente = not area or area == "Outros/TI Geral" or area not in validas
        if not todas and not pendente:
            continue
        resultado = clf.classify(title, desc)
        if resultado.area == (area or ""):
            continue
        c.execute(
            "UPDATE vagas SET area = ?, area_score = ?, area_matches = ? "
            "WHERE id = ?",
            (
                resultado.area,
                resultado.score,
                ", ".join(resultado.matches[:12]),
                vid,
            ),
        )
        mudadas += 1

    conn.commit()
    conn.close()
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

    db = Path(args.db) if args.db else (PROJECT_ROOT / "data" / "vagas.db")
    resultado = reclassificar(db, todas=args.todas)
    print(f"Analisadas: {resultado['analisadas']} | Mudadas: {resultado['mudadas']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
