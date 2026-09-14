"""Configuracao central do projeto.

Tudo que voce provavelmente vai querer ajustar (termos de busca, delays, caminhos)
esta neste arquivo ou nos YAMLs em `scraper/rules/`.
"""

from __future__ import annotations

import os
import math
from dataclasses import dataclass, field
from functools import lru_cache
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


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)




@lru_cache(maxsize=1)
def _collector_rules() -> dict:
    with open(RULES_DIR / "coletores.yml", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_search_terms() -> list[str]:
    """Termos de busca do projeto, declarados em coletores.yml."""
    dados = _collector_rules()
    termos = dados.get("termos") or []
    return [str(t).strip() for t in termos if str(t).strip()]


def load_term_match_rules() -> dict[str, list[str]]:
    """Sinais exigidos nos resultados de buscas textuais muito especificas."""
    dados = _collector_rules()

    regras = dados.get("validacao_de_termos") or {}
    return {
        str(termo).strip(): [
            str(sinal).strip() for sinal in sinais or [] if str(sinal).strip()
        ]
        for termo, sinais in regras.items()
        if str(termo).strip()
    }


# Matriz de delays da rodada padrao, medida em 05/09 (wiki "Limites e
# Bloqueios"). LinkedIn 1.0s (ponto doce; 0.5s sofre backpressure da
# API), InfoJobs 2.0s (bloqueio suave), Vagas.com 2.0s (Cloudflare),
# Solides 2.0s e as demais 1.0s (sem limite observado).
DELAYS_PADRAO: dict[str, float] = {
    "linkedin": 1.0,
    "infojobs": 2.0,
    "vagas": 2.0,
    "solides": 2.0,
    "gupy": 1.0,
    "trampos": 1.0,
    "geekhunter": 1.0,
    "abler": 1.0,
    "recrutei": 1.0,
}



@dataclass
class Settings:
    """Parametros de execucao. Sobrescritos pela CLI em `main.py`."""

    search_terms: list[str] = field(default_factory=load_search_terms)
    term_match_rules: dict[str, list[str]] = field(default_factory=load_term_match_rules)
    sources: list[str] = field(default_factory=lambda: default_sources())

    output_dir: Path = DEFAULT_OUTPUT_DIR

    delay_seconds: float = 1.0
    timeout_seconds: float = 30.0
    max_retries: int = 3
    backoff_factor: float = 1.5
    user_agent: str = USER_AGENT

    # Delay por fonte: sobrescreve o delay padrao para a fonte indicada.
    # A matriz e o padrao da rodada (medido em 05/09, ver a wiki
    # "Limites e Bloqueios"): LinkedIn 1.0s (ponto doce; 0.5s sofre
    # backpressure), InfoJobs e Vagas.com 2.0s (bloqueio suave e
    # Cloudflare), Solides 2.0s e as demais 1.0s. Os flags da CLI
    # sobrescrevem por cima quando usados.
    source_delays: dict[str, float] = field(
        default_factory=lambda: dict(DELAYS_PADRAO)
    )

    # Coleta paralela entre fontes: cada fonte roda em thread propria
    # com sessao propria; o delay vale por dominio. Padrao da rodada.
    parallel_sources: bool = True

    page_size: int = 100  # a API da Gupy rejeita limit > 100 (HTTP 400)
    start_page: int = 1
    max_pages_per_term: int = 15

    # Abler: janela de recencia do sitemap (lastmod). Padrao 1 = ultimas
    # 24h (rodada diaria); a coleta completa usa um valor grande via
    # --abler-days. O corte de 2026 (data minima do projeto) vale sempre.
    abler_days_back: int = 1

    # Recrutei: janela de recencia do sitemap (padrao 24h na rodada
    # diaria). A coleta completa usa --recrutei-full (paginacao SSR da
    # listagem, que expoe todas as vagas ativas; o sitemap cobre so as
    # ~1.000 mais recentes).
    recrutei_days_back: int = 1
    recrutei_full: bool = False

    only_junior: bool = True

    # Se False, o pipeline nao busca descricoes do LinkedIn durante a coleta.
    # Util no fluxo agendado, onde o enriquecimento roda depois da importacao
    # (so para vagas pendentes, via scripts/enrich_descriptions.py).
    enrich_linkedin: bool = True

    def __post_init__(self) -> None:
        for name in ("page_size", "start_page", "max_pages_per_term", "abler_days_back", "recrutei_days_back"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} deve ser maior que zero.")
        if self.page_size > 100:
            raise ValueError("page_size deve ser no maximo 100.")
        for name in ("delay_seconds", "timeout_seconds", "backoff_factor"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0 or (name == "timeout_seconds" and value == 0):
                raise ValueError(f"{name} possui valor invalido.")
        if self.max_retries < 0:
            raise ValueError("max_retries nao pode ser negativo.")
        if any(not math.isfinite(delay) or delay < 0 for delay in self.source_delays.values()):
            raise ValueError("O atraso por fonte deve ser um numero finito nao negativo.")

    def ensure_output_dir(self) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        return self.output_dir


def default_sources() -> list[str]:
    from scraper.sources import DEFAULT_SOURCES

    return list(DEFAULT_SOURCES)

