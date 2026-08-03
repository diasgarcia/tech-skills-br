"""Testes dos parsers, usando respostas reais capturadas dos portais (offline)."""

import pytest

from scraper.config import Settings
from scraper.sources.gupy import GupySource
from scraper.sources.programathor import FILTROS_NIVEL_ENTRADA, ProgramathorSource
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


# Recorte real de https://programathor.com.br/jobs?expertise=Júnior
# Dois cards: um ativo e um com o selo "Vencida".
PROGRAMATHOR_HTML = """
<div class="wrapper-jobs-list">
<a href="/jobs/33692-desenvolvedor-a-php-junior">
  <div class="cell-list-content">
    <h3 class="text-24 line-height-30">Desenvolvedor(a) PHP Júnior</h3>
    <div class="cell-list-content-icon">
      <span><i class="fa fa-briefcase"></i>TECHLEGAL SERVICOS - ME</span>
      <span><i class="fas fa-map-marker-alt"></i>São Paulo  (Híbrido)</span>
      <span><i class="fa fa-building"></i>Startup</span>
      <span><i class="far fa-money-bill-alt"></i>Até R$4.000</span>
      <span><i class="far fa-chart-bar"></i>Júnior</span>
      <span><i class="far fa-file-alt"></i>PJ</span>
      <span><i class="fas fa-plane"></i>Não Aceito candidatos de outras cidades</span>
    </div>
    <div>
      <span class="tag-list background-gray">API</span>
      <span class="tag-list background-gray">CodeIgniter</span>
      <span class="tag-list background-gray">HTML</span>
      <span class="tag-list background-gray">JavaScript</span>
      <span class="tag-list background-gray">MySQL</span>
      <span class="tag-list background-gray">PHP</span>
    </div>
  </div>
</a>
<a href="/jobs/13029-programador-a-php">
  <div class="cell-list-content">
    <h3 class="color-gray text-24 line-height-30">
      <span class="text-16 border-red color-red">Vencida</span>
      Programador(a) PHP
    </h3>
    <div class="cell-list-content-icon">
      <span><i class="fa fa-briefcase"></i>Wase Tecnologia</span>
      <span><i class="fas fa-map-marker-alt"></i>Remoto</span>
      <span><i class="far fa-chart-bar"></i>Júnior</span>
      <span><i class="far fa-file-alt"></i>Estágio</span>
    </div>
    <div><span class="tag-list background-gray">PHP</span></div>
  </div>
</a>
</div>
"""


def test_programathor_parse_mapeia_campos_pelo_icone():
    jobs = _source(ProgramathorSource)._parse_page(PROGRAMATHOR_HTML, "Júnior")
    assert len(jobs) == 1  # a vaga "Vencida" foi descartada
    job = jobs[0]
    assert job.source == "programathor"
    assert job.external_id == "33692"
    assert job.title == "Desenvolvedor(a) PHP Júnior"
    assert job.company == "TECHLEGAL SERVICOS - ME"
    assert job.url == "https://programathor.com.br/jobs/33692-desenvolvedor-a-php-junior"
    assert job.search_term == "Júnior"


def test_programathor_descarta_vaga_vencida():
    jobs = _source(ProgramathorSource)._parse_page(PROGRAMATHOR_HTML, "x")
    assert "13029" not in {j.external_id for j in jobs}


def test_programathor_separa_local_e_modalidade():
    parse = ProgramathorSource._local_e_modalidade
    assert parse("São Paulo  (Híbrido)") == ("São Paulo", "Híbrido")
    assert parse("São Luís, Maranhão  (Presencial)") == ("São Luís, Maranhão", "Presencial")
    assert parse("Remoto") == ("", "Remoto")
    assert parse("") == ("", "")


def test_programathor_usa_a_senioridade_declarada_pelo_portal():
    """O portal informa o nível num campo próprio; não dependemos do título."""
    job = _source(ProgramathorSource)._parse_page(PROGRAMATHOR_HTML, "x")[0]
    assert job.seniority == "Júnior"


def test_programathor_contrato_de_estagio_vence_a_senioridade():
    # O portal marca estágio como expertise=Júnior + contract_type=Estágio.
    senioridade = ProgramathorSource._senioridade(
        {"expertise": "Júnior", "contract": "Estágio"}
    )
    assert senioridade == "Estágio"


def test_programathor_tecnologias_entram_na_descricao():
    """O card não traz descrição, mas traz as tags -- que alimentam o classificador."""
    job = _source(ProgramathorSource)._parse_page(PROGRAMATHOR_HTML, "x")[0]
    assert "CodeIgniter" in job.description
    assert "PHP" in job.description
    assert "Faixa salarial" in job.description


def test_programathor_pagina_vazia():
    assert _source(ProgramathorSource)._parse_page("<html></html>", "x") == []


def test_programathor_ignora_card_sem_id_valido():
    html = '<div class="wrapper-jobs-list"><a href="/jobs/sem-id"><h3>X</h3></a></div>'
    assert _source(ProgramathorSource)._parse_page(html, "x") == []


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


def test_trampos_usa_custom_company_name_quando_existe():
    raw = dict(TRAMPOS_JSON, custom_company_name="Empresa Confidencial")
    assert _source(TramposSource)._parse(raw, "x").company == "Empresa Confidencial"


def test_programathor_filtros_de_nivel_de_entrada():
    # O portal não tem busca textual, então a fonte usa os filtros nativos.
    assert set(FILTROS_NIVEL_ENTRADA) == {"Júnior", "Estágio"}
    assert FILTROS_NIVEL_ENTRADA["Júnior"] == {"expertise": "Júnior"}
    assert FILTROS_NIVEL_ENTRADA["Estágio"] == {"contract_type": "Estágio"}
