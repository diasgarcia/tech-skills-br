"""Testes do coletor do Recrutei, com fixtures capturadas do portal (offline)."""

import csv

from scraper.config import Settings
from scraper.sources.recrutei import CHECKPOINT_NAME, RecruteiSource

SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://empregos.recrutei.com.br/vaga/alpha-estagio/153211-estagio-em-ti</loc>
    <lastmod>2026-09-04T10:00:00+00:00</lastmod>
  </url>
  <url>
    <loc>https://empregos.recrutei.com.br/vaga/outra/999999-antiga</loc>
    <lastmod>2026-08-01T10:00:00+00:00</lastmod>
  </url>
</urlset>
"""

LISTAGEM_HTML = """
<html><body>
<p>Exibindo Resultados 1 - 12 de um total de <strong>144</strong> vagas</p>
<script type="application/ld+json">
{"@type":"ItemList","itemListElement":[
 {"url":"https://empregos.recrutei.com.br/vaga/alpha-estagio/153211-estagio-em-ti","name":"Estagio em TI"},
 {"url":"https://empregos.recrutei.com.br/vaga/anonimo/7b2d9a38-9099-439b-873e-917a82d70feb","name":"Gerente"}
]}
</script>
<link rel="next" href="https://empregos.recrutei.com.br/vagas?page=2" />
</body></html>
"""

DETALHE_HTML = """
<html><head>
<script type="application/ld+json">
{
 "@context": "https://schema.org",
 "@type": "JobPosting",
 "title": "EST\\u00c1GIO EM TECNOLOGIA DA INFORMA\\u00c7\\u00c3O - HOME OFFICE",
 "description": "Nosso cliente busca estagiario para atuar na implantacao de solucoes.\\nRequisitos: Logica de programacao.\\nAtividades: Mapeamento de processos.",
 "datePosted": "2026-08-06T12:58:17.000000Z",
 "employmentType": ["INTERN"],
 "hiringOrganization": {"@type": "Organization", "name": "Alpha Estagio"},
 "jobLocation": {"@type": "Place", "address": {
   "@type": "PostalAddress", "addressLocality": "Belo Horizonte",
   "addressRegion": "MG", "addressCountry": "Brasil"}}
}
</script>
</head><body></body></html>
"""

VAGA_URL = "https://empregos.recrutei.com.br/vaga/alpha-estagio/153211-estagio-em-ti"


def _source(**kw):
    base = dict(output_dir=kw.pop("output_dir", None) or "output", recrutei_days_back=1)
    base.update(kw)
    return RecruteiSource(session=None, settings=Settings(**base))


def test_parse_page_mapeia_campos():
    job = _source()._parse_page(DETALHE_HTML, VAGA_URL)
    assert job is not None
    assert job.source == "recrutei"
    assert job.external_id == "153211"
    assert "TECNOLOGIA DA INFORMA" in job.title
    assert job.company == "Alpha Estagio"
    assert job.location == "Belo Horizonte, MG"
    assert job.published_date == "2026-08-06"
    assert "Logica de programacao" in job.description
    assert job.url == VAGA_URL


def test_parse_page_ignora_vaga_anterior_a_2026():
    antiga = DETALHE_HTML.replace("2026-08-06", "2025-12-01")
    assert _source()._parse_page(antiga, VAGA_URL) is None


def test_parse_page_ignora_html_sem_jobposting():
    assert _source()._parse_page("<html>sem json-ld</html>", VAGA_URL) is None


def test_vid_da_url_aceita_numerico_e_uuid():
    from scraper.sources.recrutei import _vid_da_url
    assert _vid_da_url(VAGA_URL) == "153211"
    assert _vid_da_url(
        "https://empregos.recrutei.com.br/vaga/anonimo/7b2d9a38-9099-439b-873e-917a82d70feb"
    ) == "7b2d9a38-9099-439b-873e-917a82d70feb"


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
    base = dict(output_dir=tmp_path, recrutei_days_back=1)
    base.update(kw)
    return RecruteiSource(session=FakeSession(responses), settings=Settings(**base))


def test_coleta_completa_percorre_a_listagem_e_para_no_fim(tmp_path):
    src = _source_com_sessao(
        tmp_path,
        [
            FakeResponse(LISTAGEM_HTML),          # page 1
            FakeResponse("<html>sem vagas</html>"),  # page 2 (fim)
            FakeResponse(DETALHE_HTML),           # detalhe 1 (153211)
            FakeResponse("<html>sem jobposting</html>"),  # detalhe 2 (uuid)
        ],
        recrutei_full=True,
    )
    jobs = src.fetch([])
    assert [j.external_id for j in jobs] == ["153211"]


def test_coleta_sitemap_usa_a_janela_de_dias(tmp_path):
    src = _source_com_sessao(
        tmp_path,
        [
            FakeResponse(SITEMAP_XML),
            FakeResponse(DETALHE_HTML),
        ],
    )
    jobs = src.fetch([])
    # so a vaga de 04/09 esta dentro das ultimas 24h
    assert [j.external_id for j in jobs] == ["153211"]


def test_checkpoint_grava_e_retoma(tmp_path):
    sitemap2 = SITEMAP_XML.replace(
        '999999-antiga</loc>',
        '999999-fresca</loc>'
    ).replace('2026-08-01T10:00:00+00:00', '2026-09-04T11:00:00+00:00')
    src = _source_com_sessao(
        tmp_path,
        [
            FakeResponse(sitemap2),
            FakeResponse(DETALHE_HTML),
            FakeResponse(""),  # body vazio: para e mantem o checkpoint
        ],
    )
    jobs = src.fetch([])
    assert len(jobs) == 1
    checkpoint = tmp_path / CHECKPOINT_NAME
    assert checkpoint.is_file()
    with open(checkpoint, encoding="utf-8-sig", newline="") as fh:
        linhas = list(csv.DictReader(fh))
    assert [l["external_id"] for l in linhas] == ["153211"]


def test_coleta_completa_remove_o_checkpoint(tmp_path):
    src = _source_com_sessao(
        tmp_path,
        [
            FakeResponse(LISTAGEM_HTML),
            FakeResponse("<html>sem vagas</html>"),
            FakeResponse(DETALHE_HTML),
            FakeResponse("<html>sem jobposting</html>"),
        ],
        recrutei_full=True,
    )
    src.fetch([])
    assert not (tmp_path / CHECKPOINT_NAME).exists()
