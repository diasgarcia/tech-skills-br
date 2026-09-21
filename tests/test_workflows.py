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
