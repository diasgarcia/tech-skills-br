"""Testes do enriquecedor de descricoes do LinkedIn."""

import sqlite3

from scripts.enrich_descriptions import QUERY_PENDENTES


def test_query_pendentes_ignora_a_janela_de_dias():
    # Vaga antiga e ainda viva no LinkedIn nao pode ficar sem descricao
    # para sempre: a janela de 30 dias foi removida (404 marca como
    # encerrada, entao retentar nao e infinito).
    conn = sqlite3.connect(":memory:")
    c = conn.cursor()
    c.execute(
        """CREATE TABLE vagas (
            id INTEGER PRIMARY KEY, source TEXT, external_id TEXT,
            title TEXT, url TEXT, location TEXT, workplace_type TEXT,
            description TEXT, enrich_encerrada INTEGER DEFAULT 0,
            published_date TEXT)"""
    )
    c.executemany(
        "INSERT INTO vagas (id, source, external_id, title, description, enrich_encerrada, published_date) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (1, "linkedin", "e1", "t", None, 0, "2026-04-23"),   # antiga, sem desc -> pendente
            (2, "linkedin", "e2", "t", "x" * 500, 0, "2026-04-23"),  # antiga, truncada 500 -> pendente
            (3, "linkedin", "e3", "t", "x" * 20, 0, "2026-04-23"),   # antiga, curta -> pendente
            (4, "linkedin", "e4", "t", "x" * 800, 0, "2026-08-01"),  # completa -> fora
            (5, "linkedin", "e5", "t", None, 1, "2026-04-23"),       # encerrada -> fora
            (6, "gupy", "e6", "t", None, 0, "2026-04-23"),           # outra fonte -> fora
        ],
    )
    ids = {r[0] for r in c.execute(QUERY_PENDENTES)}
    assert ids == {1, 2, 3}
