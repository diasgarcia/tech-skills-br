"""Jobbol: listagem, detalhes e falhas simuladas, sem chamadas reais."""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from scraper.config import Settings, load_search_terms
from scraper.models import HIBRIDO, NAO_INFORMADO, PRESENCIAL, REMOTO
from scraper.skills import default_extractor
from scraper.sources import jobbol
from scraper.sources.jobbol import JobbolSource

NOW = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)


class FakeSession:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.request_count = 0
        self.calls = []
        self.last_status_code = None

    def get(self, url, params=None):
        self.calls.append((url, dict(params) if params else None))
        self.request_count += 1
        response = next(self.responses, None)
        self.last_status_code = 404 if response is None else 200
        return response

    get_json = get


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)

    monkeypatch.setattr(jobbol, "datetime", FrozenDatetime)


def row(job_id="123", **changes):
    return {
        "jobkey": job_id, "CARGO": "Desenvolvedor Júnior", "EMPRESA": "Acme",
        "CIDADE": "São Paulo", "ESTADO": "SP", "TIPO": "Presencial",
        "post_date_epoch": str(int(NOW.timestamp())), **changes,
    }


def detail(job_id="123", **changes):
    posting = {
        "@type": "JobPosting", "identifier": {"value": job_id},
        "description": "<p><strong>Atividades</strong></p><ul><li>Desenvolver sistemas.</li></ul>"
                       "<p><strong>Requisitos</strong></p><p>SQL.</p>"
                       "<p><strong>Benefícios</strong></p><p>Curso de Inglês.</p>"
                       "<p><strong>Observações</strong></p><p>Conhecimento em Python e Docker.</p>",
        "hiringOrganization": {"name": "Acme"}, **changes,
    }
    return SimpleNamespace(text=f'<script type="application/ld+json">{json.dumps(posting)}</script>')


def redirected_detail(
    job_id="123", page_id="145231", title="Desenvolvedor Júnior", *,
    final_url=None, history=None, **changes,
):
    identifier = changes.pop("identifier", {"@type": "PropertyValue", "value": f"v{page_id}"})
    response = detail(identifier=identifier, title=title, **changes)
    response.url = final_url or f"{jobbol.SITE_URL}/vaga/{page_id}-desenvolvedor-junior?cidade=4006"
    response.history = [SimpleNamespace(url=f"{jobbol.SITE_URL}/vaga/{job_id}")] if history is None else history
    return response


def html_detail(**changes):
    response = redirected_detail(**changes)
    response.text = """
        <link rel="canonical" href="https://candidatos.jobbol.com.br/vaga/145231-desenvolvedor-junior">
        <script type="application/ld+json">{"@type": "BreadcrumbList"}</script>
        <div id="vagaContainer">
          <header><h1 class="pl-manchete-titulo">Desenvolvedor Júnior</h1></header>
          <div class="jb-vaga-corpo">
            <h2 class="jb-vaga-secao">Sobre a empresa</h2>
            <div class="jb-empresa"><p class="jb-empresa-nome">Empresa do detalhe</p>
              <p>A empresa usa Java.</p></div>
            <h2 class="jb-vaga-secao"><i></i> Atividades</h2>
            <p class="fs-6">Desenvolver sistemas e consultar SQL.</p>
            <h2 class="jb-vaga-secao">Benefícios</h2>
            <ul class="fs-6 jb-vaga-beneficios"><li>Curso de Inglês.</li></ul>
            <h2 class="jb-vaga-secao">Observações</h2>
            <p class="fs-6">Conhecimento em Python e Docker.</p>
            <div class="jb-vaga-saida"><a>Quero me candidatar</a></div>
            <section><p>Receber alertas de AWS.</p></section>
            <p>Publicidade de Azure.</p>
          </div>
        </div>
        <h2 class="jb-secao-titulo">Vagas relacionadas</h2><p>Analista de Redes.</p>
    """
    return response


def source(session, **settings):
    return JobbolSource(session, Settings(sources=["jobbol"], **settings))


def test_detalhe_preserva_skills_das_observacoes_sem_extrair_beneficios():
    session = FakeSession({"vagas": [row()], "total": 1}, detail())
    collector = source(session)

    jobs = collector.fetch_term("desenvolvedor junior")
    skills = default_extractor().extract(jobs[0].description)

    assert len(jobs) == 1
    assert set(skills) == {"SQL", "Python", "Docker"}
    assert jobs[0].description.index("Python") < jobs[0].description.index("Benefícios")
    assert "Curso de Inglês" in jobs[0].description
    assert jobs[0].source == "jobbol"
    assert jobs[0].company == "Acme"
    assert jobs[0].location == "São Paulo, SP"
    assert jobs[0].published_date == "2026-10-12"
    assert jobs[0].url == "https://candidatos.jobbol.com.br/vaga/123"
    assert session.request_count == 2


@pytest.mark.parametrize("label, expected", [
    ("Presencial", PRESENCIAL), ("Remota", REMOTO), ("Híbrida", HIBRIDO), ("", NAO_INFORMADO),
])
def test_modalidade_declarada_da_listagem(label, expected):
    session = FakeSession({"vagas": [row(TIPO=label)], "total": 1}, detail())

    jobs = source(session).fetch_term("junior")

    assert jobs[0].workplace_type == expected
    assert jobs[0].workplace_declared is (expected != NAO_INFORMADO)


def test_telecommute_cobre_rotulo_ausente_sem_perder_cidade():
    session = FakeSession({"vagas": [row(TIPO="")], "total": 1}, detail(jobLocationType="TELECOMMUTE"))

    jobs = source(session).fetch_term("junior")

    assert jobs[0].workplace_type == REMOTO
    assert jobs[0].location == "São Paulo, SP"


def test_anuncio_promovido_antigo_nao_impede_pagina_seguinte():
    old = row("1", post_date_epoch=str(int((NOW - timedelta(days=5)).timestamp())), impulsionada="1")
    session = FakeSession({"vagas": [old], "total": 2}, {"vagas": [row()], "total": 2}, detail())

    jobs = source(session, max_pages_per_term=2).fetch_term("junior")

    assert [job.external_id for job in jobs] == ["123"]
    assert [params["offset"] for _, params in session.calls if params] == [0, 1]
    assert session.request_count == 3


def test_nao_busca_detalhe_de_senior_fora_da_janela_ou_id_repetido():
    batch = [row(), row(), row("2", CARGO="Desenvolvedor Sênior"),
             row("3", post_date_epoch=str(int((NOW - timedelta(days=8)).timestamp())))]
    session = FakeSession({"vagas": batch, "total": 4}, detail())

    jobs = source(session).fetch_term("junior")

    assert [job.external_id for job in jobs] == ["123"]
    assert session.request_count == 2


def test_all_levels_permite_senior():
    session = FakeSession({"vagas": [row(CARGO="Desenvolvedor Sênior")], "total": 1}, detail())

    jobs = source(session, only_junior=False).fetch_term("desenvolvedor")

    assert jobs[0].title == "Desenvolvedor Sênior"


def test_detalhe_e_reutilizado_entre_termos_da_rodada():
    session = FakeSession({"vagas": [row()], "total": 1}, detail(), {"vagas": [row()], "total": 1})
    collector = source(session)

    jobs = collector.fetch(["junior", "desenvolvedor"])

    assert len(jobs) == 2
    assert session.request_count == 3
    assert collector.stats.requests_made == 3


def test_rodada_padrao_cobre_estagio_fora_da_categoria_ti():
    session = FakeSession(*[{"vagas": [], "total": 0} for _ in range(4)])

    jobs = source(session).fetch(load_search_terms())

    assert jobs == []
    assert [params for _, params in session.calls] == [
        {"categoria": "Informática / TI", "sort": "data_desc", "limit": 50, "offset": 0},
        {"wordkey": "estagio", "sort": "data_desc", "limit": 50, "offset": 0},
        {"cargo": "trainee", "sort": "data_desc", "limit": 50, "offset": 0},
        {"cargo": "aprendiz", "sort": "data_desc", "limit": 50, "offset": 0},
    ]


def test_busca_personalizada_e_inicio_de_pagina_respeitados():
    session = FakeSession({"vagas": [], "total": 0})

    source(session, start_page=2, max_pages_per_term=3).fetch(["estagio ti"])

    assert session.calls[0][1] == {"cargo": "estagio ti", "sort": "data_desc", "limit": 50, "offset": 50}


def test_page_size_permite_teste_curto_sem_buscar_detalhes_em_lote_grande():
    session = FakeSession({"vagas": [], "total": 0})

    source(session, page_size=5, start_page=2).fetch_term("junior")

    assert session.calls[0][1]["limit"] == 5
    assert session.calls[0][1]["offset"] == 5


@pytest.mark.parametrize("payload", [None, {}, [], {"vagas": None}, {"vagas": {}}])
def test_listagem_invalida_e_falha_nao_pagina_vazia(payload):
    collector = source(FakeSession(payload))

    jobs = collector.fetch(["junior"])

    assert jobs == []
    assert "formato esperado" in collector.stats.errors[0]


def test_pagina_vazia_valida_nao_gera_falha():
    collector = source(FakeSession({"vagas": [], "total": 0}))

    jobs = collector.fetch(["junior"])

    assert jobs == []
    assert collector.stats.errors == []


def test_listagem_falha_preserva_detalhes_ja_coletados():
    collector = source(FakeSession({"vagas": [row()], "total": 100}, detail(), None))

    jobs = collector.fetch(["junior"])

    assert len(jobs) == 1
    assert collector.stats.errors
    assert collector.stats.raw_jobs == 1


@pytest.mark.parametrize("response", [None, SimpleNamespace(text="<html>Login</html>"),
                                      detail(description=""), detail("999")])
def test_detalhe_ausente_ou_de_outra_vaga_e_reportado(response):
    collector = source(FakeSession({"vagas": [row()], "total": 1}, response))

    jobs = collector.fetch(["junior"])

    assert jobs == []
    assert collector.stats.errors


def test_datas_invalidas_sao_reportadas_sem_descartar_outros_registros():
    collector = source(FakeSession({"vagas": [row("1", post_date_epoch="ontem"), row()], "total": 2}, detail()))

    jobs = collector.fetch_term("junior")

    assert len(jobs) == 1
    assert "data de publicacao invalida" in collector.stats.errors[0]


def test_data_e_convertida_para_brasil():
    timestamp = int(datetime(2026, 10, 12, 1, tzinfo=timezone.utc).timestamp())
    collector = source(FakeSession({"vagas": [row(post_date_epoch=str(timestamp))], "total": 1}, detail()))

    jobs = collector.fetch_term("junior")

    assert jobs[0].published_date == "2026-10-11"


@pytest.mark.parametrize("shape", ["array", "graph"])
def test_jsonld_aceita_array_e_graph(shape):
    posting = {"@type": "JobPosting", "description": "Requisitos: SQL."}
    data = [posting] if shape == "array" else {"@graph": [posting]}
    response = SimpleNamespace(text=f'<script type="application/ld+json">{json.dumps(data)}</script>')
    collector = source(FakeSession({"vagas": [row()], "total": 1}, response))

    jobs = collector.fetch_term("junior")

    assert jobs[0].description == "Requisitos: SQL."


@pytest.mark.parametrize(
    "title", ["Desenvolvedor Júnior", "DESENVOLVEDOR JUNIOR", "Desenvolvedor  Júnior"]
)
def test_redirect_migrado_preserva_identidade_da_listagem_e_skills(title):
    session = FakeSession({"vagas": [row()], "total": 1}, redirected_detail(title=title))
    collector = source(session)

    jobs = collector.fetch_term("junior")

    assert len(jobs) == 1
    assert jobs[0].external_id == "123"
    assert jobs[0].url == f"{jobbol.SITE_URL}/vaga/123"
    assert jobs[0].title == "Desenvolvedor Júnior"
    assert set(default_extractor().extract(jobs[0].description)) == {"SQL", "Python", "Docker"}
    assert collector.stats.errors == []
    assert session.request_count == 2


@pytest.mark.parametrize(
    "response",
    [
        redirected_detail(page_id="999", final_url=f"{jobbol.SITE_URL}/vaga/145231-desenvolvedor-junior"),
        redirected_detail(final_url="https://outro.example/vaga/145231-desenvolvedor-junior"),
        redirected_detail(final_url="https://candidatos.jobbol.com.br.evil.example/vaga/145231-dev"),
        redirected_detail(final_url="http://candidatos.jobbol.com.br/vaga/145231-dev"),
        redirected_detail(final_url=f"{jobbol.SITE_URL}/outra/145231-dev"),
        redirected_detail(final_url=f"{jobbol.SITE_URL}/vaga/145231"),
        redirected_detail(page_id="145abc"),
        redirected_detail(title="Analista de Suporte Júnior"),
        redirected_detail(title=""),
        redirected_detail(title=None),
        redirected_detail(history=[]),
        redirected_detail(history=[SimpleNamespace(url=f"{jobbol.SITE_URL}/vaga/999")]),
    ],
)
def test_redirect_migrado_rejeita_detalhe_sem_vinculo_com_a_vaga(response):
    collector = source(FakeSession({"vagas": [row()], "total": 1}, response))

    jobs = collector.fetch_term("junior")

    assert jobs == []
    assert collector.stats.errors
    assert response.url in collector.stats.errors[0]


def test_redirect_migrado_reutiliza_detalhe_entre_buscas():
    session = FakeSession(
        {"vagas": [row()], "total": 1}, redirected_detail(), {"vagas": [row()], "total": 1}
    )
    collector = source(session)

    jobs = collector.fetch(["junior", "desenvolvedor"])

    assert [job.external_id for job in jobs] == ["123", "123"]
    assert session.request_count == 3
    assert collector.stats.errors == []


def test_html_sem_jobposting_extrai_secoes_da_vaga_e_preserva_identidade():
    collector = source(FakeSession({"vagas": [row()], "total": 1}, html_detail()))

    jobs = collector.fetch(["junior"])
    job = jobs[0]

    assert len(jobs) == 1
    assert job.external_id == "123"
    assert job.title == "Desenvolvedor Júnior"
    assert job.url == f"{jobbol.SITE_URL}/vaga/123"
    assert job.company == "Empresa do detalhe"
    assert job.location == "São Paulo, SP"
    assert set(default_extractor().extract(job.description)) == {"SQL", "Python", "Docker"}
    assert "Curso de Inglês" in job.description
    assert "A empresa usa Java" not in job.description
    assert "alertas" not in job.description
    assert "Publicidade" not in job.description
    assert "relacionadas" not in job.description
    assert collector.stats.errors == []


def test_html_sem_empresa_usa_o_nome_da_listagem():
    response = html_detail()
    response.text = response.text.replace("Empresa do detalhe", "")
    collector = source(FakeSession({"vagas": [row()], "total": 1}, response))

    jobs = collector.fetch(["junior"])

    assert jobs[0].company == "Acme"
    assert collector.stats.errors == []


def test_html_aceita_requisitos_em_lista():
    response = html_detail()
    response.text = response.text.replace(
        '<p class="fs-6">Conhecimento em Python e Docker.</p>',
        "<ul><li>Conhecimento em Python e Docker.</li></ul>",
    )
    collector = source(FakeSession({"vagas": [row()], "total": 1}, response))

    jobs = collector.fetch(["junior"])

    assert set(default_extractor().extract(jobs[0].description)) == {"SQL", "Python", "Docker"}
    assert collector.stats.errors == []


@pytest.mark.parametrize("replacement", [
    ("pl-manchete-titulo", "outro-titulo"),
    ("Desenvolvedor Júnior</h1>", "Analista de Suporte Júnior</h1>"),
    ('id="vagaContainer"', 'id="outroContainer"'),
    ("jb-vaga-corpo", "outra-secao"),
    ('rel="canonical"', 'rel="alternate"'),
    ("/vaga/145231-desenvolvedor-junior", "/vaga/999-desenvolvedor-junior"),
    ("https://candidatos.jobbol.com.br/vaga/145231", "https://outro.example/vaga/145231"),
])
def test_html_incompleto_ou_divergente_continua_com_falha(replacement):
    response = html_detail()
    response.text = response.text.replace(*replacement)
    collector = source(FakeSession({"vagas": [row()], "total": 1}, response))

    jobs = collector.fetch(["junior"])

    assert jobs == []
    assert collector.stats.errors


def test_html_com_apenas_beneficios_continua_com_falha():
    response = html_detail()
    response.text = response.text.replace("Desenvolver sistemas e consultar SQL.", "")
    response.text = response.text.replace("Conhecimento em Python e Docker.", "")
    collector = source(FakeSession({"vagas": [row()], "total": 1}, response))

    jobs = collector.fetch(["junior"])

    assert jobs == []
    assert collector.stats.errors


@pytest.mark.parametrize("changes", [
    {"history": []},
    {"history": [SimpleNamespace(url=f"{jobbol.SITE_URL}/vaga/999")]},
    {"final_url": "https://outro.example/vaga/145231-desenvolvedor-junior"},
])
def test_html_rejeita_redirecionamento_sem_vinculo_com_a_listagem(changes):
    collector = source(FakeSession({"vagas": [row()], "total": 1}, html_detail(**changes)))

    jobs = collector.fetch(["junior"])

    assert jobs == []
    assert collector.stats.errors


def test_html_reutiliza_detalhe_entre_buscas():
    session = FakeSession({"vagas": [row()], "total": 1}, html_detail(), {"vagas": [row()], "total": 1})
    collector = source(session)

    jobs = collector.fetch(["junior", "desenvolvedor"])

    assert [job.external_id for job in jobs] == ["123", "123"]
    assert session.request_count == 3
    assert collector.stats.errors == []


def test_jsonld_tem_prioridade_sobre_html_do_mesmo_detalhe():
    response = html_detail()
    response.text += detail(description="Requisitos: Java.").text
    collector = source(FakeSession({"vagas": [row()], "total": 1}, response))

    jobs = collector.fetch(["junior"])

    assert jobs[0].company == "Acme"
    assert jobs[0].description == "Requisitos: Java."
    assert collector.stats.errors == []


@pytest.mark.parametrize("detail_factory", [redirected_detail, html_detail])
@pytest.mark.parametrize("final_host", [jobbol.SITE_URL, "https://www.jobbol.com.br"])
@pytest.mark.parametrize("link", [
    "/vaga/145231-desenvolvedor-junior",
    f"{jobbol.SITE_URL}/vaga/145231-desenvolvedor-junior",
    "https://www.jobbol.com.br/vaga/145231-desenvolvedor-junior",
])
def test_usa_link_migrado_da_listagem_com_id_estavel_e_cidade(detail_factory, final_host, link):
    listing = row(link=link, id_vaga="145231", id_cidade="4006")
    path = "/vaga/145231-desenvolvedor-junior"
    response = detail_factory(history=[], final_url=f"{final_host}{path}?cidade=4006")
    response.text = response.text.replace(jobbol.SITE_URL, final_host)
    session = FakeSession({"vagas": [listing], "total": 1}, response)
    collector = source(session)

    jobs = collector.fetch(["junior"])

    requested_link = f"{jobbol.SITE_URL}{link}" if link.startswith("/") else link
    assert session.calls[1][0] == f"{requested_link}?cidade=4006"
    assert jobs[0].external_id == "123"
    assert jobs[0].url == session.calls[1][0]
    assert set(default_extractor().extract(jobs[0].description)) == {"SQL", "Python", "Docker"}
    assert collector.stats.errors == []


def test_link_da_listagem_e_reutilizado_entre_buscas():
    listing = row(link="/vaga/145231-desenvolvedor-junior?cidade=4006", id_vaga=145231)
    session = FakeSession(
        {"vagas": [listing], "total": 1}, redirected_detail(history=[]),
        {"vagas": [listing], "total": 1},
    )
    collector = source(session)

    jobs = collector.fetch(["junior", "desenvolvedor"])

    assert [job.external_id for job in jobs] == ["123", "123"]
    assert session.request_count == 3
    assert collector.stats.errors == []


@pytest.mark.parametrize("link, page_id", [
    ("https://outro.example/vaga/145231-desenvolvedor-junior", "145231"),
    ("//outro.example/vaga/145231-desenvolvedor-junior", "145231"),
    ("http://candidatos.jobbol.com.br/vaga/145231-desenvolvedor-junior", "145231"),
    ("/vaga/999-desenvolvedor-junior", "145231"),
    ("/vaga/145231-desenvolvedor-junior", None),
    ("/outra/145231-desenvolvedor-junior", "145231"),
    ("/vaga/999", "999"),
    (123, "145231"),
])
def test_link_invalido_da_listagem_e_reportado_antes_da_chamada(link, page_id):
    session = FakeSession({"vagas": [row(link=link, id_vaga=page_id)], "total": 1})
    collector = source(session)

    jobs = collector.fetch(["junior"])

    assert jobs == []
    assert session.request_count == 1
    assert collector.stats.errors


@pytest.mark.parametrize("response", [
    redirected_detail(page_id="999", history=[]),
    redirected_detail(title="Outra vaga", history=[]),
    redirected_detail(final_url="https://outro.example/vaga/145231-desenvolvedor-junior", history=[]),
    redirected_detail(final_url="https://www.jobbol.com.br/vaga/999-outra-vaga", page_id="999", history=[]),
    redirected_detail(identifier={"value": "123"}, history=[]),
])
def test_link_da_listagem_rejeita_detalhe_de_outra_identidade(response):
    listing = row(link="/vaga/145231-desenvolvedor-junior", id_vaga="145231")
    collector = source(FakeSession({"vagas": [listing], "total": 1}, response))

    jobs = collector.fetch(["junior"])

    assert jobs == []
    assert collector.stats.errors


def test_404_no_link_da_listagem_continua_com_erro_sem_repeticao():
    listing = row(link="/vaga/145231-desenvolvedor-junior", id_vaga="145231")
    payload = {"vagas": [listing], "total": 1}
    session = FakeSession(payload, None, payload)
    collector = source(session)

    jobs = collector.fetch(["junior", "desenvolvedor"])

    assert jobs == []
    assert session.request_count == 3
    assert len(collector.stats.errors) == 1
    assert "http=404" in collector.stats.errors[0]
