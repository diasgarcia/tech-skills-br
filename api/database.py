"""Conexao com o SQLite e sessao do SQLAlchemy."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from scraper.config import PROJECT_ROOT

DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "vagas.db"


def database_url(path: str | Path | None = None) -> str:
    """URL do banco. `VAGAS_DB` sobrescreve, o que os testes usam."""
    if path is None:
        env = os.getenv("VAGAS_DB")
        path = env if env else DEFAULT_DB_PATH
    return f"sqlite:///{Path(path).as_posix()}"


class Base(DeclarativeBase):
    pass


def make_engine(path: str | Path | None = None):
    url = database_url(path)
    if not url.endswith(":memory:"):
        Path(url.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: o uvicorn atende requisicoes em threads diferentes.
    return create_engine(url, connect_args={"check_same_thread": False}, future=True)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(bind=None) -> None:
    Base.metadata.create_all(bind=bind or engine)


def get_db() -> Iterator[Session]:
    """Dependencia do FastAPI: uma sessao por requisicao."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
