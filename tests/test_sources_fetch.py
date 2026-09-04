"""Testes das funcoes de paginacao/coleta das fontes, com sessao falsa (offline)."""

from scraper.config import Settings
from scraper.models import Job
from scraper.sources.base import JobSource
from scraper.sources.gupy import GupySource
from scraper.sources.infojobs import InfoJobsSource
from scraper.sources.linkedin import LinkedInSource
from scraper.sources.trampos import TramposSource
from scraper.sources.vagas_com import VagasComSource

from test_sources import GUPY_JOB, INFOJOBS_HTML, LINKEDIN_HTML


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


def test_gupy_pagina_deduplica_e_para_em_repeticao():
    outro = dict(GUPY_JOB, id=999, name="Analista de Suporte Junior")
    session = FakeSession(
        [
            {"data": [GUPY_JOB, GUPY_JOB, outro]},
            {"data": [outro]},
            {"data": [dict(GUPY_JOB, id=777)]},  # nunca deve ser buscada
        ]
    )
    source = GupySource(session=session, settings=_settings(page_size=1))
    jobs = source.fetch_term("desenvolvedor junior")

    assert {j.external_id for j in jobs} == {"11617525", "999"}
    assert session.request_count == 2
    offsets = [p["offset"] for p in session.chamadas]
    assert offsets == [0, 1]


def test_gupy_para_quando_api_falha():
    session = FakeSession([None, {"data": [GUPY_JOB]}])
    source = GupySource(session=session, settings=_settings())
    assert source.fetch_term("x") == []
    assert session.request_count == 1


def test_linkedin_pagina_deduplica_e_para_em_repeticao():
    session = FakeSession(
        [
            FakeHtmlResponse(LINKEDIN_HTML),
            FakeHtmlResponse(LINKEDIN_HTML),
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


def test_trampos_para_no_total_pages():
    payload = {"opportunities": [{"id": 1, "name": "Dev .Net C#"}],
               "pagination": {"total_pages": 2}}
    session = FakeSession([payload, dict(payload), dict(payload)])
    source = TramposSource(session=session, settings=_settings(max_pages_per_term=10))
    jobs = source.fetch_term("desenvolvedor")

    assert [j.external_id for j in jobs] == ["1"]
    assert session.request_count == 2


def test_trampos_para_quando_api_falha():
    session = FakeSession([None])
    source = TramposSource(session=session, settings=_settings())
    assert source.fetch_term("x") == []


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


def test_infojobs_pagina_deduplica_e_para_em_repeticao():
    session = FakeSession(
        [
            FakeHtmlResponse(INFOJOBS_HTML),
            FakeHtmlResponse(INFOJOBS_HTML),
            FakeHtmlResponse(INFOJOBS_HTML),  # nunca deve ser buscada
        ]
    )
    source = InfoJobsSource(session=session, settings=_settings(max_pages_per_term=4))
    jobs = source.fetch_term("desenvolvedor")

    assert {j.external_id for j in jobs} == {"11985552", "11983931"}
    assert session.request_count == 2
    paginas = [p["Page"] for p in session.chamadas]
    assert paginas == [1, 2]


def test_infojobs_para_em_pagina_vazia():
    session = FakeSession(
        [
            FakeHtmlResponse(INFOJOBS_HTML),
            FakeHtmlResponse("<html></html>"),
        ]
    )
    source = InfoJobsSource(session=session, settings=_settings(max_pages_per_term=4))
    jobs = source.fetch_term("desenvolvedor")
    assert len(jobs) == 2
    assert session.request_count == 2


def test_infojobs_para_em_body_vazio():
    """200 com body vazio = bloqueio suave do portal: para o termo."""
    session = FakeSession(
        [
            FakeHtmlResponse(INFOJOBS_HTML),
            FakeHtmlResponse(""),
            FakeHtmlResponse(INFOJOBS_HTML),  # nunca deve ser buscada
        ]
    )
    source = InfoJobsSource(session=session, settings=_settings(max_pages_per_term=4))
    jobs = source.fetch_term("desenvolvedor")
    assert len(jobs) == 2
    assert session.request_count == 2


def test_infojobs_fetch_separa_termos_junior_dos_filtros_nativos():
    """Estagio/trainee/aprendiz vem dos filtros nativos; junior da busca textual."""
    session = FakeSession([])
    source = InfoJobsSource(session=session, settings=_settings(max_pages_per_term=4))
    source.fetch(["desenvolvedor junior", "estagio ti", "trainee tecnologia", "devops junior"])

    # 4 filtros nativos + 2 termos junior; estagio/trainee nao repetem.
    assert session.request_count == 6
    chaves = [sorted(p) for p in session.chamadas]
    assert chaves[0] == ["Page", "categoria", "tipocontrato"]  # Estágio
    assert chaves[1] == ["Page", "categoria", "im"]            # Estagiário
    assert chaves[4] == ["Page", "Palabra", "categoria"]       # termo junior
    assert session.chamadas[4]["Palabra"] == "desenvolvedor junior"
    assert session.chamadas[5]["Palabra"] == "devops junior"
