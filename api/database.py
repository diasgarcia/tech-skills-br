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
import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session

PROJECT_ROOT = Path(__file__).resolve().parent.parent
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
    from scraper.config import _load_dotenv

    _load_dotenv()
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


def resolve_sqlite_path(db_path: str | Path | None = None) -> Path | str:
    """Resolve o mesmo destino para SQLAlchemy e comandos sqlite3."""
    url = make_url(database_url(db_path))
    if url.get_backend_name() != "sqlite":
        raise ValueError("Este comando requer um banco SQLite.")
    if url.query:
        raise ValueError("Use uma URL SQLite sem parametros ou um caminho de arquivo.")
    if url.database in (None, "", ":memory:"):
        return ":memory:"
    return Path(url.database).resolve()


def connect_sqlite(
    db_path: str | Path | None = None, *, read_only: bool = False,
) -> sqlite3.Connection:
    """Abre uma base existente; comandos de manutencao nao criam bases vazias."""
    path = resolve_sqlite_path(db_path)
    if path == ":memory:":
        if read_only:
            raise ValueError("Uma base em memoria nao pode ser aberta para leitura existente.")
        conn = sqlite3.connect(":memory:")
    else:
        mode = "ro" if read_only else "rw"
        conn = sqlite3.connect(f"{path.as_uri()}?mode={mode}", uri=True)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


class Base(DeclarativeBase):
    pass


@contextmanager
def read_session(db_path: str | Path | None = None) -> Iterator[Session]:
    """Sessao de exportacao: somente leitura, base existente e conexao fechada."""
    path = resolve_sqlite_path(db_path)
    engine = create_engine("sqlite://", creator=lambda: connect_sqlite(path, read_only=True))
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def make_engine(destino: str | Path | None = None):
    url = database_url(destino)
    opcoes: dict = {"future": True}

    if url.startswith("sqlite"):
        opcoes["connect_args"] = {"check_same_thread": False}
    bind = create_engine(url, **opcoes)
    if bind.dialect.name == "sqlite":
        caminho = resolve_sqlite_path(destino)

        @event.listens_for(bind, "do_connect")
        def preparar_diretorio(dialect, connection_record, args, kwargs):
            if caminho != ":memory:":
                caminho.parent.mkdir(parents=True, exist_ok=True)

        @event.listens_for(bind, "connect")
        def ativar_chaves_estrangeiras(connection, connection_record):
            connection.execute("PRAGMA foreign_keys = ON")

    return bind


def init_db(bind=None, *, db_path: str | Path | None = None) -> None:
    from api import models  # noqa: F401 - registra as tabelas sem criar banco no import

    if bind is not None and db_path is not None:
        raise ValueError("Informe bind ou db_path, nao ambos.")
    if bind is not None:
        Base.metadata.create_all(bind=bind)
        return
    owned_engine = make_engine(db_path)
    try:
        Base.metadata.create_all(bind=owned_engine)
    finally:
        owned_engine.dispose()
