"""Endpoints de tecnologias."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import crud
from ..database import get_db
from ..schemas import Erro, TecnologiaOut

router = APIRouter(prefix="/tecnologias", tags=["tecnologias"])


@router.get(
    "",
    response_model=list[TecnologiaOut],
    summary="Listar tecnologias com contagem de menções",
    description=(
        "As tecnologias de `skills.yml`, da mais para a menos citada. "
        "A contagem é o número de vagas que citam a tecnologia — vem da "
        "relação vaga↔tecnologia, não do CSV `skills_por_area`, que é "
        "truncado no top-15 de cada área."
    ),
)
def listar_tecnologias(
    db: Session = Depends(get_db),
    grupo: str | None = Query(
        default=None, description="Filtra por grupo, ex.: `linguagens`."
    ),
    com_vagas: bool = Query(
        default=False, description="Se verdadeiro, omite tecnologias com zero vagas."
    ),
) -> list[TecnologiaOut]:
    rows = crud.count_by_tecnologia(db)
    if grupo:
        rows = [r for r in rows if r["grupo"].lower() == grupo.lower()]
    if com_vagas:
        rows = [r for r in rows if r["vagas"] > 0]
    return [TecnologiaOut(**row) for row in rows]


@router.get(
    "/{nome}",
    response_model=TecnologiaOut,
    summary="Buscar tecnologia por nome",
    responses={404: {"model": Erro, "description": "Tecnologia não encontrada."}},
)
def buscar_tecnologia(nome: str, db: Session = Depends(get_db)) -> TecnologiaOut:
    row = crud.get_tecnologia(db, nome)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tecnologia não encontrada: {nome!r}.",
        )
    return TecnologiaOut(**row)
