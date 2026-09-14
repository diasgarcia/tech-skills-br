"""Testes da pagina estatica publicada no GitHub Pages."""

from pathlib import Path
import shutil
import subprocess

from bs4 import BeautifulSoup
import pytest


INDEX_PATH = Path(__file__).resolve().parents[1] / ".github" / "web" / "index.html"
KAGGLE_DATASET_URL = (
    "https://www.kaggle.com/datasets/rafaeldiasgarcia/tech-skills-br"
)


def test_footer_exibe_links_do_github_e_kaggle():
    content = INDEX_PATH.read_text(encoding="utf-8")
    page = BeautifulSoup(content, "html.parser")
    footer = page.find("footer")
    github = footer.find("a", href="https://github.com/diasgarcia/tech-skills-br")
    kaggle = footer.find("a", href=KAGGLE_DATASET_URL)

    assert github is not None and github.find("svg") is not None
    assert kaggle is not None and kaggle.find("svg") is not None
    assert github.get("aria-label") == "Abrir o projeto no GitHub"
    assert kaggle.get("aria-label") == "Abrir o dataset no Kaggle"


def test_footer_mobile_oculta_rotulos_e_mantem_icones():
    content = INDEX_PATH.read_text(encoding="utf-8") + INDEX_PATH.with_name("styles.css").read_text(encoding="utf-8")

    assert ".footer-link-label { display: none; }" in content
    assert "padding: 3px;\n        color: var(--text-muted);" in content
    assert content.count('class="footer-icon"') == 2


def test_links_do_footer_usam_o_mesmo_destaque_azul():
    content = INDEX_PATH.with_name("styles.css").read_text(encoding="utf-8")

    assert ".footer-link:focus-visible" in content
    assert "color: var(--accent);" in content
    assert ".footer-link-kaggle:hover" not in content


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js necessário para os testes offline do DOM")
def test_renderizacao_interacao_e_recuperacao_sem_rede():
    script = Path(__file__).with_name("web_runtime.cjs")

    result = subprocess.run(
        [shutil.which("node"), "--test", str(script)],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
