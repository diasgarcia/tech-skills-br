"""Testes das funcoes de paginacao/coleta das fontes, com sessao falsa (offline)."""

from scraper.config import Settings
from scraper.models import Job
from scraper.sources.base import JobSource
from scraper.sources.gupy import GupySource
from scraper.sources.linkedin import LinkedInSource
from scraper.sources.programathor import ProgramathorSource
from scraper.sources.trampos import TramposSource
from scraper.sources.vagas_com import VagasComSource

from test_sources import GUPY_JOB, LINKEDIN_HTML, PROGRAMATHOR_HTML


class FakeSession:
    """Devolve as respostas enfileiradas, registrando cada chamada."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.request_count = 0
        self.chamadas = []

    def _proximo(self, params):
        self.chamadas.append(params)
        self.request_count += 1
        if not self._responses:
            return None
        return self._responses.pop(0)

    def get(self, url, params=None):
        return self._proximo(params)

    def get_json(self, url, params=None):
        return self._proximo(params)


class FakeHtmlResponse:
    def __init__(self, text):
        self.text = text


def _settings(**kw):
    base = dict(start_page=1, max_pages_per_term=10)
    base.update(kw)
    return Settings(**base)


# --------------------------------------------------------------------------- #
# Gupy: paginacao por offset com limit, parando em pagina vazia ou repetida.
# --------------------------------------------------------------------------- #


def test_gupy_pagina_deduplica_e_para_em_repeticao():
    outro = dict(GUPY_JOB, id=999, name="Analista de Suporte Junior")
    session = FakeSession(
        [
            {"data": [GUPY_JOB, GUPY_JOB, outro]},  # repeticao na mesma pagina
            {"data": [outro]},                      # repeticao entre paginas
            {"data": [dict(GUPY_JOB, id=777)]},     # nunca deve ser buscada
        ]
    )
    source = GupySource(session=session, settings=_settings(page_size=1))
    jobs = source.fetch_term("desenvolvedor junior")

    assert {j.external_id for j in jobs} == {"11617525", "999"}
    assert session.request_count == 2  # parou antes da terceira pagina
    offsets = [p["offset"] for p in session.chamadas]
    assert offsets == [0, 1]


def test_gupy_para_quando_api_falha():
    session = FakeSession([None, {"data": [GUPY_JOB]}])
    source = GupySource(session=session, settings=_settings())
    assert source.fetch_term("x") == []
    assert session.request_count == 1


# --------------------------------------------------------------------------- #
# LinkedIn: paginas de 10 cards, parando em vazio ou repeticao.
# --------------------------------------------------------------------------- #


def test_linkedin_pagina_deduplica_e_para_em_repeticao():
    session = FakeSession(
        [
            FakeHtmlResponse(LINKEDIN_HTML),
            FakeHtmlResponse(LINKEDIN_HTML),  # mesma vaga em duas paginas
            FakeHtmlResponse(LINKEDIN_HTML),  # nunca deve ser buscada
        ]
    )
    source = LinkedInSource(session=session, settings=_settings(max_pages_per_term=4))
    jobs = source.fetch_term("desenvolvedor junior")

    assert [j.external_id for j in jobs] == ["4422123289"]
    assert session.request_count == 2
    starts = [p["start"] for p in session.chamadas]
    assert starts == [0, 10]


def test_linkedin_para_em_pagina_vazia():
    segunda_vaga = LINKEDIN_HTML.replace("4422123289", "9999999")
    session = FakeSession(
        [
            FakeHtmlResponse(LINKEDIN_HTML),
            FakeHtmlResponse(segunda_vaga),
            FakeHtmlResponse("<html></html>"),
            FakeHtmlResponse(LINKEDIN_HTML),  # nunca deve ser buscada
        ]
    )
    source = LinkedInSource(session=session, settings=_settings(max_pages_per_term=4))
    jobs = source.fetch_term("desenvolvedor junior")

    assert {j.external_id for j in jobs} == {"4422123289", "9999999"}
    assert session.request_count == 3


def test_linkedin_para_quando_api_falha():
    session = FakeSession([None])
    source = LinkedInSource(session=session, settings=_settings())
    assert source.fetch_term("x") == []


# --------------------------------------------------------------------------- #
# Vagas.com: paginacao 1-indexada, parando em pagina vazia.
# --------------------------------------------------------------------------- #


def test_vagas_com_pagina_e_deduplica():
    session = FakeSession(
        [
            FakeHtmlResponse(
                '<ul><li class="vaga"><a class="link-detalhes-vaga" data-id-vaga="1" '
                'title="Dev Jr" href="/vagas/v1/dev"><h2 class="cargo">Dev Jr</h2></a></li></ul>'
            ),
            FakeHtmlResponse("<html></html>"),
        ]
    )
    source = VagasComSource(session=session, settings=_settings(max_pages_per_term=3))
    jobs = source.fetch_term("desenvolvedor junior")

    assert [j.external_id for j in jobs] == ["1"]
    assert session.request_count == 2
    paginas = [p["pagina"] for p in session.chamadas]
    assert paginas == [1, 2]


def test_vagas_com_para_em_repeticao():
    html = (
        '<ul><li class="vaga"><a class="link-detalhes-vaga" data-id-vaga="1" '
        'title="Dev Jr" href="/vagas/v1/dev"><h2 class="cargo">Dev Jr</h2></a></li></ul>'
    )
    session = FakeSession([FakeHtmlResponse(html), FakeHtmlResponse(html)])
    source = VagasComSource(session=session, settings=_settings(max_pages_per_term=3))
    jobs = source.fetch_term("x")
    assert len(jobs) == 1
    assert session.request_count == 2


# --------------------------------------------------------------------------- #
# Trampos: respeita pagination.total_pages da propria API.
# --------------------------------------------------------------------------- #


def test_trampos_para_no_total_pages():
    payload = {"opportunities": [{"id": 1, "name": "Dev .Net C#"}],
               "pagination": {"total_pages": 2}}
    session = FakeSession([payload, dict(payload), dict(payload)])
    source = TramposSource(session=session, settings=_settings(max_pages_per_term=10))
    jobs = source.fetch_term("desenvolvedor")

    assert [j.external_id for j in jobs] == ["1"]
    assert session.request_count == 2  # nao pediu a pagina 3


def test_trampos_para_quando_api_falha():
    session = FakeSession([None])
    source = TramposSource(session=session, settings=_settings())
    assert source.fetch_term("x") == []


# --------------------------------------------------------------------------- #
# base.JobSource.fetch: isola a falha de um termo dos demais.
# --------------------------------------------------------------------------- #


class _FonteDeTeste(JobSource):
    name = "teste"

    def fetch_term(self, term: str) -> list[Job]:
        if term == "explode":
            raise RuntimeError("portal caiu")
        return [Job(source=self.name, external_id=f"{term}-1", title=term)]


def test_fetch_isola_falha_de_um_termo():
    source = _FonteDeTeste(session=FakeSession([]), settings=_settings())
    jobs = source.fetch(["ok1", "explode", "ok2"])

    assert [j.title for j in jobs] == ["ok1", "ok2"]
    assert source.stats.raw_jobs == 2
    assert any("explode" in e for e in source.stats.errors)


# --------------------------------------------------------------------------- #
# ProgramaThor: paginacao sobre _get_page_html, com browser real abstraido.
# --------------------------------------------------------------------------- #


def test_programathor_fetch_pagina_e_para_em_pagina_vazia(monkeypatch):
    respostas = [PROGRAMATHOR_HTML, PROGRAMATHOR_HTML, "<html></html>"]
    chamadas = []

    def html_fake(self, url, params):
        chamadas.append(dict(params))
        return respostas.pop(0) if respostas else None

    monkeypatch.setattr(ProgramathorSource, "_get_page_html", html_fake)
    source = ProgramathorSource(session=FakeSession([]), settings=_settings())
    jobs = source.fetch_term("Júnior")

    assert [j.external_id for j in jobs] == ["33692"]  # dedupe entre paginas
    assert [p["page"] for p in chamadas] == [1, 2, 3]


def test_programathor_fetch_para_quando_pagina_falha(monkeypatch):
    monkeypatch.setattr(
        ProgramathorSource, "_get_page_html", lambda self, url, params: None
    )
    source = ProgramathorSource(session=FakeSession([]), settings=_settings())
    assert source.fetch_term("Júnior") == []


def test_programathor_card_sem_h3_ou_titulo_vazio_e_ignorado():
    source = ProgramathorSource(session=FakeSession([]), settings=_settings())
    sem_h3 = '<div class="wrapper-jobs-list"><a href="/jobs/1"><div></div></a></div>'
    assert source._parse_page(sem_h3, "x") == []
    titulo_vazio = (
        '<div class="wrapper-jobs-list"><a href="/jobs/1"><h3>   </h3></a></div>'
    )
    assert source._parse_page(titulo_vazio, "x") == []


def test_programathor_local_sem_modalidade_explicita():
    assert ProgramathorSource._local_e_modalidade("São Paulo") == ("São Paulo", "")


def test_programathor_texto_de_no_vazio():
    assert ProgramathorSource._text(None) == ""
