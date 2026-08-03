"""Coletor do LinkedIn Jobs pela API de convidado (sem login).

    GET https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search
        ?keywords=<termo>&geoId=106057199&start=<n>

E o endpoint que o proprio site chama para carregar mais resultados na busca
publica. Devolve um fragmento HTML com 10 cards por chamada, e responde 200 ate
com o User-Agent do projeto -- nao exige navegador nem sessao.

**A localizacao precisa ser o geoId.** Passar `location=Brasil` (em portugues)
falha em silencio: a API responde 200 e devolve vagas dos Estados Unidos
("Brooklyn, NY", "San Francisco Bay Area"). `location=Brazil` em ingles filtra
quase tudo, mas o geoId e o unico que acertou 10 de 10 nos testes.

Limitacao: o card da busca **nao traz a descricao da vaga**. A classificacao
desta fonte se apoia so no titulo -- que no LinkedIn costuma ser descritivo
("Desenvolvedor Back-end Junior"). Buscar a descricao exigiria uma requisicao
por vaga, o que multiplicaria a carga no portal e aumentaria o risco de bloqueio.

Esta e a fonte com maior chance de passar a bloquear no futuro. Se isso
acontecer, `PoliteSession.get` devolve None, o coletor devolve o que tiver e a
coleta das outras fontes segue normalmente.
"""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from ..models import NAO_INFORMADO, REMOTO, Job, normalize
from .base import JobSource

logger = logging.getLogger(__name__)

API_URL = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
)

# geoId do Brasil no LinkedIn. Ver o docstring: o nome do pais em portugues
# nao filtra nada e traz vagas dos EUA sem qualquer aviso.
GEO_ID_BRASIL = "106057199"

RESULTADOS_POR_PAGINA = 10

_ID_RE = re.compile(r"(\d+)$")
_WS_RE = re.compile(r"\s+")


class LinkedInSource(JobSource):
    name = "linkedin"
    label = "LinkedIn Jobs"

    def fetch_term(self, term: str) -> list[Job]:
        jobs: list[Job] = []
        seen: set[str] = set()

        for page in range(self.settings.max_pages_per_term):
            response = self.session.get(
                API_URL,
                params={
                    "keywords": term,
                    "geoId": GEO_ID_BRASIL,
                    "start": page * RESULTADOS_POR_PAGINA,
                },
            )
            if response is None:
                break

            batch = self._parse_page(response.text, term)
            if not batch:
                break

            novos = 0
            for job in batch:
                if job.external_id in seen:
                    continue
                seen.add(job.external_id)
                jobs.append(job)
                novos += 1

            if novos == 0:
                break  # a API comecou a repetir resultados

        return jobs

    def _parse_page(self, html: str, term: str) -> list[Job]:
        soup = BeautifulSoup(html, "html.parser")
        jobs: list[Job] = []
        for card in soup.select("div.base-card"):
            job = self._parse_card(card, term)
            if job is not None:
                jobs.append(job)
        return jobs

    def _parse_card(self, card, term: str) -> Job | None:
        urn = card.get("data-entity-urn") or ""
        match = _ID_RE.search(urn)
        title = self._text(card.select_one("h3.base-search-card__title"))
        if match is None or not title:
            return None

        link = card.select_one("a.base-card__full-link")
        url = (link.get("href") or "").split("?")[0] if link else ""

        momento = card.select_one("time")
        publicada = (momento.get("datetime") or "") if momento else ""

        location = self._text(card.select_one("span.job-search-card__location"))

        return Job(
            source=self.name,
            external_id=match.group(1),
            title=title,
            company=self._text(card.select_one("h4.base-search-card__subtitle")),
            url=url,
            description="",  # o card da busca nao traz a descricao
            location=location,
            workplace_type=self._modalidade(location),
            published_date=publicada[:10],
            search_term=term,
        )

    @staticmethod
    def _modalidade(location: str) -> str:
        """So afirma remoto quando o proprio texto do local diz isso.

        O card nao tem campo de modalidade; presencial e hibrido sao
        indistinguiveis aqui, entao ficam como nao informado em vez de chute.
        """
        texto = normalize(location)
        if "remoto" in texto or "remote" in texto:
            return REMOTO
        return NAO_INFORMADO

    @staticmethod
    def _text(node) -> str:
        if node is None:
            return ""
        return _WS_RE.sub(" ", node.get_text(" ", strip=True)).strip()
