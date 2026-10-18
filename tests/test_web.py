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


def test_kpi_identifica_a_skill_com_maior_presenca():
    page = BeautifulSoup(INDEX_PATH.read_text(encoding="utf-8"), "html.parser")

    card = page.find(id="kpi-top-skill").parent

    assert card.find(class_="card-title").get_text() == "Skill com maior presença"


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


def test_detalhes_da_vaga_usam_dialog_com_titulo_e_botao_de_fechar():
    page = BeautifulSoup(INDEX_PATH.read_text(encoding="utf-8"), "html.parser")

    dialog = page.find("dialog", id="job-details")

    assert dialog["aria-labelledby"] == "job-details-title"
    assert dialog.find("h2", id="job-details-title") is not None
    assert dialog.find("button", attrs={"aria-label": "Fechar detalhes"}) is not None


def test_detalhes_ocultam_fechar_apenas_no_hover():
    content = INDEX_PATH.with_name("styles.css").read_text(encoding="utf-8")

    assert ".job-details:not(:modal) .job-details-close { display: none; }" in content


def test_link_das_vagas_fica_na_ultima_coluna_tambem_no_mobile():
    page = BeautifulSoup(INDEX_PATH.read_text(encoding="utf-8"), "html.parser")

    headers = page.find("table", id="table-vagas").find_all("th")

    assert headers[-2].get_text() == "Local / Mod."
    assert headers[-1].get_text() == "Link"
    assert "job-link-col" in headers[-1]["class"]
    assert "hide-mobile" not in headers[-1]["class"]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js necessário para os testes offline do DOM")
@pytest.mark.parametrize("filename", ["web_runtime.cjs", "analytics_runtime.cjs"])
def test_renderizacao_interacao_e_recuperacao_sem_rede(filename):
    script = Path(__file__).with_name(filename)

    result = subprocess.run(
        [shutil.which("node"), "--test", str(script)],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_analytics_tem_consentimento_e_preferencias_sem_tag_remota_no_html():
    page = BeautifulSoup(INDEX_PATH.read_text(encoding="utf-8"), "html.parser")

    panel = page.find("dialog", id="analytics-consent")
    scripts = [script.get("src") for script in page.find_all("script")]

    assert panel["aria-labelledby"] == "analytics-title"
    assert panel.find("button", id="analytics-accept") is not None
    assert panel.find("button", id="analytics-reject") is not None
    assert page.find("footer").find("button", id="analytics-preferences") is not None
    assert scripts == ["analytics.js", "app.js"]
    assert "googletagmanager.com" not in INDEX_PATH.read_text(encoding="utf-8")
