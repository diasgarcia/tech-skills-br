from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"


def test_workflows_sao_yaml_validos():
    for path in WORKFLOW_DIR.glob("*.yml"):
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict), path.name
        assert payload.get("jobs"), path.name


def test_workflows_usam_actions_compativeis_com_node_24():
    content = "\n".join(
        path.read_text(encoding="utf-8") for path in WORKFLOW_DIR.glob("*.yml")
    )

    assert "actions/checkout@v4" not in content
    assert "actions/setup-python@v5" not in content
    assert "actions/setup-node@v4" not in content
    assert "actions/upload-artifact@v4" not in content
    assert "actions/upload-pages-artifact@v3" not in content
    assert "actions/deploy-pages@v4" not in content
    assert "actions/configure-pages@v5" not in content


def test_ci_mantem_apenas_python_312():
    content = (WORKFLOW_DIR / "ci.yml").read_text(encoding="utf-8")

    assert "python-version: \"3.12\"" in content
    assert "matrix.python-version" not in content


def test_coleta_diaria_valida_qualidade_e_registra_frescor_antes_da_release():
    content = (WORKFLOW_DIR / "daily_scraper.yml").read_text(encoding="utf-8")

    assert "--quality-gate" in content
    assert "python scripts/collection_health.py check" in content
    assert "python scripts/collection_health.py record" in content
    assert content.index("collection_health.py check") < content.index("scripts/import_csv.py")
    assert content.index("collection_health.py record") < content.index("release_snapshot.py publish")


def test_coleta_diaria_preserva_metricas_e_nao_mascara_falhas_com_tee():
    content = (WORKFLOW_DIR / "daily_scraper.yml").read_text(encoding="utf-8")

    assert content.count("set -o pipefail") == 2
    assert "output/collection_metrics.json" in content
    assert "status --max-age-hours 24 --warn-only)" in content


def test_falha_de_fonte_so_encerra_workflow_depois_do_pages():
    content = (WORKFLOW_DIR / "daily_scraper.yml").read_text(encoding="utf-8")
    jobs = yaml.safe_load(content)["jobs"]
    collection = jobs["scrape-and-update"]
    final = jobs["report-source-errors"]
    consolidation = next(step for step in collection["steps"] if step.get("id") == "consolidation")
    recovery = next(step for step in collection["steps"] if step.get("if", "").startswith("failure()"))

    assert jobs["deploy-pages"]["needs"] == "scrape-and-update"
    assert final["needs"] == ["scrape-and-update", "deploy-pages"]
    assert "!cancelled()" in final["if"]
    assert "needs.scrape-and-update.result == 'success'" in final["if"]
    assert "needs.scrape-and-update.outputs.has_source_errors == 'true'" in final["if"]
    assert collection["outputs"]["has_source_errors"] == "${{ steps.consolidation.outputs.has_source_errors }}"
    assert "scripts/collection_health.py check" in consolidation["run"]
    assert "scripts/release_snapshot.py publish" in consolidation["run"]
    assert "scripts/export_kaggle.py" in consolidation["run"]
    assert "has_source_errors == 'true'" in recovery["if"]
    assert "::error title=Coleta parcial::" in final["steps"][0]["run"]
    assert final["steps"][0]["run"].rstrip().endswith("exit 1")
    assert "continue-on-error" not in final["steps"][0]


def test_commit_diario_recebe_o_mesmo_dia_de_brasilia_usado_no_titulo():
    content = (WORKFLOW_DIR / "daily_scraper.yml").read_text(encoding="utf-8")

    assert "TZ=America/Sao_Paulo date +'DATA_HOJE=%d/%m/%Y%nDIA_RESUMO=%Y-%m-%d'" in content
    assert '--dia "$DIA_RESUMO"' in content
    assert 'python scripts/report_db.py --dia "$DIA_RESUMO"' in content
    assert content.count('--dia "$DIA_RESUMO"') == 2
    assert content.index("collection_health.py record") < content.index("scripts/resumo_commit.py")
