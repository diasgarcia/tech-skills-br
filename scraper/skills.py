"""Extracao das tecnologias/habilidades citadas em cada vaga.

As regras vivem em `scraper/rules/skills.yml` -- edite la, nao aqui.

Diferente do resto do projeto, aqui o texto passa por uma normalizacao propria
que PRESERVA "#" e "+": com a normalizacao padrao, "C#" viraria "c" e casaria
com qualquer "c" solto no texto.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from functools import lru_cache
from pathlib import Path

import yaml

from .config import RULES_DIR
from .models import Job

_WS_RE = re.compile(r"\s+")
_KEEP_RE = re.compile(r"[^a-z0-9#+ ]+")
# Caracteres que "colam" numa keyword -- usados como limite de palavra.
_BOUNDARY = r"[a-z0-9#+]"


def normalize_tech(text: str | None) -> str:
    """Minusculas, sem acento, mantendo '#' e '+'. Pontuacao vira espaco."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = _KEEP_RE.sub(" ", text.lower())
    return _WS_RE.sub(" ", text).strip()


def _compile_alias(alias: str) -> re.Pattern:
    token = normalize_tech(alias)
    if not token:
        return re.compile(r"(?!x)x")
    return re.compile(rf"(?<!{_BOUNDARY}){re.escape(token)}(?!{_BOUNDARY})")


class SkillExtractor:
    """Encontra tecnologias no texto da vaga, a partir de `skills.yml`."""

    def __init__(self, rules: dict) -> None:
        # nome canonico -> lista de padroes; guarda tambem o grupo (linguagens...)
        self.skills: dict[str, list[re.Pattern]] = {}
        self.groups: dict[str, str] = {}
        for group, entries in (rules or {}).items():
            for canonical, aliases in (entries or {}).items():
                patterns = [_compile_alias(a) for a in (aliases or [canonical])]
                self.skills[canonical] = patterns
                self.groups[canonical] = group

    @classmethod
    def from_file(cls, path: Path | None = None) -> "SkillExtractor":
        path = path or (RULES_DIR / "skills.yml")
        with open(path, encoding="utf-8") as fh:
            return cls(yaml.safe_load(fh) or {})

    def extract(self, *texts: str) -> list[str]:
        """Tecnologias citadas nos textos, sem repetir, em ordem alfabetica."""
        haystack = normalize_tech(" ".join(t for t in texts if t))
        if not haystack:
            return []
        found = [
            name
            for name, patterns in self.skills.items()
            if any(p.search(haystack) for p in patterns)
        ]
        return sorted(found)


@lru_cache(maxsize=1)
def default_extractor() -> SkillExtractor:
    return SkillExtractor.from_file()


def attach_skills(jobs: list[Job], extractor: SkillExtractor | None = None) -> list[Job]:
    """Preenche `job.skills`. Deve rodar ANTES da exportacao, que trunca a descricao."""
    extractor = extractor or default_extractor()
    for job in jobs:
        job.skills = extractor.extract(job.title, job.description)
    return jobs


def skills_by_area(jobs: list[Job], top_n: int = 8) -> dict[str, list[tuple[str, int]]]:
    """Top-N tecnologias por area: {area: [(tecnologia, n_vagas), ...]}."""
    counters: dict[str, Counter] = {}
    for job in jobs:
        counters.setdefault(job.area, Counter()).update(job.skills)
    return {
        area: counter.most_common(top_n)
        for area, counter in counters.items()
        if counter
    }


def jobs_with_skills_by_area(jobs: list[Job]) -> dict[str, int]:
    """Quantas vagas de cada area citam ao menos uma tecnologia.

    E a base correta para percentuais: nem toda vaga informa tecnologia. O
    LinkedIn nao traz descricao no card, entao areas cheias de vaga vinda de la
    tem base bem menor que o total -- em "Outros/TI Geral", 31 de 144.
    """
    base: dict[str, int] = {}
    for job in jobs:
        if job.skills:
            base[job.area] = base.get(job.area, 0) + 1
    return base


def overall_skill_counts(jobs: list[Job], top_n: int = 20) -> list[tuple[str, int]]:
    counter: Counter = Counter()
    for job in jobs:
        counter.update(job.skills)
    return counter.most_common(top_n)
