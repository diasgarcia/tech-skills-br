"""Testes do reclassificador de areas, com banco temporario."""

import sqlite3

import pytest

from scripts.reclassify_areas import reclassificar


@pytest.fixture
def db(tmp_path):
    caminho = tmp_path / "t.db"
    conn = sqlite3.connect(caminho)
    conn.execute(
        "CREATE TABLE vagas (id INTEGER PRIMARY KEY, title TEXT, area TEXT, "
        "area_score REAL, area_matches TEXT, description TEXT)"
    )
    conn.commit()
    return caminho


def _inserir(db, vid, title, area, desc):
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO vagas (id, title, area, area_score, area_matches, description) "
        "VALUES (?, ?, ?, 0, '', ?)",
        (vid, title, area, desc),
    )
    conn.commit()
    conn.close()


def test_pendente_sem_descricao_nao_e_analisada(db):
    _inserir(db, 1, "Analista de Redes Jr", "Outros/TI Geral", "")
    resultado = reclassificar(db)
    assert resultado["analisadas"] == 0
    assert resultado["mudadas"] == 0


def test_pendente_com_descricao_e_reclassificada(db):
    _inserir(db, 1, "Analista de Redes Jr", "Outros/TI Geral",
             "Configurar switches, roteadores e cabeamento estruturado.")
    resultado = reclassificar(db)
    assert resultado["mudadas"] >= 1
    conn = sqlite3.connect(db)
    area = conn.execute("SELECT area FROM vagas WHERE id = 1").fetchone()[0]
    conn.close()
    assert area == "Infraestrutura / Redes"


def test_area_boa_nao_e_tocada_no_modo_pendentes(db):
    _inserir(db, 1, "Analista de Redes Jr", "Infraestrutura / Redes",
             "Configurar switches e roteadores.")
    resultado = reclassificar(db)
    assert resultado["analisadas"] == 0


def test_todas_reclassifica_mas_so_grava_quando_muda(db):
    _inserir(db, 1, "Analista de Redes Jr", "Infraestrutura / Redes",
             "Configurar switches e roteadores.")
    _inserir(db, 2, "Desenvolvedor Python Jr", "Backend",
             "Atuar com Python, Django e APIs REST.")
    resultado = reclassificar(db, todas=True)
    assert resultado["analisadas"] == 2
    assert resultado["mudadas"] == 0  # nada mudou: sem UPDATE inutil


def test_todas_corrige_area_errada(db):
    _inserir(db, 1, "Analista de Redes Jr", "Data",
             "Configurar switches, roteadores e cabeamento estruturado.")
    resultado = reclassificar(db, todas=True)
    assert resultado["mudadas"] >= 1
    conn = sqlite3.connect(db)
    area = conn.execute("SELECT area FROM vagas WHERE id = 1").fetchone()[0]
    conn.close()
    assert area == "Infraestrutura / Redes"
