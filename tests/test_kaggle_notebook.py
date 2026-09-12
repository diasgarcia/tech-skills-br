"""Valida os arquivos usados para publicar o notebook no Kaggle."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_DIR = ROOT / "notebooks" / "kaggle"
NOTEBOOK_PATH = NOTEBOOK_DIR / "tech-skills-br-analise-diaria.ipynb"
METADATA_PATH = NOTEBOOK_DIR / "kernel-metadata.json"


def test_metadata_vincula_dataset_mais_recente() -> None:
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))

    assert metadata["id_no"] == 133865421
    assert "id" not in metadata
    assert metadata["title"] == "Tech Skills Brasil - Analise diaria"
    assert metadata["code_file"] == NOTEBOOK_PATH.name
    assert metadata["kernel_type"] == "notebook"
    assert metadata["dataset_sources"] == ["rafaeldiasgarcia/tech-skills-br"]


def test_notebook_e_json_valido_e_codigo_compila() -> None:
    notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    celulas_codigo = [
        cell for cell in notebook["cells"] if cell["cell_type"] == "code"
    ]
    codigo = "\n\n".join(
        "".join(cell["source"])
        for cell in celulas_codigo
    )
    compiled = compile(codigo, str(NOTEBOOK_PATH), "exec")

    assert notebook["nbformat"] == 4
    assert all(cell["metadata"].get("_kg_hide-input") is True for cell in celulas_codigo)
    assert all(not cell["metadata"].get("_kg_hide-output", False) for cell in celulas_codigo)
    assert "/kaggle/input/tech-skills-br/vagas.parquet" in codigo
    assert "/kaggle/input/datasets/rafaeldiasgarcia/tech-skills-br/vagas.parquet" in codigo
    assert '.rglob("vagas.parquet")' in codigo
    assert '.str.split(";")' in codigo
    assert 'vagas["area"].astype("string").fillna("Não informada")' in codigo
    assert compiled is not None


def test_workflows_usam_slug_sem_acentos_e_rodada_3_atualiza_notebook() -> None:
    slug = "rafaeldiasgarcia/tech-skills-brasil-analise-diaria"
    old_slug = "rafaeldiasgarcia/tech-skills-brasil-an-lise-di-ria"
    daily = (ROOT / ".github" / "workflows" / "daily_scraper.yml").read_text(
        encoding="utf-8"
    )
    manual = (
        ROOT / ".github" / "workflows" / "publish_kaggle_notebook.yml"
    ).read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert slug in daily
    assert slug in manual
    assert slug in readme
    assert old_slug not in daily + manual + readme
    assert "env.RODADA_EXECUCAO == '3'" in daily
    assert "env.KAGGLE_PRONTO == '1'" in daily
    assert "kaggle kernels push --path notebooks/kaggle --timeout 900" in daily
