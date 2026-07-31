"""Consultas ao banco.

`/areas` e `/tecnologias` sao sempre calculados a partir da tabela de vagas --
nunca lidos dos CSVs de ranking. Os CSVs `ranking_areas` e `skills_por_area` sao
recortes ja agregados (o de skills e truncado no top-15 por area), entao serviriam
numeros errados e desatualizados assim que o banco mudasse.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import vocabulary
from .models import Tecnologia, Vaga, vaga_tecnologia


def list_vagas(
    db: Session,
    *,
    area: str | None = None,
    tecnologia: str | None = None,
    modalidade: str | None = None,
    fonte: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[Vaga]]:
    """(total que casa com os filtros, pagina pedida). Filtros combinam em AND."""
    stmt = select(Vaga)

    if area:
        stmt = stmt.where(Vaga.area == area)
    if modalidade:
        stmt = stmt.where(Vaga.workplace_type == modalidade)
    if fonte:
        stmt = stmt.where(Vaga.source == fonte)
    if q:
        stmt = stmt.where(Vaga.title.ilike(f"%{q}%"))
    if tecnologia:
        stmt = stmt.where(
            Vaga.tecnologias.any(func.lower(Tecnologia.nome) == tecnologia.lower())
        )

    total = db.scalar(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ) or 0

    page = stmt.order_by(
        Vaga.published_date.desc().nulls_last(), Vaga.id
    ).limit(limit).offset(offset)

    return total, list(db.scalars(page).unique())


def get_vaga(db: Session, vaga_id: int) -> Vaga | None:
    return db.get(Vaga, vaga_id)


def count_by_area(db: Session) -> list[dict]:
    """Todas as areas do vocabulario, inclusive as que estao com zero vagas."""
    rows = db.execute(
        select(Vaga.area, func.count(Vaga.id)).group_by(Vaga.area)
    ).all()
    counts = {area: total for area, total in rows}
    total = sum(counts.values())

    result = [
        {
            "area": area,
            "vagas": counts.get(area, 0),
            "percentual": round(100 * counts.get(area, 0) / total, 1) if total else 0.0,
        }
        for area in vocabulary.areas()
    ]
    # Areas que existem no banco mas sairam do YAML nao somem do relatorio.
    for area in counts:
        if area not in vocabulary.areas():
            result.append({
                "area": area,
                "vagas": counts[area],
                "percentual": round(100 * counts[area] / total, 1) if total else 0.0,
            })

    return sorted(result, key=lambda row: (-row["vagas"], row["area"]))


def count_by_tecnologia(db: Session) -> list[dict]:
    """Todas as tecnologias do vocabulario, inclusive as sem nenhuma vaga."""
    rows = db.execute(
        select(Tecnologia.nome, Tecnologia.grupo, func.count(vaga_tecnologia.c.vaga_id))
        .outerjoin(vaga_tecnologia, Tecnologia.id == vaga_tecnologia.c.tecnologia_id)
        .group_by(Tecnologia.id)
    ).all()

    known = vocabulary.technologies()
    result = [
        {"nome": nome, "grupo": grupo or known.get(nome, ""), "vagas": total}
        for nome, grupo, total in rows
    ]
    return sorted(result, key=lambda row: (-row["vagas"], row["nome"]))


def get_area(db: Session, nome: str) -> dict | None:
    for row in count_by_area(db):
        if row["area"].lower() == nome.lower():
            return row
    return None


def get_tecnologia(db: Session, nome: str) -> dict | None:
    for row in count_by_tecnologia(db):
        if row["nome"].lower() == nome.lower():
            return row
    return None
