"""Testes dos graficos SVG publicados no README."""

from datetime import date

import pytest

from scraper import charts
from scraper.charts import (
    ChartJob,
    build_area_skill_matrix,
    build_daily_activity,
    build_skill_presence,
    chart_area_skill_heatmap,
    chart_daily_jobs_and_skills,
    chart_skill_presence,
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


def test_build_daily_activity_data_futura_nao_adianta_dia_da_rodada():
    jobs = [
        _job(date(2026, 10, 5), "Backend", "Python"),
        _job(date(2026, 10, 6), "Data", "SQL"),
        _job(date(2026, 10, 7), "Frontend", "React"),
    ]

    result = build_daily_activity(jobs, days=2, reference_date=date(2026, 10, 6))

    assert result.dates == (date(2026, 10, 5), date(2026, 10, 6))
    assert result.jobs == (1, 1)
    assert result.skills == (1, 1)
    assert result.total_jobs == 3
    assert result.period_jobs == 2
    assert result.period_skills == 2
    assert jobs[-1].published_date == date(2026, 10, 7)


def test_build_daily_activity_so_datas_futuras_nao_contam_no_periodo():
    jobs = [_job(date(2026, 10, 7), "Backend", "Python")]

    result = build_daily_activity(jobs, days=2, reference_date=date(2026, 10, 6))

    assert result.last_date == date(2026, 10, 6)
    assert result.jobs == (0, 0)
    assert result.skills == (0, 0)
    assert result.total_jobs == 1


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


def test_heatmap_padrao_mostra_dez_areas_e_quinze_habilidades(tmp_path):
    jobs = [
        _job(date(2026, 10, 10), f"Área {index:02}", f"Skill {index:02}")
        for index in range(18)
    ]
    output_path = tmp_path / "heatmap.svg"

    matrix = build_area_skill_matrix(jobs, top_areas=10, top_skills=15)
    chart_area_skill_heatmap(jobs, output_path)
    svg = output_path.read_text(encoding="utf-8")

    assert len(matrix.areas) == 10
    assert len(matrix.skills) == 15
    assert "10 maiores áreas × 15 habilidades" in svg
    assert "Área 09" in svg and "Skill 14" in svg
    assert "Área 10" not in svg and "Skill 15" not in svg
    assert 'width="864pt"' in svg
    assert 'height="712.8pt"' in svg


def test_heatmap_rotula_dimensoes_reais_em_base_pequena(tmp_path):
    jobs = [_job(date(2026, 10, 10), "Backend", "Python", "SQL")]
    output_path = tmp_path / "heatmap.svg"

    chart_area_skill_heatmap(jobs, output_path)
    svg = output_path.read_text(encoding="utf-8")

    assert "1 maior área × 2 habilidades" in svg


def test_heatmap_mostra_zero_percentual_sem_travessao(tmp_path):
    jobs = [
        _job(date(2026, 10, 10), "Backend", "Python"),
        _job(date(2026, 10, 10), "Data", "SQL"),
    ]
    output_path = tmp_path / "heatmap.svg"

    chart_area_skill_heatmap(jobs, output_path)
    svg = output_path.read_text(encoding="utf-8")

    assert svg.count(">0,0%</text>") == 2
    assert "—" not in svg


def test_funcoes_de_grafico_rejeitam_lista_vazia(tmp_path):
    daily_path = tmp_path / "daily.svg"
    heatmap_path = tmp_path / "heatmap.svg"
    presence_path = tmp_path / "presence.svg"

    with pytest.raises(ValueError):
        chart_daily_jobs_and_skills([], daily_path)
    with pytest.raises(ValueError):
        chart_area_skill_heatmap([], heatmap_path)
    with pytest.raises(ValueError):
        chart_skill_presence([], presence_path)


def test_export_readme_charts_gera_tres_svgs(tmp_path):
    jobs = [
        _job(date(2026, 9, 10), "Backend", "Python", "SQL"),
        _job(date(2026, 9, 11), "Frontend", "React", "JavaScript"),
    ]

    files = export_readme_charts(jobs, tmp_path)

    assert set(files) == {"daily", "heatmap", "presence"}
    assert files["daily"].name == "vagas-habilidades-30d.svg"
    assert files["heatmap"].name == "areas-habilidades.svg"
    assert files["presence"].name == "skills-presenca-vagas.svg"
    assert all(path.exists() and path.stat().st_size > 0 for path in files.values())


def test_export_readme_charts_sem_vagas_nao_gera_arquivos(tmp_path):
    result = export_readme_charts([], tmp_path)

    assert result == {}


def test_presenca_media_inclui_todas_as_areas_e_vagas_sem_skills():
    jobs = [
        _job(None, "Grande", "Hardware", "Hardware", "Inglês"),
        _job(None, "Grande", "Hardware"),
        _job(None, "Grande", "Hardware"),
        _job(None, "Grande"),
        _job(None, "Pequena", "Inglês"),
        _job(None, "Sem habilidades"),
    ]

    rows = build_skill_presence(jobs)

    assert [row.name for row in rows] == ["Inglês", "Hardware"]
    assert [row.jobs for row in rows] == [2, 3]
    assert [row.mean_percent for row in rows] == pytest.approx([125 / 3, 25])


def test_presenca_seleciona_quinze_mais_citadas_antes_de_ordenar_por_media():
    jobs = [
        _job(None, "Grande", *(f"Skill {index:02}" for index in range(16)))
        for _ in range(3)
    ] + [_job(None, "Pequena", "Rara")]

    rows = build_skill_presence(jobs)

    assert len(rows) == 15
    assert [row.name for row in rows] == [f"Skill {index:02}" for index in range(15)]
    assert all(row.jobs == 3 and row.mean_percent == 50 for row in rows)


def test_presenca_reordena_com_novos_dados_sem_fixar_ingles():
    jobs = [_job(None, "Backend", "Inglês"), _job(None, "Frontend", "Python")]

    before = build_skill_presence(jobs)
    after = build_skill_presence(jobs + [_job(None, "Backend", "Python")])

    assert [row.name for row in before] == ["Inglês", "Python"]
    assert [row.name for row in after] == ["Python", "Inglês"]


@pytest.mark.parametrize(
    "maximum,percentage,expected",
    [(21.95, True, 25), (90, True, 100), (100, True, 100),
     (2218, False, 2500), (25000, False, 30000), (0, False, 1), (1, False, 2)],
)
def test_escalas_adaptam_limites_e_divisoes(maximum, percentage, expected):
    fig, ax = charts.plt.subplots()

    charts._automatic_scale(ax, maximum, percentage=percentage)
    lower, upper = ax.get_ylim()
    ticks = [tick for tick in ax.get_yticks() if lower <= tick <= upper]
    charts.plt.close(fig)

    assert lower == 0 and upper == expected
    assert len(ticks) <= 11
    assert percentage or all(tick == int(tick) for tick in ticks)


def test_presenca_gera_svg_sem_anotacoes_e_com_nomes_em_uma_linha(tmp_path, monkeypatch):
    jobs = [_job(None, "Backend", "Inglês", "Banco de Dados")]
    output_path = tmp_path / "presence.svg"
    fig, ax = charts.plt.subplots()
    monkeypatch.setattr(charts.plt, "subplots", lambda **kwargs: (fig, ax))

    chart_skill_presence(jobs, output_path)
    svg = output_path.read_text(encoding="utf-8")

    assert "Habilidades: volume e presença" in svg
    assert "2 skills mais citadas" in svg
    assert "Banco de Dados" in svg and "Inglês" in svg
    assert "Presença média por área" in svg and "Vagas com a skill" in svg
    assert all(not axis.texts for axis in fig.axes)
    assert all("\n" not in label.get_text() for label in ax.get_xticklabels())
