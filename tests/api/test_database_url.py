"""Resolucao do destino do banco: SQLite em `data/vagas.db` por padrao."""

from __future__ import annotations

from pathlib import Path

import pytest

from api.database import database_url, make_engine


@pytest.fixture(autouse=True)
def _ambiente_limpo(monkeypatch):
    """Isola dos envs da máquina: o padrão do projeto tem que ser SQLite."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("VAGAS_DB", raising=False)


def test_padrao_continua_sqlite():
    url = database_url()

    assert url.startswith("sqlite:///")
    assert url.endswith("data/vagas.db")


def test_caminho_de_arquivo_vira_sqlite():
    path = Path("data/outro.db")

    string_url = database_url("data/outro.db")
    path_url = database_url(path)

    assert string_url == "sqlite:///data/outro.db"
    assert path_url.startswith("sqlite:///")


def test_url_sqlite_do_ambiente_passa_direto(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:////tmp/env.db")

    url = database_url()

    assert url == "sqlite:////tmp/env.db"


def test_vagas_db_continua_funcionando(monkeypatch):
    monkeypatch.setenv("VAGAS_DB", "/tmp/x.db")

    url = database_url()

    assert url == "sqlite:////tmp/x.db"


def test_argumento_vence_o_ambiente(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:////tmp/env.db")

    url = database_url("data/x.db")

    assert url == "sqlite:///data/x.db"


def test_engine_sqlite_recebe_check_same_thread(tmp_path):
    engine = make_engine(tmp_path / "t.db")
    try:
        dialect = engine.dialect.name
        creator = engine.pool._creator
    finally:
        engine.dispose()

    assert dialect == "sqlite"
    assert creator  # engine criado sem erro
