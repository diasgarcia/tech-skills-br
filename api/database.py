"""Conexao e sessao do SQLAlchemy.

Funciona com SQLite e com PostgreSQL sem mudar o resto do codigo. A escolha e
so de configuracao, nesta ordem de precedencia:

    1. o destino passado no argumento (usado pelo importador e pelos testes)
    2. a variavel de ambiente DATABASE_URL  -- e o que o docker-compose usa
    3. a variavel de ambiente VAGAS_DB      -- caminho de arquivo SQLite
    4. o padrao: data/vagas.db

Sem nenhuma variavel definida, o comportamento e exatamente o de antes: SQLite
em `data/vagas.db`. E o que o deploy no Render continua usando.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from scraper.config import PROJECT_ROOT

DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "vagas.db"


def _normalizar(url: str) -> str:
    """Ajusta prefixos de Postgres para o driver que o projeto instala.

    Provedores gerenciados (Render, Heroku, Railway) ainda entregam a URL com
    o prefixo historico `postgres://`, que o SQLAlchemy nao aceita mais.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _como_url(destino: str | Path) -> str:
    """Aceita tanto uma URL de banco quanto um caminho de arquivo SQLite."""
    texto = str(destino)
    if "://" in texto:
        return _normalizar(texto)
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
    """URL segura para log: esconde a senha, que aparece na do Postgres."""
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
        # check_same_thread: o uvicorn atende requisicoes em threads diferentes.
        opcoes["connect_args"] = {"check_same_thread": False}
        caminho = url.replace("sqlite:///", "")
        if caminho and caminho != ":memory:":
            Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    else:
        # pool_pre_ping: no compose a API sobe junto com o banco, e a conexao
        # pode ter morrido enquanto o container do Postgres reiniciava.
        opcoes["pool_pre_ping"] = True

    return create_engine(url, **opcoes)


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
