"""Classificacao de vagas em areas de tecnologia via keywords ponderadas.

As regras vivem em `scraper/rules/areas.yml` -- edite la, nao aqui.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .config import RULES_DIR
from .models import Job, normalize


@dataclass
class AreaScore:
    area: str
    score: float
    matches: list[str]
    title_score: float = 0.0


def _compile_keyword(keyword: str) -> re.Pattern:
    """Casa a keyword como palavra/frase inteira no texto normalizado."""
    kw = normalize(keyword)
    if not kw:
        return re.compile(r"(?!x)x")  # nunca casa
    return re.compile(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])")


class AreaClassifier:
    """Pontua cada area por keywords e escolhe a de maior pontuacao."""

    def __init__(self, rules: dict) -> None:
        settings = rules.get("settings") or {}
        self.title_boost: float = float(settings.get("title_boost", 3.0))
        self.min_score: float = float(settings.get("min_score", 1.0))
        self.fallback_area: str = settings.get("fallback_area", "Outros/TI Geral")

        weights = rules.get("weights") or {}
        self.tiers: dict[str, float] = {k: float(v) for k, v in weights.items()}

        gate = rules.get("tech_gate") or {}
        if isinstance(gate, list):  # formato antigo: lista unica
            gate = {"titulo": gate, "descricao": gate}
        self.gate_title: list[re.Pattern] = [
            _compile_keyword(kw) for kw in (gate.get("titulo") or [])
        ]
        self.gate_body: list[re.Pattern] = [
            _compile_keyword(kw) for kw in (gate.get("descricao") or [])
        ]
        self.gate_exclude: list[re.Pattern] = [
            _compile_keyword(kw) for kw in (gate.get("excluir") or [])
        ]

        # Peso a partir do qual uma keyword conta como sinal "forte" no portao.
        self.strong_weight: float = self.tiers.get("peso_alto", 4.0)

        # area -> lista de (pattern, peso, keyword original)
        self.areas: dict[str, list[tuple[re.Pattern, float, str]]] = {}
        for area, tiers in (rules.get("areas") or {}).items():
            compiled: list[tuple[re.Pattern, float, str]] = []
            for tier_name, keywords in (tiers or {}).items():
                weight = self.tiers.get(tier_name, 1.0)
                for kw in keywords or []:
                    compiled.append((_compile_keyword(kw), weight, kw))
            self.areas[area] = compiled

    def _strong_patterns(self):
        for keywords in self.areas.values():
            for pattern, weight, _kw in keywords:
                if weight >= self.strong_weight:
                    yield pattern

    @classmethod
    def from_file(cls, path: Path | None = None) -> "AreaClassifier":
        path = path or (RULES_DIR / "areas.yml")
        with open(path, encoding="utf-8") as fh:
            return cls(yaml.safe_load(fh) or {})

    @property
    def area_names(self) -> list[str]:
        return list(self.areas.keys()) + [self.fallback_area]

    def score_all(self, title: str, description: str = "") -> list[AreaScore]:
        """Pontuacao de todas as areas, da maior para a menor."""
        title_text = normalize(title)
        body_text = normalize(description)

        results: list[AreaScore] = []
        for area, keywords in self.areas.items():
            total = 0.0
            title_total = 0.0
            matches: list[str] = []
            for pattern, weight, raw_kw in keywords:
                in_title = bool(pattern.search(title_text))
                in_body = bool(pattern.search(body_text))
                if in_title:
                    total += weight * self.title_boost
                    title_total += weight * self.title_boost
                    matches.append(f"{raw_kw}(t)")
                elif in_body:
                    total += weight
                    matches.append(raw_kw)
            if total > 0:
                results.append(
                    AreaScore(area, round(total, 2), matches, round(title_total, 2))
                )

        results.sort(key=lambda r: (-r.score, r.area))
        return results

    def is_tech(self, title: str, description: str = "") -> bool:
        """A vaga e de tecnologia?

        Descarta o lixo que a busca solta dos portais devolve ("Analista
        Contábil Jr", "Analista Fiscal Jr", ...). Ver `tech_gate` em areas.yml:
        o titulo aceita sinais amplos, a descricao so aceita sinais estritos --
        porque a descricao curta do Vagas.com e cheia de palavra generica.
        """
        title_text = normalize(title)
        if any(p.search(title_text) for p in self.gate_exclude):
            return False
        if any(p.search(title_text) for p in self.gate_title):
            return True
        if any(p.search(title_text) for p in self._strong_patterns()):
            return True

        body_text = normalize(description)
        if not body_text:
            return False
        if any(p.search(body_text) for p in self.gate_body):
            return True
        return any(p.search(body_text) for p in self._strong_patterns())

    def classify(self, title: str, description: str = "") -> AreaScore:
        """Escolhe a area da vaga.

        Regra do titulo dominante: se ALGUMA area foi sinalizada pelo titulo,
        so essas areas disputam. Sem isso, uma descricao longa da Gupy que cita
        "dados" de passagem ("protecao de dados", "dados cadastrais") faria uma
        vaga de Governanca de TI virar vaga de Data.
        """
        ranked = self.score_all(title, description)
        if not ranked:
            return AreaScore(self.fallback_area, 0.0, [])

        titled = [r for r in ranked if r.title_score > 0]
        best = (titled or ranked)[0]  # `ranked` ja vem ordenado por pontuacao

        if best.score < self.min_score:
            return AreaScore(self.fallback_area, 0.0, [])
        return best


@lru_cache(maxsize=1)
def default_classifier() -> AreaClassifier:
    return AreaClassifier.from_file()


def classify_jobs(jobs: list[Job], clf: AreaClassifier | None = None) -> list[Job]:
    """Preenche `area`, `area_score` e `area_matches` em cada vaga."""
    clf = clf or default_classifier()
    for job in jobs:
        result = clf.classify(job.title, job.description)
        job.area = result.area
        job.area_score = result.score
        job.area_matches = ", ".join(result.matches[:12])
    return jobs


def filter_tech(
    jobs: list[Job], clf: AreaClassifier | None = None
) -> tuple[list[Job], list[Job]]:
    """Separa (vagas de tecnologia, vagas descartadas por nao serem de tech)."""
    clf = clf or default_classifier()
    tech, non_tech = [], []
    for job in jobs:
        (tech if clf.is_tech(job.title, job.description) else non_tech).append(job)
    return tech, non_tech
