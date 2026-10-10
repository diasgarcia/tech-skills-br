from pathlib import Path
import os
import shutil
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
PAGES_JOBS = [
    ("daily_scraper.yml", "scrape-and-update", "deploy-pages", "consolidation"),
    ("enrich_manual.yml", "enrich", "deploy-pages", "snapshot"),
    ("deploy_pages.yml", "build", "deploy", "snapshot"),
]


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
    assert content.count('--dia "$DIA_RESUMO"') == 3
    assert content.index("collection_health.py record") < content.index("scripts/resumo_commit.py")


@pytest.mark.parametrize("workflow,producer_id,deploy_id,step_id", PAGES_JOBS)
def test_pages_nao_mantem_o_banco_bloqueado(workflow, producer_id, deploy_id, step_id):
    payload = yaml.safe_load((WORKFLOW_DIR / workflow).read_text(encoding="utf-8"))
    producer = payload["jobs"][producer_id]
    deploy = payload["jobs"][deploy_id]

    assert "concurrency" not in payload
    assert producer["concurrency"] == {"group": "vagas-snapshot-latest", "cancel-in-progress": False}
    assert "environment" not in producer
    assert deploy["needs"] == producer_id
    assert deploy["concurrency"] == {"group": "vagas-pages-deploy", "cancel-in-progress": False}
    assert deploy["environment"]["name"] == "github-pages"
    assert producer["outputs"]["snapshot_id"] == f"${{{{ steps.{step_id}.outputs.snapshot_id }}}}"


@pytest.mark.parametrize("workflow,producer_id,deploy_id,step_id", PAGES_JOBS)
def test_pages_confere_snapshot_antes_de_publicar(workflow, producer_id, deploy_id, step_id):
    payload = yaml.safe_load((WORKFLOW_DIR / workflow).read_text(encoding="utf-8"))
    producer = payload["jobs"][producer_id]
    deploy = payload["jobs"][deploy_id]
    capture = next(step for step in producer["steps"] if step.get("id") == step_id)
    guard = next(step for step in deploy["steps"] if step.get("id") == "snapshot")
    publication = next(step for step in deploy["steps"] if step.get("id") == "deployment")

    assert 'echo "snapshot_id=' in capture["run"]
    assert guard["env"]["SNAPSHOT_ESPERADO"] == f"${{{{ needs.{producer_id}.outputs.snapshot_id }}}}"
    assert '--repo "$GITHUB_REPOSITORY" --pattern snapshot.json' in guard["run"]
    assert "jq -er" in guard["run"]
    assert "^[0-9a-f]{64}$" in guard["run"]
    assert publication["if"] == "steps.snapshot.outputs.atual == 'true'"
    assert publication["uses"] == "actions/deploy-pages@v5"
    assert "continue-on-error" not in guard
    assert "continue-on-error" not in publication
    assert deploy.get("permissions", payload.get("permissions"))["contents"] == "read"


def test_publicacao_kaggle_continua_coordenada_com_o_banco():
    payload = yaml.safe_load((WORKFLOW_DIR / "publish_kaggle.yml").read_text(encoding="utf-8"))

    assert payload["concurrency"] == {"group": "vagas-snapshot-latest", "cancel-in-progress": False}


@pytest.mark.parametrize(
    "expected,current,gh_status,jq_status,result,output",
    [
        ("a" * 64, "a" * 64, 0, 0, 0, "atual=true\n"),
        ("a" * 64, "b" * 64, 0, 0, 0, "atual=false\n"),
        ("", "a" * 64, 0, 0, 1, ""),
        ("a" * 64, "a" * 64, 1, 0, 1, ""),
        ("a" * 64, "", 0, 1, 1, ""),
    ],
)
def test_verificacao_pages_nao_mascara_falhas(tmp_path, expected, current, gh_status, jq_status, result, output):
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    bash = str(git_bash) if os.name == "nt" and git_bash.exists() else shutil.which("bash")
    if bash is None:
        pytest.skip("Bash indisponivel para validar o passo do runner Linux.")
    payload = yaml.safe_load((WORKFLOW_DIR / "deploy_pages.yml").read_text(encoding="utf-8"))
    guard = next(step for step in payload["jobs"]["deploy"]["steps"] if step.get("id") == "snapshot")
    output_path = tmp_path / "output"
    env = {
        **os.environ,
        "SNAPSHOT_ESPERADO": expected,
        "SNAPSHOT_TESTE": current,
        "GH_STATUS": str(gh_status),
        "JQ_STATUS": str(jq_status),
        "GITHUB_REPOSITORY": "teste/repo",
        "RUNNER_TEMP": tmp_path.as_posix(),
        "GITHUB_OUTPUT": output_path.as_posix(),
        "GITHUB_STEP_SUMMARY": (tmp_path / "summary").as_posix(),
    }
    mocks = 'gh() { return "$GH_STATUS"; }\njq() { echo "$SNAPSHOT_TESTE"; return "$JQ_STATUS"; }\n'

    completed = subprocess.run(
        [bash, "--noprofile", "--norc", "-e", "-o", "pipefail"],
        input=mocks + guard["run"], env=env, text=True, capture_output=True, timeout=10,
    )

    assert completed.returncode == result, completed.stderr
    assert (output_path.read_text(encoding="utf-8") if output_path.exists() else "") == output
