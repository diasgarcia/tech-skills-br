import pytest

from scraper.models import Job, normalize, strip_html


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Desenvolvedor Júnior (Back-End)", "desenvolvedor junior back end"),
        ("CI/CD", "ci cd"),
        (None, ""),
    ],
)
def test_normalize_remove_acentos_e_pontuacao(raw, expected):
    result = normalize(raw)

    assert result == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("<p>Vaga  J&uacute;nior</p>", "Vaga Júnior"),
        ("", ""),
        (None, ""),
    ],
)
def test_strip_html_remove_tags_e_entidades(raw, expected):
    result = strip_html(raw)

    assert result == expected


def test_job_limpa_titulo_e_descricao():
    data = {
        "source": "t",
        "external_id": "1",
        "title": "  Dev   Júnior  ",
        "description": "<b>Java</b>&nbsp;e Python",
    }

    job = Job(**data)

    assert job.title == "Dev Júnior"
    assert "<b>" not in job.description
    assert "Java" in job.description


def test_fingerprint_ignora_caixa_e_acento():
    a = Job(source="gupy", external_id="1", title="Desenvolvedor Júnior", company="ACME")
    b = Job(source="vagas", external_id="9", title="desenvolvedor junior", company="acme")

    result = (a.fingerprint == b.fingerprint, a.source_key != b.source_key)

    assert result == (True, True)


def test_to_row_trunca_descricao():
    job = Job(source="t", external_id="1", title="Dev", description="x" * 1000)

    row = job.to_row(description_chars=100)

    assert len(row["description"]) == 100


def test_to_row_mantem_descricao_completa_por_padrao():
    job = Job(source="t", external_id="1", title="Dev", description="x" * 1000)

    row = job.to_row()

    assert len(row["description"]) == 1000
