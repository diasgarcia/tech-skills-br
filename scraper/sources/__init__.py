"""Registro de portais disponiveis."""

from __future__ import annotations

from .base import JobSource
from .gupy import GupySource
from .linkedin import LinkedInSource
from .programathor import ProgramathorSource
from .serpapi import SerpApiSource
from .theirstack import TheirStackSource
from .trampos import TramposSource
from .vagas_com import VagasComSource

SOURCE_REGISTRY: dict[str, type[JobSource]] = {
    GupySource.name: GupySource,
    VagasComSource.name: VagasComSource,
    ProgramathorSource.name: ProgramathorSource,
    TramposSource.name: TramposSource,
    LinkedInSource.name: LinkedInSource,
    TheirStackSource.name: TheirStackSource,
    SerpApiSource.name: SerpApiSource,
}

AVAILABLE_SOURCES = list(SOURCE_REGISTRY)
DEFAULT_SOURCES = [
    "gupy",
    "vagas",
    "programathor",
    "trampos",
    "linkedin",
]


__all__ = [
    "JobSource",
    "GupySource",
    "VagasComSource",
    "ProgramathorSource",
    "TramposSource",
    "LinkedInSource",
    "TheirStackSource",
    "SerpApiSource",
    "SOURCE_REGISTRY",
    "AVAILABLE_SOURCES",
    "DEFAULT_SOURCES",
]


