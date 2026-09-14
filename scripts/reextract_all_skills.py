"""Reextrai skills em uma transacao explicita; --dry-run mostra a diferenca."""

from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.database import connect_sqlite, resolve_sqlite_path
from api.vocabulary import technologies
from scraper.skills import default_extractor


@dataclass(frozen=True)
class ReextractionResult:
    vagas: int
    vinculos_antes: int
    vinculos_depois: int
    adicionados: int
    removidos: int
    vagas_alteradas: int
    dry_run: bool


def reextract_all_skills(
    db_path: Path | str | None = None, *, dry_run: bool = False,
) -> ReextractionResult:
    extractor = default_extractor()
    vocabulary = technologies()
    with closing(connect_sqlite(db_path)) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("Banco com relacoes orfas; audite uma copia antes da reextracao.")
            known = {name.casefold(): tid for tid, name in conn.execute("SELECT id, nome FROM tecnologias")}
            for name, group in vocabulary.items():
                if name.casefold() not in known:
                    cursor = conn.execute("INSERT INTO tecnologias (nome, grupo) VALUES (?, ?)", (name, group))
                    known[name.casefold()] = cursor.lastrowid
                else:
                    conn.execute(
                        "UPDATE tecnologias SET grupo = ? WHERE id = ? AND grupo != ?",
                        (group, known[name.casefold()], group),
                    )
            before = set(conn.execute("SELECT vaga_id, tecnologia_id FROM vaga_tecnologia"))
            rows = conn.execute("SELECT id, title, description FROM vagas").fetchall()
            after = {
                (vid, known[skill.casefold()])
                for vid, title, description in rows
                for skill in extractor.extract(title or "", description or "")
            }
            added, removed = after - before, before - after
            changed = {vid for vid, _ in added | removed}
            conn.executemany(
                "DELETE FROM vaga_tecnologia WHERE vaga_id = ? AND tecnologia_id = ?", sorted(removed),
            )
            conn.executemany(
                "INSERT INTO vaga_tecnologia (vaga_id, tecnologia_id) VALUES (?, ?)", sorted(added),
            )
            conn.executemany(
                "UPDATE vagas SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                [(vid,) for vid in sorted(changed)],
            )
            result = ReextractionResult(
                len(rows), len(before), len(after), len(added), len(removed), len(changed), dry_run,
            )
            if dry_run:
                conn.rollback()
            else:
                conn.commit()
            return result
        except BaseException:
            conn.rollback()
            raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="Arquivo ou URL SQLite; respeita DATABASE_URL e VAGAS_DB.")
    parser.add_argument("--dry-run", action="store_true", help="Calcula diferencas e desfaz a transacao.")
    args = parser.parse_args(argv)
    print(f"Banco: {resolve_sqlite_path(args.db)}")
    result = reextract_all_skills(args.db, dry_run=args.dry_run)
    print(json.dumps(asdict(result), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
