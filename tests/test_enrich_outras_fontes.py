"""Testes do enriquecedor de Vagas.com e Trampos, com sessao falsa."""

from threading import Lock

from scripts.enrich_outras_fontes import (
    fetch_gupy,
    fetch_programathor,
    fetch_trampos,
    fetch_vagas_com,
)

PROGRAMATHOR_HTML = """
<html><body>
  <div class="wrapper-content-job-show">
    Descrição da vaga: atuacao com Java, Spring Boot e Vue.js em equipe
    ageis, com testes automatizados e deploy em AWS.
  </div>
</body></html>
"""


class FonteFake:
    def __init__(self, html):
        self._html = html

    def _get_page_html(self, url, params):
        return self._html

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

    def get(self, url):
        return self._responses.pop(0) if self._responses else None


def test_fetch_vagas_com_extrai_a_descricao_completa():
    session = FakeSession([FakeResponse(text=VAGAS_HTML)])
    desc = fetch_vagas_com(session, Lock(), "https://www.vagas.com.br/vagas/v1/x")
    assert "Spring Boot" in desc
    assert "manutencao" in desc


def test_fetch_vagas_com_sem_o_seletor_devolve_vazio():
    session = FakeSession([FakeResponse(text="<html>sem descricao</html>")])
    assert fetch_vagas_com(session, Lock(), "http://x") == ""


def test_fetch_vagas_com_retorna_vazio_quando_api_falha():
    session = FakeSession([None])
    assert fetch_vagas_com(session, Lock(), "http://x") == ""


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
    desc = fetch_trampos(session, Lock(), "1-vaga-x")
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
    desc = fetch_trampos(session, Lock(), "1-x")
    assert "Logica de programacao" in desc
    assert "Testes automatizados" in desc


def test_fetch_trampos_resposta_invalida_devolve_vazio():
    session = FakeSession([FakeResponse(text="<html>nao json</html>")])
    assert fetch_trampos(session, Lock(), "1-x") == ""


def test_fetch_programathor_extrai_da_pagina_de_detalhe():
    fonte = FonteFake(PROGRAMATHOR_HTML)
    desc = fetch_programathor(fonte, Lock(), "https://programathor.com.br/jobs/1-x")
    assert "Spring Boot" in desc
    assert "AWS" in desc


def test_fetch_programathor_sem_pagina_devolve_vazio():
    fonte = FonteFake(None)
    assert fetch_programathor(fonte, Lock(), "https://programathor.com.br/jobs/1-x") == ""


def test_fetch_gupy_extrai_e_limpa_html_da_descricao():
    payload = {
        "id": 123,
        "description": "<p>Vaga para atuar com <b>Python</b> e Django.</p>",
    }
    session = FakeSession([FakeResponse(payload=payload)])
    desc = fetch_gupy(session, Lock(), "123")
    assert "Python" in desc
    assert "<p>" not in desc


def test_fetch_gupy_job_removido_devolve_vazio():
    session = FakeSession([None])  # PoliteSession devolve None em 404
    assert fetch_gupy(session, Lock(), "123") == ""
