"""Testes do fluxo completo do pipeline, sem rede."""

import pytest

import scraper.pipeline as pipeline
from scraper.config import Settings
from scraper.models import Job
from scraper.pipeline import PipelineResult, _enrich_linkedin_parallel, run


def _settings(tmp_path, **kw):
    base = dict(
        search_terms=["desenvolvedor junior"],
        sources=["linkedin"],
        output_dir=tmp_path,
        enrich_linkedin=True,
    )
    base.update(kw)
    return Settings(**base)


def _vaga(**kw):
    base = dict(
        source="linkedin",
        external_id="4457495990",
        title="Desenvolvedor Backend Python Júnior",
        company="byx",
        url="https://br.linkedin.com/jobs/view/exemplo",
        description="",
        location="Brasil",
        workplace_type="Remoto",
        published_date="2026-08-25",
        search_term="desenvolvedor junior",
    )
    base.update(kw)
    return Job(**base)


def test_collect_paralelo_equivale_ao_sequencial(monkeypatch):
    """Fontes em paralelo devolvem os mesmos jobs, na mesma ordem, com
    delay por fonte respeitado (sessao propria por fonte)."""
    from scraper.sources.base import JobSource as Base

    def make_source(name):
        return type(
            f"{name.title()}Fake",
            (Base,),
            {
                "name": name,
                "label": name,
                "fetch_term": lambda self, term: [],
                "fetch": lambda self, terms: [
                    Job(source=self.name, external_id=self.name, title=self.name)
                ],
            },
        )

    monkeypatch.setattr(
        pipeline, "SOURCE_REGISTRY", {"a": make_source("a"), "b": make_source("b")}
    )

    delays_vistos = []

    class FakePolite:
        def __init__(self, **kw):
            self.request_count = 0
            delays_vistos.append(kw.get("delay_seconds"))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(pipeline, "PoliteSession", FakePolite)

    settings = Settings(
        sources=["a", "b"], source_delays={"b": 0.5}, parallel_sources=True
    )
    jobs, stats, _ = pipeline.collect(settings)

    assert [j.external_id for j in jobs] == ["a", "b"]
    assert [s.source for s in stats] == ["a", "b"]
    # "a" usa o delay padrao; "b" usa o override.
    assert sorted(delays_vistos) == [0.5, 1.5]


def test_fetch_base_reporta_progresso_por_termo(monkeypatch):
    """O JobSource.fetch avisa o callback com o total corrente a cada termo."""
    from scraper.sources.base import JobSource as Base

    class FonteFake(Base):
        name = "f"

        def fetch_term(self, term):
            return [
                Job(source=self.name, external_id=term, title=term)
                for _ in range(int(term))
            ]

    class SessaoFake:
        request_count = 0

    fonte = FonteFake(session=SessaoFake(), settings=Settings(sources=["f"]))
    vistos = []
    fonte.progress_callback = vistos.append
    jobs = fonte.fetch(["2", "3"])
    assert len(jobs) == 5
    assert vistos == [2, 5]


def test_resumo_paralelo_abre_fecha_grupos(capsys):
    """O resumo emite grupos colapsaveis com as contagens do momento."""
    resumo = pipeline._ResumoParalelo(["a", "b"])
    resumo.abrir()
    resumo.registrar("a", 10)
    resumo.registrar("b", 5)
    resumo.abrir()  # fecha o anterior e abre com contagens novas
    resumo.fechar()

    saida = capsys.readouterr().out
    assert saida.count("::group::[resumo") == 2
    assert saida.count("::endgroup::") == 2
    assert "a 10 | b 5" in saida


@pytest.fixture
def sem_enriquecimento(monkeypatch):
    monkeypatch.setattr(pipeline, "_enrich_linkedin_parallel", lambda jobs: None)


def test_run_coleta_classifica_e_exporta(tmp_path, monkeypatch, sem_enriquecimento):
    def coleta_fake(settings):
        return [_vaga()], [], 0

    monkeypatch.setattr(pipeline, "collect", coleta_fake)
    result = run(_settings(tmp_path), with_charts=False)

    assert isinstance(result, PipelineResult)
    assert len(result.jobs) == 1
    assert result.jobs[0].area == "Backend"
    assert "Python" in result.jobs[0].skills
    assert result.ranking[0]["area"] == "Backend"
    assert result.meta["raw_jobs"] == 1
    assert result.meta["duplicates"] == 0
    assert result.files["jobs_csv"].exists()
    assert result.files["ranking_csv"].exists()
    assert result.files["skills_csv"].exists()
    assert result.files["report_md"].exists()


def test_run_descarta_vaga_nao_tech(tmp_path, monkeypatch, sem_enriquecimento):
    vagas = [
        _vaga(),
        _vaga(
            external_id="2",
            url="",
            title="Recepcionista Júnior",
            description="Atendimento ao publico e recepcao.",
        ),
    ]
    monkeypatch.setattr(pipeline, "collect", lambda settings: (vagas, [], 0))
    result = run(_settings(tmp_path), with_charts=False)
    assert len(result.jobs) == 1
    assert result.meta["dropped_non_tech"] == 1


def test_run_mantem_nao_tech_quando_pedido(tmp_path, monkeypatch, sem_enriquecimento):
    vagas = [
        _vaga(),
        _vaga(
            external_id="2",
            url="",
            title="Recepcionista Júnior",
            description="Atendimento ao publico e recepcao.",
        ),
    ]
    monkeypatch.setattr(pipeline, "collect", lambda settings: (vagas, [], 0))
    result = run(_settings(tmp_path), keep_non_tech=True, with_charts=False)
    assert len(result.jobs) == 2
    assert result.meta["dropped_non_tech"] == 0


def test_run_pula_enriquecimento_quando_desabilitado(tmp_path, monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        pipeline, "_enrich_linkedin_parallel", lambda jobs: chamadas.append(len(jobs))
    )
    monkeypatch.setattr(pipeline, "collect", lambda settings: ([_vaga()], [], 0))
    run(_settings(tmp_path, enrich_linkedin=False), with_charts=False)
    assert chamadas == []


def test_enriquecimento_preenche_descricao_da_vaga(monkeypatch):
    class FakeResponse:
        def __init__(self, text):
            self.text = text

    class FakeSession:
        def __init__(self, *args, **kwargs):
            self.request_count = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            self.request_count += 1
            return FakeResponse(
                '<div class="show-more-less-html__markup">'
                "Python, Django e FastAPI.</div>"
            )

    monkeypatch.setattr("scraper.http_client.PoliteSession", FakeSession)
    job = _vaga()
    _enrich_linkedin_parallel([job])
    assert "Django" in job.description


def test_enriquecimento_ignora_html_sem_o_seletor(monkeypatch):
    class FakeResponse:
        def __init__(self, text):
            self.text = text

    class FakeSession:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            return FakeResponse("<html>pagina de bot sem descricao</html>")

    monkeypatch.setattr("scraper.http_client.PoliteSession", FakeSession)
    job = _vaga()
    _enrich_linkedin_parallel([job])
    assert job.description == ""


def test_enriquecimento_suporta_erro_de_sessao(monkeypatch):
    class FakeSession:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            raise RuntimeError("falha inesperada")

    monkeypatch.setattr("scraper.http_client.PoliteSession", FakeSession)
    job = _vaga()
    _enrich_linkedin_parallel([job])  # nao pode derrubar a coleta
    assert job.description == ""
