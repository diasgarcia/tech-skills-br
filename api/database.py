"""Conexao e sessao do SQLAlchemy.

O projeto usa SQLite. A escolha do arquivo e so de configuracao, nesta ordem
de precedencia:

    1. o destino passado no argumento (usado pelo importador e pelos testes)
    2. a variavel de ambiente DATABASE_URL -- caminho ou URL sqlite
    3. a variavel de ambiente VAGAS_DB      -- caminho de arquivo SQLite
    4. o padrao: data/vagas.db

Sem nenhuma variavel definida, o comportamento e exatamente o de antes: SQLite
em `data/vagas.db`.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from scraper.config import PROJECT_ROOT

DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "vagas.db"


def _como_url(destino: str | Path) -> str:
    """Aceita tanto uma URL sqlite quanto um caminho de arquivo SQLite."""
    texto = str(destino)
    if "://" in texto:
        return texto
    return f"sqlite:///{Path(texto).as_posix()}"


def database_url(destino: str | Path | None = None) -> str:
    if destino is not None:
        return _como_url(destino)
    for variavel in ("DATABASE_URL", "VAGAS_DB"):
        valor = os.getenv(variavel)
        if valor:
            return _como_url(valor)
    return _como_url(DEFAULT_DB_PATH)


def url_sem_senha(url: str) -> str:
    """URL segura para log: esconde a senha, se houver alguma na URL."""
    try:
        return make_url(url).render_as_string(hide_password=True)
    except Exception:  # pragma: no cover - URL malformada nao deve derrubar log
        return url


class Base(DeclarativeBase):
    pass


def make_engine(destino: str | Path | None = None):
    url = database_url(destino)
    opcoes: dict = {"future": True}

    if url.startswith("sqlite"):
        opcoes["connect_args"] = {"check_same_thread": False}
        caminho = url.replace("sqlite:///", "")
        if caminho and caminho != ":memory:":
            Path(caminho).parent.mkdir(parents=True, exist_ok=True)

    return create_engine(url, **opcoes)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(bind=None) -> None:
    Base.metadata.create_all(bind=bind or engine)
