"""Orquestracao: coleta -> filtro de senioridade -> classificacao -> dedupe -> export."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .classifier import classify_jobs, default_classifier, filter_tech
from .config import Settings
from .dedupe import deduplicate
from .export import build_ranking, export_all
from .geo import attach_geo_info
from .http_client import PoliteSession
from .models import NAO_INFORMADO, Job, SourceStats, infer_workplace


from .seniority import SeniorityFilter, canonicalize_seniority, filter_entry_level
from .skills import attach_skills
from .sources import SOURCE_REGISTRY

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    jobs: list[Job]
    ranking: list[dict]
    files: dict[str, Path] = field(default_factory=dict)
    stats: list[SourceStats] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @property
    def top_area(self) -> str | None:
        return self.ranking[0]["area"] if self.ranking else None


def collect(settings: Settings) -> tuple[list[Job], list[SourceStats], int]:
    """Roda todos os portais selecionados e devolve as vagas brutas."""
    all_jobs: list[Job] = []
    stats: list[SourceStats] = []
    total_requests = 0

    for source_name in settings.sources:
        source_cls = SOURCE_REGISTRY.get(source_name)
        if source_cls is None:
            logger.warning("Portal desconhecido, ignorando: %s", source_name)
            continue

        logger.info("=== Coletando em %s ===", source_cls.label)
        with PoliteSession(
            user_agent=settings.user_agent,
            delay_seconds=settings.delay_seconds,
            timeout_seconds=settings.timeout_seconds,
            max_retries=settings.max_retries,
            backoff_factor=settings.backoff_factor,
        ) as session:
            source = source_cls(session, settings)
            jobs = source.fetch(settings.search_terms)
            all_jobs.extend(jobs)
            stats.append(source.stats)
            total_requests += session.request_count

        logger.info("%s: %d vagas brutas", source_cls.label, len(jobs))

    return all_jobs, stats, total_requests


def run(
    settings: Settings,
    strict_seniority: bool = False,
    keep_non_tech: bool = False,
    with_charts: bool = True,
) -> PipelineResult:
    """Executa o fluxo completo e grava os arquivos de saida."""
    raw_jobs, stats, requests_made = collect(settings)
    logger.info("Total bruto: %d vagas", len(raw_jobs))

    if settings.only_junior:
        seniority_filter = SeniorityFilter.from_file(strict=strict_seniority)
        jobs = filter_entry_level(raw_jobs, seniority_filter)
        dropped_seniority = len(raw_jobs) - len(jobs)
    else:
        jobs = raw_jobs
        for job in jobs:
            job.seniority = (
                canonicalize_seniority(job.seniority) if job.seniority else "Não filtrado"
            )
        dropped_seniority = 0
    logger.info("Apos filtro de senioridade: %d vagas (-%d)", len(jobs), dropped_seniority)

    jobs, duplicates = deduplicate(jobs)
    logger.info("Apos deduplicacao: %d vagas (-%d)", len(jobs), duplicates)

    classifier = default_classifier()
    if keep_non_tech:
        dropped_non_tech = 0
    else:
        jobs, non_tech = filter_tech(jobs, classifier)
        dropped_non_tech = len(non_tech)
        logger.info("Apos filtro de tecnologia: %d vagas (-%d nao-tech)",
                    len(jobs), dropped_non_tech)

    linkedin_to_enrich = [j for j in jobs if j.source == "linkedin" and not j.description]
    if settings.enrich_linkedin and linkedin_to_enrich:
        logger.info("Enriquecendo descricoes de %d vagas unicas do LinkedIn em paralelo...", len(linkedin_to_enrich))
        _enrich_linkedin_parallel(linkedin_to_enrich)

    jobs = classify_jobs(jobs, classifier)
    jobs = attach_skills(jobs)
    for job in jobs:
        if not job.workplace_type or job.workplace_type == NAO_INFORMADO:
            job.workplace_type = infer_workplace(
                job.workplace_type,
                location=job.location,
                title=job.title,
                description=job.description,
            )

    jobs = attach_geo_info(jobs)
    ranking = build_ranking(jobs)



    meta = {
        "sources": [SOURCE_REGISTRY[s].label for s in settings.sources
                    if s in SOURCE_REGISTRY],
        "terms_count": len(settings.search_terms),
        "raw_jobs": len(raw_jobs),
        "dropped_seniority": dropped_seniority,
        "dropped_non_tech": dropped_non_tech,
        "duplicates": duplicates,
        "requests": requests_made,
    }

    files = export_all(jobs, settings.ensure_output_dir(), meta,
                       with_charts=with_charts)
    return PipelineResult(jobs=jobs, ranking=ranking, files=files,
                          stats=stats, meta=meta)


def _enrich_linkedin_parallel(jobs: list[Job], max_workers: int = 3) -> None:
    """Busca descricoes completas apenas para as vagas unicas filtradas.

    Usa PoliteSession (delay + retry em 429/5xx) e registra falhas no log em
    vez de engoli-las. O lock serializa os GETs para que o delay da sessao
    valha de verdade; o parse roda em paralelo.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from threading import Lock

    from bs4 import BeautifulSoup

    from .http_client import PoliteSession

    detail_url = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    lock = Lock()

    def _fetch(job: Job, session: PoliteSession) -> None:
        try:
            with lock:
                response = session.get(detail_url.format(job_id=job.external_id))
            if response is None:
                return  # falha ja registrada pelo PoliteSession
            soup = BeautifulSoup(response.text, "html.parser")
            el = soup.select_one(".show-more-less-html__markup, .description__text")
            if el:
                job.description = el.get_text(" ", strip=True)
            else:
                logger.warning("[linkedin] Descricao nao encontrada na vaga %s",
                               job.external_id)
        except Exception as exc:
            logger.warning("[linkedin] Falha ao enriquecer a vaga %s: %s",
                           job.external_id, exc)

    with PoliteSession(
        user_agent=user_agent,
        delay_seconds=1.0,
        timeout_seconds=12,
        max_retries=2,
        backoff_factor=1.5,
    ) as session:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(_fetch, job, session) for job in jobs]
            for _ in as_completed(futures):
                pass

