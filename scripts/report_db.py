"""Gera um relatorio consolidado completo da base de dados (SQLite).

Exemplos de uso:
    python scripts/report_db.py                  # exibe resumo no terminal e salva relatorio MD
    python scripts/report_db.py --db data/vagas.db
    python scripts/report_db.py --no-export       # apenas exibe no terminal
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


from sqlalchemy import func, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.database import Base, database_url, make_engine, url_sem_senha
from api.models import Tecnologia, Vaga, vaga_tecnologia
from scraper.config import DEFAULT_OUTPUT_DIR, PROJECT_ROOT



def _bar(percent: float, width: int = 20) -> str:
    filled = round(percent / 100 * width)
    return "#" * filled + "." * (width - filled)




def generate_db_report(
    db_path: Path | str | None = None,
    export_md: bool = True,
) -> str:
    engine = make_engine(db_path)

    Base.metadata.create_all(engine)
    lines: list[str] = []


    with Session(engine) as session:
        total_vagas = session.scalar(select(func.count(Vaga.id))) or 0
        if total_vagas == 0:
            print("O banco de dados está vazio. Nenhuma vaga cadastrada.")
            return ""

        min_date = session.scalar(select(func.min(Vaga.published_date)))
        max_date = session.scalar(select(func.max(Vaga.published_date)))
        periodo_str = (
            f"{min_date.strftime('%d/%m/%Y')} até {max_date.strftime('%d/%m/%Y')}"
            if min_date and max_date
            else "Sem data informada"
        )

        area_counts = session.execute(
            select(Vaga.area, func.count(Vaga.id))
            .group_by(Vaga.area)
            .order_by(func.count(Vaga.id).desc())
        ).all()

        regiao_counts = session.execute(
            select(func.coalesce(Vaga.regiao, "Não informado"), func.count(Vaga.id))
            .group_by(Vaga.regiao)
            .order_by(func.count(Vaga.id).desc())
        ).all()

        polo_counts = session.execute(
            select(Vaga.polo, func.count(Vaga.id))
            .where(Vaga.polo.isnot(None), Vaga.polo != "", Vaga.polo != "Não informado")
            .group_by(Vaga.polo)
            .order_by(func.count(Vaga.id).desc())
            .limit(10)
        ).all()

        modalidade_counts = session.execute(
            select(func.coalesce(Vaga.workplace_type, "Não informado"), func.count(Vaga.id))
            .group_by(Vaga.workplace_type)
            .order_by(func.count(Vaga.id).desc())
        ).all()

        seniority_counts = session.execute(
            select(func.coalesce(Vaga.seniority, "Não informado"), func.count(Vaga.id))
            .group_by(Vaga.seniority)
            .order_by(func.count(Vaga.id).desc())
        ).all()

        source_counts = session.execute(
            select(Vaga.source, func.count(Vaga.id))
            .group_by(Vaga.source)
            .order_by(func.count(Vaga.id).desc())
        ).all()

        tech_counts = session.execute(
            select(Tecnologia.nome, func.count(vaga_tecnologia.c.vaga_id))
            .join(vaga_tecnologia, Tecnologia.id == vaga_tecnologia.c.tecnologia_id)
            .group_by(Tecnologia.nome)
            .order_by(func.count(vaga_tecnologia.c.vaga_id).desc())
            .limit(20)
        ).all()

        company_counts = session.execute(
            select(Vaga.company, func.count(Vaga.id))
            .where(Vaga.company.isnot(None), Vaga.company != "")
            .group_by(Vaga.company)
            .order_by(func.count(Vaga.id).desc())
            .limit(10)
        ).all()

    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    header = (
        "=" * 68 + "\n"
        f"  RELATÓRIO CONSOLIDADO DO BANCO DE DADOS -- {total_vagas} VAGAS TOTAIS\n"
        f"  Gerado em: {now_str} | Período: {periodo_str}\n"
        f"  Banco: {url_sem_senha(database_url(db_path))}\n"
        + "=" * 68
    )
    print(header)

    lines.append(f"# Relatório Consolidado da Base de Vagas ({total_vagas} vagas)")
    lines.append("")
    lines.append(f"- **Data de geração:** {now_str}")
    lines.append(f"- **Período coberto:** {periodo_str}")
    lines.append(f"- **Total de vagas consolidadas:** {total_vagas}")
    lines.append("")
    lines.append("Os resultados descrevem os anúncios coletados. As menções identificadas não representam toda a demanda do mercado nem o número de contratações.\n")

    print("\n[RANKING DE ÁREAS DE TECNOLOGIA]")
    lines.append("## Ranking de Áreas de Tecnologia\n")
    lines.append("| Posição | Área | Vagas | % | Gráfico |")
    lines.append("|---|---|---|---|---|")
    for pos, (area, count) in enumerate(area_counts, start=1):
        pct = round(100 * count / total_vagas, 1)
        bar = _bar(pct)
        print(f"  {pos:2d}. {area:<20} {count:4d} vagas ({pct:5.1f}%) {bar}")
        lines.append(f"| {pos} | {area} | {count} | {pct}% | {bar} |")

    print("\n[DISTRIBUIÇÃO POR MACRORREGIÃO]")
    lines.append("\n## Distribuição por Macrorregião\n")
    lines.append("| Região | Vagas | % | Gráfico |")
    lines.append("|---|---|---|---|")
    for reg, count in regiao_counts:
        pct = round(100 * count / total_vagas, 1)
        bar = _bar(pct)
        print(f"  - {reg:<20} {count:4d} vagas ({pct:5.1f}%) {bar}")
        lines.append(f"| {reg} | {count} | {pct}% | {bar} |")

    if polo_counts:
        print("\n[TOP 10 POLOS TECNOLÓGICOS REGIONAIS]")
        lines.append("\n## Top 10 Polos Tecnológicos Regionais\n")
        lines.append("| Posição | Polo | Vagas | % | Gráfico |")
        lines.append("|---|---|---|---|---|")
        for pos, (polo, count) in enumerate(polo_counts, start=1):
            pct = round(100 * count / total_vagas, 1)
            bar = _bar(pct)
            print(f"  {pos:2d}. {polo:<20} {count:4d} vagas ({pct:5.1f}%) {bar}")
            lines.append(f"| {pos} | {polo} | {count} | {pct}% | {bar} |")

    print("\n[DISTRIBUIÇÃO POR MODALIDADE DE TRABALHO]")
    lines.append("\n## Distribuição por Modalidade de Trabalho\n")
    lines.append("| Modalidade | Vagas | % | Gráfico |")
    lines.append("|---|---|---|---|")
    for mod, count in modalidade_counts:
        pct = round(100 * count / total_vagas, 1)
        bar = _bar(pct)
        print(f"  - {mod:<20} {count:4d} vagas ({pct:5.1f}%) {bar}")
        lines.append(f"| {mod} | {count} | {pct}% | {bar} |")

    print("\n[DISTRIBUIÇÃO POR NÍVEL DE ENTRADA]")
    lines.append("\n## Distribuição por Nível de Entrada\n")
    lines.append("| Senioridade | Vagas | % |")
    lines.append("|---|---|---|")
    for sen, count in seniority_counts:
        pct = round(100 * count / total_vagas, 1)
        print(f"  - {sen:<20} {count:4d} vagas ({pct:5.1f}%)")
        lines.append(f"| {sen} | {count} | {pct}% |")

    print("\n[DISTRIBUIÇÃO POR PORTAL / FONTE]")
    lines.append("\n## Distribuição por Portal de Origem\n")
    lines.append("| Portal | Vagas | % |")
    lines.append("|---|---|---|")
    for src, count in source_counts:
        pct = round(100 * count / total_vagas, 1)
        print(f"  - {src:<20} {count:4d} vagas ({pct:5.1f}%)")
        lines.append(f"| {src} | {count} | {pct}% |")

    if tech_counts:
        print("\n[TOP 20 TECNOLOGIAS MAIS CITADAS NOS ANÚNCIOS]")
        lines.append("\n## Top 20 Tecnologias Mais Citadas nos Anúncios\n")
        lines.append("| Posição | Tecnologia | Anúncios com menção identificada |")
        lines.append("|---|---|---|")
        for pos, (tech, count) in enumerate(tech_counts, start=1):
            print(f"  {pos:2d}. {tech:<20} {count:4d} citações")
            lines.append(f"| {pos} | {tech} | {count} |")

    if company_counts:
        print("\n[TOP 10 EMPRESAS CONTRATANDO]")
        lines.append("\n## Top 10 Empresas com Mais Vagas\n")
        lines.append("| Empresa | Vagas |")
        lines.append("|---|---|")
        for company, count in company_counts:
            print(f"  - {company:<30} {count:4d} vagas")
            lines.append(f"| {company} | {count} |")

    print("\n" + "=" * 68)

    md_content = "\n".join(lines)
    if export_md:
        output_dir = DEFAULT_OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        report_path = output_dir / f"relatorio_banco_consolidado_{stamp}.md"
        report_path.write_text(md_content, encoding="utf-8")
        print(f"\nArquivos gerados:")
        print(f"  - Relatório Markdown: {report_path}")

        docs_reports_dir = PROJECT_ROOT / "docs" / "relatorios"
        docs_reports_dir.mkdir(parents=True, exist_ok=True)
        docs_md_path = docs_reports_dir / "relatorio_banco_consolidado.md"
        docs_md_path.write_text(md_content, encoding="utf-8")
        print(f"  - Snapshot Docs: {docs_md_path}")

    return md_content



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gera relatorio estatistico consolidado do banco de dados de vagas."
    )
    parser.add_argument(
        "--db", default=None, help="Caminho do SQLite."
    )
    parser.add_argument(
        "--no-export", action="store_true", help="Nao grava o arquivo Markdown em output/."
    )
    args = parser.parse_args(argv)

    generate_db_report(
        db_path=args.db,
        export_md=not args.no_export,
    )

    try:
        from scripts.export_pages_data import export_all_pages_data
        export_all_pages_data()
    except Exception as exc:
        logging.warning(f"Nao foi possivel exportar endpoints estaticos do Pages: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

