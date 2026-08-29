"""Registro de portais disponiveis."""

from __future__ import annotations

from .base import JobSource
from .geekhunter import GeekHunterSource
from .gupy import GupySource
from .linkedin import LinkedInSource
from .programathor import ProgramathorSource
from .solides import SolidesSource
from .trampos import TramposSource
from .vagas_com import VagasComSource

SOURCE_REGISTRY: dict[str, type[JobSource]] = {
    GupySource.name: GupySource,
    VagasComSource.name: VagasComSource,
    ProgramathorSource.name: ProgramathorSource,
    TramposSource.name: TramposSource,
    LinkedInSource.name: LinkedInSource,
    SolidesSource.name: SolidesSource,
    GeekHunterSource.name: GeekHunterSource,
}

AVAILABLE_SOURCES = list(SOURCE_REGISTRY)
DEFAULT_SOURCES = [
    "gupy",
    "vagas",
    "programathor",
    "trampos",
    "linkedin",
    "solides",
    "geekhunter",
]


__all__ = [
    "JobSource",
    "GupySource",
    "VagasComSource",
    "ProgramathorSource",
    "TramposSource",
    "LinkedInSource",
    "SolidesSource",
    "GeekHunterSource",
    "SOURCE_REGISTRY",
    "AVAILABLE_SOURCES",
    "DEFAULT_SOURCES",
]


