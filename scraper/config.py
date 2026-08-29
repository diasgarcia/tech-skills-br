"""Configuracao central do projeto.

Tudo que voce provavelmente vai querer ajustar (termos de busca, delays, caminhos)
esta neste arquivo ou nos YAMLs em `scraper/rules/`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RULES_DIR = Path(__file__).resolve().parent / "rules"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"


def _load_dotenv(env_path: Path | None = None) -> None:
    """Carrega variaveis de .env sem depender obrigatoriamente de python-dotenv."""
    path = env_path or (PROJECT_ROOT / ".env")
    if not path.is_file():
        return
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(path)
    except ImportError:
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if (v.startswith('"') and v.endswith('"')) or (
                        v.startswith("'") and v.endswith("'")
                    ):
                        v = v[1:-1]
                    os.environ.setdefault(k, v)
        except OSError:
            pass


_load_dotenv()

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)




def load_search_terms() -> list[str]:
    """Termos de busca do projeto, declarados em coletores.yml."""
    with open(RULES_DIR / "coletores.yml", encoding="utf-8") as fh:
        dados = yaml.safe_load(fh) or {}
    termos = dados.get("termos") or []
    return [str(t).strip() for t in termos if str(t).strip()]


SEARCH_TERMS: list[str] = load_search_terms()



@dataclass
class Settings:
    """Parametros de execucao. Sobrescritos pela CLI em `main.py`."""

    search_terms: list[str] = field(default_factory=lambda: list(SEARCH_TERMS))
    sources: list[str] = field(
        default_factory=lambda: [
            "gupy",
            "vagas",
            "programathor",
            "trampos",
            "linkedin",
            "solides",
            "geekhunter",
        ]
    )

    output_dir: Path = DEFAULT_OUTPUT_DIR

    delay_seconds: float = 1.5
    timeout_seconds: float = 30.0
    max_retries: int = 3
    backoff_factor: float = 1.5
    user_agent: str = USER_AGENT

    page_size: int = 100  # a API da Gupy rejeita limit > 100 (HTTP 400)
    start_page: int = 1
    max_pages_per_term: int = 15

    only_junior: bool = True

    # Se False, o pipeline nao busca descricoes do LinkedIn durante a coleta.
    # Util no fluxo agendado, onde o enriquecimento roda depois da importacao
    # (so para vagas pendentes, via scripts/enrich_descriptions.py).
    enrich_linkedin: bool = True

    def ensure_output_dir(self) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        return self.output_dir

