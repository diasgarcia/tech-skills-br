"""Politicas puras para consolidar dados de cards e detalhes de anuncios."""

from dataclasses import dataclass
from datetime import date
import re

from scraper.models import normalize

MIN_DATA_CORTE = date(2026, 1, 1)
_EMPRESAS_CANONICAS = {
    "venha ser sanguelaranja": "FCamara",
    "randstad 1": "Randstad",
    "randstad matriz": "Randstad",
    "nava tech for business": "Nava Technology for Business",
    "minsait brasil": "Minsait",
    "minsait an indra company": "Minsait",
}


def canonical_company(name: str) -> str:
    key = normalize(name)
    if len(key) <= 1:
        return ""
    if re.search(r"\bconfidencial\d*\b", key):
        return "Confidencial"
    return _EMPRESAS_CANONICAS.get(key, name)


@dataclass(frozen=True)
class DescriptionDecision:
    text: str
    preserved: bool


def consolidate_description(saved: str | None, incoming: str | None, *, detail: bool = False) -> DescriptionDecision:
    old, new = saved or "", incoming or ""
    preserve = bool(old) and (
        not new
        or (detail and len(old) >= len(new))
        or (
            len(old) >= 500 and not old.endswith("...")
            and (len(new) < 500 or new.endswith("..."))
        )
    )
    return DescriptionDecision(old if preserve else new, preserve)
