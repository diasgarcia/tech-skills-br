"""Coletor da SerpApi (Google Jobs).

Exige chave de API informada via variavel de ambiente `SERPAPI_API_KEY`
ou configurada em `Settings.serpapi_api_key`.

Endpoint utilizado:
    GET https://serpapi.com/search
    Query: engine=google_jobs, q=<termo>, location=Brazil, hl=pt, gl=br, api_key=<KEY>
"""

from __future__ import annotations

import logging
from typing import Any

from ..geo import resolve_hubs
from ..models import (
    NAO_INFORMADO,
    REMOTO,
    Job,
    infer_workplace,
    normalize_workplace,
)
from .base import JobSource


logger = logging.getLogger(__name__)

API_URL = "https://serpapi.com/search"


class SerpApiSource(JobSource):
    name = "serpapi"
    label = "SerpApi (Google Jobs)"

    def fetch_term(self, term: str) -> list[Job]:
        api_key = self.settings.serpapi_api_key
        if not api_key:
            msg = "Chave SERPAPI_API_KEY nao configurada. Pulando SerpApi."
            logger.warning(msg)
            self.stats.errors.append(msg)
            return []

        jobs: list[Job] = []
        seen_ids: set[str] = set()

        hubs = resolve_hubs(self.settings.locations)
        is_filtered = bool(
            self.settings.locations
            and "todos" not in [l.lower() for l in self.settings.locations]
        )
        locations_to_query = (
            [h["serpapi_location"] for h in hubs if h.get("serpapi_location")]
            if is_filtered
            else ["Brazil"]
        )

        start_page = max(1, self.settings.start_page)
        end_page = max(start_page, self.settings.max_pages_per_term)

        for loc in locations_to_query:
            next_page_token: str | None = None
            for page_idx in range(start_page, end_page + 1):
                params: dict[str, Any] = {
                    "engine": "google_jobs",
                    "q": term,
                    "location": loc,
                    "hl": "pt",
                    "gl": "br",
                    "api_key": api_key,
                }
                if next_page_token:
                    params["next_page_token"] = next_page_token
                elif page_idx > 1:
                    params["start"] = (page_idx - 1) * 10


                resp_data = self.session.get_json(API_URL, params=params)
                if not resp_data or not isinstance(resp_data, dict):
                    break

                if "error" in resp_data:
                    err_msg = f"SerpApi erro ({loc}): {resp_data.get('error')}"
                    logger.warning(err_msg)
                    self.stats.errors.append(err_msg)
                    break

                batch = resp_data.get("jobs_results") or []
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

                pagination = resp_data.get("serpapi_pagination") or {}
                next_page_token = pagination.get("next_page_token")
                if not next_page_token or new_in_page == 0:
                    break

        return jobs


    def _parse(self, raw: dict[str, Any], term: str) -> Job | None:
        job_id = raw.get("job_id")
        title = raw.get("title")
        if not job_id or not title:
            return None

        company = (raw.get("company_name") or "").strip()
        location = (raw.get("location") or "").strip()

        url = ""
        apply_options = raw.get("apply_options") or []
        if apply_options and isinstance(apply_options, list):
            for opt in apply_options:
                if isinstance(opt, dict) and opt.get("link"):
                    url = opt["link"]
                    break

        if not url:
            related_links = raw.get("related_links") or []
            if related_links and isinstance(related_links, list):
                for rel in related_links:
                    if isinstance(rel, dict) and rel.get("link"):
                        url = rel["link"]
                        break

        if not url:
            url = raw.get("share_link") or ""


        description = raw.get("description") or ""

        highlights = raw.get("job_highlights") or []
        extra_texts: list[str] = []
        for hl in highlights:
            if isinstance(hl, dict):
                items = hl.get("items") or []
                if items and isinstance(items, list):
                    extra_texts.extend(str(item) for item in items if item)
        if extra_texts:
            description = f"{description}\n\nRequisitos:\n" + "\n".join(
                extra_texts
            )

        detected = raw.get("detected_extensions") or {}
        is_wfh = detected.get("work_from_home") is True
        extensions = raw.get("extensions") or []
        ext_text = " ".join(str(e) for e in extensions if e)

        if is_wfh:
            workplace = REMOTO
        else:
            workplace = infer_workplace(
                detected.get("schedule_type") or ext_text,
                location=location,
                title=title,
                description=description,
            )

        published_date = str(detected.get("posted_at") or "")


        return Job(
            source=self.name,
            external_id=str(job_id),
            title=str(title).strip(),
            company=company,
            url=url,
            description=description,
            location=location,
            workplace_type=workplace,
            published_date=published_date,
            search_term=term,
        )
