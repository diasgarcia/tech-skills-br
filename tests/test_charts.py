"""Testes dos graficos SVG publicados no README."""

from datetime import date

import pytest

from scraper.charts import (
    ChartJob,
    build_area_skill_matrix,
    build_daily_activity,
    chart_area_skill_heatmap,
    chart_daily_jobs_and_skills,
    export_readme_charts,
)


def _job(day: date | None, area: str, *skills: str) -> ChartJob:
    return ChartJob(published_date=day, area=area, skills=skills)


def test_build_daily_activity_agrupa_vagas_e_skills_distintas():
    jobs = [
        _job(date(2026, 9, 10), "Frontend", "React"),
        _job(date(2026, 9, 11), "Backend", "Python", "SQL"),
        _job(date(2026, 9, 11), "Frontend", "React", "Python"),
        _job(date(2026, 8, 1), "Backend", "Java"),
        _job(None, "Data", "Power BI"),
    ]

    result = build_daily_activity(jobs, days=2)

    assert result.dates == (date(2026, 9, 10), date(2026, 9, 11))
    assert result.jobs == (1, 2)
    assert result.skills == (1, 3)
    assert result.total_jobs == 5
    assert result.period_jobs == 3
    assert result.period_skills == 3
    assert result.last_date == date(2026, 9, 11)


def test_build_daily_activity_rejeita_periodo_invalido():
    jobs = [_job(date(2026, 9, 11), "Backend", "Python")]

    with pytest.raises(ValueError, match="periodo"):
        build_daily_activity(jobs, days=0)


def test_build_daily_activity_rejeita_base_sem_datas():
    jobs = [_job(None, "Backend", "Python")]

    with pytest.raises(ValueError, match="data de publicacao"):
        build_daily_activity(jobs)


def test_build_area_skill_matrix_reordena_ranking_automaticamente():
    jobs = [
        _job(date(2026, 9, 11), "Frontend", "React"),
        _job(date(2026, 9, 11), "Frontend", "React"),
        _job(date(2026, 9, 11), "Frontend", "React"),
        _job(date(2026, 9, 11), "Backend", "Python", "SQL"),
        _job(date(2026, 9, 11), "Backend", "Python"),
        _job(date(2026, 9, 11), "Data", "COBOL"),
    ]

    result = build_area_skill_matrix(jobs, top_areas=2, top_skills=2)

    assert result.areas == ("Frontend", "Backend")
    assert result.area_sizes == (3, 2)
    assert result.skills == ("React", "Python")
    assert result.percentages == ((100.0, 0.0), (0.0, 100.0))


def test_build_area_skill_matrix_rejeita_base_sem_skills():
    jobs = [_job(date(2026, 9, 11), "Backend")]

    with pytest.raises(ValueError, match="habilidades"):
        build_area_skill_matrix(jobs)


def test_funcoes_de_grafico_rejeitam_lista_vazia(tmp_path):
    daily_path = tmp_path / "daily.svg"
    heatmap_path = tmp_path / "heatmap.svg"

    with pytest.raises(ValueError):
        chart_daily_jobs_and_skills([], daily_path)
    with pytest.raises(ValueError):
        chart_area_skill_heatmap([], heatmap_path)


def test_export_readme_charts_gera_dois_svgs(tmp_path):
    jobs = [
        _job(date(2026, 9, 10), "Backend", "Python", "SQL"),
        _job(date(2026, 9, 11), "Frontend", "React", "JavaScript"),
    ]

    files = export_readme_charts(jobs, tmp_path)

    assert set(files) == {"daily", "heatmap"}
    assert files["daily"].name == "vagas-habilidades-30d.svg"
    assert files["heatmap"].name == "areas-habilidades.svg"
    assert all(path.exists() and path.stat().st_size > 0 for path in files.values())


def test_export_readme_charts_sem_vagas_nao_gera_arquivos(tmp_path):
    result = export_readme_charts([], tmp_path)

    assert result == {}
