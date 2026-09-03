"""Coletor da Gupy.

Endpoint usado: o mesmo JSON que o front do Portal Gupy chama no browser.

    GET https://employability-portal.gupy.io/api/v1/jobs?jobName=<termo>&limit=<n>&offset=<n>

Descoberto inspecionando a aba Network de https://portal.gupy.io/job-search/term=...
Nao e a API oficial `api.gupy.io` (essa exige token de empresa); este endpoint e
publico e nao pede autenticacao.

Detalhes praticos descobertos testando o endpoint ao vivo:
  - `limit` maximo e 100; acima disso a API responde HTTP 400.
  - `pagination.total` NAO e confiavel: vem limitado ao tamanho da pagina
    (com limit=100 ele responde total=100 mesmo havendo centenas de vagas).
    Por isso paginamos ate receber uma pagina vazia, e nao ate bater o `total`.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from ..models import Job, normalize_workplace
from .base import JobSource

logger = logging.getLogger(__name__)

API_URL = "https://employability-portal.gupy.io/api/v1/jobs"
MAX_LIMIT = 100

# Paginas de carreiras COMPARTILHADAS (holdings): o careerPageName rotula
# a pagina, nao a empresa. Ex.: Grupo Fertipar -> "Agronegocio". Nesses
# casos a empresa vem do subdominio da URL (grupofertipar.gupy.io).
_PAGINAS_GENERICAS = {
    "agronegocio",
    "banco de talentos",
    "banco talentos",
    "carreiras",
    "vagas",
    "portal de vagas",
    "trabalhe conosco",
    "talentos",
    "gente e gestao",
    "rh",
    "empregos",
    "carreiras e talentos",
}


def _nome_empresa(raw: dict) -> str:
    nome = (raw.get("careerPageName") or "").strip()
    if nome.lower() in _PAGINAS_GENERICAS:
        slug = urlparse(raw.get("careerPageUrl") or "").hostname or ""
        slug = slug.split(".")[0]
        palavras = [p.capitalize() for p in re.split(r"[-_ ]+", slug) if p]
        derivado = " ".join(palavras)
        if derivado:
            return derivado
    return nome


class GupySource(JobSource):
    name = "gupy"
    label = "Gupy (portal.gupy.io)"
    MAX_PAGES_PER_TERM = 20

    def fetch_term(self, term: str) -> list[Job]:
        jobs: list[Job] = []
        seen_ids: set[str] = set()
        limit = min(self.settings.page_size, MAX_LIMIT)
        start_page = max(0, self.settings.start_page - 1)
        end_page = max(start_page + 1, self.page_limit())

        for page in range(start_page, end_page):

            offset = page * limit
            payload = self.session.get_json(
                API_URL,
                params={"jobName": term, "limit": limit, "offset": offset},
            )

            if not payload:
                break

            batch = payload.get("data") or []
            if not batch:
                break  # fim real da paginacao

            new_in_page = 0
            for raw in batch:
                job = self._parse(raw, term)
                if job is None or job.external_id in seen_ids:
                    continue
                seen_ids.add(job.external_id)
                jobs.append(job)
                new_in_page += 1

            if len(batch) < limit:
                break  # ultima pagina
            if new_in_page == 0:
                break  # API repetindo resultados; evita loop inutil

        return jobs

    def _parse(self, raw: dict, term: str) -> Job | None:
        job_id = raw.get("id")
        title = raw.get("name")
        if job_id is None or not title:
            return None

        city = (raw.get("city") or "").strip()
        state = (raw.get("state") or "").strip()
        location = ", ".join(part for part in (city, state) if part)
        if not location:
            location = (raw.get("country") or "").strip()

        url = raw.get("jobUrl") or raw.get("careerPageUrl") or ""
        if "&inactive" in url.lower():
            return None

        pub_date = (raw.get("publishedDate") or "")[:10]
        if pub_date and pub_date < "2026-01-01":
            return None

        return Job(
            source=self.name,
            external_id=str(job_id),
            title=title,
            company=_nome_empresa(raw),
            url=url,
            description=raw.get("description") or "",
            location=location,
            workplace_type=normalize_workplace(
                raw.get("workplaceType")
                or ("remote" if raw.get("isRemoteWork") else "")
            ),
            published_date=pub_date,
            search_term=term,
        )

