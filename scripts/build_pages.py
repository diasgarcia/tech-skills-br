"""Monta os arquivos locais do Pages; o workflow decide quando gerar os graficos."""

import argparse
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
WEB_FILES = ("index.html", "styles.css", "app.js")
API_FILES = ("resumo.json", "areas.json", "tecnologias.json", "vagas.json")


def build_pages(output: Path, *, web_dir: Path = ROOT / ".github/web", api_dir: Path = ROOT / "api/web") -> None:
    inputs = [*(web_dir / name for name in WEB_FILES), *(api_dir / name for name in API_FILES)]
    missing = [str(path) for path in inputs if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Arquivos do site ausentes: {', '.join(missing)}")
    (output / "api").mkdir(parents=True, exist_ok=True)
    (output / "assets").mkdir(exist_ok=True)
    for name in WEB_FILES:
        shutil.copyfile(web_dir / name, output / name)
    for name in API_FILES:
        shutil.copyfile(api_dir / name, output / "api" / name)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "_site")
    args = parser.parse_args(argv)
    build_pages(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
