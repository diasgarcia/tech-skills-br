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

from ..models import (
    HIBRIDO,
    NAO_INFORMADO,
    PRESENCIAL,
    REMOTO,
    Job,
    normalize,
)
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


DETAIL_API_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"


class LinkedInSource(JobSource):

    name = "linkedin"
    label = "LinkedIn Jobs"

    def fetch_term(self, term: str) -> list[Job]:
        jobs: list[Job] = []
        seen: set[str] = set()

        start_page = max(0, self.settings.start_page - 1)
        end_page = max(start_page + 1, self.settings.max_pages_per_term)

        for page in range(start_page, end_page):
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

    def _fetch_description(self, job_id: str) -> str:
        """Busca a descricao completa da vaga no endpoint publico de detalhe do LinkedIn."""
        if not self.session:
            return ""
        try:
            url = DETAIL_API_URL.format(job_id=job_id)
            resp = self.session.get(url)
            if not resp or resp.status_code != 200:
                return ""
            soup = BeautifulSoup(resp.text, "html.parser")
            desc_el = soup.select_one(".show-more-less-html__markup, .description__text")
            if desc_el:
                return self._text(desc_el)
        except Exception as e:
            logger.debug("[%s] Falha ao obter descricao da vaga %s: %s", self.name, job_id, e)
        return ""


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
        card_text = self._text(card)

        return Job(
            source=self.name,
            external_id=match.group(1),
            title=title,
            company=self._text(card.select_one("h4.base-search-card__subtitle")),
            url=url,
            description="",  # o card da busca nao traz a descricao
            location=location,
            workplace_type=self._modalidade(location, card_text, title),
            published_date=publicada[:10],
            search_term=term,
        )

    @staticmethod
    def _modalidade(location: str, card_text: str = "", title: str = "") -> str:
        """Infere a modalidade com base no padrao do LinkedIn.

        - Card/Local/Titulo contendo 'Híbrido'/'Hybrid' -> Híbrido
        - Card/Local/Titulo contendo 'Remoto'/'Remote' -> Remoto
        - 'Brasil' / 'Brazil' / 'Nacional' -> Remoto (vagas de escopo nacional)
        - Cidade física ('Rio de Janeiro e Região', 'Curitiba, PR') -> Presencial
        - Vazio -> Não informado

        O titulo entra na analise porque o card da busca nao informa modalidade,
        e anuncios remotos costumam dizer isso no titulo ("Trabalho Remoto")
        enquanto a localizacao do card lista uma cidade qualquer.
        """
        full_text = normalize(f"{location} {card_text} {title}")
        if not full_text:
            return NAO_INFORMADO
        if "hibrid" in full_text or "hybrid" in full_text:
            return HIBRIDO
        if "remoto" in full_text or "remote" in full_text:
            return REMOTO
        loc_norm = normalize(location)
        if loc_norm in ("brasil", "brazil", "nacional"):
            return REMOTO
        if loc_norm:
            return PRESENCIAL
        return NAO_INFORMADO




    @staticmethod
    def _text(node) -> str:
        if node is None:
            return ""
        return _WS_RE.sub(" ", node.get_text(" ", strip=True)).strip()
