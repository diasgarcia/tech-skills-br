"""Testes do classificador geografico (geo.py)."""

import pytest

from scraper.geo import (
    GeoClassifier,
    attach_geo_info,
    default_geo_classifier,
    get_all_hubs,
    resolve_hubs,
)
from scraper.models import Job


@pytest.fixture
def classifier():
    return default_geo_classifier()


@pytest.mark.parametrize(
    "loc,modalidade,esperado_polo,esperada_regiao",
    [
        ("São Paulo, SP", "Presencial", "São Paulo", "Sudeste"),
        ("Sao Paulo, Brazil", "Híbrido", "São Paulo", "Sudeste"),
        ("Campinas - SP", "Presencial", "Campinas", "Sudeste"),
        ("Rio de Janeiro / RJ", "Presencial", "Rio de Janeiro", "Sudeste"),
        ("Belo Horizonte, MG", "Presencial", "Belo Horizonte", "Sudeste"),
        ("Curitiba, PR", "Presencial", "Curitiba", "Sul"),
        ("Florianópolis, Santa Catarina", "Presencial", "Florianópolis", "Sul"),
        ("Porto Alegre / RS", "Presencial", "Porto Alegre", "Sul"),
        ("Recife, Pernambuco", "Presencial", "Recife", "Nordeste"),
        ("Porto Digital - Recife", "Presencial", "Recife", "Nordeste"),
        ("Salvador, BA", "Presencial", "Salvador", "Nordeste"),
        ("Fortaleza, CE", "Presencial", "Fortaleza", "Nordeste"),
        ("Brasília, DF", "Presencial", "Brasília", "Centro-Oeste"),
        ("Goiânia, GO", "Presencial", "Goiânia", "Centro-Oeste"),
        ("Manaus, AM", "Presencial", "Manaus", "Norte"),
        ("Belém, PA", "Presencial", "Belém", "Norte"),
        # Capitais e polos expandidos

        ("Vitória, ES", "Presencial", "Vitória", "Sudeste"),
        ("Natal, RN", "Presencial", "Natal", "Nordeste"),
        ("Cuiabá, MT", "Presencial", "Cuiabá", "Centro-Oeste"),
        # UFs quando a vaga informa apenas o estado sem cidade mapeada
        ("ES", "Presencial", "Estado/ES", "Sudeste"),
        ("RN", "Presencial", "Estado/RN", "Nordeste"),
        ("MT", "Presencial", "Estado/MT", "Centro-Oeste"),

        # Vagas remotas
        ("", "Remoto", "Remoto", "Remoto Nacional"),
        ("Brasil", "Remoto", "Remoto", "Remoto Nacional"),
        ("Remoto", "Remoto", "Remoto", "Remoto Nacional"),
        # Nao informado
        ("", "Presencial", "Não informado", "Não informado"),
    ],
)
def test_geo_classify_mapeia_corretamente(
    classifier, loc, modalidade, esperado_polo, esperada_regiao
):
    polo, regiao = classifier.classify(loc, modalidade)
    assert polo == esperado_polo
    assert regiao == esperada_regiao


def test_attach_geo_info(classifier):
    jobs = [
        Job(
            source="gupy",
            external_id="1",
            title="Dev",
            location="Recife, PE",
            workplace_type="Presencial",
        ),
        Job(
            source="gupy",
            external_id="2",
            title="Dev",
            location="Curitiba, PR",
            workplace_type="Híbrido",
        ),
        Job(
            source="gupy",
            external_id="3",
            title="Dev",
            location="",
            workplace_type="Remoto",
        ),
    ]
    attach_geo_info(jobs, classifier)
    assert jobs[0].polo == "Recife"
    assert jobs[0].regiao == "Nordeste"
    assert jobs[1].polo == "Curitiba"
    assert jobs[1].regiao == "Sul"
    assert jobs[2].polo == "Remoto"
    assert jobs[2].regiao == "Remoto Nacional"


def test_get_all_hubs():
    hubs = get_all_hubs()
    assert len(hubs) >= 14
    nomes = [h["nome"] for h in hubs]
    assert "São Paulo" in nomes
    assert "Recife" in nomes
    assert "Florianópolis" in nomes
    assert "Manaus" in nomes
    assert "Brasília" in nomes


def test_resolve_hubs_todos():
    hubs = resolve_hubs(["todos"])
    assert len(hubs) == len(get_all_hubs())


def test_resolve_hubs_por_regiao():
    nordeste_hubs = resolve_hubs(["nordeste"])
    assert len(nordeste_hubs) >= 3
    for h in nordeste_hubs:
        assert h["regiao"] == "Nordeste"


def test_resolve_hubs_por_cidade():
    recife = resolve_hubs(["Recife"])
    assert len(recife) == 1
    assert recife[0]["nome"] == "Recife"
