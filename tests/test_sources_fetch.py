"""Testes das funcoes de paginacao/coleta das fontes, com sessao falsa (offline)."""

import pytest

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
    offsets = [p["offset"] for p in session.chamadas]

    assert {j.external_id for j in jobs} == {"11617525", "999"}
    assert session.request_count == 2
    assert offsets == [0, 1]


def test_gupy_para_quando_api_falha():
    session = FakeSession([None, {"data": [GUPY_JOB]}])
    source = GupySource(session=session, settings=_settings())

    jobs = source.fetch_term("x")

    assert jobs == []
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
    starts = [p["start"] for p in session.chamadas]

    assert [j.external_id for j in jobs] == ["4422123289"]
    assert session.request_count == 2
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

    jobs = source.fetch_term("x")

    assert jobs == []


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
    paginas = [p["pagina"] for p in session.chamadas]

    assert [j.external_id for j in jobs] == ["1"]
    assert session.request_count == 2
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

    jobs = source.fetch_term("x")

    assert jobs == []


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


class _FonteComBuscaImprecisa(JobSource):
    name = "imprecisa"

    def fetch_term(self, term: str) -> list[Job]:
        return [
            Job(source=self.name, external_id="1", title="Mainframe Tester Júnior"),
            Job(source=self.name, external_id="2", title="Operador Técnico N1 Júnior"),
            Job(
                source=self.name,
                external_id="3",
                title="Analista de TI Júnior",
                description="Manutenção de sistemas legados em COBOL.",
            ),
        ]


def test_fetch_exige_sinal_de_busca_especifica():
    settings = _settings(
        term_match_rules={"mainframe junior": ["mainframe", "cobol"]}
    )
    source = _FonteComBuscaImprecisa(session=FakeSession([]), settings=settings)

    jobs = source.fetch(["mainframe junior"])

    assert [job.external_id for job in jobs] == ["1", "3"]
    assert source.stats.raw_jobs == 2


def test_fetch_mantem_flexiveis_os_termos_sem_validacao():
    source = _FonteComBuscaImprecisa(
        session=FakeSession([]), settings=_settings(term_match_rules={})
    )

    jobs = source.fetch(["desenvolvedor junior"])

    assert [job.external_id for job in jobs] == ["1", "2", "3"]


@pytest.mark.parametrize(
    "term,title,description",
    [
        ("dba junior", "Database Administrator Junior", ""),
        ("analista de rpa junior", "UiPath Developer Junior", ""),
        ("analista de telecom junior", "Analista de Telecom Júnior", ""),
        ("mainframe junior", "Mainframe Tester Júnior", ""),
        ("embarcados junior", "Analista Júnior", "Desenvolvimento de firmware."),
        ("desenvolvedor de jogos junior", "Unity Developer Junior", ""),
        ("suporte aplicacoes junior", "Suporte a Sistemas Júnior", ""),
        ("analista de integracao junior", "Analista de Integração Júnior", ""),
        ("analista de integracoes junior", "Integration Analyst Junior", ""),
    ],
)
def test_fetch_aceita_sinais_das_funcoes_auditadas(term, title, description):
    class Fonte(JobSource):
        name = "auditada"

        def fetch_term(self, current_term: str) -> list[Job]:
            return [
                Job(
                    source=self.name,
                    external_id="1",
                    title=title,
                    description=description,
                )
            ]

    source = Fonte(session=FakeSession([]), settings=_settings())

    jobs = source.fetch([term])

    assert [job.external_id for job in jobs] == ["1"]


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
    paginas = [p["Page"] for p in session.chamadas]

    assert {j.external_id for j in jobs} == {"11985552", "11983931"}
    assert session.request_count == 2
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
    chaves = [sorted(p) for p in session.chamadas]

    # 4 filtros nativos + 2 termos junior; estagio/trainee nao repetem.
    assert session.request_count == 6
    assert chaves[0] == ["Page", "categoria", "tipocontrato"]  # Estágio
    assert chaves[1] == ["Page", "categoria", "im"]            # Estagiário
    assert chaves[4] == ["Page", "Palabra", "categoria"]       # termo junior
    assert session.chamadas[4]["Palabra"] == "desenvolvedor junior"
    assert session.chamadas[5]["Palabra"] == "devops junior"
