"""Testes do enriquecedor de Vagas.com e Trampos, com sessao falsa."""

import sqlite3
from threading import Lock

from scraper.skills import SkillExtractor
from scripts.enrich_outras_fontes import (
    QUERY_VAGAS_PENDENTES,
    _enriquecer,
    fetch_gupy,
    fetch_trampos,
    fetch_vagas_com,
)

VAGAS_HTML = """
<html><body>
  <div class="job-description__text">
    Resumo da Vaga: desenvolvimento com Java, Spring Boot e Angular,
    atuando na manutencao de aplicacoes backend e frontend.
  </div>
</body></html>
"""


class FakeResponse:
    def __init__(self, text=None, payload=None):
        self.text = text or ""
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("nao e json")
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.last_status_code = None

    def get(self, url):
        return self._responses.pop(0) if self._responses else None


def test_fetch_vagas_com_extrai_a_descricao_completa():
    session = FakeSession([FakeResponse(text=VAGAS_HTML)])
    desc, status = fetch_vagas_com(session, Lock(), "https://www.vagas.com.br/vagas/v1/x")
    assert "Spring Boot" in desc
    assert "manutencao" in desc
    assert status is None


def test_fetch_vagas_com_sem_o_seletor_devolve_vazio():
    session = FakeSession([FakeResponse(text="<html>sem descricao</html>")])
    desc, _ = fetch_vagas_com(session, Lock(), "http://x")
    assert desc == ""


def test_fetch_vagas_com_retorna_vazio_quando_api_falha():
    session = FakeSession([None])
    assert fetch_vagas_com(session, Lock(), "http://x") == ("", None)


def test_fetch_trampos_junta_os_campos_de_texto():
    payload = {
        "opportunity": {
            "description": "Vaga para atuar com Python e Django.",
            "prerequisite": "Conhecimento de Git.",
            "desirable": "Experiencia com AWS.",
            "other_info": "",
            "perks": "Vale refeicao",
        }
    }
    session = FakeSession([FakeResponse(payload=payload)])
    desc, _ = fetch_trampos(session, Lock(), "1-vaga-x")
    assert "Django" in desc
    assert "Git" in desc
    assert "AWS" in desc
    assert "Vale refeicao" not in desc  # perks ficam de fora


def test_fetch_trampos_suporta_listas_nos_campos():
    payload = {
        "opportunity": {
            "description": "Buscamos QA.",
            "prerequisite": ["Logica de programacao", "Testes automatizados"],
        }
    }
    session = FakeSession([FakeResponse(payload=payload)])
    desc, _ = fetch_trampos(session, Lock(), "1-x")
    assert "Logica de programacao" in desc
    assert "Testes automatizados" in desc


def test_fetch_trampos_resposta_invalida_devolve_vazio():
    session = FakeSession([FakeResponse(text="<html>nao json</html>")])
    assert fetch_trampos(session, Lock(), "1-x")[0] == ""


def test_fetch_gupy_extrai_e_limpa_html_da_descricao():
    payload = {
        "id": 123,
        "description": "<p>Vaga para atuar com <b>Python</b> e Django.</p>",
    }
    session = FakeSession([FakeResponse(payload=payload)])
    desc, _ = fetch_gupy(session, Lock(), "123")
    assert "Python" in desc
    assert "<p>" not in desc


def test_fetch_gupy_job_removido_devolve_vazio():
    session = FakeSession([None])  # PoliteSession devolve None em 404
    assert fetch_gupy(session, Lock(), "123") == ("", None)


def test_data_anterior_ao_corte_remove_a_vaga_em_vez_de_atualizar():
    # A GeekHunter traz data antiga no JSON-LD sem passar pelo corte do
    # import_csv: a vaga precisa sair da base, nao ganhar data de 2025.
    conn = sqlite3.connect(":memory:")
    c = conn.cursor()
    c.execute(
        """CREATE TABLE vagas (
            id INTEGER PRIMARY KEY, url TEXT, title TEXT, description TEXT,
            company TEXT, published_date TEXT, enrich_encerrada INTEGER DEFAULT 0)"""
    )
    c.execute(
        "CREATE TABLE vaga_tecnologia (vaga_id INTEGER, tecnologia_id INTEGER)"
    )
    c.execute("INSERT INTO vagas (id, url, title) VALUES (1, 'http://velha', 'QA')")
    c.execute("INSERT INTO vagas (id, url, title) VALUES (2, 'http://nova', 'Dev Python')")
    conn.commit()

    extractor = SkillExtractor(
        {"dev": {"Python": ["python"]}},
        secoes_descarte=[],
        secoes_conteudo=[],
        contextos_descarte={},
    )
    tech_map = {"python": 1}
    respostas = {
        "http://velha": ({"description": "Vaga de 2025", "published_date": "2025-07-21", "company": "X"}, None),
        "http://nova": ({"description": "Vaga com Python", "published_date": "2026-08-01", "company": "Y"}, None),
    }

    def fake_fetch(session, lock, url):
        return respostas[url]

    total = _enriquecer(
        c, None, Lock(), extractor, tech_map,
        "SELECT id, url, title FROM vagas", [], fake_fetch,
    )
    assert total == 1
    sobreviventes = c.execute("SELECT id, published_date FROM vagas").fetchall()
    assert sobreviventes == [(2, "2026-08-01")]


def _vagas_com_fixture():
    conn = sqlite3.connect(":memory:")
    c = conn.cursor()
    c.execute(
        """CREATE TABLE vagas (
            id INTEGER PRIMARY KEY, url TEXT, title TEXT, description TEXT,
            source TEXT DEFAULT 'vagas',
            enrich_encerrada INTEGER DEFAULT 0, published_date TEXT)"""
    )
    return conn, c


def test_query_vagas_seleciona_snippet_truncado_do_portal():
    # O card do Vagas.com traz snippet com "...": nao batia no corte de
    # LENGTH < 300 e nunca recebia a descricao completa.
    _, c = _vagas_com_fixture()
    truncada = "x" * 380 + "..."
    completa = "descricao completa " * 80
    c.executemany(
        "INSERT INTO vagas (id, url, title, description, enrich_encerrada, published_date) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1, "u1", "t", truncada, 0, "2026-08-01"),   # snippet truncado -> pendente
            (2, "u2", "t", completa, 0, "2026-08-01"),   # completa -> nao pendente
            (3, "u3", "t", None, 0, "2026-08-01"),       # sem desc -> pendente
            (4, "u4", "t", truncada, 1, "2026-08-01"),   # encerrada -> fora
            (5, "u5", "t", "curta", 0, "2026-08-01"),    # < 300 -> pendente
        ],
    )
    ids = {r[0] for r in c.execute(QUERY_VAGAS_PENDENTES, (300, "-30 days"))}
    assert ids == {1, 3, 5}
