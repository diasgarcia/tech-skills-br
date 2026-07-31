"""Vocabulario controlado da API, lido dos mesmos YAMLs que o scraper usa.

As areas e as tecnologias validas nao sao redigitadas aqui: vem de
`scraper/rules/areas.yml` e `scraper/rules/skills.yml`. Editar o YAML muda o
scraper e a API juntos, que e a premissa do projeto.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache

import yaml

from scraper.config import RULES_DIR
from scraper.models import WORKPLACE_ORDER


@lru_cache(maxsize=1)
def areas() -> list[str]:
    """As 10 areas: as 9 declaradas no YAML mais a area de fallback."""
    with open(RULES_DIR / "areas.yml", encoding="utf-8") as fh:
        rules = yaml.safe_load(fh) or {}
    declared = list((rules.get("areas") or {}).keys())
    fallback = (rules.get("settings") or {}).get("fallback_area")
    if fallback and fallback not in declared:
        declared.append(fallback)
    return declared


@lru_cache(maxsize=1)
def technologies() -> dict[str, str]:
    """{nome canonico: grupo}, na ordem em que aparecem no YAML."""
    with open(RULES_DIR / "skills.yml", encoding="utf-8") as fh:
        rules = yaml.safe_load(fh) or {}
    return {
        name: group
        for group, entries in (rules or {}).items()
        for name in (entries or {})
    }


@lru_cache(maxsize=1)
def workplace_types() -> list[str]:
    return list(WORKPLACE_ORDER)


@lru_cache(maxsize=1)
def sources() -> list[str]:
    from scraper.sources import AVAILABLE_SOURCES

    return list(AVAILABLE_SOURCES)


def _enum(name: str, values: list[str]) -> type[Enum]:
    """Enum de strings para o FastAPI validar (422) e documentar sozinho.

    Os nomes dos membros sao irrelevantes -- o que vai para a query string e
    para o /docs sao os valores.
    """
    members = {f"V{i}": value for i, value in enumerate(values)}
    return Enum(name, members, type=str)  # type: ignore[return-value]


AreaEnum = _enum("AreaEnum", areas())
ModalidadeEnum = _enum("ModalidadeEnum", workplace_types())
FonteEnum = _enum("FonteEnum", sources())
