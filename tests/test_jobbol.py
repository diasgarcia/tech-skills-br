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

    def get(self, url, params=None):
        self.calls.append((url, dict(params) if params else None))
        self.request_count += 1
        return next(self.responses, None)

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
