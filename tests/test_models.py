from scraper.models import Job, normalize, strip_html


def test_normalize_remove_acentos_e_pontuacao():
    assert normalize("Desenvolvedor Júnior (Back-End)") == "desenvolvedor junior back end"
    assert normalize("CI/CD") == "ci cd"
    assert normalize(None) == ""


def test_strip_html_remove_tags_e_entidades():
    assert strip_html("<p>Vaga  J&uacute;nior</p>") == "Vaga Júnior"
    assert strip_html("") == ""
    assert strip_html(None) == ""


def test_job_limpa_titulo_e_descricao():
    job = Job(source="t", external_id="1", title="  Dev   Júnior  ",
              description="<b>Java</b>&nbsp;e Python")
    assert job.title == "Dev Júnior"
    assert "<b>" not in job.description
    assert "Java" in job.description


def test_fingerprint_ignora_caixa_e_acento():
    a = Job(source="gupy", external_id="1", title="Desenvolvedor Júnior", company="ACME")
    b = Job(source="vagas", external_id="9", title="desenvolvedor junior", company="acme")
    assert a.fingerprint == b.fingerprint
    assert a.source_key != b.source_key


def test_to_row_trunca_descricao():
    job = Job(source="t", external_id="1", title="Dev", description="x" * 1000)
    assert len(job.to_row(description_chars=100)["description"]) == 100
