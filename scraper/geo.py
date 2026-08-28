"""Classificador geografico: associa cada vaga a um polo tecnologico e macrorregiao."""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .config import RULES_DIR
from .models import REMOTO, Job, normalize

_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9 ]+")


def _norm(text: str | None) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = _NON_ALNUM_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


class GeoClassifier:
    """Classifica a localizacao da vaga em (polo, regiao)."""

    def __init__(self, rules: dict[str, Any]) -> None:
        self.rules = rules or {}
        self.regioes = self.rules.get("regioes") or {}
        self.ufs_map = self.rules.get("ufs_para_regioes") or {}

        self.polo_patterns: list[tuple[re.Pattern, str, str]] = []
        for regiao_nome, polos in self.regioes.items():
            for polo in polos:
                nome_polo = polo.get("nome", "")
                aliases = polo.get("aliases") or []
                aliases.append(nome_polo)
                for alias in aliases:
                    norm_alias = _norm(alias)
                    if not norm_alias:
                        continue
                    pat = re.compile(rf"\b{re.escape(norm_alias)}\b")
                    self.polo_patterns.append((pat, nome_polo, regiao_nome))

        # Padroes mais longos primeiro: prioriza nomes compostos.
        self.polo_patterns.sort(key=lambda item: len(item[0].pattern), reverse=True)


    @classmethod
    def from_file(cls, path: Path | None = None) -> "GeoClassifier":
        path = path or (RULES_DIR / "locations.yml")
        with open(path, encoding="utf-8") as fh:
            return cls(yaml.safe_load(fh) or {})

    def classify(
        self, location_text: str | None, workplace_type: str | None = None
    ) -> tuple[str, str]:
        """Devolve (polo, regiao) para a vaga."""
        norm_loc = _norm(location_text)
        is_remoto = (workplace_type or "").strip().lower() == REMOTO.lower()

        if norm_loc:
            for pat, polo_nome, regiao_nome in self.polo_patterns:
                if pat.search(norm_loc):
                    return polo_nome, regiao_nome

            for uf, regiao_nome in self.ufs_map.items():
                uf_pat = re.compile(rf"\b{re.escape(uf.lower())}\b")
                if uf_pat.search(norm_loc):
                    return f"Estado/{uf}", regiao_nome

        if is_remoto:
            return "Remoto", "Remoto Nacional"

        if "brasil" in norm_loc or "brazil" in norm_loc:
            return "Nacional", "Nacional"

        return "Não informado", "Não informado"


@lru_cache(maxsize=1)
def default_geo_classifier() -> GeoClassifier:
    return GeoClassifier.from_file()


def attach_geo_info(
    jobs: list[Job], classifier: GeoClassifier | None = None
) -> list[Job]:
    """Preenche job.polo e job.regiao para todas as vagas."""
    classifier = classifier or default_geo_classifier()
    for job in jobs:
        polo, regiao = classifier.classify(job.location, job.workplace_type)
        job.polo = polo
        job.regiao = regiao
    return jobs


def get_all_hubs(rules_path: Path | None = None) -> list[dict[str, Any]]:
    """Devolve a lista de todos os polos configurados em locations.yml."""
    path = rules_path or (RULES_DIR / "locations.yml")
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    hubs: list[dict[str, Any]] = []
    for regiao_nome, polos in (data.get("regioes") or {}).items():
        for polo in polos:
            item = dict(polo)
            item["regiao"] = regiao_nome
            hubs.append(item)
    return hubs


def resolve_hubs(
    location_filters: list[str] | None, rules_path: Path | None = None
) -> list[dict[str, Any]]:
    """Filtra polos conforme os argumentos passados pelo usuario."""
    all_hubs = get_all_hubs(rules_path)
    if not location_filters or "todos" in [f.lower() for f in location_filters]:
        return all_hubs

    selected: list[dict[str, Any]] = []
    norm_filters = [_norm(f) for f in location_filters]

    for hub in all_hubs:
        hub_name = _norm(hub.get("nome"))
        hub_regiao = _norm(hub.get("regiao"))
        hub_uf = _norm(hub.get("uf"))
        if any(
            nf in (hub_name, hub_regiao, hub_uf) or nf in [_norm(a) for a in hub.get("aliases", [])]
            for nf in norm_filters
        ):
            selected.append(hub)

    return selected or all_hubs
