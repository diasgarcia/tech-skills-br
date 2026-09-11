"""Contrato comum a todos os portais."""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from functools import lru_cache

from ..config import Settings
from ..http_client import PoliteSession
from ..models import Job, SourceStats, normalize

logger = logging.getLogger(__name__)


@lru_cache(maxsize=None)
def _signal_pattern(signal: str) -> re.Pattern:
    normalized = normalize(signal)
    if not normalized:
        return re.compile(r"(?!x)x")
    return re.compile(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])")


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
        self.progress_callback = None

    def report(
        self,
        total: int,
        current_term: str | None = None,
        requests: int | None = None,
        progresso: float | None = None,
    ) -> None:
        """Avisa o coletor externo quantas vagas esta fonte ja tem.

        `progresso` e a fracao do trabalho da fonte ja feita (0..1),
        quando a fonte sabe calcular (termos ou paginas processados).
        """
        if self.progress_callback is not None:
            reqs = requests if requests is not None else self.session.request_count
            try:
                self.progress_callback(total, current_term, reqs, progresso)
            except TypeError:
                try:
                    self.progress_callback(total, current_term, reqs)
                except TypeError:
                    try:
                        self.progress_callback(total, current_term)
                    except TypeError:
                        try:
                            self.progress_callback(total)
                        except Exception:
                            pass
            except Exception:
                pass

    def page_limit(self) -> int:
        """Teto efetivo de paginacao: o menor entre CLI e o natural da fonte."""
        return min(self.settings.max_pages_per_term, self.MAX_PAGES_PER_TERM)

    @abstractmethod
    def fetch_term(self, term: str) -> list[Job]:
        """Coleta as vagas de um unico termo de busca."""

    def fetch(self, terms: list[str]) -> list[Job]:
        """Coleta todos os termos, isolando falhas de um termo dos demais."""
        jobs: list[Job] = []
        total_terms = len(terms)
        for idx, term in enumerate(terms, 1):
            try:
                found = self.fetch_term(term)
            except Exception as exc:  # nao derruba a coleta inteira
                message = f"{self.name}/{term}: {exc}"
                logger.warning("Erro coletando %s", message)
                self.stats.errors.append(message)
                continue
            sinais = self.settings.term_match_rules.get(term, [])
            if sinais:
                total_encontrado = len(found)
                found = [
                    job
                    for job in found
                    if any(
                        _signal_pattern(sinal).search(job.searchable_text())
                        for sinal in sinais
                    )
                ]
                descartadas = total_encontrado - len(found)
                if descartadas:
                    logger.debug(
                        "[%s] '%s': %d resultados sem o sinal esperado",
                        self.name,
                        term,
                        descartadas,
                    )
            if self.settings.parallel_sources:
                logger.debug("[%s] '%s' -> %d vagas", self.name, term, len(found))
            else:
                logger.info("[%s] '%s' -> %d vagas", self.name, term, len(found))
            jobs.extend(found)
            self.report(
                len(jobs),
                current_term=f"[{idx}/{total_terms}] {term}",
                requests=self.session.request_count,
                progresso=idx / total_terms,
            )
        self.stats.raw_jobs = len(jobs)
        self.stats.requests_made = self.session.request_count
        return jobs

