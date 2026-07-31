import pytest

from scraper.export import build_workplace_ranking
from scraper.models import Job, normalize_workplace
from scraper.sources.vagas_com import VagasComSource


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("remote", "Remoto"),
        ("hybrid", "Híbrido"),
        ("on-site", "Presencial"),
        ("Remoto", "Remoto"),
        ("100% Home Office", "Remoto"),
        ("Híbrido", "Híbrido"),
        ("presencial", "Presencial"),
        ("", "Não informado"),
        (None, "Não informado"),
        ("qualquer coisa", "Não informado"),
    ],
)
def test_normalize_workplace(raw, expected):
    assert normalize_workplace(raw) == expected


def test_vagas_afirma_remoto_e_nao_adivinha_o_resto():
    # O card do Vagas.com nao distingue hibrido de presencial: so o remoto
    # aparece explicitamente ("100% Home Office").
    assert VagasComSource._workplace("100% Home Office") == "Remoto"
    assert VagasComSource._workplace("Rio de Janeiro / RJ") == "Não informado"
    assert VagasComSource._workplace("") == "Não informado"


def test_ranking_respeita_a_ordem_remoto_hibrido_presencial():
    jobs = [
        Job(source="t", external_id="1", title="a", workplace_type="Presencial"),
        Job(source="t", external_id="2", title="b", workplace_type="Remoto"),
        Job(source="t", external_id="3", title="c", workplace_type="Presencial"),
        Job(source="t", external_id="4", title="d", workplace_type="Híbrido"),
    ]
    ranking = build_workplace_ranking(jobs)
    assert [r["modalidade"] for r in ranking] == ["Remoto", "Híbrido", "Presencial"]
    assert ranking[2]["vagas"] == 2
    assert ranking[2]["percentual"] == 50.0


def test_ranking_omite_modalidade_sem_vagas():
    jobs = [Job(source="t", external_id="1", title="a", workplace_type="Remoto")]
    assert [r["modalidade"] for r in build_workplace_ranking(jobs)] == ["Remoto"]


def test_ranking_trata_campo_vazio_como_nao_informado():
    jobs = [Job(source="t", external_id="1", title="a", workplace_type="")]
    ranking = build_workplace_ranking(jobs)
    assert ranking[0]["modalidade"] == "Não informado"


def test_ranking_lista_vazia():
    assert build_workplace_ranking([]) == []
