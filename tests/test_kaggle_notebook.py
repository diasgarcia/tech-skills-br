"""Valida os arquivos usados para publicar o notebook no Kaggle."""

from __future__ import annotations

import json
from pathlib import Path
import pathlib
import sys
from types import ModuleType

import pytest


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


@pytest.mark.parametrize("relative_path", [
    "tech-skills-br/vagas.parquet",
    "datasets/rafaeldiasgarcia/tech-skills-br/vagas.parquet",
    "outra-pasta/vagas.parquet",
])
def test_celulas_executam_com_parquet_categorico_nulos_e_caminhos_kaggle(tmp_path, monkeypatch, relative_path):
    import matplotlib.pyplot as plt
    import pandas as pd

    from scripts.export_kaggle import _aplicar_tipos_vagas

    input_dir = tmp_path / "input"
    data_path = input_dir / relative_path
    data_path.parent.mkdir(parents=True)
    columns = ["source", "external_id", "title", "company", "skills", "area", "seniority",
               "workplace_type", "location", "regiao", "polo", "published_date", "description",
               "url", "search_term", "enrich_encerrada"]
    frame = pd.DataFrame([
        ["gupy", "01", "Dev", "A", "Python; SQL", "Backend", "Júnior", "Remoto", None,
         None, None, "2026-09-01", None, "https://example.test/1", None, False],
        ["linkedin", "01", "Dev", "B", "Python", None, None, None, None,
         None, None, None, None, "https://example.test/2", None, True],
        ["gupy", "02", "Dev", None, None, "Frontend", None, None, None,
         None, None, "2026-09-02", None, "https://example.test/3", None, False],
    ], columns=columns)
    _aplicar_tipos_vagas(frame).to_parquet(data_path, index=False)
    rendered = []
    ipython = ModuleType("IPython")
    ipython.get_ipython = lambda: None
    ipython.version_info = (9, 0)
    display_module = ModuleType("IPython.display")
    display_module.Markdown = str
    display_module.display = rendered.append
    monkeypatch.setitem(sys.modules, "IPython", ipython)
    monkeypatch.setitem(sys.modules, "IPython.display", display_module)
    original_path = Path

    class NotebookPath(type(Path())):
        def __new__(cls, *parts, **kwargs):
            path = original_path(*parts, **kwargs)
            text = path.as_posix()
            if text.startswith("/kaggle/input"):
                return input_dir / text.removeprefix("/kaggle/input").lstrip("/")
            return path

    monkeypatch.setattr(pathlib, "Path", NotebookPath)
    monkeypatch.setattr(plt, "show", lambda: None)
    notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    namespace = {}

    try:
        with pd.option_context("display.max_colwidth", 80, "display.max_rows", 30):
            for index, cell in enumerate(notebook["cells"]):
                if cell["cell_type"] == "code":
                    exec(compile("".join(cell["source"]), f"notebook-cell-{index}", "exec"), namespace)
    finally:
        plt.close("all")

    assert namespace["CAMINHO_DADOS"] == data_path
    assert len(namespace["vagas"]) == 3
    assert len(namespace["analise_skills"]) == 3
    ranking = namespace["ranking_skills"].set_index("skill")
    assert ranking.loc["Python", "vagas"] == 2
    assert ranking.loc["Python", "frequencia_%"] == 100
    assert "Não informada" in namespace["distribuicao_areas"]["área"].values
    assert len(rendered) >= 4
