"""Contratos transacionais dos enriquecedores, sem banco ou rede reais."""

import argparse
import json
import logging
import sqlite3
from contextlib import closing
from threading import Event, Lock

import pytest

from api.database import connect_sqlite, init_db
from scraper.enrichment import DetailResult, EnrichmentSummary, read_summaries, write_summary
from scraper.skills import SkillExtractor
from scripts import enrich_descriptions as linkedin
from scripts import enrich_outras_fontes as outras
from scripts import resumo_commit


class FakeSession:
    def __init__(self, *, status=200, text="", fail_enter=False):
        self.last_status_code = status
        self.text = text
        self.fail_enter = fail_enter
        self.calls = []

    def __enter__(self):
        if self.fail_enter:
            raise RuntimeError("falha ao abrir cliente")
        return self

    def __exit__(self, *args):
        return False

    def get(self, url):
        self.calls.append(url)
        if self.last_status_code >= 400:
            return None
        return type("Response", (), {"text": self.text})()


@pytest.fixture
def database_factory(tmp_path):
    def create(name="vagas.db", source="linkedin", count=2):
        path = tmp_path / name
        init_db(db_path=path)
        with closing(connect_sqlite(path)) as conn, conn:
            conn.execute("INSERT INTO tecnologias (id, nome, grupo) VALUES (1, 'Python', 'linguagens')")
            conn.executemany(
                "INSERT INTO vagas (id, source, external_id, title, area, url, description, "
                "company, enrich_encerrada, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (index, source, str(index), "Desenvolvedor Python Junior", "Backend",
                     f"https://empresa.gupy.io/job/{index}", "teaser", "Empresa salva", 0,
                     "2000-01-01 00:00:00")
                    for index in range(1, count + 1)
                ],
            )
        return path
    return create


def _extractor():
    return SkillExtractor(
        {"linguagens": {"Python": ["python"]}},
        secoes_descarte=[], secoes_conteudo=[], contextos_descarte={},
    )


def _rows(path):
    with closing(connect_sqlite(path, read_only=True)) as conn:
        return conn.execute(
            "SELECT id, description, company, enrich_encerrada, updated_at FROM vagas ORDER BY id"
        ).fetchall()


def _fail_first_skill_insert(path):
    with closing(connect_sqlite(path)) as conn, conn:
        conn.execute(
            "CREATE TRIGGER simular_falha BEFORE INSERT ON vaga_tecnologia "
            "WHEN NEW.vaga_id = 1 BEGIN SELECT RAISE(ABORT, 'falha simulada nas skills'); END"
        )


def test_linkedin_confirma_sucesso_so_depois_da_transacao(database_factory, monkeypatch):
    path = database_factory()
    _fail_first_skill_insert(path)
    description = "Desenvolver sistemas com Python e integrar os servicos da equipe."
    session = FakeSession(text=f'<div class="description__text">{description}</div>')
    monkeypatch.setattr(linkedin, "PoliteSession", lambda **kwargs: session)

    summary = linkedin.enrich_linkedin_jobs(db_path=path, max_workers=1)
    rows = _rows(path)
    with closing(connect_sqlite(path, read_only=True)) as conn:
        skills = conn.execute("SELECT * FROM vaga_tecnologia").fetchall()

    assert rows[0][1:] == ("teaser", "Empresa salva", 0, "2000-01-01 00:00:00")
    assert rows[1][1] == description
    assert rows[1][3] == 1
    assert rows[1][4] != "2000-01-01 00:00:00"
    assert skills == [(2, 1)]
    assert summary.enriched == 1
    assert summary.failures == 1
    assert summary.pending == 1
    assert summary.attempted == 2


def test_linkedin_enriquecimento_preserva_modalidade_declarada(
    database_factory, monkeypatch,
):
    path = database_factory(count=1)
    with closing(connect_sqlite(path)) as conn, conn:
        conn.execute(
            "UPDATE vagas SET workplace_type = 'Híbrido', "
            "workplace_declared = 1, location = 'João Pessoa, PB' WHERE id = 1"
        )
    description = "MODALIDADE: Home Office. Desenvolvimento de sistemas com Python."
    session = FakeSession(text=f'<div class="description__text">{description}</div>')
    monkeypatch.setattr(linkedin, "PoliteSession", lambda **kwargs: session)

    linkedin.enrich_linkedin_jobs(db_path=path, max_workers=1)
    with closing(connect_sqlite(path, read_only=True)) as conn:
        workplace = conn.execute(
            "SELECT workplace_type FROM vagas WHERE id = 1"
        ).fetchone()[0]

    assert workplace == "Híbrido"


def test_outras_fontes_desfaz_campos_e_skills_da_vaga_com_falha(database_factory, caplog):
    path = database_factory(source="gupy")
    _fail_first_skill_insert(path)
    description = "Desenvolvimento com Python em descricao completa."

    def fetch(session, lock, url):
        return {"description": description, "company": "Empresa nova", "published_date": "2026-09-01"}, 200

    with closing(connect_sqlite(path)) as conn, caplog.at_level(logging.INFO):
        count = outras._enriquecer(
            conn.cursor(), FakeSession(), Lock(), _extractor(), {"python": 1},
            outras.QUERY_GUPY_PENDENTES, [], fetch, max_workers=1, fonte="gupy",
        )
    rows = _rows(path)

    assert count == 1
    assert rows[0][1:] == ("teaser", "Empresa salva", 0, "2000-01-01 00:00:00")
    assert rows[1][1:4] == (description, "Empresa nova", 1)
    assert rows[1][4] != "2000-01-01 00:00:00"
    assert "enriquecidas=1 | encerradas=0 | removidas=0 | pendentes=1 | falhas=1" in caplog.text


@pytest.mark.parametrize("source", ["linkedin", "gupy"])
def test_enriquecimento_altera_apenas_o_destino_explicito(database_factory, monkeypatch, source):
    env_path = database_factory("ambiente.db", source=source)
    selected_path = database_factory("selecionado.db", source=source)
    before = _rows(env_path)
    monkeypatch.setenv("DATABASE_URL", str(env_path))
    session = FakeSession(text='<div class="description__text">Desenvolvimento de sistemas com Python.</div>')
    if source == "linkedin":
        monkeypatch.setattr(linkedin, "PoliteSession", lambda **kwargs: session)
    else:
        monkeypatch.setattr(outras, "PoliteSession", lambda **kwargs: session)
        monkeypatch.setattr(outras, "fetch_gupy", lambda *args: ({"description": "Desenvolvimento de sistemas com Python."}, 200))

    if source == "linkedin":
        linkedin.enrich_linkedin_jobs(db_path=selected_path)
    else:
        outras.enriquecer(db_path=selected_path, fonte="gupy")

    assert _rows(env_path) == before
    assert all(row[3] == 1 for row in _rows(selected_path))


@pytest.mark.parametrize("module", [linkedin, outras])
def test_conexao_fecha_se_o_cliente_nao_abre(database_factory, monkeypatch, module):
    path = database_factory(source="gupy" if module is outras else "linkedin")
    opened = []

    def connect(path):
        conn = connect_sqlite(path)
        opened.append(conn)
        return conn

    monkeypatch.setattr(module, "connect_sqlite", connect)
    monkeypatch.setattr(module, "PoliteSession", lambda **kwargs: FakeSession(fail_enter=True))

    with pytest.raises(RuntimeError, match="falha ao abrir cliente"):
        if module is linkedin:
            module.enrich_linkedin_jobs(db_path=path)
        else:
            module.enriquecer(db_path=path, fonte="gupy")

    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].execute("SELECT 1")


def test_linkedin_nao_encurta_descricao_nem_extrai_do_texto_descartado(database_factory, monkeypatch):
    path = database_factory(count=1)
    with closing(connect_sqlite(path)) as conn, conn:
        conn.execute("UPDATE vagas SET description = 'Descricao com Python.'")
    session = FakeSession(text='<div class="description__text">Curta.</div>')
    monkeypatch.setattr(linkedin, "PoliteSession", lambda **kwargs: session)

    summary = linkedin.enrich_linkedin_jobs(db_path=path)

    assert summary.enriched == 1
    assert _rows(path)[0][1] == "Descricao com Python."
    with closing(connect_sqlite(path, read_only=True)) as conn:
        assert conn.execute("SELECT * FROM vaga_tecnologia").fetchall() == [(1, 1)]


def test_outras_fontes_remove_relacoes_junto_da_vaga_antiga(database_factory):
    path = database_factory(source="gupy", count=1)
    with closing(connect_sqlite(path)) as conn, conn:
        conn.execute("INSERT INTO vaga_tecnologia VALUES (1, 1)")

    with closing(connect_sqlite(path)) as conn:
        count = outras._enriquecer(
            conn.cursor(), FakeSession(), Lock(), _extractor(), {"python": 1},
            outras.QUERY_GUPY_PENDENTES, [],
            lambda *args: ({"published_date": "2025-01-01"}, 200),
        )
        vagas = conn.execute("SELECT COUNT(*) FROM vagas").fetchone()[0]
        links = conn.execute("SELECT COUNT(*) FROM vaga_tecnologia").fetchone()[0]
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()

    assert count == vagas == links == 0
    assert violations == []


def test_linkedin_429_distingue_nao_tentadas_de_http_real(database_factory, monkeypatch):
    path = database_factory(count=5)
    session = FakeSession(status=429)
    monkeypatch.setattr(linkedin, "PoliteSession", lambda **kwargs: session)

    summary = linkedin.enrich_linkedin_jobs(db_path=path, max_workers=3)

    assert len(session.calls) == summary.attempted == 1
    assert summary.selected == summary.pending == 5
    assert summary.skipped == 4
    assert summary.reasons == {"http_429": 1, "lote_interrompido_apos_429": 4}
    assert all(row[3] == 0 for row in _rows(path))


def test_outras_429_distingue_nao_tentadas_e_checa_a_parada_dentro_do_lock(database_factory, caplog):
    path = database_factory(source="gupy", count=5)
    session = FakeSession(status=429)

    with closing(connect_sqlite(path)) as conn, caplog.at_level(logging.INFO):
        count = outras._enriquecer(
            conn.cursor(), session, Lock(), _extractor(), {"python": 1},
            outras.QUERY_GUPY_PENDENTES, [], outras.fetch_gupy,
            parar_em_429=True, fonte="gupy", max_workers=3,
        )

    assert count == 0
    assert len(session.calls) == 1
    assert "tentadas=1" in caplog.text
    assert "selecionadas=5 | nao_tentadas=4" in caplog.text
    skipped_messages = [record.message for record in caplog.records if "nao tentada |" in record.message]
    assert len(skipped_messages) == 4
    assert all("http=" not in message for message in skipped_messages)


def test_fetch_linkedin_interrompido_nao_inventa_status_http():
    session = FakeSession()
    stopped = Event()
    stopped.set()

    result = linkedin.fetch_one_description(session, Lock(), "123", stopped)

    assert result == DetailResult.stopped()
    assert result.status is None
    assert session.calls == []


def test_resumo_usa_a_mesma_fila_inclusive_descricao_nula(database_factory, monkeypatch):
    env_path = database_factory("ambiente.db", source="linkedin", count=1)
    selected_path = database_factory("selecionado.db", source="vagas", count=2)
    with closing(connect_sqlite(selected_path)) as conn, conn:
        conn.execute("UPDATE vagas SET description = NULL WHERE id = 1")
    monkeypatch.setenv("DATABASE_URL", str(env_path))
    args = argparse.Namespace(db=selected_path, brutas=None, elegiveis=None, novas=None, atualizadas=None, log=None)
    before = _rows(selected_path)

    text = resumo_commit.resumir(args)

    assert "Base: 2 vagas" in text
    assert "Pendentes: vagas.com 2" in text
    assert _rows(selected_path) == before


def test_resumo_nao_cria_banco_quando_o_destino_nao_existe(tmp_path):
    path = tmp_path / "inexistente.db"
    args = argparse.Namespace(db=path)

    with pytest.raises(sqlite3.OperationalError):
        resumo_commit.resumir(args)

    assert not path.exists()


@pytest.mark.parametrize("module", [linkedin, outras])
def test_enriquecedor_nao_cria_banco_quando_o_destino_nao_existe(tmp_path, module):
    path = tmp_path / "inexistente.db"

    with pytest.raises(sqlite3.OperationalError):
        if module is linkedin:
            module.enrich_linkedin_jobs(db_path=path)
        else:
            module.enriquecer(db_path=path)

    assert not path.exists()


def test_resumo_estruturado_combina_arquivos_e_nao_depende_de_log(database_factory, tmp_path):
    path = database_factory()
    linkedin_json = tmp_path / "linkedin.json"
    outras_json = tmp_path / "outras.json"
    write_summary(linkedin_json, {"linkedin": EnrichmentSummary(selected=2, attempted=2, enriched=2)})
    write_summary(outras_json, {"gupy": EnrichmentSummary(selected=3, attempted=3, enriched=3)})
    args = argparse.Namespace(
        db=path, brutas=None, elegiveis=None, novas=None, atualizadas=None,
        log=None, summary_json=[linkedin_json, outras_json],
    )

    text = resumo_commit.resumir(args)

    assert "Enriquecidas: gupy 3 | linkedin 2" in text


def test_artefato_estruturado_substitui_contadores_da_execucao_anterior(tmp_path):
    path = tmp_path / "enrich.json"
    write_summary(path, {"gupy": EnrichmentSummary(selected=1, attempted=1, enriched=1)})

    write_summary(path, {"linkedin": EnrichmentSummary(selected=0)})
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert set(payload["sources"]) == {"linkedin"}
    assert read_summaries([path])["linkedin"]["enriched"] == 0
    assert list(tmp_path.iterdir()) == [path]


def test_resumo_estruturado_inconsistente_nao_vira_sucesso(tmp_path):
    path = tmp_path / "enrich.json"
    write_summary(path, {"gupy": EnrichmentSummary(selected=10, attempted=10, enriched=1)})

    with pytest.raises(ValueError, match="inconsistentes"):
        read_summaries([path])


def test_resumo_estruturado_ausente_nao_vira_sucesso(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_summaries([tmp_path / "ausente.json"])


def test_resumo_estruturado_rejeita_fontes_repetidas(tmp_path):
    path = tmp_path / "enrich.json"
    write_summary(path, {"gupy": EnrichmentSummary(selected=0)})

    with pytest.raises(ValueError, match="Fonte repetida"):
        read_summaries([path, path])


@pytest.mark.parametrize("module,source", [(linkedin, "linkedin"), (outras, "gupy")])
def test_enriquecedor_grava_resumo_da_propria_execucao(database_factory, monkeypatch, tmp_path, module, source):
    path = database_factory(source=source, count=2)
    output = tmp_path / "enrich.json"
    session = FakeSession(status=429)
    monkeypatch.setattr(module, "PoliteSession", lambda **kwargs: session)

    if module is linkedin:
        module.enrich_linkedin_jobs(db_path=path, summary_path=output)
    else:
        module.enriquecer(db_path=path, fonte="gupy", summary_path=output)
    counts = read_summaries([output])[source]

    assert counts["selected"] == counts["pending"] == 2
    assert counts["attempted"] == counts["skipped"] == 1
    assert counts["enriched"] == 0
