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

    assert metadata["id"] == "rafaeldiasgarcia/tech-skills-brasil-an-lise-di-ria"
    assert metadata["code_file"] == NOTEBOOK_PATH.name
    assert metadata["kernel_type"] == "notebook"
    assert metadata["dataset_sources"] == ["rafaeldiasgarcia/tech-skills-br"]


def test_notebook_e_json_valido_e_codigo_compila() -> None:
    notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    codigo = "\n\n".join(
        "".join(cell["source"])
        for cell in notebook["cells"]
        if cell["cell_type"] == "code"
    )

    assert notebook["nbformat"] == 4
    assert "/kaggle/input/tech-skills-br/vagas.parquet" in codigo
    assert '.str.split(";")' in codigo
    compile(codigo, str(NOTEBOOK_PATH), "exec")
