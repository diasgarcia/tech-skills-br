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


def test_historico_ignora_referencia_de_outro_perfil():
    metrics = {
        "full_scope": True,
        "source_stats": [
            {
                "source": "infojobs",
                "raw_jobs": 20,
                "collection_profile": "last-3d-v1",
            }
        ],
    }
    history = [
        {"full_scope": True, "source_stats": [{"source": "infojobs", "raw_jobs": n}]}
        for n in (100, 110, 90)
    ]

    alerts = assess_history(metrics, history)

    assert alerts == []


def test_historico_compara_execucoes_do_mesmo_perfil():
    profile = "last-3d-v1"
    metrics = {
        "full_scope": True,
        "source_stats": [
            {
                "source": "infojobs",
                "raw_jobs": 20,
                "collection_profile": profile,
            }
        ],
    }
    history = [
        {
            "full_scope": True,
            "source_stats": [
                {
                    "source": "infojobs",
                    "raw_jobs": n,
                    "collection_profile": profile,
                }
            ],
        }
        for n in (100, 110, 90)
    ]

    alerts = assess_history(metrics, history)

    assert [alert.rule for alert in alerts] == ["sharp_drop"]


def test_historico_avisa_sem_bloquear_variacao_de_janela_de_24_horas():
    profile = "last-24h-v1"
    metrics = {
        "full_scope": True,
        "source_stats": [
            {
                "source": "linkedin",
                "raw_jobs": 4_320,
                "collection_profile": profile,
            }
        ],
    }
    history = [
        {
            "full_scope": True,
            "source_stats": [
                {
                    "source": "linkedin",
                    "raw_jobs": value,
                    "collection_profile": profile,
                }
            ],
        }
        for value in (19_570, 19_661, 20_067)
    ]

    alerts = assess_history(metrics, history)

    assert [(alert.rule, alert.severity) for alert in alerts] == [
        ("sharp_drop", "warning")
    ]
    assert not has_high_alerts({"alerts": [alert.__dict__ for alert in alerts]})


def test_historico_bloqueia_queda_quase_total_em_janela_de_24_horas():
    profile = "last-24h-v1"
    metrics = {
        "full_scope": True,
        "source_stats": [
            {
                "source": "linkedin",
                "raw_jobs": 900,
                "collection_profile": profile,
            }
        ],
    }
    history = [
        {
            "full_scope": True,
            "source_stats": [
                {
                    "source": "linkedin",
                    "raw_jobs": value,
                    "collection_profile": profile,
                }
            ],
        }
        for value in (19_570, 19_661, 20_067)
    ]

    alerts = assess_history(metrics, history)

    assert [(alert.rule, alert.severity) for alert in alerts] == [
        ("sharp_drop", "high")
    ]


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


def test_metricas_guardam_perfil_de_coleta_quando_declarado():
    metrics = build_metrics(
        [_job()],
        [
            SourceStats(
                "infojobs",
                raw_jobs=1,
                requests_made=2,
                collection_profile="last-3d-v1",
            )
        ],
        raw_jobs=1,
        requests=2,
        full_scope=True,
    )

    assert metrics["source_stats"][0]["collection_profile"] == "last-3d-v1"


def test_falha_conhecida_permite_coleta_parcial_sem_renovar_escopo_completo():
    metrics = build_metrics(
        [_job(source="linkedin")],
        [
            SourceStats("gupy", errors=["HTTP 404"]),
            SourceStats("linkedin", raw_jobs=1),
        ],
        raw_jobs=1, requests=2, full_scope=True,
    )
    history = [
        {"full_scope": True, "source_stats": [{"source": "gupy", "raw_jobs": 300}]}
        for _ in range(3)
    ]

    historical_alerts = assess_history(metrics, history)

    assert not has_high_alerts(metrics)
    assert metrics["requested_full_scope"] is True
    assert metrics["full_scope"] is False
    assert metrics["failed_sources"] == ["gupy"]
    assert any(alert["rule"] == "partial_collection" for alert in metrics["alerts"])
    assert historical_alerts == []


def test_falha_conhecida_nao_libera_coleta_totalmente_vazia():
    metrics = build_metrics(
        [], [SourceStats("gupy", errors=["HTTP 404"])],
        raw_jobs=0, requests=1, full_scope=True,
    )

    assert has_high_alerts(metrics)
    assert any(alert["rule"] == "collection_empty" for alert in metrics["alerts"])


def test_falha_conhecida_nao_oculta_outra_fonte_zerada_sem_erro():
    metrics = build_metrics(
        [_job(source="infojobs")],
        [
            SourceStats("gupy", errors=["HTTP 404"]),
            SourceStats("linkedin", raw_jobs=0),
            SourceStats("infojobs", raw_jobs=1),
        ],
        raw_jobs=1, requests=3, full_scope=True,
    )

    assert has_high_alerts(metrics)
    assert any(
        alert["rule"] == "source_empty" and alert["source"] == "linkedin"
        for alert in metrics["alerts"]
    )


def test_coleta_parcial_ainda_bloqueia_queda_silenciosa_de_outra_fonte():
    metrics = build_metrics(
        [_job(source="linkedin")],
        [
            SourceStats("gupy", errors=["HTTP 404"]),
            SourceStats("linkedin", raw_jobs=1),
        ],
        raw_jobs=1, requests=2, full_scope=True,
    )
    history = [
        {"full_scope": True, "source_stats": [{"source": "linkedin", "raw_jobs": 100}]}
        for _ in range(3)
    ]

    alerts = assess_history(metrics, history)

    assert [(alert.rule, alert.source, alert.severity) for alert in alerts] == [
        ("sharp_drop", "linkedin", "high")
    ]
