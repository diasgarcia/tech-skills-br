import pytest

from scraper.models import Job, normalize, normalize_location, strip_html


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
        (None, ""), ("", ""), ("Não informado", "Não informado"),
        ("Ourinhos, São Paulo", "Ourinhos, SP"),
        ("Ourinhos, SP", "Ourinhos, SP"),
        ("Ourinhos / sp", "Ourinhos, SP"),
        ("Ourinhos-SP", "Ourinhos, SP"),
        ("Ourinhos, Brasil", "Ourinhos, Brasil"),
        ("São Paulo, São Paulo", "São Paulo, SP"),
        ("São Paulo, Brasil", "São Paulo, Brasil"),
        ("Rio de Janeiro, Rio de Janeiro, Brazil", "Rio de Janeiro, RJ"),
        ("Belo Horizonte, Minas Gerais", "Belo Horizonte, MG"),
        ("Florianópolis / Santa Catarina", "Florianópolis, SC"),
        ("Campo Grande - Mato Grosso do Sul", "Campo Grande, MS"),
        ("Brasília, Distrito Federal", "Brasília, DF"),
        ("Mogi-Mirim - SP, Brasil", "Mogi-Mirim, SP"),
        ("Embu-Guaçu, São Paulo", "Embu-Guaçu, SP"),
        ("Praia Grande / SP e Região", "Praia Grande, SP e Região"),
        ("São Paulo e Região", "São Paulo e Região"),
        ("São Paulo", "São Paulo"), ("Santa Maria", "Santa Maria"),
        ("Adamantina", "Adamantina"),
        ("Adamantina, Brasil", "Adamantina, Brasil"),
        ("Minas Gerais, Brasil", "Minas Gerais, Brasil"),
        ("Porto, Portugal", "Porto, Portugal"),
        ("Lisboa, Lisboa, Portugal", "Lisboa, Lisboa, Portugal"),
        ("Nacional", "Brasil"), ("Brazil", "Brasil"),
        ("Todo Brasil", "Brasil"), ("Todo o Brasil", "Brasil"),
        ("Remoto", "Remoto"), ("100% Remoto", "Remoto"),
        ("remoto 100%", "Remoto"), ("100% Home Office", "Remoto"),
        ("Totalmente remota", "Remoto"), ("remoto, remoto", "Remoto"),
        ("  Campinas  -  sp , Brasil ", "Campinas, SP"),
    ],
)
def test_normalize_location_padroniza_sem_adivinhar_estado(raw, expected):
    result = normalize_location(raw)

    assert result == expected
    assert normalize_location(result) == result


def test_job_padroniza_local_sem_mudar_modalidade_declarada():
    job = Job(source="t", external_id="1", title="Dev", location="100% Home Office",
              workplace_type="Híbrido", workplace_declared=True)

    assert job.location == "Remoto"
    assert job.workplace_type == "Híbrido"
    assert job.workplace_declared is True


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


def test_source_key_combina_fonte_e_id_externo():
    job = Job(source="gupy", external_id="1", title="Desenvolvedor Júnior")

    result = job.source_key

    assert result == "gupy:1"


def test_to_row_trunca_descricao():
    job = Job(source="t", external_id="1", title="Dev", description="x" * 1000)

    row = job.to_row(description_chars=100)

    assert len(row["description"]) == 100


def test_to_row_mantem_descricao_completa_por_padrao():
    job = Job(source="t", external_id="1", title="Dev", description="x" * 1000)

    row = job.to_row()

    assert len(row["description"]) == 1000
