"""Testes dos parsers, usando respostas reais capturadas dos portais (offline)."""

import pytest

from scraper.config import Settings
from scraper.sources.geekhunter import GeekHunterSource
from scraper.sources.gupy import GupySource
from scraper.sources.infojobs import FILTROS_NIVEL_ENTRADA as FILTROS_INFOJOBS, InfoJobsSource
from scraper.sources.linkedin import GEO_ID_BRASIL, LinkedInSource
from scraper.sources.solides import FILTROS_NIVEL_ENTRADA as FILTROS_SOLIDES, SolidesSource
from scraper.sources.trampos import TramposSource
from scraper.sources.vagas_com import VagasComSource, slugify_term


# Recorte real da resposta de
# GET https://employability-portal.gupy.io/api/v1/jobs?jobName=desenvolvedor+junior
GUPY_JOB = {
    "id": 11617525,
    "companyId": 551,
    "name": "Desenvolvedor de Sistema Junior",
    "description": "<p>Buscamos um(a) Desenvolvedor(a) Full Stack J&uacute;nior "
                   "para atuar com Java no back-end.</p>",
    "careerPageId": 166261,
    "careerPageName": "Minsait",
    "careerPageUrl": "https://minsait.gupy.io/",
    "type": "vacancy_type_effective",
    "publishedDate": "2026-07-31T14:00:13.962Z",
    "applicationDeadline": "2026-08-14",
    "isRemoteWork": False,
    "city": "São Paulo",
    "state": "São Paulo",
    "country": "Brasil",
    "jobUrl": "https://minsait.gupy.io/job/abc123",
    "workplaceType": "hybrid",
    "disabilities": False,
    "skills": [],
}

# Recorte real de https://www.vagas.com.br/vagas-de-desenvolvedor-junior
VAGAS_HTML = """
<ul>
<li class="vaga odd ">
  <header class="clearfix">
    <div class="informacoes-header">
      <h2 class="cargo">
        <a class="link-detalhes-vaga" data-id-vaga="2824782"
           title="Desenvolvedor de Software Jr" id="v2824782"
           href="/vagas/v2824782/desenvolvedor-de-software-jr">
            <mark>Desenvolvedor</mark> de Software Jr
        </a>
      </h2>
      <span class="emprVaga"> HStern </span>
      <div class="nivelQtdVagas"><span class="nivelVaga">Júnior/Trainee</span></div>
    </div>
  </header>
  <div class="detalhes"><p>Descrição: <mark>Desenvolvedor</mark> Júnior de Software</p></div>
  <footer>
    <div class="vaga-local"><i class="bx bx-map"></i> Rio de Janeiro / RJ </div>
    <span class="data-publicacao"><i class="bx bx-time-five"></i>09/07/2026</span>
  </footer>
</li>
</ul>
"""


def _source(cls):
    return cls(session=None, settings=Settings())


def test_gupy_parse_mapeia_campos():
    job = _source(GupySource)._parse(GUPY_JOB, "desenvolvedor junior")
    assert job is not None
    assert job.source == "gupy"
    assert job.external_id == "11617525"
    assert job.title == "Desenvolvedor de Sistema Junior"
    assert job.company == "Minsait"
    assert job.url == "https://minsait.gupy.io/job/abc123"
    assert job.location == "São Paulo, São Paulo"
    assert job.workplace_type == "Híbrido"
    assert job.published_date == "2026-07-31"
    assert job.search_term == "desenvolvedor junior"


def test_gupy_parse_limpa_html_da_descricao():
    job = _source(GupySource)._parse(GUPY_JOB, "x")
    assert "<p>" not in job.description
    assert "Júnior" in job.description


def test_gupy_parse_ignora_registro_incompleto():
    assert _source(GupySource)._parse({"id": None, "name": ""}, "x") is None
    assert _source(GupySource)._parse({"id": 1}, "x") is None


def test_gupy_usa_country_quando_nao_ha_cidade():
    raw = dict(GUPY_JOB, city="", state="")
    assert _source(GupySource)._parse(raw, "x").location == "Brasil"


def test_vagas_parse_page():
    jobs = _source(VagasComSource)._parse_page(VAGAS_HTML, "desenvolvedor junior")
    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "vagas"
    assert job.external_id == "2824782"
    assert job.title == "Desenvolvedor de Software Jr"
    assert job.company == "HStern"
    assert job.url == "https://www.vagas.com.br/vagas/v2824782/desenvolvedor-de-software-jr"
    assert job.location == "Rio de Janeiro / RJ"
    assert job.published_date == "09/07/2026"
    # "Júnior/Trainee" (span.nivelVaga) e senioridade, nao modalidade de trabalho.
    assert job.workplace_type == "Não informado"


def test_vagas_parse_page_detecta_home_office():
    html = VAGAS_HTML.replace("Rio de Janeiro / RJ", "100% Home Office")
    job = _source(VagasComSource)._parse_page(html, "x")[0]
    assert job.workplace_type == "Remoto"
    assert job.location == "100% Home Office"


def test_vagas_parse_page_vazia():
    assert _source(VagasComSource)._parse_page("<html><body></body></html>", "x") == []


def test_slugify_term():
    assert slugify_term("desenvolvedor júnior") == "desenvolvedor-junior"
    assert slugify_term("Estágio  em TI") == "estagio-em-ti"


# Recorte real de GET https://trampos.co/api/v2/opportunities?tr=desenvolvedor&page=1
TRAMPOS_JSON = {
    "id": 773915,
    "name": "Desenvolvedor(a) .Net C#",
    "type_name": "Emprego",
    "type_slug": "emprego",
    "category_name": "Tecnologia da Informação",
    "category_slug": "ti",
    "home_office": None,
    "hybrid": True,
    "salary": "NÃO DIVULGADA",
    "published_at": "2026-08-02T12:00:07.000-03:00",
    "custom_company_name": None,
    "company": {
        "id": 725735,
        "name": "Artium Soluções",
        "slug": "artium-solucoes",
        "description": "Somos uma empresa de tecnologia da inovação.",
    },
    "email_share_url":
        "https://trampos.co/oportunidades/773915-desenvolvedor-a-net-c/share/email",
}


def test_trampos_parse_mapeia_campos():
    job = _source(TramposSource)._parse(TRAMPOS_JSON, "desenvolvedor")
    assert job is not None
    assert job.source == "trampos"
    assert job.external_id == "773915"
    assert job.title == "Desenvolvedor(a) .Net C#"
    assert job.company == "Artium Soluções"
    assert job.published_date == "2026-08-02"
    assert job.search_term == "desenvolvedor"


def test_trampos_url_sai_do_link_de_compartilhamento():
    # A API não devolve a URL da vaga; ela está dentro das de compartilhamento.
    job = _source(TramposSource)._parse(TRAMPOS_JSON, "x")
    assert job.url == "https://trampos.co/oportunidades/773915-desenvolvedor-a-net-c"


@pytest.mark.parametrize(
    "flags,esperado",
    [
        ({"home_office": True, "hybrid": False}, "Remoto"),
        ({"home_office": True, "hybrid": True}, "Remoto"),
        ({"home_office": None, "hybrid": True}, "Híbrido"),
        ({"home_office": False, "hybrid": False}, "Presencial"),
        ({}, "Presencial"),
    ],
)
def test_trampos_modalidade(flags, esperado):
    # `hybrid` vem sempre; `home_office` às vezes vem nulo.
    assert TramposSource._modalidade(flags) == esperado


def test_trampos_estagio_vem_do_tipo_nativo():
    raw = dict(TRAMPOS_JSON, type_slug="estagio", type_name="Estágio")
    assert _source(TramposSource)._parse(raw, "x").seniority == "Estágio"


def test_trampos_emprego_deixa_senioridade_para_o_regex():
    assert _source(TramposSource)._parse(TRAMPOS_JSON, "x").seniority == ""


def test_trampos_descricao_usa_a_categoria_nativa():
    job = _source(TramposSource)._parse(TRAMPOS_JSON, "x")
    assert "Tecnologia da Informação" in job.description


def test_trampos_descricao_ignora_o_texto_da_empresa():
    """company.description fala da EMPRESA -- usá-la classificaria errado."""
    job = _source(TramposSource)._parse(TRAMPOS_JSON, "x")
    assert "inovação" not in job.description


def test_trampos_salario_nao_divulgado_fica_de_fora():
    job = _source(TramposSource)._parse(TRAMPOS_JSON, "x")
    assert "Salário" not in job.description
    com_salario = _source(TramposSource)._parse(
        dict(TRAMPOS_JSON, salary="R$ 5.000"), "x"
    )
    assert "Salário: R$ 5.000." in com_salario.description


def test_trampos_ignora_registro_incompleto():
    src = _source(TramposSource)
    assert src._parse({"id": None, "name": "x"}, "t") is None
    assert src._parse({"id": 1, "name": ""}, "t") is None


# Recorte real da resposta de
# GET https://apigw.solides.com.br/jobs/v3/portal-vacancies
SOLIDES_JOB = {
    "id": 911953,
    "title": "Desenvolvedor(a) Júnior | Prestação de Serviços (PJ)  em Franca/SP",
    "description": "<p>Estamos buscando uma pessoa <strong>Desenvolvedora Júnior</strong> "
                   "para atuar com APIs REST e Python.</p>",
    "companyName": "Empresa Tech S.A.",
    "state": {"name": "São Paulo", "code": "SP"},
    "city": {"name": "FRANCA", "state_id": 0},
    "redirectLink": "https://empresa.solides.jobs/vacancies/911953?origem=portal",
    "homeOffice": False,
    "jobType": "presencial",
    "createdAt": "2026-08-29",
}


def test_solides_parse_mapeia_campos():
    src = _source(SolidesSource)
    job = src._parse(SOLIDES_JOB, "Júnior")
    assert job is not None
    assert job.source == "solides"
    assert job.external_id == "911953"
    assert job.title.startswith("Desenvolvedor(a) Júnior")
    assert job.company == "Empresa Tech S.A."
    assert job.location == "FRANCA, São Paulo"
    assert job.workplace_type == "Presencial"
    assert job.published_date == "2026-08-29"
    assert job.seniority == "Júnior"
    # O redirectLink (`empresa.solides.jobs`) foi desativado pela Solides:
    # a URL salva e a canonica do portal (/vaga/{id}/{titulo-slug}).
    assert job.url == (
        "https://vagas.solides.com.br/vaga/911953/"
        "desenvolvedor-a-junior-prestacao-de-servicos-pj-em-franca-sp"
    )
    assert "Desenvolvedora Júnior" in job.description


def test_solides_home_office_vira_remoto():
    job = _source(SolidesSource)._parse(
        dict(SOLIDES_JOB, homeOffice=True, jobType="presencial"), "Júnior"
    )
    assert job.workplace_type == "Remoto"


def test_solides_ignora_registro_incompleto_e_antigo():
    src = _source(SolidesSource)
    assert src._parse({"id": None, "title": "x"}, "Júnior") is None
    assert src._parse({"id": 1, "title": ""}, "Júnior") is None
    antiga = dict(SOLIDES_JOB, createdAt="2025-12-31")
    assert src._parse(antiga, "Júnior") is None


def test_solides_filtros_nativos_por_nivel():
    assert set(FILTROS_SOLIDES) == {"Júnior", "Estágio", "Estagiário", "Trainee", "Aprendiz"}
    assert FILTROS_SOLIDES["Júnior"]["seniorities"] == "junior"
    assert FILTROS_SOLIDES["Estágio"]["title"] == "estagio"
    assert FILTROS_SOLIDES["Estagiário"]["title"] == "estagiario"
    assert FILTROS_SOLIDES["Aprendiz"]["title"] == "aprendiz"


# Recorte real da listagem publica de https://www.geekhunter.com.br/pt/vagas
# (o card de "Desenvolvedor(a) Fullstack Java Júnior").
GEEKHUNTER_CARD = """
<li class="css-1oxv7b7" id="job-desenvolvedor-a--fullstack-java-junior-1"><article>
<div role="group">
  <div><p class="chakra-text">Atualizada há 19 horas</p></div>
  <div>
    <h3 class="chakra-text"><a href="https://www.geekhunter.com/pt/nava-technology-for-business-1/jobs/desenvolvedor-a--fullstack-java-junior-1">Desenvolvedor(a) Fullstack Java Júnior</a></h3>
  </div>
  <div>
    <div><p class="chakra-text">Júnior</p></div>
    <div><p class="chakra-text">Híbrido</p></div>
    <div><p class="chakra-text">São Paulo, SP, Brasil</p></div>
  </div>
</div>
<div>
  <p class="chakra-text">Tarefas e Responsabilidades</p>
  <p class="chakra-text">Desenvolvedor(a) Fullstack Java Júnior Modelo de trabalho: Híbrido — 3 dias presenciais e 2 dias em Home Office Local: Santo Amaro e/ou Interlagos — São Paulo/SP Contratação: CLT + pacote de benefícios Sobre a Nava: Na Nava, atuamos no core de empresas líderes em seus segmentos, conectando tecnologia</p>
</div>
<div>
  <p class="chakra-text">Requisitos</p>
  <div><p class="chakra-text">Angular 8+</p></div>
  <div><p class="chakra-text">Apis Rest</p></div>
</div>
</article></li>
"""


def test_geekhunter_parse_mapeia_campos():
    src = _source(GeekHunterSource)
    jobs = src._parse_page(GEEKHUNTER_CARD, "todas")
    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "geekhunter"
    assert job.external_id == "desenvolvedor-a--fullstack-java-junior-1"
    assert job.title == "Desenvolvedor(a) Fullstack Java Júnior"
    assert job.company == "nava-technology-for-business-1"
    assert job.workplace_type == "Híbrido"
    assert job.location == "São Paulo, SP, Brasil"
    assert job.seniority == "Júnior"
    assert "Fullstack Java Júnior" in job.description
    assert job.url.startswith("https://www.geekhunter.com/pt/")
    assert job.published_date == "Atualizada há 19 horas"


def test_geekhunter_ignora_card_sem_link():
    src = _source(GeekHunterSource)
    assert src._parse_page("<li id='job-x'><article><p>sem link</p></article></li>", "todas") == []


def test_geekhunter_nao_confia_em_nivel_alto_do_portal():
    """Card que declara 'Pleno' deixa senioridade vazia: o filtro de
    senioridade decide pelo titulo (titulos mistos 'Júnior/Pleno' seguem
    aceitando candidatos juniores)."""
    card = GEEKHUNTER_CARD.replace(">Júnior<", ">Pleno<")
    job = _source(GeekHunterSource)._parse_page(card, "todas")[0]
    assert job.seniority == ""


def test_trampos_usa_custom_company_name_quando_existe():
    raw = dict(TRAMPOS_JSON, custom_company_name="Empresa Confidencial")
    assert _source(TramposSource)._parse(raw, "x").company == "Empresa Confidencial"


# Recorte real de
# GET .../jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=desenvolvedor+junior&geoId=106057199
LINKEDIN_HTML = """
<ul>
<li>
  <div class="base-card job-search-card"
       data-entity-urn="urn:li:jobPosting:4422123289">
    <a class="base-card__full-link"
       href="https://www.linkedin.com/jobs/view/desenvolvedor-junior-at-acme-4422123289?position=1&amp;pageNum=0">
      <span class="sr-only">Desenvolvedor Back-end Júnior</span>
    </a>
    <div class="base-search-card__info">
      <h3 class="base-search-card__title">Desenvolvedor Back-end Júnior</h3>
      <h4 class="base-search-card__subtitle">ACME Tecnologia</h4>
      <span class="job-search-card__location">São Paulo, São Paulo, Brazil</span>
      <time datetime="2026-08-01">1 dia atrás</time>
    </div>
  </div>
</li>
</ul>
"""


def test_linkedin_parse_mapeia_campos():
    jobs = _source(LinkedInSource)._parse_page(LINKEDIN_HTML, "desenvolvedor junior")
    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "linkedin"
    assert job.external_id == "4422123289"
    assert job.title == "Desenvolvedor Back-end Júnior"
    assert job.company == "ACME Tecnologia"
    assert job.location == "São Paulo, São Paulo, Brazil"
    assert job.published_date == "2026-08-01"
    assert job.search_term == "desenvolvedor junior"


def test_linkedin_url_perde_os_parametros_de_rastreio():
    job = _source(LinkedInSource)._parse_page(LINKEDIN_HTML, "x")[0]
    assert job.url == (
        "https://www.linkedin.com/jobs/view/desenvolvedor-junior-at-acme-4422123289"
    )
    assert "?" not in job.url


def test_linkedin_usa_geoid_do_brasil():
    """`location=Brasil` em português falha em silêncio e traz vagas dos EUA."""
    assert GEO_ID_BRASIL == "106057199"


@pytest.mark.parametrize(
    "local,esperado",
    [
        ("São Paulo, São Paulo, Brazil", "Presencial"),
        ("Rio de Janeiro e Região", "Presencial"),
        ("Brazil (Remote)", "Remoto"),
        ("São Paulo (Remoto)", "Remoto"),
        ("Curitiba (Híbrido)", "Híbrido"),
        ("Brasil", "Remoto"),
        ("Brazil", "Remoto"),
        ("", "Não informado"),
    ],
)
def test_linkedin_modalidade(local, esperado):
    assert LinkedInSource._modalidade(local) == esperado




def test_linkedin_ignora_card_sem_urn_ou_titulo():
    src = _source(LinkedInSource)
    assert src._parse_page('<div class="base-card"><h3>X</h3></div>', "x") == []
    assert src._parse_page(
        '<div class="base-card" data-entity-urn="urn:li:jobPosting:1"></div>', "x"
    ) == []


def test_linkedin_titulo_com_remoto_vence_cidade_do_card():
    assert LinkedInSource._modalidade(
        "Goiânia, GO", title="Desenvolvedor Python Junior - Trabalho Remoto"
    ) == "Remoto"
    assert LinkedInSource._modalidade(
        "Goiânia, GO", title="Desenvolvedor Python Junior"
    ) == "Presencial"


def test_linkedin_pagina_vazia():
    assert _source(LinkedInSource)._parse_page("<html></html>", "x") == []


def test_linkedin_sem_descricao_no_card():
    """A busca não traz descrição; a classificação se apoia no título."""
    assert _source(LinkedInSource)._parse_page(LINKEDIN_HTML, "x")[0].description == ""


# Recorte real de
# GET https://www.infojobs.com.br/vagas-de-emprego.aspx?Palabra=desenvolvedor
# (dois cards + o contêiner "vacancylistDetail" que NAO e card de vaga).
INFOJOBS_HTML = """
<div class="js_vacanciesGridFragment mb-16">
<div data-typesimilar="" class="card card-shadow card-shadow-hover text-break mb-16 pb-24 grid-row js_rowCard active">
  <div id="vacancy11985552" data-modelversion="" data-id="11985552" class="pt-24 px-24 cursor-pointer js_vacancyLoad js_rowCard js_cardLink" data-href="/vaga-de-desenvolvedor-devops-backend-senior-em-__11985552.aspx" data-testabbutton="false">
    <div class="d-flex flex-wrap gap-8">
      <div hidden class="js_date" data-value="2026/09/03 05:32:00"></div>
    </div>
    <div class="d-flex gap-8 justify-content-between">
      <a class="text-decoration-none" href="/vaga-de-desenvolvedor-devops-backend-senior-em-__11985552.aspx">
        <h2 class="h3 font-weight-bold text-body mb-2 js_vacancyTitle">Desenvolvedor Devops Backend S&#xEA;nior</h2>
      </a>
      <div class="text-medium small text-nowrap">Ontem</div>
    </div>
    <div class="d-flex align-items-baseline">
      <div class="mr-8"><span class="font-weight-bold text-body">4,5</span></div>
      <div class="text-body"> Empresa <span class="text-nowrap"> confidencial <span class="cursor-pointer"></span></span></div>
    </div>
    <div class="mb-8"> Todo Brasil </div>
    <div class="d-inline-flex flex-wrap mb-8 text-medium" style="gap: 2px 16px">
      <div><svg class="icon icon-money icon-size-16"></svg> A combinar </div>
      <div><svg class="icon icon-suitcase icon-size-16"></svg> Entre 1 e 3 anos </div>
      <div><svg class="icon icon-graduate-hat icon-size-16"></svg> Ensino Superior </div>
      <div><svg class="icon icon-house-and-building icon-size-16"></svg> H&#xED;brido </div>
    </div>
    <div class="text-medium"> Procuramos uma Pessoa Desenvolvedora DevOps Back-End S&#xEA;nior com perfil altamente t&#xE9;cnico ... </div>
  </div>
</div>
<div data-typesimilar="" class="card card-shadow card-shadow-hover text-break mb-16 pb-24 grid-row js_rowCard ">
  <div id="vacancy11983931" data-modelversion="" data-id="11983931" class="pt-24 px-24 cursor-pointer js_vacancyLoad js_rowCard js_cardLink" data-href="/vaga-de-desenvolvedor-sr-em-sao-paulo__11983931.aspx">
    <div class="d-flex flex-wrap gap-8">
      <div hidden class="js_date" data-value="2026/09/03 01:52:00"></div>
    </div>
    <div class="d-flex gap-8 justify-content-between">
      <a class="text-decoration-none" href="/vaga-de-desenvolvedor-sr-em-sao-paulo__11983931.aspx">
        <h2 class="h3 font-weight-bold text-body mb-2 js_vacancyTitle">Desenvolvedor Sr.</h2>
      </a>
      <div class="text-medium small text-nowrap">Ontem</div>
    </div>
    <div class="d-flex align-items-baseline">
      <div class="text-body">
        <a class="text-body text-decoration-none" href="https://www.infojobs.com.br/gafor-ltda">
          <span class="text-nowrap"> GAFOR <span class="cursor-pointer"></span></span>
        </a>
      </div>
    </div>
    <div class="mb-8"> Guarulhos - SP , 0 Km de voc&#xEA;. </div>
    <div class="d-inline-flex flex-wrap mb-8 text-medium" style="gap: 2px 16px">
      <div><svg class="icon icon-money icon-size-16"></svg> R$ 6.000,00 </div>
      <div><svg class="icon icon-house-and-building icon-size-16"></svg> Presencial </div>
    </div>
    <div class="text-medium"> Desenvolvimento e manuten&#xE7;&#xE3;o de sistemas ... </div>
  </div>
</div>
<div id="vacancylistDetailContainer" class="col-12 col-lg-auto position-relative detail-container">
  <div id="vacancylistDetail" class="shadow-loading"></div>
</div>
</div>
"""


def test_infojobs_parse_page_mapeia_campos():
    jobs = _source(InfoJobsSource)._parse_page(INFOJOBS_HTML, "desenvolvedor")
    assert [j.external_id for j in jobs] == ["11985552", "11983931"]

    job = jobs[0]
    assert job.source == "infojobs"
    assert job.title == "Desenvolvedor Devops Backend Sênior"
    assert job.company == "confidencial"
    assert job.url == (
        "https://www.infojobs.com.br/vaga-de-desenvolvedor-devops-backend-"
        "senior-em-__11985552.aspx"
    )
    assert job.location == "Todo Brasil"
    assert job.workplace_type == "Híbrido"
    assert job.published_date == "2026-09-03"
    assert "DevOps Back-End" in job.description


def test_infojobs_empresa_com_link_e_local_sem_km():
    job = _source(InfoJobsSource)._parse_page(INFOJOBS_HTML, "x")[1]
    assert job.company == "GAFOR"
    assert job.location == "Guarulhos - SP"
    assert job.workplace_type == "Presencial"


def test_infojobs_ignora_containers_que_nao_sao_cards():
    # `div[id^=vacancy]` pega tambem os contêineres vacancylistDetail*:
    # o parse nao pode devolver cards sem data-id.
    assert len(_source(InfoJobsSource)._parse_page(INFOJOBS_HTML, "x")) == 2


def test_infojobs_ignora_vaga_anterior_a_2026():
    html = INFOJOBS_HTML.replace(
        'data-value="2026/09/03 05:32:00"', 'data-value="2025/12/31 10:00:00"'
    )
    jobs = _source(InfoJobsSource)._parse_page(html, "x")
    assert [j.external_id for j in jobs] == ["11983931"]


def test_infojobs_senioridade_so_nos_filtros_nativos():
    jobs = _source(InfoJobsSource)._parse_page(INFOJOBS_HTML, "Estágio")
    assert all(j.seniority == "Estágio" for j in jobs)
    jobs = _source(InfoJobsSource)._parse_page(INFOJOBS_HTML, "desenvolvedor junior")
    assert all(j.seniority == "" for j in jobs)


def test_infojobs_filtros_nativos_por_nivel():
    assert set(FILTROS_INFOJOBS) == {"Estágio", "Estagiário", "Trainee", "Aprendiz"}
    assert FILTROS_INFOJOBS["Estágio"] == {"categoria": "74", "tipocontrato": "4"}
    assert FILTROS_INFOJOBS["Estagiário"] == {"categoria": "74", "im": "1"}
    assert FILTROS_INFOJOBS["Trainee"] == {"categoria": "74", "tipocontrato": "15"}
    assert FILTROS_INFOJOBS["Aprendiz"] == {"categoria": "74", "tipocontrato": "19"}


