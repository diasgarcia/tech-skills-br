"""Gera o corpo da mensagem de commit dos workflows de dados.

Le o banco SQLite e (opcionalmente) o log do enriquecimento e imprime um
resumo curto: coleta, importacao, base, enriquecidas e pendentes por
fonte. Os workflows usam a saida como corpo do commit (`git commit -F`).

    python scripts/resumo_commit.py --brutas 12145 --elegiveis 1776 \
        --novas 45 --atualizadas 1672 --log /tmp/enrich.log

Os criterios de "pendente" repetem de proposito os dos enriquecidores:
veja `scripts/enrich_outras_fontes.py` e `scripts/enrich_descriptions.py`.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ORDEM_FONTES = ("linkedin", "solides", "gupy", "vagas", "geekhunter", "trampos")

PENDENTES_POR_FONTE = {
    "vagas.com": (
        "source='vagas' AND (description LIKE '%...' "
        "OR LENGTH(description) < 500)"
    ),
    "trampos": (
        "source='trampos' AND (description IS NULL OR LENGTH(description) < 100) "
        "AND (published_date IS NULL OR published_date >= date('now', '-30 days'))"
    ),
    "gupy": (
        "source='gupy' AND LENGTH(description) = 500 "
        "AND (published_date IS NULL OR published_date >= date('now', '-30 days'))"
    ),
    "geekhunter": (
        "source='geekhunter' AND (description IS NULL OR LENGTH(description) < 300 "
        "OR company LIKE '%-%' OR published_date IS NULL)"
    ),
    "linkedin": (
        "source='linkedin' AND (description IS NULL OR LENGTH(description) < 30 "
        "OR LENGTH(description) = 500)"
    ),
}


def _parse_enriquecidas(log_path: Path | None):
    """Le o log dos enriquecidores e devolve (outras, linkedin)."""
    outras: dict[str, int] | None = None
    linkedin: int | None = None
    if log_path and log_path.is_file():
        texto = log_path.read_text(encoding="utf-8", errors="replace")
        m = re.search(
            r"Enriquecimento concluido: (\d+) vagas\.com, (\d+) trampos, "
            r"(\d+) gupy e (\d+) geekhunter\.",
            texto,
        )
        if m:
            outras = {
                fonte: int(n)
                for fonte, n in zip(("vagas.com", "trampos", "gupy", "geekhunter"), m.groups())
            }
        m2 = re.search(
            r"Enriquecimento concluido com sucesso: (\d+) vagas enriquecidas!",
            texto,
        )
        if m2:
            linkedin = int(m2.group(1))
    return outras, linkedin


def resumir(args: argparse.Namespace) -> str:
    conn = sqlite3.connect(PROJECT_ROOT / "data" / "vagas.db")
    total = conn.execute("SELECT COUNT(*) FROM vagas").fetchone()[0]
    por_fonte = dict(conn.execute("SELECT source, COUNT(*) FROM vagas GROUP BY source"))
    pendentes = {}
    for fonte, condicao in PENDENTES_POR_FONTE.items():
        pendentes[fonte] = conn.execute(
            "SELECT COUNT(*) FROM vagas "
            f"WHERE COALESCE(enrich_encerrada, 0) = 0 AND {condicao}"
        ).fetchone()[0]
    conn.close()

    linhas: list[str] = []

    if args.brutas is not None or args.elegiveis is not None:
        partes = []
        if args.brutas is not None:
            partes.append(f"{args.brutas} brutas")
        if args.elegiveis is not None:
            partes.append(f"{args.elegiveis} elegiveis (junior/estagio/trainee)")
        linhas.append("- Coleta: " + " | ".join(partes))

    if args.novas is not None or args.atualizadas is not None:
        partes = []
        if args.novas is not None:
            partes.append(f"{args.novas} novas")
        if args.atualizadas is not None:
            partes.append(f"{args.atualizadas} atualizadas")
        linhas.append("- Importacao: " + " | ".join(partes))

    fontes = ", ".join(f"{f} {por_fonte.get(f, 0)}" for f in ORDEM_FONTES)
    linhas.append(f"- Base: {total} vagas ({fontes})")

    outras, linkedin = _parse_enriquecidas(args.log)
    if outras or linkedin is not None:
        partes = [f"{f} {n}" for f, n in (outras or {}).items()]
        if linkedin is not None:
            partes.append(f"linkedin {linkedin}")
        linhas.append("- Enriquecidas: " + " | ".join(partes))

    linhas.append(
        "- Pendentes: " + " | ".join(f"{f} {n}" for f, n in pendentes.items())
    )

    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Imprime o corpo da mensagem de commit com o resumo dos dados."
    )
    parser.add_argument("--brutas", type=int, default=None, help="Vagas brutas da coleta.")
    parser.add_argument(
        "--elegiveis", type=int, default=None,
        help="Vagas elegiveis apos filtros (junior/estagio/trainee).",
    )
    parser.add_argument("--novas", type=int, default=None, help="Vagas novas na rodada.")
    parser.add_argument(
        "--atualizadas", type=int, default=None, help="Vagas atualizadas na rodada."
    )
    parser.add_argument(
        "--log", type=Path, default=None,
        help="Arquivo de log dos enriquecidores (tee) para extrair as contagens.",
    )
    args = parser.parse_args(argv)
    print(resumir(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
