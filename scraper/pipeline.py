"""Orquestracao: coleta -> filtro de senioridade -> classificacao -> dedupe -> export."""

from __future__ import annotations

import logging
import os
import re
import sys
import threading
import time as _time
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


RESUMO_INTERVALO_S = 45.0

# Cores ANSI para o viewer do Actions (renderiza SGR; "clear" nao existe).
_ANSI = {
    "verde": "\033[32m",
    "vermelho": "\033[31m",
    "amarelo": "\033[33m",
    "ciano": "\033[36m",
    "cinza": "\033[90m",
    "negrito": "\033[1m",
}

_STATUS_COR = {
    "Concluido": _ANSI["verde"],
    "Erro": _ANSI["vermelho"],
    "Coletando": _ANSI["amarelo"],
    "Iniciando": _ANSI["cinza"],
}


def _cor(estilo: str, texto: str) -> str:
    return f"{estilo}{texto}\033[0m"


def _emitir_comando(texto: str) -> None:
    """Linha crua no stdout: comandos de workflow so valem no inicio da linha."""
    print(texto, flush=True)


class _ResumoParalelo:
    """Mantido para compatibilidade de testes unitarios."""

    def __init__(self, nomes: list[str]) -> None:
        self._contagens = {n: 0 for n in nomes}
        self._lock = threading.Lock()
        self._aberto = False

    def registrar(self, nome: str, total: int) -> None:
        with self._lock:
            self._contagens[nome] = total

    def atual(self) -> str:
        with self._lock:
            return " | ".join(
                f"{nome} {self._contagens[nome]}" for nome in self._contagens
            )

    def abrir(self) -> None:
        with self._lock:
            if self._aberto:
                _emitir_comando("::endgroup::")
            self._aberto = True
        _emitir_comando(
            f"::group::[resumo {_time.strftime('%H:%M:%S')}] {self.atual()}"
        )

    def fechar(self) -> None:
        with self._lock:
            if self._aberto:
                _emitir_comando("::endgroup::")
                self._aberto = False


FONTES_LABELS = {
    "linkedin": "LinkedIn",
    "gupy": "Gupy",
    "vagas": "Vagas.com",
    "trampos": "Trampos.co",
    "solides": "Solides",
    "geekhunter": "GeekHunter",
    "infojobs": "InfoJobs",
    "abler": "Abler",
    "recrutei": "Recrutei",
}


class _TabelaParalela:
    """Monitor de progresso em tabela para coleta paralela entre fontes.

    - Em terminal interativo (TTY local): redesenha a tabela in-place sem rolar telas.
    - No GitHub Actions / nao-TTY: imprime snapshots da tabela como linhas
      planas (sempre visiveis; o Actions nao deixa controlar o estado
      inicial de um ::group:: e nao renderiza ANSI, entao nada de "clear").
    """

    def __init__(self, fontes: list[str], labels: dict[str, str] | None = None) -> None:
        self.fontes = list(fontes)
        self.labels = labels or {}
        self.is_ci = os.getenv("GITHUB_ACTIONS") == "true"
        self.is_tty = sys.stdout.isatty() and not self.is_ci

        if self.is_tty and sys.platform == "win32":
            os.system("")  # Ativa virtual terminal ANSI no conhost se necessario

        self.estado: dict[str, dict] = {
            f: {
                "label": self.labels.get(f, FONTES_LABELS.get(f, f.capitalize())),
                "status": "Iniciando",
                "vagas": 0,
                "requests": 0,
                "termo": "-",
                "progresso": 0.0,
            }
            for f in fontes
        }
        self.lock = threading.RLock()
        self.inicio = _time.time()
        self.linhas_impressas = 0
        self.ultimo_render = 0.0
        self.parar = threading.Event()
        self.thread_timer: threading.Thread | None = None

    def formatar(self) -> str:
        with self.lock:
            decorrido = _time.time() - self.inicio
            minutos, segundos = divmod(int(decorrido), 60)
            tempo_str = f"{minutos:02d}m{segundos:02d}s"

            total_vagas = sum(d["vagas"] for d in self.estado.values())
            total_reqs = sum(d["requests"] for d in self.estado.values())
            concluidas = sum(
                1 for d in self.estado.values()
                if d["status"] == "Concluido" or d["status"].startswith("Erro")
            )
            total_fontes = len(self.estado)

            cabecalho = (
                f"[Coleta Paralela: {total_fontes} fontes | "
                f"{concluidas}/{total_fontes} concluidas | "
                f"{self._percentual()}% | {tempo_str} decorridos]"
            )

            # A ultima coluna cresce conforme o conteudo (sem cortar o termo);
            # o log do Actions tem scroll horizontal para linhas longas.
            celulas_info = [d["termo"] or "-" for d in
                            (self.estado[n] for n in self.fontes)]
            celulas_info.append(f"{total_vagas} vagas brutas")
            larg_info = max(len("Ultimo Termo / Info"), *(len(c) for c in celulas_info))

            larguras = [20, 10, 7, 8, larg_info]
            borda = "+" + "+".join("-" * (w + 2) for w in larguras) + "+"
            cabecalhos = ["Fonte", "Status", "Vagas", "Requests", "Ultimo Termo / Info"]
            colorir = self.is_ci or self.is_tty

            def cel(c, w, cor=None):
                t = c.ljust(w)
                return _cor(cor, t) if (cor and colorir) else t

            linhas = [
                cabecalho,
                borda,
                "| " + " | ".join(cel(c, w, _ANSI["ciano"]) for c, w in zip(cabecalhos, larguras)) + " |",
                borda,
            ]

            for nome in self.fontes:
                d = self.estado[nome]
                lbl = d["label"][:20]
                st = d["status"][:10]
                vg = f"{d['vagas']:,}".replace(",", ".")
                rq = f"{d['requests']:,}".replace(",", ".")
                tm = d["termo"] or "-"
                linhas.append(
                    "| " + " | ".join([
                        cel(lbl, 20),
                        cel(st, 10, self._cor_status(d["status"])),
                        cel(vg.rjust(7), 7),
                        cel(rq.rjust(8), 8),
                        cel(tm, larg_info),
                    ]) + " |"
                )

            linhas.append(borda)
            resumo_st = f"{concluidas}/{total_fontes} conc."
            tot_vg = f"{total_vagas:,}".replace(",", ".")
            tot_rq = f"{total_reqs:,}".replace(",", ".")
            tot_info = f"{total_vagas} vagas brutas"
            linhas.append(
                "| " + " | ".join([
                    cel("TOTAL", 20, _ANSI["negrito"]),
                    cel(resumo_st, 10),
                    cel(tot_vg.rjust(7), 7),
                    cel(tot_rq.rjust(8), 8),
                    cel(tot_info, larg_info),
                ]) + " |"
            )
            linhas.append(borda)
            return "\n".join(linhas)

    def atualizar(
        self,
        nome: str,
        total: int | None = None,
        termo: str | None = None,
        requests: int | None = None,
        status: str | None = None,
        progresso: float | None = None,
    ) -> None:
        with self.lock:
            if nome in self.estado:
                if total is not None:
                    self.estado[nome]["vagas"] = total
                if termo is not None:
                    self.estado[nome]["termo"] = termo
                if requests is not None:
                    self.estado[nome]["requests"] = requests
                if progresso is not None:
                    self.estado[nome]["progresso"] = min(1.0, max(0.0, progresso))
                if status is not None:
                    self.estado[nome]["status"] = status
                elif self.estado[nome]["status"] == "Iniciando":
                    self.estado[nome]["status"] = "Coletando"

    @staticmethod
    def _cor_status(status: str) -> str | None:
        if status.startswith("Erro"):
            return _ANSI["vermelho"]
        return _STATUS_COR.get(status)

    def _percentual(self) -> int:
        with self.lock:
            if not self.estado:
                return 0
            return round(
                100 * sum(d["progresso"] for d in self.estado.values())
                / len(self.estado)
            )

    def finalizar_fonte(self, nome: str, total: int, requests: int) -> None:
        with self.lock:
            if nome in self.estado:
                self.estado[nome]["vagas"] = total
                self.estado[nome]["requests"] = requests
                self.estado[nome]["status"] = "Concluido"
                self.estado[nome]["termo"] = "finalizado"
                self.estado[nome]["progresso"] = 1.0
        if not self.is_tty:
            # Em CI/nao-TTY, renderiza se ja passou intervalo ou se todas terminaram
            concluidas = sum(
                1 for d in self.estado.values()
                if d["status"] == "Concluido" or d["status"].startswith("Erro")
            )
            if concluidas == len(self.estado):
                self.renderizar(forcar=True)
            else:
                self.renderizar(forcar=False)

    def erro_fonte(self, nome: str, erro: str = "", codigo: int | None = None) -> None:
        with self.lock:
            if nome in self.estado:
                self.estado[nome]["status"] = (
                    f"Erro {codigo}" if codigo else "Erro"
                )
                self.estado[nome]["termo"] = erro or "erro"
                self.estado[nome]["progresso"] = 1.0
        if not self.is_tty:
            self.renderizar(forcar=False)

    def renderizar(self, forcar: bool = False) -> None:
        agora = _time.time()
        if not self.is_tty and not forcar:
            # Em CI/nao-TTY, evita snapshots repetidos em menos de 15 segundos
            if agora - self.ultimo_render < 15.0:
                return

        texto = self.formatar()
        linhas = texto.splitlines()

        if self.is_ci:
            # Linhas planas, sem ::group::: o Actions decide sozinho se o
            # grupo nasce aberto ou fechado (hoje nasce fechado), e nao
            # existe parametro para forcar. A linha de titulo continua
            # permitindo um resumo de relance no meio do log.
            with self.lock:
                decorrido = agora - self.inicio
                minutos, segundos = divmod(int(decorrido), 60)
                tempo_str = f"{minutos:02d}m{segundos:02d}s"
                total_vagas = sum(d["vagas"] for d in self.estado.values())
                concluidas = sum(
                    1 for d in self.estado.values()
                    if d["status"] == "Concluido" or d["status"].startswith("Erro")
                )
                titulo = (
                    f"[resumo {_time.strftime('%H:%M:%S')}] {total_vagas} vagas | "
                    f"{concluidas}/{len(self.estado)} fontes ({tempo_str}) | "
                    f"{self._percentual()}%"
                )
            print(_cor(_ANSI["negrito"], titulo), flush=True)
            print(texto, flush=True)
            self.ultimo_render = agora
        elif self.is_tty:
            if self.linhas_impressas > 0:
                sys.stdout.write(f"\033[{self.linhas_impressas}F")
            sys.stdout.write(texto + "\n")
            sys.stdout.flush()
            self.linhas_impressas = len(linhas)
            self.ultimo_render = agora
        else:
            print(texto, flush=True)
            self.ultimo_render = agora

    def iniciar(self) -> None:
        intervalo = 1.0 if self.is_tty else RESUMO_INTERVALO_S

        def _loop():
            while not self.parar.wait(intervalo):
                self.renderizar()

        self.renderizar(forcar=True)
        self.thread_timer = threading.Thread(target=_loop, daemon=True)
        self.thread_timer.start()

    def encerrar(self) -> None:
        self.parar.set()
        if self.thread_timer is not None:
            self.thread_timer.join(timeout=2.0)
        if self.is_tty:
            self.renderizar(forcar=True)
            print("", flush=True)
        else:
            if _time.time() - self.ultimo_render > 1.0:
                self.renderizar(forcar=True)



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
        logger.warning("Portal desconhecido, ignorando: %s", source_name)
        return source_name, [], None, 0, None

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
        jobs = source.fetch(settings.search_terms)
        stats = source.stats
        requests = session.request_count
        ultimo_status = session.last_status_code

    if not settings.parallel_sources:
        logger.info("%s: %d vagas brutas (%d requests)", source_cls.label, len(jobs), requests)
    else:
        logger.debug("%s: %d vagas brutas (%d requests)", source_cls.label, len(jobs), requests)

    return source_name, jobs, stats, requests, ultimo_status


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
        try:
            with ThreadPoolExecutor(max_workers=len(settings.sources)) as pool:
                futures = {
                    pool.submit(_collect_source, nome, settings, _reportar(nome)): nome
                    for nome in settings.sources
                }
                for future in as_completed(futures):
                    nome = futures[future]
                    try:
                        _, jobs, fonte_stats, requests, ultimo = future.result()
                        resultados[nome] = (jobs, fonte_stats, requests)
                        if ultimo is not None and ultimo >= 400:
                            # Bloqueio/erro no portal: mostra o codigo no
                            # status e deixa o termo como "erro".
                            monitor.erro_fonte(nome, "erro", codigo=ultimo)
                        else:
                            monitor.finalizar_fonte(nome, len(jobs), requests)
                    except Exception as exc:
                        resultados[nome] = ([], None, 0)
                        monitor.erro_fonte(nome, str(exc), codigo=_codigo_do_erro(str(exc)))
        finally:
            monitor.encerrar()

        # Ordem estavel: a mesma ordem de settings.sources.
        for nome in settings.sources:
            jobs, fonte_stats, requests = resultados.get(nome, ([], None, 0))
            all_jobs.extend(jobs)
            if fonte_stats is not None:
                stats.append(fonte_stats)
            total_requests += requests
        return all_jobs, stats, total_requests

    for source_name in settings.sources:
        _, jobs, fonte_stats, requests, _ = _collect_source(source_name, settings)
        all_jobs.extend(jobs)
        if fonte_stats is not None:
            stats.append(fonte_stats)
        total_requests += requests

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

