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
            self.last_status_code = None
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
    assert sorted(delays_vistos) == [0.5, 1.0]


@pytest.mark.parametrize("parallel", [False, True])
def test_falha_de_fonte_preserva_diagnostico_e_contagem_sem_parar_as_demais(monkeypatch, parallel):
    from scraper.sources.base import JobSource

    class GoodSource(JobSource):
        name = "good"
        label = "Good"

        def fetch_term(self, term):
            self.session.request_count += 1
            return [_vaga(source=self.name)]

    class BrokenSource(JobSource):
        name = "broken"
        label = "Broken"

        def fetch_term(self, term):
            return []

        def fetch(self, terms):
            self.session.request_count += 3
            self.stats.errors.append("erro anterior por termo")
            raise ValueError("HTML invalido")

    class FakeSession:
        def __init__(self, **kwargs):
            self.request_count = 0
            self.last_status_code = None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(pipeline, "PoliteSession", FakeSession)
    monkeypatch.setattr(pipeline, "SOURCE_REGISTRY", {"broken": BrokenSource, "good": GoodSource})
    settings = Settings(sources=["broken", "good"], search_terms=["term"], parallel_sources=parallel)

    jobs, stats, requests = pipeline.collect(settings)

    assert [job.source for job in jobs] == ["good"]
    assert [stat.source for stat in stats] == ["broken", "good"]
    assert stats[0].errors == ["erro anterior por termo", "broken: ValueError: HTML invalido"]
    assert stats[0].requests_made == 3
    assert stats[1].raw_jobs == 1
    assert requests == 4


@pytest.mark.parametrize("parallel", [False, True])
def test_falha_na_construcao_de_fonte_tambem_gera_estatistica(monkeypatch, parallel):
    def failed_collect(*args):
        raise RuntimeError("nao iniciou a sessao")

    monkeypatch.setattr(pipeline, "_collect_source", failed_collect)
    settings = Settings(sources=["abler", "recrutei"], parallel_sources=parallel)

    jobs, stats, requests = pipeline.collect(settings)

    assert jobs == []
    assert requests == 0
    assert [stat.source for stat in stats] == ["abler", "recrutei"]
    assert all("nao iniciou a sessao" in stat.errors[0] for stat in stats)


def test_falha_de_fonte_recupera_checkpoint_completo(tmp_path, monkeypatch):
    from scraper.checkpoints import JobCheckpoint
    from scraper.sources.abler import AblerSource

    original = _vaga(source="abler")
    checkpoint = JobCheckpoint(tmp_path / "abler_partial.csv", "abler")

    def fail_after_save(source, terms):
        checkpoint.save([original])
        source.session.request_count += 1
        raise ValueError("falha depois de salvar")

    monkeypatch.setattr(AblerSource, "fetch", fail_after_save)
    settings = Settings(sources=["abler"], output_dir=tmp_path, parallel_sources=False)

    jobs, stats, requests = pipeline.collect(settings)

    assert jobs == [original]
    assert stats[0].raw_jobs == 1
    assert "falha depois de salvar" in stats[0].errors[0]
    assert requests == 1
    assert checkpoint.path.exists()


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


def test_typeerror_interno_do_callback_nao_repete_a_chamada(caplog):
    from scraper.sources.abler import AblerSource

    source = AblerSource(session=None, settings=Settings())
    calls = []

    def callback(*args):
        calls.append(args)
        raise TypeError("erro interno, nao erro de assinatura")

    source.progress_callback = callback

    source.report(5, requests=3)

    assert calls == [(5, None, 3, None)]
    assert "erro interno, nao erro de assinatura" in caplog.text


def test_tabela_paralela_formata_e_atualiza():
    """A tabela paralela formata as colunas e reflete atualizacoes."""
    monitor = pipeline._TabelaParalela(
        ["gupy", "vagas"], labels={"gupy": "Gupy", "vagas": "Vagas.com"}
    )

    monitor.atualizar("gupy", total=15, termo="[1/10] python", requests=2)
    monitor.finalizar_fonte("vagas", total=10, requests=1)
    monitor.erro_fonte("gupy", "timeout na conexao")
    tabela = monitor.formatar()

    assert "+----------------------+" in tabela
    assert "Gupy" in tabela
    assert "Vagas.com" in tabela
    assert "10" in tabela
    assert "15" in tabela
    assert "Erro" in tabela
    assert "Concluido" in tabela
    assert "TOTAL" in tabela


def test_tabela_paralela_renderiza_ci(monkeypatch, capsys):
    """No GitHub Actions, a tabela sai como linhas planas (sempre visivel)."""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monitor = pipeline._TabelaParalela(["gupy"])

    monitor.renderizar(forcar=True)
    saida = capsys.readouterr().out

    assert "::group::" not in saida
    assert "[resumo" in saida
    assert "Coleta Paralela" in saida
    assert "+----------------------+" in saida


def test_tabela_paralela_iniciar_encerrar():
    """Iniciar e encerrar iniciam e finalizam a thread de atualizacao sem travar."""
    monitor = pipeline._TabelaParalela(["gupy"])

    monitor.iniciar()
    estava_ativa = monitor.thread_timer is not None and monitor.thread_timer.is_alive()
    monitor.encerrar()
    esta_ativa = monitor.thread_timer.is_alive()

    assert estava_ativa
    assert not esta_ativa



@pytest.fixture
def sem_enriquecimento(monkeypatch):
    monkeypatch.setattr(pipeline, "_enrich_linkedin_parallel", lambda jobs, **kwargs: 0)


def test_run_coleta_classifica_e_exporta(tmp_path, monkeypatch, sem_enriquecimento):
    def coleta_fake(settings):
        return [_vaga()], [], 0

    monkeypatch.setattr(pipeline, "collect", coleta_fake)

    result = run(_settings(tmp_path))

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

    result = run(_settings(tmp_path))

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

    result = run(_settings(tmp_path), keep_non_tech=True)

    assert len(result.jobs) == 2
    assert result.meta["dropped_non_tech"] == 0


def test_run_pula_enriquecimento_quando_desabilitado(tmp_path, monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        pipeline, "_enrich_linkedin_parallel", lambda jobs, **kwargs: chamadas.append(len(jobs))
    )
    monkeypatch.setattr(pipeline, "collect", lambda settings: ([_vaga()], [], 0))

    run(_settings(tmp_path, enrich_linkedin=False))

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
