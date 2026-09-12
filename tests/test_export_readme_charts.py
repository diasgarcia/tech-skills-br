"""Testes da publicacao dos graficos usados no README."""

from pathlib import Path

import pytest

from scripts.export_readme_charts import export_pages_charts, load_chart_jobs
from scripts.import_csv import importar


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = (
    ROOT / ".github" / "workflows" / "daily_scraper.yml",
    ROOT / ".github" / "workflows" / "deploy_pages.yml",
    ROOT / ".github" / "workflows" / "enrich_manual.yml",
)


def test_export_pages_charts_carrega_banco_e_gera_svgs(
    tmp_path, csv_vagas_minimo
):
    db_path = tmp_path / "vagas.db"
    output_dir = tmp_path / "assets"
    importar(csv_vagas_minimo, db_path=db_path)

    jobs = load_chart_jobs(db_path)
    files = export_pages_charts(output_dir, db_path)

    assert len(jobs) == 1
    assert set(files) == {"daily", "heatmap"}
    assert files["daily"] == output_dir / "vagas-habilidades-30d.svg"
    assert files["heatmap"] == output_dir / "areas-habilidades.svg"
    assert all(path.exists() and path.stat().st_size > 0 for path in files.values())


def test_export_pages_charts_rejeita_banco_vazio(tmp_path):
    db_path = tmp_path / "vazio.db"

    with pytest.raises(ValueError, match="nao contem vagas"):
        export_pages_charts(tmp_path / "assets", db_path)


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_todo_deploy_do_pages_gera_os_graficos(workflow):
    content = workflow.read_text(encoding="utf-8")

    assert "python scripts/export_readme_charts.py --output-dir _site/assets" in content


def test_readme_referencia_os_assets_estaveis():
    content = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "/assets/vagas-habilidades-30d.svg" in content
    assert "/assets/areas-habilidades.svg" in content
