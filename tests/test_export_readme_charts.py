"""Testes da publicacao dos graficos usados no README."""

from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import yaml

from api.database import connect_sqlite, init_db
from scraper.charts import ChartJob
from scripts import export_readme_charts
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
    init_db(db_path=db_path)

    with pytest.raises(ValueError, match="nao contem vagas"):
        export_pages_charts(tmp_path / "assets", db_path)


def test_cli_grafico_respeita_dia_da_rodada_sem_alterar_banco(tmp_path, csv_vagas_minimo):
    db_path = tmp_path / "vagas.db"
    output_dir = tmp_path / "assets"
    importar(csv_vagas_minimo, db_path=db_path)
    with closing(connect_sqlite(db_path)) as conn, conn:
        conn.execute("UPDATE vagas SET published_date = '2026-10-06'")
        conn.execute(
            "INSERT INTO vagas (source,external_id,title,area,published_date,enrich_encerrada) "
            "VALUES ('linkedin','future','Dev Junior','Backend','2026-10-07',0)"
        )
    before = db_path.read_bytes()

    exit_code = export_readme_charts.main([
        "--db", str(db_path), "--output-dir", str(output_dir), "--dia", "2026-10-06",
    ])
    svg = (output_dir / "vagas-habilidades-30d.svg").read_text(encoding="utf-8")

    assert exit_code == 0
    assert "publicações até 06/10/2026" in svg
    assert "Base: 2 vagas" in svg
    assert db_path.read_bytes() == before


def test_grafico_padrao_usa_dia_de_brasilia(monkeypatch, tmp_path):
    instante = datetime(2026, 10, 7, 0, 35, tzinfo=timezone.utc)
    references = []

    class DataFixa(datetime):
        @classmethod
        def now(cls, tz=None):
            return instante.astimezone(tz) if tz else instante.replace(tzinfo=None)

    def exportar(jobs, output_dir, *, reference_date):
        references.append(reference_date)
        return {"daily": output_dir / "daily.svg"}

    monkeypatch.setattr(export_readme_charts, "datetime", DataFixa)
    monkeypatch.setattr(export_readme_charts, "load_chart_jobs", lambda path: [ChartJob(None, "Backend")])
    monkeypatch.setattr(export_readme_charts, "export_readme_charts", exportar)

    export_pages_charts(tmp_path)

    assert references == [date(2026, 10, 6)]


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
    assert 'python scripts/export_readme_charts.py --output-dir _site/assets --dia "$DIA_RESUMO"' in content


def test_cron_sem_rodada_valida_e_tratado_como_manual():
    content = DAILY_WORKFLOW.read_text(encoding="utf-8")

    assert 'EXECUCAO="manual"' in content
    assert 'RODADA_EXECUCAO="manual"' in content
    assert 'export RODADA="manual"' in content
    assert 'if [ "$EXECUCAO" = "cron" ]; then' in content


def test_deploy_de_codigo_preserva_graficos_publicados():
    workflow = PAGES_WORKFLOWS[1]
    content = workflow.read_text(encoding="utf-8")

    assert 'if [ "$ATUALIZAR_GRAFICOS" = "true" ]; then' in content
    assert "else\n" in content
    assert "https://diasgarcia.github.io/tech-skills-br/assets/${arquivo}" in content


def test_deploy_permite_regerar_graficos_sem_coleta():
    content = PAGES_WORKFLOWS[1].read_text(encoding="utf-8")
    workflow = yaml.safe_load(content)
    option = workflow[True]["workflow_dispatch"]["inputs"]["atualizar_graficos"]
    build = next(step for step in workflow["jobs"]["build"]["steps"] if step.get("id") == "snapshot")
    generation, preservation = build["run"].split("else\n", 1)

    assert option["type"] == "boolean"
    assert option["default"] is False
    assert build["env"]["ATUALIZAR_GRAFICOS"] == "${{ inputs.atualizar_graficos }}"
    assert "'matplotlib==3.11.1'" in generation
    assert "python scripts/export_readme_charts.py --output-dir _site/assets --db data/vagas.db" in generation
    assert "curl --fail" in preservation
    assert "python main.py" not in content
    assert "scripts/import_csv.py" not in content
    assert "scripts/export_kaggle.py" not in content


def test_deploy_estatico_nao_participa_do_fluxo_de_snapshots():
    content = PAGES_WORKFLOWS[1].read_text(encoding="utf-8")

    assert "gh release download latest --pattern 'vagas.db'" in content
    assert "python scripts/export_pages_data.py --db data/vagas.db" in content
    assert "scripts/release_snapshot.py" not in content
    assert "pip install -r requirements.txt" not in content


def test_enriquecimento_manual_atualiza_relatorio_e_graficos():
    content = PAGES_WORKFLOWS[2].read_text(encoding="utf-8")

    assert "python scripts/report_db.py" in content
    assert "python scripts/export_readme_charts.py --output-dir _site/assets" in content
    assert "git add docs/relatorios/*.md" in content


def test_readme_referencia_os_assets_estaveis():
    content = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "/assets/vagas-habilidades-30d.svg" in content
    assert "/assets/areas-habilidades.svg" in content
