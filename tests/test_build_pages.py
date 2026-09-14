from pathlib import Path

from bs4 import BeautifulSoup

from scripts.build_pages import API_FILES, build_pages


def test_artefato_contem_recursos_referenciados_e_preserva_graficos(tmp_path):
    api = tmp_path / "api"
    api.mkdir()
    for name in API_FILES:
        (api / name).write_text("{}", encoding="utf-8")
    output = tmp_path / "site"
    (output / "assets").mkdir(parents=True)
    (output / "assets" / "grafico.svg").write_text("<svg/>", encoding="utf-8")

    build_pages(output, api_dir=api)
    page = BeautifulSoup((output / "index.html").read_text(encoding="utf-8"), "html.parser")

    for tag in page.select("link[href], script[src]"):
        relative = tag.get("href") or tag.get("src")
        assert not Path(relative).is_absolute()
        assert (output / relative).is_file()
    assert (output / "assets" / "grafico.svg").is_file()
    assert set(path.name for path in (output / "api").iterdir()) == set(API_FILES)
