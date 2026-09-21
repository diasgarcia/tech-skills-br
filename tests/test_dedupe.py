import pytest

from scraper.dedupe import deduplicate, identidade_no_link
from scraper.models import Job


def test_remove_mesma_vaga_do_mesmo_portal():
    jobs = [
        Job(source="gupy", external_id="1", title="Dev Júnior", company="ACME"),
        Job(source="gupy", external_id="1", title="Dev Júnior", company="ACME"),
    ]

    unique, removed = deduplicate(jobs)

    assert len(unique) == 1
    assert removed == 1


def test_mantem_a_versao_com_descricao_mais_longa():
    jobs = [
        Job(source="gupy", external_id="1", title="Dev Júnior",
            company="ACME", description="curta"),
        Job(source="gupy", external_id="1", title="Dev Júnior",
            company="ACME", description="uma descricao bem mais longa da vaga"),
    ]

    unique, _ = deduplicate(jobs)

    assert unique[0].description == "uma descricao bem mais longa da vaga"


def test_cruza_portais_por_titulo_e_empresa():
    jobs = [
        Job(source="gupy", external_id="1", title="Desenvolvedor Júnior",
            company="ACME", location="São Paulo, SP", published_date="2026-09-10"),
        Job(source="vagas", external_id="99", title="desenvolvedor junior",
            company="Acme", location="São Paulo / SP", published_date="12/09/2026"),
    ]

    unique, removed = deduplicate(jobs)

    assert len(unique) == 1
    assert removed == 1


def test_nao_cruza_vagas_de_empresas_diferentes():
    jobs = [
        Job(source="gupy", external_id="1", title="Desenvolvedor Júnior", company="ACME"),
        Job(source="gupy", external_id="2", title="Desenvolvedor Júnior", company="Globex"),
    ]

    unique, removed = deduplicate(jobs)

    assert len(unique) == 2
    assert removed == 0


def test_vagas_sem_empresa_nao_sao_agrupadas():
    jobs = [
        Job(source="gupy", external_id="1", title="Desenvolvedor Júnior", company=""),
        Job(source="gupy", external_id="2", title="Desenvolvedor Júnior", company=""),
    ]

    unique, removed = deduplicate(jobs)

    assert len(unique) == 2
    assert removed == 0


def test_funde_mesma_vaga_com_nome_de_empresa_diferente():
    """Casos reais: a Gupy escreve o nome completo, o LinkedIn o curto."""
    jobs = [
        Job(source="gupy", external_id="1", title="Desenvolvedor Fullstack Jr",
            company="Minsait an Indra Company", description="descricao longa",
            location="Brasília, Distrito Federal", published_date="2026-09-10"),
        Job(source="linkedin", external_id="9", title="Desenvolvedor Fullstack Jr",
            company="Minsait", location="Brasília, DF", published_date="2026-09-11"),
    ]

    unique, removed = deduplicate(jobs)

    assert len(unique) == 1 and removed == 1
    assert unique[0].description == "descricao longa"


def test_funde_quando_o_nome_curto_esta_contido_no_longo():
    jobs = [
        Job(source="gupy", external_id="1", title="Analista de Sistemas Júnior",
            company="Centro Universitário FEI", location="São Bernardo do Campo, SP",
            published_date="2026-09-10"),
        Job(source="linkedin", external_id="9", title="Analista de Sistemas Júnior",
            company="FEI", location="São Bernardo do Campo, São Paulo",
            published_date="2026-09-12"),
    ]

    unique, _ = deduplicate(jobs)

    assert len(unique) == 1


def test_titulo_generico_em_empresas_diferentes_nao_funde():
    """'Analista de Sistemas Júnior' existe em dezenas de empresas."""
    jobs = [
        Job(source="gupy", external_id="1", title="Analista de Sistemas Júnior",
            company="Techne"),
        Job(source="linkedin", external_id="9", title="Analista de Sistemas Júnior",
            company="Globoaves"),
    ]

    unique, removed = deduplicate(jobs)

    assert len(unique) == 2 and removed == 0


def test_confidencial_nao_identifica_empresa():
    """Duas vagas confidenciais com o mesmo título não são a mesma vaga."""
    jobs = [
        Job(source="gupy", external_id="1", title="Analista Júnior de TI",
            company="Confidencial"),
        Job(source="vagas", external_id="9", title="Analista Júnior de TI",
            company="Confidencial"),
    ]

    unique, _ = deduplicate(jobs)

    assert len(unique) == 2


def test_sufixo_societario_nao_impede_a_fusao():
    jobs = [
        Job(source="gupy", external_id="1", title="Dev Júnior", company="ACME",
            location="Recife, PE", published_date="2026-09-10"),
        Job(source="linkedin", external_id="9", title="Dev Júnior",
            company="ACME Soluções em Tecnologia LTDA", location="Recife, Pernambuco",
            published_date="2026-09-11"),
    ]

    unique, _ = deduplicate(jobs)

    assert len(unique) == 1


def test_titulos_diferentes_da_mesma_empresa_nao_fundem():
    """Duas vagas distintas na mesma empresa continuam sendo duas."""
    jobs = [
        Job(source="gupy", external_id="1", title="Desenvolvedor Júnior",
            company="ACME"),
        Job(source="linkedin", external_id="9", title="Analista de Testes Júnior",
            company="ACME"),
    ]

    unique, _ = deduplicate(jobs)

    assert len(unique) == 2


def test_lista_vazia():
    unique, removed = deduplicate([])

    assert unique == []
    assert removed == 0


@pytest.mark.parametrize(
    "url,esperado",
    [
        (
            "https://br.linkedin.com/jobs/view/dev-jr-at-acme-4464615185",
            "linkedin.com:4464615185",
        ),
        (
            "https://empresa.gupy.io/job/eyJqb2JJZCI6MTIwNTk3Mzh9=",
            "gupy.io:eyJqb2JJZCI6MTIwNTk3Mzh9=",
        ),
        (
            "https://www.infojobs.com.br/vaga-de-auxiliar__12005412.aspx",
            "infojobs.com.br:12005412",
        ),
        (
            "https://trampos.co/oportunidades/774266-estagiario-a-em-qa",
            "trampos.co:774266",
        ),
    ],
)
def test_identidade_no_link_extrai_id_confiavel(url, esperado):
    result = identidade_no_link(url)

    assert result == esperado


@pytest.mark.parametrize(
    "url",
    [
        "https://www.geekhunter.com/pt/acme/jobs/desenvolvedor-junior-1",
        "https://empresa.gupy.io/",
        "#",
        "",
    ],
)
def test_identidade_no_link_ignora_slug_sem_id_confiavel(url):
    result = identidade_no_link(url)

    assert result == ""


def test_id_longo_do_linkedin_vence_numero_no_inicio_do_titulo():
    url = (
        "https://br.linkedin.com/jobs/view/"
        "10274-analyst-analista-de-dados-junior-at-provider-it-4454450486"
    )

    result = identidade_no_link(url)

    assert result == "linkedin.com:4454450486"


def test_id_no_link_funde_mesmo_com_url_texto_e_fonte_diferentes():
    jobs = [
        Job(
            source="linkedin",
            external_id="4464615185",
            title="Desenvolvedor Júnior",
            company="ACME",
            url="https://br.linkedin.com/jobs/view/dev-jr-at-acme-4464615185",
        ),
        Job(
            source="agregador",
            external_id="9",
            title="Programa de Tecnologia",
            company="Empresa confidencial",
            url="https://www.linkedin.com/jobs/view/4464615185/?tracking=abc",
        ),
    ]

    unique, removed = deduplicate(jobs)

    assert len(unique) == 1
    assert removed == 1


def test_marca_de_duas_letras_funde_com_contexto_compativel():
    jobs = [
        Job(
            source="linkedin",
            external_id="1",
            title="Desenvolvedor Júnior",
            company="MV",
            location="Recife, PE",
            published_date="2026-09-18",
        ),
        Job(
            source="geekhunter",
            external_id="2",
            title="Desenvolvedor Júnior",
            company="MV Saúde Digital",
            location="Recife, Pernambuco",
            published_date="2026-09-20",
        ),
    ]

    unique, removed = deduplicate(jobs)

    assert len(unique) == 1
    assert removed == 1


def test_mesma_fonte_com_ids_diferentes_nao_funde_por_texto():
    jobs = [
        Job(source="linkedin", external_id="1", title="Dev Júnior", company="EY",
            location="São Paulo, SP", published_date="2026-09-12"),
        Job(source="linkedin", external_id="2", title="Dev Júnior", company="EY",
            location="São Paulo, SP", published_date="2026-09-12"),
    ]

    unique, removed = deduplicate(jobs)

    assert len(unique) == 2
    assert removed == 0


def test_mesmo_titulo_e_empresa_em_cidades_diferentes_nao_funde():
    jobs = [
        Job(source="linkedin", external_id="1", title="Engenheiro de Dados Júnior",
            company="EY", location="São Paulo, SP", published_date="2026-09-12"),
        Job(source="vagas", external_id="2", title="Engenheiro de Dados Júnior",
            company="EY", location="Recife, PE", published_date="2026-09-12"),
    ]

    unique, removed = deduplicate(jobs)

    assert len(unique) == 2
    assert removed == 0


def test_mesma_cidade_em_estados_diferentes_nao_funde():
    jobs = [
        Job(source="gupy", external_id="1", title="Dev Júnior", company="FI Group",
            location="Palmas, TO", published_date="2026-09-10"),
        Job(source="linkedin", external_id="2", title="Dev Júnior", company="FI",
            location="Palmas, PR", published_date="2026-09-11"),
    ]

    unique, removed = deduplicate(jobs)

    assert len(unique) == 2
    assert removed == 0


def test_sigla_generica_de_duas_letras_nao_identifica_empresa():
    jobs = [
        Job(source="gupy", external_id="1", title="Analista de Suporte Júnior",
            company="Consultoria em TI", location="São Paulo, SP",
            published_date="2026-09-10"),
        Job(source="linkedin", external_id="2", title="Analista de Suporte Júnior",
            company="Soluções em TI", location="São Paulo, SP",
            published_date="2026-09-11"),
    ]

    unique, removed = deduplicate(jobs)

    assert len(unique) == 2
    assert removed == 0


def test_publicacoes_com_mais_de_sete_dias_nao_fundem():
    jobs = [
        Job(source="gupy", external_id="1", title="Dev Júnior", company="FI Group",
            location="São Paulo, SP", published_date="2026-09-01"),
        Job(source="linkedin", external_id="2", title="Dev Júnior", company="FI",
            location="São Paulo, SP", published_date="2026-09-09"),
    ]

    unique, removed = deduplicate(jobs)

    assert len(unique) == 2
    assert removed == 0


@pytest.mark.parametrize("campo_ausente", ["location", "published_date"])
def test_contexto_incompleto_nao_funde_por_texto(campo_ausente):
    valores = {
        "location": "São Paulo, SP",
        "published_date": "2026-09-10",
    }
    incompleto = valores | {campo_ausente: ""}
    jobs = [
        Job(source="gupy", external_id="1", title="Dev Júnior", company="FI Group",
            **valores),
        Job(source="linkedin", external_id="2", title="Dev Júnior", company="FI",
            **incompleto),
    ]

    unique, removed = deduplicate(jobs)

    assert len(unique) == 2
    assert removed == 0
