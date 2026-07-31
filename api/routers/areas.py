"""Endpoints de areas de tecnologia."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import crud
from ..database import get_db
from ..schemas import AreaOut, Erro

router = APIRouter(prefix="/areas", tags=["areas"])


@router.get(
    "",
    response_model=list[AreaOut],
    summary="Listar áreas com contagem de vagas",
    description=(
        "As 10 áreas do vocabulário, da mais para a menos frequente. "
        "As contagens saem da tabela de vagas, não de um CSV agregado, "
        "então acompanham o estado atual do banco. Áreas sem vagas aparecem "
        "com zero."
    ),
)
def listar_areas(db: Session = Depends(get_db)) -> list[AreaOut]:
    return [AreaOut(**row) for row in crud.count_by_area(db)]


@router.get(
    "/{nome}",
    response_model=AreaOut,
    summary="Buscar área por nome",
    responses={404: {"model": Erro, "description": "Área não encontrada."}},
)
def buscar_area(nome: str, db: Session = Depends(get_db)) -> AreaOut:
    row = crud.get_area(db, nome)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Área não encontrada: {nome!r}.",
        )
    return AreaOut(**row)
