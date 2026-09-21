from scraper.models import Job, SourceStats
from scraper.quality import assess_current, assess_history, build_metrics, has_high_alerts


def _job(**changes):
    values = {
        "source": "gupy",
        "external_id": "1",
        "title": "Desenvolvedor Júnior",
        "company": "ACME",
        "url": "https://example.com/vaga/1",
        "area": "Backend",
        "workplace_type": "Não informado",
        "published_date": "2026-09-20",
    }
    values.update(changes)
    return Job(**values)


def test_coleta_completa_detecta_fonte_zerada_sem_erro():
    alerts = assess_current(
        [_job()],
        [SourceStats("gupy", raw_jobs=0)],
        full_scope=True,
    )

    assert [(alert.rule, alert.severity) for alert in alerts] == [
        ("source_empty", "high")
    ]


def test_coleta_parcial_nao_trata_fonte_zerada_como_anomalia():
    alerts = assess_current(
        [_job()],
        [SourceStats("gupy", raw_jobs=0)],
        full_scope=False,
    )

    assert all(alert.rule != "source_empty" for alert in alerts)


def test_fonte_de_janela_diaria_pode_retornar_zero():
    alerts = assess_current(
        [_job()],
        [SourceStats("abler", raw_jobs=0)],
        full_scope=True,
    )

    assert all(alert.rule != "source_empty" for alert in alerts)


def test_historico_detecta_queda_brusca_de_uma_fonte():
    metrics = {
        "full_scope": True,
        "source_stats": [{"source": "linkedin", "raw_jobs": 20}],
    }
    history = [
        {"full_scope": True, "source_stats": [{"source": "linkedin", "raw_jobs": n}]}
        for n in (100, 110, 90)
    ]

    alerts = assess_history(metrics, history)

    assert len(alerts) == 1
    assert alerts[0].rule == "sharp_drop"
    assert alerts[0].severity == "high"


def test_metricas_guardam_contadores_e_alertas():
    metrics = build_metrics(
        [_job(workplace_type="fora-do-dominio")],
        [SourceStats("gupy", raw_jobs=1, requests_made=2)],
        raw_jobs=1,
        requests=2,
        full_scope=True,
    )

    assert metrics["source_stats"][0]["requests"] == 2
    assert has_high_alerts(metrics)
