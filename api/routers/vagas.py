"""Endpoints de vagas (somente leitura)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import crud, vocabulary
from ..database import get_db
from ..schemas import Erro, VagaOut, VagaPage
from ..vocabulary import AreaEnum, FonteEnum, ModalidadeEnum

router = APIRouter(prefix="/vagas", tags=["vagas"])


def _validar_tecnologia(tecnologia: str | None) -> str | None:
    """422 para tecnologia fora do vocabulario de `skills.yml`.

    Nao vira Enum como area/modalidade/fonte porque sao 107 valores -- a lista
    inteira dentro do /docs atrapalharia mais do que ajudaria.
    """
    if tecnologia is None:
        return None
    conhecidas = vocabulary.technologies()
    for nome in conhecidas:
        if nome.lower() == tecnologia.lower():
            return nome
    raise HTTPException(
        status_code=422,
        detail=(
            f"Tecnologia desconhecida: {tecnologia!r}. "
            "Consulte GET /tecnologias para a lista completa."
        ),
    )


@router.get(
    "",
    response_model=VagaPage,
    summary="Listar vagas",
    description=(
        "Lista as vagas coletadas pelo scraper. Os filtros combinam entre si "
        "(E lógico). Valores inválidos devolvem 422."
    ),
)
def listar_vagas(
    db: Session = Depends(get_db),
    area: AreaEnum | None = Query(default=None, description="Área de tecnologia."),
    tecnologia: str | None = Query(
        default=None, description="Nome da tecnologia, ex.: `Python`."
    ),
    modalidade: ModalidadeEnum | None = Query(
        default=None, description="Modalidade de trabalho."
    ),
    fonte: FonteEnum | None = Query(default=None, description="Portal de origem."),
    q: str | None = Query(
        default=None, min_length=2, max_length=100,
        description="Busca livre no título da vaga.",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> VagaPage:
    total, items = crud.list_vagas(
        db,
        area=area.value if area else None,
        tecnologia=_validar_tecnologia(tecnologia),
        modalidade=modalidade.value if modalidade else None,
        fonte=fonte.value if fonte else None,
        q=q,
        limit=limit,
        offset=offset,
    )
    return VagaPage(total=total, limit=limit, offset=offset, items=items)


@router.get(
    "/{vaga_id}",
    response_model=VagaOut,
    summary="Buscar vaga por id",
    responses={404: {"model": Erro, "description": "Vaga não encontrada."}},
)
def buscar_vaga(vaga_id: int, db: Session = Depends(get_db)) -> VagaOut:
    vaga = crud.get_vaga(db, vaga_id)
    if vaga is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vaga {vaga_id} não encontrada.",
        )
    return vaga
