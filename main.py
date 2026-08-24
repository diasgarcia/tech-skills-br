"""CLI do tech-skills-br - Mapeamento de Skills em Tecnologia no Brasil (PIBIC).

Exemplos:
    python main.py                          # coleta padrao gratuita (Gupy, LinkedIn, etc.)
    python main.py --sources serpapi        # coleta isolada Google Jobs
    python main.py --sources theirstack     # coleta isolada TheirStack
    python main.py --terms "estagio ti" "engenheiro de dados junior"
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
from scraper.sources import AVAILABLE_SOURCES, DEFAULT_SOURCES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tech-skills-br",
        description="Mineracao e mapeamento de habilidades tecnicas (skills) demandadas no mercado de tecnologia no Brasil (PIBIC).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--sources", nargs="+", default=list(DEFAULT_SOURCES),
        choices=AVAILABLE_SOURCES,
        help=f"Portais a consultar (padrão: {' '.join(DEFAULT_SOURCES)}).",
    )

    parser.add_argument(
        "--locations", nargs="+", default=["todos"],
        help="Polos ou regioes a consultar (ex: todos, sudeste, sul, nordeste, 'São Paulo', 'Recife').",
    )
    parser.add_argument(
        "--terms", nargs="+", default=None,
        help=f"Termos de busca (padrao: {len(SEARCH_TERMS)} termos de config.py).",
    )
    parser.add_argument(
        "--start-page", type=int, default=1,
        help="Pagina inicial da busca por portal (padrao: 1). Util para pular paginas iniciais.",
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
        locations=args.locations,
        delay_seconds=args.delay,
        page_size=min(args.page_size, 100),
        start_page=max(1, args.start_page),
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

    tipo_vagas = "junior/estagio/trainee" if settings.only_junior else "todos os niveis"
    print("\n" + "=" * 62)
    print(f"  RANKING DE AREAS -- {len(result.jobs)} vagas ({tipo_vagas})")
    print("=" * 62)
    for row in result.ranking:
        bar = "#" * round(row["percentual"] / 2)
        print(f"  {row['posicao']:>2}. {row['area']:<18} {row['vagas']:>4} vagas "
              f"({row['percentual']:>5.1f}%) {bar}")
    print("=" * 62)
    demanda_label = "demanda junior" if settings.only_junior else "demanda geral"
    print(f"\n  Area com mais {demanda_label}: {result.top_area}")


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
