"""Jobbol: listagem JSON anonima e detalhes em JSON-LD, sem navegador.

A listagem nao traz a descricao. Cada candidato de entrada dentro da janela
recebe uma chamada de detalhe; IDs repetidos reutilizam o detalhe da rodada.
Anuncios promovidos podem furar a ordem de data, entao uma data antiga nao
encerra a paginacao. O teto de paginas continua valendo.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from ..config import Settings, load_jobbol_searches, load_search_terms
from ..http_client import PoliteSession
from ..models import HIBRIDO, NAO_INFORMADO, PRESENCIAL, REMOTO, Job, normalize
from ..seniority import default_filter
from .base import JobSource

logger = logging.getLogger(__name__)
SITE_URL = "https://candidatos.jobbol.com.br"
API_URL = f"{SITE_URL}/assets/php/buscar-vagas-redis.php"
RESULTADOS_POR_PAGINA = 50
FUSO_BRASIL = timezone(timedelta(hours=-3))


def _jobposting(html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(tag.get_text())
        except ValueError:
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get("@type") == "JobPosting":
                return node
            graph = node.get("@graph")
            for item in graph if isinstance(graph, list) else []:
                if isinstance(item, dict) and item.get("@type") == "JobPosting":
                    return item
    return None


def _descricao(raw: str) -> str:
    """Mantem Observacoes tecnicas antes dos beneficios, que o extrator corta."""
    soup = BeautifulSoup(raw, "html.parser")
    headers = soup.find_all("p")
    observations = next((p for p in headers if normalize(p.get_text(" ", strip=True)) == "observacoes"), None)
    benefits = next((p for p in headers if normalize(p.get_text(" ", strip=True)) == "beneficios"), None)
    if observations is not None and benefits is not None:
        section = [observations]
        for sibling in observations.next_siblings:
            if getattr(sibling, "name", None) == "p" and sibling.find("strong"):
                break
            section.append(sibling)
        observations.string = "Requisitos adicionais (Observações)"
        for node in section:
            benefits.insert_before(node.extract())
    return soup.get_text(" ", strip=True)


class JobbolSource(JobSource):
    name = "jobbol"
    label = "Jobbol"
    COLLECTION_PROFILE = "last-3d-jsonld-v1"
    MAX_PAGES_PER_TERM = 100

    def __init__(self, session: PoliteSession, settings: Settings) -> None:
        super().__init__(session, settings)
        self.searches = load_jobbol_searches()
        self._details: dict[str, Job] = {}
        self.stats.collection_profile = f"last-{settings.jobbol_days_back}d-jsonld-v1"

    def fetch(self, terms: list[str]) -> list[Job]:
        self._details.clear()
        searches = list(self.searches) if terms == load_search_terms() else terms
        return super().fetch(searches)

    def fetch_term(self, term: str) -> list[Job]:
        page_size = min(self.settings.page_size, RESULTADOS_POR_PAGINA)
        params = dict(self.searches.get(term, {"cargo": term}))
        params.update(sort="data_desc", limit=page_size)
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.settings.jobbol_days_back)
        jobs: list[Job] = []
        seen: set[str] = set()
        start_page = max(0, self.settings.start_page - 1)
        params["offset"] = start_page * page_size

        for _ in range(start_page, max(start_page + 1, self.page_limit())):
            payload = self.session.get_json(API_URL, params=params)
            if not isinstance(payload, dict) or not isinstance(payload.get("vagas"), list):
                self._erro(f"{term}: listagem indisponivel ou fora do formato esperado")
                break
            batch = payload["vagas"]
            if not batch:
                break
            novos = 0
            for raw in batch:
                if not isinstance(raw, dict):
                    self._erro(f"{term}: registro fora do formato esperado")
                    continue
                job_id = str(raw.get("jobkey") or "")
                title = raw.get("CARGO") or ""
                if not job_id.isdigit() or not isinstance(title, str) or not title.strip():
                    self._erro(f"{term}: registro sem ID ou titulo valido")
                    continue
                if job_id in seen:
                    continue
                seen.add(job_id)
                novos += 1
                try:
                    published = datetime.fromtimestamp(int(raw["post_date_epoch"]), timezone.utc)
                except (KeyError, ValueError, TypeError, OverflowError, OSError):
                    self._erro(f"{job_id}: data de publicacao invalida")
                    continue
                if published < cutoff:
                    continue
                if self.settings.only_junior and not default_filter().is_entry_level(title):
                    continue
                job = self._details.get(job_id)
                if job is None:
                    job = self._detalhe(raw, published, term)
                    if job is not None:
                        self._details[job_id] = job
                if job is not None:
                    jobs.append(job)
            if novos == 0:
                break
            total = payload.get("total")
            if isinstance(total, int) and params["offset"] + len(batch) >= total:
                break
            # Respeita o tamanho efetivamente retornado se o servidor reduzir
            # o limit. Avancar pelo tamanho pedido poderia pular anuncios.
            params["offset"] += len(batch)
        return jobs

    def _erro(self, message: str) -> None:
        message = f"{self.name}: {message}"
        logger.warning(message)
        self.stats.errors.append(message)

    def _detalhe(self, raw: dict, published: datetime, term: str) -> Job | None:
        job_id = str(raw["jobkey"])
        url = f"{SITE_URL}/vaga/{job_id}"
        response = self.session.get(url)
        posting = _jobposting(response.text) if response is not None else None
        if posting is None or not isinstance(posting.get("description"), str) or not posting["description"].strip():
            self._erro(f"{job_id}: detalhe indisponivel ou sem descricao JobPosting")
            return None
        identifier = posting.get("identifier") or {}
        if isinstance(identifier, dict) and str(identifier.get("value", job_id)) != job_id:
            self._erro(f"{job_id}: detalhe retornou outro ID")
            return None
        org = posting.get("hiringOrganization") or {}
        company = org.get("name", "") if isinstance(org, dict) else ""
        location = ", ".join(str(raw.get(key) or "").strip() for key in ("CIDADE", "ESTADO")
                             if raw.get(key))
        workplace = {
            "presencial": PRESENCIAL, "remota": REMOTO, "remoto": REMOTO,
            "hibrida": HIBRIDO, "hibrido": HIBRIDO,
        }.get(normalize(raw.get("TIPO") or ""), NAO_INFORMADO)
        if workplace == NAO_INFORMADO and posting.get("jobLocationType") == "TELECOMMUTE":
            workplace = REMOTO
        return Job(
            source=self.name, external_id=job_id, title=raw["CARGO"],
            company=company or str(raw.get("EMPRESA") or ""), url=url,
            description=_descricao(posting["description"]), location=location,
            workplace_type=workplace, workplace_declared=workplace != NAO_INFORMADO,
            published_date=published.astimezone(FUSO_BRASIL).date().isoformat(), search_term=term,
        )
