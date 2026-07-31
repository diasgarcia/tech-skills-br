"""Testes dos parsers, usando respostas reais capturadas dos portais (offline)."""

from scraper.config import Settings
from scraper.sources.gupy import GupySource
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
    assert job.workplace_type == "hybrid"
    assert job.published_date == "2026-07-31"
    assert job.search_term == "desenvolvedor junior"


def test_gupy_parse_limpa_html_da_descricao():
    job = _source(GupySource)._parse(GUPY_JOB, "x")
    assert "<p>" not in job.description
    assert "Júnior" in job.description  # entidade &uacute; decodificada


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


def test_vagas_parse_page_vazia():
    assert _source(VagasComSource)._parse_page("<html><body></body></html>", "x") == []


def test_slugify_term():
    assert slugify_term("desenvolvedor júnior") == "desenvolvedor-junior"
    assert slugify_term("Estágio  em TI") == "estagio-em-ti"
