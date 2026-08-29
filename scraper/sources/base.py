"""Contrato comum a todos os portais."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from ..config import Settings
from ..http_client import PoliteSession
from ..models import Job, SourceStats

logger = logging.getLogger(__name__)


class JobSource(ABC):
    """Um portal de vagas.

    Para adicionar um portal novo: herde desta classe, implemente
    `fetch_term` e registre a classe em `scraper/sources/__init__.py`.
    """

    name: str = "base"
    label: str = "Base"

    # Teto natural de paginas por termo nesta fonte, descoberto por
    # sondagem (ex.: Solides tem 115 paginas no filtro junior; GeekHunter
    # tem 81). O --max-pages da CLI continua valendo como teto MENOR
    # (pilotos locais), mas nunca deixa a fonte passar deste limite.
    MAX_PAGES_PER_TERM: int = 10

    def __init__(self, session: PoliteSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.stats = SourceStats(source=self.name)

    def page_limit(self) -> int:
        """Teto efetivo de paginacao: o menor entre CLI e o natural da fonte."""
        return min(self.settings.max_pages_per_term, self.MAX_PAGES_PER_TERM)

    @abstractmethod
    def fetch_term(self, term: str) -> list[Job]:
        """Coleta as vagas de um unico termo de busca."""

    def fetch(self, terms: list[str]) -> list[Job]:
        """Coleta todos os termos, isolando falhas de um termo dos demais."""
        jobs: list[Job] = []
        for term in terms:
            try:
                found = self.fetch_term(term)
            except Exception as exc:  # nao derruba a coleta inteira
                message = f"{self.name}/{term}: {exc}"
                logger.warning("Erro coletando %s", message)
                self.stats.errors.append(message)
                continue
            logger.info("[%s] '%s' -> %d vagas", self.name, term, len(found))
            jobs.extend(found)
        self.stats.raw_jobs = len(jobs)
        self.stats.requests_made = self.session.request_count
        return jobs
