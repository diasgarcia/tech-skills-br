"""Testes dos caminhos baratos dos graficos (sem renderizar PNG)."""

import pytest

from scraper.charts import (
    chart_areas,
    chart_regions,
    chart_skills,
    chart_workplace,
    export_charts,
)
from scraper.models import Job


def _vaga(area="Backend", skills=None):
    return Job(
        source="t",
        external_id="1",
        title="Desenvolvedor Júnior",
        area=area,
        skills=skills or [],
    )


def test_chart_areas_sem_vagas_levanta_erro(tmp_path):
    with pytest.raises(ValueError):
        chart_areas([], tmp_path / "x.png")


def test_chart_workplace_sem_vagas_levanta_erro(tmp_path):
    with pytest.raises(ValueError):
        chart_workplace([], tmp_path / "x.png")


def test_chart_regions_sem_vagas_levanta_erro(tmp_path):
    with pytest.raises(ValueError):
        chart_regions([], tmp_path / "x.png")


def test_chart_skills_devolve_none_quando_nenhuma_area_informa_tecnologia(tmp_path):
    assert chart_skills([_vaga()], tmp_path / "skills.png") is None
    assert chart_skills([], tmp_path / "skills.png") is None


def test_export_charts_sem_vagas_devolve_dicionario_vazio(tmp_path):
    assert export_charts([], tmp_path, "stamp") == {}
