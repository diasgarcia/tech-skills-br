"""Registro de portais disponiveis."""

from __future__ import annotations

from .base import JobSource
from .gupy import GupySource
from .linkedin import LinkedInSource
from .programathor import ProgramathorSource
from .trampos import TramposSource
from .vagas_com import VagasComSource

SOURCE_REGISTRY: dict[str, type[JobSource]] = {
    GupySource.name: GupySource,
    VagasComSource.name: VagasComSource,
    ProgramathorSource.name: ProgramathorSource,
    TramposSource.name: TramposSource,
    LinkedInSource.name: LinkedInSource,
}

AVAILABLE_SOURCES = list(SOURCE_REGISTRY)

__all__ = ["JobSource", "GupySource", "VagasComSource", "ProgramathorSource",
           "TramposSource", "LinkedInSource",
           "SOURCE_REGISTRY", "AVAILABLE_SOURCES"]
