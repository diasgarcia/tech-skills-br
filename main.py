"""CLI do vagas-tech-junior.

Exemplos:
    python main.py                          # coleta completa (Gupy + Vagas.com)
    python main.py --sources gupy           # so a Gupy
    python main.py --terms "estagio dados" "engenheiro de dados junior"
    python main.py --max-pages 2 --delay 2  # coleta menor e mais lenta
    python main.py --strict                 # descarta titulos "Junior/Pleno"
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from scraper.config import SEARCH_TERMS, Settings
from scraper.pipeline import run
from scraper.sources import AVAILABLE_SOURCES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vagas-tech-junior",
        description="Descobre qual area de tecnologia tem mais vagas junior no Brasil.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--sources", nargs="+", default=list(AVAILABLE_SOURCES),
        choices=AVAILABLE_SOURCES,
        help=f"Portais a consultar (padrão: todos — {' '.join(AVAILABLE_SOURCES)}).",
    )
    parser.add_argument(
        "--terms", nargs="+", default=None,
        help=f"Termos de busca (padrao: {len(SEARCH_TERMS)} termos de config.py).",
    )
    parser.add_argument(
        "--max-pages", type=int, default=5,
        help="Maximo de paginas por termo, por portal (padrao: 5).",
    )
    parser.add_argument(
        "--page-size", type=int, default=100,
        help="Vagas por pagina; a Gupy aceita no maximo 100 (padrao: 100).",
    )
    parser.add_argument(
        "--delay", type=float, default=1.5,
        help="Segundos de espera entre requests (padrao: 1.5).",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Diretorio de saida (padrao: ./output).",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Descarta titulos mistos como 'Desenvolvedor Junior/Pleno'.",
    )
    parser.add_argument(
        "--all-levels", action="store_true",
        help="Nao filtra por senioridade (coleta tudo que os portais devolverem).",
    )
    parser.add_argument(
        "--keep-non-tech", action="store_true",
        help="Mantem vagas fora de tecnologia (Contabil, Fiscal...) que a busca "
             "solta dos portais devolve. Por padrao elas sao descartadas.",
    )
    parser.add_argument(
        "--no-charts", action="store_true",
        help="Nao gera os graficos PNG (util se matplotlib nao estiver instalado).",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Log detalhado (DEBUG)."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )

    settings = Settings(
        search_terms=args.terms or list(SEARCH_TERMS),
        sources=args.sources,
        delay_seconds=args.delay,
        page_size=min(args.page_size, 100),
        max_pages_per_term=args.max_pages,
        only_junior=not args.all_levels,
    )
    if args.output:
        settings.output_dir = args.output

    result = run(
        settings,
        strict_seniority=args.strict,
        keep_non_tech=args.keep_non_tech,
        with_charts=not args.no_charts,
    )

    if not result.jobs:
        print("\nNenhuma vaga encontrada. Verifique conexao e termos de busca.")
        return 1

    print("\n" + "=" * 62)
    print(f"  RANKING DE AREAS -- {len(result.jobs)} vagas junior/estagio/trainee")
    print("=" * 62)
    for row in result.ranking:
        bar = "#" * round(row["percentual"] / 2)
        print(f"  {row['posicao']:>2}. {row['area']:<18} {row['vagas']:>4} vagas "
              f"({row['percentual']:>5.1f}%) {bar}")
    print("=" * 62)
    print(f"\n  Area com mais demanda junior: {result.top_area}")

    print("\n  Arquivos gerados:")
    for label, path in result.files.items():
        print(f"    - {label:<12} {path}")

    errors = [e for s in result.stats for e in s.errors]
    if errors:
        print(f"\n  Avisos ({len(errors)}):")
        for err in errors[:10]:
            print(f"    ! {err}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
