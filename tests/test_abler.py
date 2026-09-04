"""Testes do coletor da Abler, com fixtures capturadas do portal (offline)."""

import csv

from scraper.config import Settings
from scraper.sources.abler import CHECKPOINT_NAME, AblerSource

SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://candidatos.abler.com.br/vagas/</loc>
    <lastmod>2018-01-19T14:31:11+00:00</lastmod>
  </url>
  <url>
    <loc>https://candidatos.abler.com.br/vagas/217-estagio-de-engenharia-134508</loc>
    <lastmod>2026-09-04T11:00:00+00:00</lastmod>
  </url>
  <url>
    <loc>https://candidatos.abler.com.br/vagas/analista-de-suporte-943244</loc>
    <lastmod>2026-09-04T10:00:00+00:00</lastmod>
  </url>
  <url>
    <loc>https://candidatos.abler.com.br/vagas/vendedora-de-loja-332701</loc>
    <lastmod>2026-09-04T11:00:00+00:00</lastmod>
  </url>
  <url>
    <loc>https://candidatos.abler.com.br/vagas/advogado-a-jr-757511</loc>
    <lastmod>2026-09-01T11:00:00+00:00</lastmod>
  </url>
  <url>
    <loc>https://candidatos.abler.com.br/vagas/analista-de-dados-junior-111111</loc>
    <lastmod>2025-06-10T11:00:00+00:00</lastmod>
  </url>
</urlset>
"""

# Recorte real do payload window.__NUXT__ da pagina de vaga (valores com
# escapes JSON como o portal emite).
VAGA_HTML = """
<html><script>window.__NUXT__=(function(a,b,c,d,e,f){return {layout:"default",data:[{}],
vacancy:{vacancy:{companyName:"Engeko Engenharia",companyLogo:"x",
title:"217 - Est\\u00E1gio de Engenharia",titleFormatted:"217 Est\\u00E1gio de Engenharia",
address:{cityId:"78",stateId:"2",cityName:"Messias",stateName:"Alagoas",stateAbbr:"AL"},
areaOfInterests:[{id:"82",name:"Constru\\u00E7\\u00E3o Civil"}],
createdAt:"2026-08-19T11:09:37.367-03:00",
description:"\\u003Cul\\u003E\\u003Cli\\u003EApoiar o controle de documentos;\\u003C\\u002Fli\\u003E\\u003C\\u002Ful\\u003E",
publishedAt:"2026-08-19T11:37:25.943-03:00",id:"386934",
salary:"A combinar",slug:"217-estagio-de-engenharia-134508",
status:"Em andamento",vacancyBenefits:[],vacancyTemplates:[],
companyCollection:{data:[],pagination:{count:e,last:1,page:1,perPage:15,q:c}}}}}(0,false,null,null,null,null));</script>
</body></html>
"""

VAGA_URL = "https://candidatos.abler.com.br/vagas/217-estagio-de-engenharia-134508"


def _source(**kw):
    base = dict(abler_days_back=1)
    base.update(kw)
    return AblerSource(session=None, settings=Settings(**base))


def test_sitemap_filtra_slug_tech_e_janela_de_dias():
    src = _source(abler_days_back=1)
    alvos = src._filtrar_sitemap(SITEMAP_XML)
    assert alvos == [
        "https://candidatos.abler.com.br/vagas/217-estagio-de-engenharia-134508",
        "https://candidatos.abler.com.br/vagas/analista-de-suporte-943244",
    ]


def test_sitemap_janela_maior_pega_2026_mas_nunca_antes_de_2026():
    """A coleta completa volta ate o corte do projeto, nunca antes dele."""
    src = _source(abler_days_back=36500)
    alvos = src._filtrar_sitemap(SITEMAP_XML)
    assert any("advogado-a-jr-757511" in a for a in alvos)
    assert not any("analista-de-dados-junior-111111" in a for a in alvos)


def test_parse_page_mapeia_campos():
    job = _source()._parse_page(VAGA_HTML, VAGA_URL)
    assert job is not None
    assert job.source == "abler"
    assert job.external_id == "134508"
    assert job.title == "217 - Estágio de Engenharia"
    assert job.company == "Engeko Engenharia"
    assert job.location == "Messias, AL"
    assert job.published_date == "2026-08-19"
    assert job.url == VAGA_URL
    assert "Apoiar o controle de documentos" in job.description
    assert "<ul>" not in job.description  # strip_html do modelo


def test_parse_page_ignora_html_sem_payload():
    assert _source()._parse_page("<html>sem vaga</html>", VAGA_URL) is None


def test_parse_page_ignora_vaga_anterior_a_2026():
    antiga = VAGA_HTML.replace(
        'publishedAt:"2026-08-19T11:37:25.943-03:00"',
        'publishedAt:"2025-12-01T11:37:25.943-03:00"',
    )
    assert _source()._parse_page(antiga, VAGA_URL) is None


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.request_count = 0

    def get(self, url, params=None):
        self.request_count += 1
        if not self._responses:
            return None
        return self._responses.pop(0)


def _source_com_sessao(tmp_path, responses, **kw):
    base = dict(output_dir=tmp_path, abler_days_back=1)
    base.update(kw)
    return AblerSource(session=FakeSession(responses), settings=Settings(**base))


def test_coleta_grava_checkpoint_ao_parar_no_body_vazio(tmp_path):
    """Body vazio (bloqueio) para a coleta e mantem o que ja foi coletado."""
    src = _source_com_sessao(
        tmp_path,
        [
            FakeResponse(SITEMAP_XML),
            FakeResponse(VAGA_HTML),
            FakeResponse(""),
        ],
    )
    jobs = src._coletar()
    assert len(jobs) == 1
    checkpoint = tmp_path / CHECKPOINT_NAME
    assert checkpoint.is_file()
    with open(checkpoint, encoding="utf-8-sig", newline="") as fh:
        linhas = list(csv.DictReader(fh))
    assert [l["external_id"] for l in linhas] == ["134508"]


def test_coleta_retoma_do_checkpoint_e_nao_refaz_get(tmp_path):
    """Pagina ja no checkpoint nao gera novo request."""
    checkpoint = tmp_path / CHECKPOINT_NAME
    with open(checkpoint, "w", encoding="utf-8-sig", newline="") as fh:
        fh.write("external_id,title\n134508,ja coletada\n")

    src = _source_com_sessao(
        tmp_path,
        [
            FakeResponse(SITEMAP_XML),
            FakeResponse(VAGA_HTML),
        ],
    )
    jobs = src._coletar()
    # 134508 pulado sem GET; so a segunda pagina foi buscada.
    assert [j.external_id for j in jobs] == ["943244"]
    assert src.session.request_count == 2  # sitemap + 1 pagina


def test_coleta_completa_remove_o_checkpoint(tmp_path):
    src = _source_com_sessao(
        tmp_path,
        [
            FakeResponse(SITEMAP_XML),
            FakeResponse(VAGA_HTML),
        ],
        abler_days_back=36500,
    )
    src._coletar()
    assert not (tmp_path / CHECKPOINT_NAME).exists()
