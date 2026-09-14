"""Registro de portais disponiveis."""

from __future__ import annotations

from .abler import AblerSource
from .base import JobSource
from .geekhunter import GeekHunterSource
from .gupy import GupySource
from .infojobs import InfoJobsSource
from .linkedin import LinkedInSource
from .recrutei import RecruteiSource
from .solides import SolidesSource
from .trampos import TramposSource
from .vagas_com import VagasComSource

SOURCE_REGISTRY: dict[str, type[JobSource]] = {
    GupySource.name: GupySource,
    VagasComSource.name: VagasComSource,
    TramposSource.name: TramposSource,
    LinkedInSource.name: LinkedInSource,
    SolidesSource.name: SolidesSource,
    GeekHunterSource.name: GeekHunterSource,
    InfoJobsSource.name: InfoJobsSource,
    AblerSource.name: AblerSource,
    RecruteiSource.name: RecruteiSource,
}

AVAILABLE_SOURCES = list(SOURCE_REGISTRY)
DEFAULT_SOURCES = list(SOURCE_REGISTRY)


__all__ = [
    "JobSource",
    "GupySource",
    "VagasComSource",
    "TramposSource",
    "LinkedInSource",
    "SolidesSource",
    "GeekHunterSource",
    "InfoJobsSource",
    "AblerSource",
    "RecruteiSource",
    "SOURCE_REGISTRY",
    "AVAILABLE_SOURCES",
    "DEFAULT_SOURCES",
]
