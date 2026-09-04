"""Filtro de senioridade: mantem apenas vagas de entrada (junior/estagio/trainee)."""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import yaml

from .config import RULES_DIR
from .models import Job, normalize

_WS_RE = re.compile(r"\s+")
_KEEP_RE = re.compile(r"[^a-z0-9. ]+")


def _normalize_seniority(text: str | None) -> str:
    """Minusculas, sem acento, PONTUACAO vira espaco -- exceto o ponto.

    O ponto importa aqui: "N1.5" e tier de suporte (entre junior e
    pleno), nao "N1" junior. Com o ponto preservado, a regra `\bn1\b`
    pode exigir que nao venha ".digito" em seguida.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = _KEEP_RE.sub(" ", text.lower())
    return _WS_RE.sub(" ", text).strip()


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
        text = _normalize_seniority(title)
        return any(p.search(text) for p in self.exclude)

    def label(self, title: str) -> str | None:
        """Devolve o rotulo de senioridade ("Júnior", "Estágio", ...) ou None."""
        text = _normalize_seniority(title)
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


def canonicalize_seniority(label: str, flt: SeniorityFilter | None = None) -> str:
    """Normaliza o rotulo de senioridade informado pela fonte.

    As fontes podem rotular o mesmo nivel com variantes ("Estagio" e
    "Estagiario" sao filtros nativos diferentes nos portais). O rotulo
    canonico sai das mesmas regras de `seniority.yml` usadas para o
    titulo; variante desconhecida passa direto (nada e inventado).
    """
    if not label:
        return ""
    flt = flt or default_filter()
    return flt.label(label) or label


def filter_entry_level(jobs: list[Job], flt: SeniorityFilter | None = None) -> list[Job]:
    """Mantem apenas vagas de entrada, preenchendo `job.seniority`.

    Se a fonte ja informou o nivel, ele e respeitado e o titulo nao e
    consultado. Portais como a Solides (filtro nativo de junior) declaram
    a senioridade num campo proprio, que e mais confiavel do que adivinhar
    pelo titulo -- "Programador(a) PHP" nao tem marca nenhuma de nivel,
    mas o portal a classifica como Junior. Coletores que nao sabem o
    nivel deixam o campo vazio e caem no regex. O rotulo da fonte passa
    pela canonicalizacao (variantes viram a categoria unica do projeto).
    """
    flt = flt or default_filter()
    kept = []
    for job in jobs:
        if job.seniority:
            job.seniority = canonicalize_seniority(job.seniority, flt)
            kept.append(job)
            continue
        label = flt.label(job.title)
        if label:
            job.seniority = label
            kept.append(job)
    return kept
