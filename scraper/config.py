"""Configuracao central do projeto.

Tudo que voce provavelmente vai querer ajustar (termos de busca, delays, caminhos)
esta neste arquivo ou nos YAMLs em `scraper/rules/`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

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
    "tech-skills-br/1.0 (pesquisa academica PIBIC - mapeamento de skills tech) python-requests"
)



# Termos usados na busca. Cada termo vira uma consulta separada em cada portal.
SEARCH_TERMS: list[str] = [
    "desenvolvedor junior",
    "desenvolvedor jr",
    "programador junior",
    "analista de sistemas junior",
    "estagio desenvolvimento",
    "estagio ti",
    "estagio tecnologia",
    "trainee tecnologia",
    "engenheiro de dados junior",
    "analista de dados junior",
    "qa junior",
    "devops junior",
    "suporte tecnico junior",
]


@dataclass
class Settings:
    """Parametros de execucao. Sobrescritos pela CLI em `main.py`."""

    search_terms: list[str] = field(default_factory=lambda: list(SEARCH_TERMS))
    # Todos os portais que funcionam hoje. Ver `scraper/sources/__init__.py`.
    sources: list[str] = field(
        default_factory=lambda: [
            "gupy",
            "vagas",
            "programathor",
            "trampos",
            "linkedin",
        ]
    )


    # Escopo geografico / polos (padrao: "todos")
    locations: list[str] = field(default_factory=lambda: ["todos"])
    output_dir: Path = DEFAULT_OUTPUT_DIR


    # Chaves de API para fontes especializadas
    theirstack_api_key: str = field(
        default_factory=lambda: os.getenv("THEIRSTACK_API_KEY", "")
    )
    serpapi_api_key: str = field(
        default_factory=lambda: os.getenv("SERPAPI_API_KEY", "")
    )

    # Educacao com o servidor
    delay_seconds: float = 1.5
    timeout_seconds: float = 30.0
    max_retries: int = 3
    backoff_factor: float = 1.5
    user_agent: str = USER_AGENT

    # Limites de coleta
    page_size: int = 100  # a API da Gupy rejeita limit > 100 (HTTP 400)
    start_page: int = 1
    max_pages_per_term: int = 15



    # Filtros
    only_junior: bool = True

    def ensure_output_dir(self) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        return self.output_dir

