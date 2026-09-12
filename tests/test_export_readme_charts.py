"""Testes da publicacao dos graficos usados no README."""

from pathlib import Path

import pytest

from scripts.export_readme_charts import export_pages_charts, load_chart_jobs
from scripts.import_csv import importar


ROOT = Path(__file__).resolve().parents[1]
PAGES_WORKFLOWS = (
    ROOT / ".github" / "workflows" / "daily_scraper.yml",
    ROOT / ".github" / "workflows" / "deploy_pages.yml",
    ROOT / ".github" / "workflows" / "enrich_manual.yml",
)
DAILY_WORKFLOW = PAGES_WORKFLOWS[0]


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


@pytest.mark.parametrize("workflow", PAGES_WORKFLOWS)
def test_todo_deploy_do_pages_inclui_os_graficos(workflow):
    content = workflow.read_text(encoding="utf-8")

    gera = "python scripts/export_readme_charts.py --output-dir _site/assets"
    preserva = "vagas-habilidades-30d.svg areas-habilidades.svg"
    assert gera in content or preserva in content


def test_rodada_3_e_coleta_manual_atualizam_relatorio_e_graficos():
    content = DAILY_WORKFLOW.read_text(encoding="utf-8")

    condition = 'if [ "$EXECUCAO" = "manual" ] || [ "$RODADA_INPUT" = "3" ]; then'
    start = content.index(condition)
    end = content.index("fi", start)
    rodada_3 = content[start:end]

    assert "python scripts/report_db.py" in rodada_3
    assert 'echo "ATUALIZAR_RESUMOS=1"' in rodada_3
    assert content.count("python scripts/report_db.py") == 1
    assert content.count(
        "python scripts/export_readme_charts.py --output-dir _site/assets"
    ) == 1


def test_cron_sem_rodada_valida_e_tratado_como_manual():
    content = DAILY_WORKFLOW.read_text(encoding="utf-8")

    assert 'EXECUCAO="manual"' in content
    assert 'RODADA_EXECUCAO="manual"' in content
    assert 'export RODADA="manual"' in content
    assert 'if [ "$EXECUCAO" = "cron" ]; then' in content


def test_deploy_de_codigo_preserva_graficos_publicados():
    workflow = PAGES_WORKFLOWS[1]
    content = workflow.read_text(encoding="utf-8")

    assert "python scripts/export_readme_charts.py" not in content
    assert "https://diasgarcia.github.io/tech-skills-br/assets/${arquivo}" in content


def test_enriquecimento_manual_atualiza_relatorio_e_graficos():
    content = PAGES_WORKFLOWS[2].read_text(encoding="utf-8")

    assert "python scripts/report_db.py" in content
    assert "python scripts/export_readme_charts.py --output-dir _site/assets" in content
    assert "git add docs/relatorios/*.md" in content


def test_readme_referencia_os_assets_estaveis():
    content = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "/assets/vagas-habilidades-30d.svg" in content
    assert "/assets/areas-habilidades.svg" in content
