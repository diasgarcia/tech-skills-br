"""Filtro de senioridade: mantem apenas vagas de entrada (junior/estagio/trainee)."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from .config import RULES_DIR
from .models import Job, normalize


class SeniorityFilter:
    """Decide se um titulo de vaga e de nivel de entrada, com base em `seniority.yml`.

    Modo padrao: um sinal de entrada ("junior", "estagio", ...) faz a vaga passar,
    mesmo que o titulo tambem cite um nivel maior -- e o caso de titulos mistos
    como "Desenvolvedor Junior/Pleno", que ainda aceitam candidatos juniores.

    Modo estrito (`strict=True`): qualquer sinal de senioridade alta descarta a
    vaga, mesmo com sinal de entrada presente. Util para uma contagem conservadora.
    """

    def __init__(self, rules: dict, strict: bool = False) -> None:
        self.strict = strict
        self.include: dict[str, list[re.Pattern]] = {
            label: [re.compile(p) for p in patterns]
            for label, patterns in (rules.get("include") or {}).items()
        }
        self.exclude: list[re.Pattern] = [
            re.compile(p) for p in (rules.get("exclude") or [])
        ]

    @classmethod
    def from_file(cls, path: Path | None = None, strict: bool = False) -> "SeniorityFilter":
        path = path or (RULES_DIR / "seniority.yml")
        with open(path, encoding="utf-8") as fh:
            return cls(yaml.safe_load(fh) or {}, strict=strict)

    def has_senior_signal(self, title: str) -> bool:
        """Titulo cita explicitamente um nivel acima de junior."""
        text = normalize(title)
        return any(p.search(text) for p in self.exclude)

    def label(self, title: str) -> str | None:
        """Devolve o rotulo de senioridade ("Júnior", "Estágio", ...) ou None."""
        text = normalize(title)
        if not text:
            return None

        for label, patterns in self.include.items():
            if any(p.search(text) for p in patterns):
                if self.strict and self.has_senior_signal(title):
                    return None
                return label
        return None

    def is_entry_level(self, title: str) -> bool:
        return self.label(title) is not None


@lru_cache(maxsize=2)
def default_filter(strict: bool = False) -> SeniorityFilter:
    return SeniorityFilter.from_file(strict=strict)


def filter_entry_level(jobs: list[Job], flt: SeniorityFilter | None = None) -> list[Job]:
    """Mantem apenas vagas de entrada, preenchendo `job.seniority`."""
    flt = flt or default_filter()
    kept = []
    for job in jobs:
        label = flt.label(job.title)
        if label:
            job.seniority = label
            kept.append(job)
    return kept
