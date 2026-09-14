"""Orquestracao: coleta -> filtro de senioridade -> classificacao -> dedupe -> export."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from .classifier import classify_jobs, default_classifier, filter_tech
from .config import Settings
from .dedupe import deduplicate
from .export import build_ranking, export_all
from .geo import attach_geo_info
from .http_client import PoliteSession
from .models import NAO_INFORMADO, Job, SourceStats, infer_workplace
from .progress import FONTES_LABELS, _BufferLog, _TabelaParalela


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





def _codigo_do_erro(mensagem: str) -> int | None:
    """Extrai um codigo HTTP de uma mensagem de excecao ('HTTP 429', '500 Server Error'...)."""
    m = re.search(r"\b([45]\d\d)\b", mensagem or "")
    return int(m.group(1)) if m else None


def _collect_source(
    source_name: str, settings: Settings, reportar=None
) -> tuple[str, list[Job], SourceStats | None, int, int | None]:
    """Coleta uma unica fonte com sessao propria.

    Cada fonte tem sua sessao (e seu delay): isso permite rodar as
    fontes em paralelo sem compartilhar estado, mantendo o ritmo por
    dominio. O ultimo elemento devolve o status HTTP da ultima chamada
    (para o monitor marcar bloqueio/erro na tabela).
    """
    source_cls = SOURCE_REGISTRY.get(source_name)
    if source_cls is None:
        message = f"Portal desconhecido: {source_name}"
        logger.warning(message)
        return source_name, [], SourceStats(source_name, errors=[message]), 0, None

    delay = settings.source_delays.get(source_name, settings.delay_seconds)
    if not settings.parallel_sources:
        logger.info("=== Coletando em %s (delay %.1fs) ===", source_cls.label, delay)
    else:
        logger.debug("=== Coletando em %s (delay %.1fs) ===", source_cls.label, delay)

    with PoliteSession(
        user_agent=settings.user_agent,
        delay_seconds=delay,
        timeout_seconds=settings.timeout_seconds,
        max_retries=settings.max_retries,
        backoff_factor=settings.backoff_factor,
    ) as session:
        source = source_cls(session, settings)
        if reportar is not None:
            source.progress_callback = reportar
        stats = source.stats
        try:
            jobs = source.fetch(settings.search_terms)
        except Exception as exc:
            message = f"{source_name}: {type(exc).__name__}: {exc}"
            stats.errors.append(message)
            logger.warning("Erro coletando %s", message)
            jobs = []
            from .checkpoints import CHECKPOINT_NAMES, JobCheckpoint

            checkpoint_name = CHECKPOINT_NAMES.get(source_name)
            if checkpoint_name:
                try:
                    jobs = JobCheckpoint(Path(settings.output_dir) / checkpoint_name, source_name).load()
                except (OSError, ValueError) as checkpoint_error:
                    stats.errors.append(f"{source_name}/checkpoint: {checkpoint_error}")
        requests = session.request_count
        ultimo_status = session.last_status_code
        stats.raw_jobs = len(jobs)
        stats.requests_made = requests

    if not settings.parallel_sources:
        logger.info("%s: %d vagas brutas (%d requests)", source_cls.label, len(jobs), requests)
    else:
        logger.debug("%s: %d vagas brutas (%d requests)", source_cls.label, len(jobs), requests)

    return source_name, jobs, stats, requests, ultimo_status


def _collect_source_safe(
    source_name: str, settings: Settings, reportar=None
) -> tuple[str, list[Job], SourceStats | None, int, int | None]:
    """Isola tambem falhas ao construir/fechar a sessao, nos dois modos."""
    try:
        return _collect_source(source_name, settings, reportar)
    except Exception as exc:
        message = f"{source_name}: {type(exc).__name__}: {exc}"
        logger.warning("Erro coletando %s", message)
        return source_name, [], SourceStats(source_name, errors=[message]), 0, None


def collect(settings: Settings) -> tuple[list[Job], list[SourceStats], int]:
    """Roda todos os portais selecionados e devolve as vagas brutas."""
    all_jobs: list[Job] = []
    stats: list[SourceStats] = []
    total_requests = 0

    if settings.parallel_sources and len(settings.sources) > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        labels = {
            s: FONTES_LABELS.get(s, SOURCE_REGISTRY[s].label)
            for s in settings.sources
            if s in SOURCE_REGISTRY
        }
        monitor = _TabelaParalela(settings.sources, labels=labels)
        monitor.iniciar()

        def _reportar(nome: str):
            return lambda total, termo=None, reqs=None, progresso=None: monitor.atualizar(
                nome, total=total, termo=termo, requests=reqs, progresso=progresso
            )

        resultados: dict[str, tuple[list[Job], SourceStats | None, int]] = {}
        buffer = _BufferLog()
        buffer.ativar()
        try:
            with ThreadPoolExecutor(max_workers=len(settings.sources)) as pool:
                futures = {}
                for nome in settings.sources:
                    futures[pool.submit(_collect_source_safe, nome, settings, _reportar(nome))] = nome
                    # Marca "Coletando" ja no disparo: o primeiro report so
                    # vem depois do primeiro termo, e fontes de termo unico
                    # ficariam "Iniciando" ate o final sem isso.
                    monitor.atualizar(nome, status="Coletando")
                for future in as_completed(futures):
                    nome = futures[future]
                    try:
                        _, jobs, fonte_stats, requests, ultimo = future.result()
                        resultados[nome] = (jobs, fonte_stats, requests)
                        if fonte_stats is not None and fonte_stats.errors:
                            monitor.erro_fonte(nome, fonte_stats.errors[-1])
                        elif ultimo is not None and ultimo >= 400:
                            # Bloqueio/erro no portal: mostra o codigo no
                            # status e deixa o termo como "erro".
                            monitor.erro_fonte(nome, "erro", codigo=ultimo)
                        else:
                            monitor.finalizar_fonte(nome, len(jobs), requests)
                    except Exception as exc:
                        resultados[nome] = ([], SourceStats(nome, errors=[str(exc)]), 0)
                        monitor.erro_fonte(nome, str(exc), codigo=_codigo_do_erro(str(exc)))
        finally:
            monitor.encerrar()
            buffer.desativar()
        buffer.despejar()

        # Ordem estavel: a mesma ordem de settings.sources.
        for nome in settings.sources:
            jobs, fonte_stats, requests = resultados.get(nome, ([], None, 0))
            all_jobs.extend(jobs)
            if fonte_stats is not None:
                stats.append(fonte_stats)
            total_requests += requests
        return all_jobs, stats, total_requests

    for source_name in settings.sources:
        _, jobs, fonte_stats, requests, _ = _collect_source_safe(source_name, settings)
        all_jobs.extend(jobs)
        if fonte_stats is not None:
            stats.append(fonte_stats)
        total_requests += requests

    return all_jobs, stats, total_requests



def run(
    settings: Settings,
    strict_seniority: bool = False,
    keep_non_tech: bool = False,
) -> PipelineResult:
    """Executa o fluxo completo e grava os arquivos de saida."""
    from .checkpoints import checkpoint_receipts

    raw_jobs, stats, requests_made = collect(settings)
    receipts = checkpoint_receipts(raw_jobs, Path(settings.output_dir))
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
        requests_made += _enrich_linkedin_parallel(linkedin_to_enrich, settings=settings) or 0

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

    files = export_all(jobs, settings.ensure_output_dir(), meta)
    for receipt in receipts:
        if receipt.confirm():
            logger.info("Checkpoint confirmado apos exportacao: %s", receipt.path)
    return PipelineResult(jobs=jobs, ranking=ranking, files=files,
                          stats=stats, meta=meta)


def _enrich_linkedin_parallel(jobs: list[Job], max_workers: int = 3, *, settings: Settings | None = None) -> int:
    """Busca descricoes completas apenas para as vagas unicas filtradas.

    Usa PoliteSession (delay + retry em 429/5xx) e registra falhas no log em
    vez de engoli-las. O lock serializa os GETs para que o delay da sessao
    valha de verdade; o parse roda em paralelo.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from threading import Lock

    from .http_client import PoliteSession
    from .sources.linkedin import DETAIL_API_URL, parse_linkedin_description

    settings = settings or Settings(timeout_seconds=12, max_retries=2)
    lock = Lock()

    def _fetch(job: Job, session: PoliteSession) -> None:
        try:
            with lock:
                response = session.get(DETAIL_API_URL.format(job_id=job.external_id))
            if response is None:
                return  # falha ja registrada pelo PoliteSession
            description = parse_linkedin_description(response.text)
            if description:
                job.description = description
            else:
                logger.warning("[linkedin] Descricao nao encontrada na vaga %s",
                               job.external_id)
        except Exception as exc:
            logger.warning("[linkedin] Falha ao enriquecer a vaga %s: %s",
                           job.external_id, exc)

    with PoliteSession(
        user_agent=settings.user_agent,
        delay_seconds=settings.source_delays.get("linkedin", settings.delay_seconds),
        timeout_seconds=settings.timeout_seconds,
        max_retries=settings.max_retries,
        backoff_factor=settings.backoff_factor,
    ) as session:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(_fetch, job, session) for job in jobs]
            for _ in as_completed(futures):
                pass
        return getattr(session, "request_count", 0)

