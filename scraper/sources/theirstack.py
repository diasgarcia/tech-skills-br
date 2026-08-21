"""Coletor da TheirStack (theirstack.com).

Exige chave de API informada via variavel de ambiente `THEIRSTACK_API_KEY`
ou configurada em `Settings.theirstack_api_key`.

Endpoint utilizado:
    POST https://api.theirstack.com/v1/jobs/search
    Header: Authorization: Bearer <KEY>
"""

from __future__ import annotations

import logging
from typing import Any

from ..geo import resolve_hubs
from ..models import (
    HIBRIDO,
    NAO_INFORMADO,
    PRESENCIAL,
    REMOTO,
    Job,
    infer_workplace,
    normalize_workplace,
)
from .base import JobSource


logger = logging.getLogger(__name__)

API_URL = "https://api.theirstack.com/v1/jobs/search"
MAX_LIMIT = 25



class TheirStackSource(JobSource):
    name = "theirstack"
    label = "TheirStack API"

    def fetch_term(self, term: str) -> list[Job]:
        api_key = self.settings.theirstack_api_key
        if not api_key:
            msg = "Chave THEIRSTACK_API_KEY nao configurada. Pulando TheirStack."
            logger.warning(msg)
            self.stats.errors.append(msg)
            return []

        jobs: list[Job] = []
        seen_ids: set[str] = set()
        limit = min(self.settings.page_size, MAX_LIMIT)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Resolve se há filtros de polo específicos
        hubs = resolve_hubs(self.settings.locations)
        is_filtered = bool(
            self.settings.locations
            and "todos" not in [l.lower() for l in self.settings.locations]
        )

        start_page = max(0, self.settings.start_page - 1)
        end_page = max(start_page + 1, self.settings.max_pages_per_term)

        for page in range(start_page, end_page):
            payload_req: dict[str, Any] = {
                "page": page,
                "limit": limit,
                "job_title_or": [term],
                "posted_at_max_age_days": 30,
                "order_by": [{"desc": True, "field": "date_posted"}],
            }



            if is_filtered:
                loc_ids = [
                    int(h["theirstack_id"])
                    for h in hubs
                    if h.get("theirstack_id")
                ]
                if loc_ids:
                    payload_req["job_location_or"] = loc_ids
                else:
                    payload_req["job_country_code_or"] = ["BR"]
            else:
                payload_req["job_country_code_or"] = ["BR"]

            resp_data = self.session.post_json(
                API_URL,
                headers=headers,
                json=payload_req,
            )

            if not resp_data or not isinstance(resp_data, dict):
                break

            batch = resp_data.get("data") or []
            if not batch:
                break

            new_in_page = 0
            for raw in batch:
                job = self._parse(raw, term)
                if job is None or job.external_id in seen_ids:
                    continue
                seen_ids.add(job.external_id)
                jobs.append(job)
                new_in_page += 1

            if len(batch) < limit or new_in_page == 0:
                break

        return jobs

    def _parse(self, raw: dict[str, Any], term: str) -> Job | None:
        job_id = raw.get("id")
        title = raw.get("job_title") or raw.get("title")
        if not job_id or not title:
            return None

        company_obj = raw.get("company_object")
        company = ""
        if isinstance(company_obj, dict):
            company = (company_obj.get("name") or "").strip()
        if not company:
            company = str(raw.get("company") or "").strip()

        location = (raw.get("location") or raw.get("city") or "").strip()
        if not location and raw.get("country_code"):
            location = str(raw.get("country_code"))

        is_remote = raw.get("remote") is True
        is_hybrid = raw.get("hybrid") is True

        if is_remote:
            workplace = REMOTO
        elif is_hybrid:
            workplace = HIBRIDO
        elif raw.get("remote") is False and raw.get("hybrid") is False:
            workplace = (
                PRESENCIAL
                if location and "remoto" not in location.lower()
                else NAO_INFORMADO
            )
        else:
            workplace = infer_workplace(
                raw.get("workplace_type"),
                location=location,
                title=title,
                description=raw.get("description"),
            )

        date_posted = raw.get("date_posted") or ""
        published_date = str(date_posted)[:10] if date_posted else ""

        return Job(
            source=self.name,
            external_id=str(job_id),
            title=title.strip(),
            company=company,
            url=raw.get("final_url") or raw.get("url") or "",
            description=raw.get("description") or "",
            location=location,
            workplace_type=workplace,
            published_date=published_date,
            search_term=term,
        )

