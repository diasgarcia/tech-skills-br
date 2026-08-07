"""Aplicacao FastAPI.

API somente leitura sobre os dados que o scraper produz. Nao ha endpoints de
escrita: as vagas entram pelo pipeline de raspagem e pelo script de importacao
(`scripts/import_csv.py`), nunca por HTTP.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scraper import __version__

from .database import database_url, get_db, init_db, url_sem_senha
from .models import Vaga
from .routers import areas, tecnologias, vagas

logger = logging.getLogger(__name__)

DESCRIPTION = """
API de consulta das vagas júnior de tecnologia coletadas pelo scraper.

**Somente leitura.** Os dados vêm da raspagem da Gupy e do Vagas.com.br; para
atualizar, rode o scraper (`python main.py`) e depois a importação
(`python scripts/import_csv.py`).

- `/vagas` — listagem com filtros por área, tecnologia, modalidade e fonte
- `/areas` — as 10 áreas com contagem de vagas
- `/tecnologias` — as tecnologias com contagem de menções
"""

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Banco: %s", url_sem_senha(database_url()))
    yield


app = FastAPI(
    title="vagas-tech-junior API",
    description=DESCRIPTION,
    version=__version__,
    contact={"name": "vagas-tech-junior"},
    lifespan=lifespan,
)

app.include_router(vagas.router)
app.include_router(areas.router)
app.include_router(tecnologias.router)


@app.exception_handler(RequestValidationError)
async def _validacao(request: Request, exc: RequestValidationError) -> JSONResponse:
    """422 com o mesmo formato `{"detail": ...}` dos erros 404."""
    erros = "; ".join(
        f"{'.'.join(str(p) for p in e['loc'][1:])}: {e['msg']}" for e in exc.errors()
    )
    return JSONResponse(
        status_code=422,
        content={"detail": f"Parâmetros inválidos. {erros}"},
    )


@app.get("/", tags=["meta"], summary="Informações da API")
def raiz() -> dict:
    return {
        "nome": "vagas-tech-junior API",
        "versao": __version__,
        "somente_leitura": True,
        "docs": "/docs",
        "endpoints": ["/vagas", "/vagas/{id}", "/areas", "/tecnologias"],
    }


@app.get("/health", tags=["meta"], summary="Checagem de saúde")
def health(db: Session = Depends(get_db)) -> dict:
    """Usa a mesma sessao das demais rotas, e nao um engine proprio.

    Assim a checagem enxerga exatamente o banco que a API esta atendendo --
    seja SQLite ou Postgres -- e falha junto com ela se o banco cair, que e o
    que o healthcheck do compose precisa detectar.
    """
    total = db.scalar(select(func.count()).select_from(Vaga)) or 0
    return {"status": "ok", "vagas": total}
