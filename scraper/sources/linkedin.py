"""Coletor do LinkedIn Jobs pela API de convidado (sem login).

    GET https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search
        ?keywords=<termo>&geoId=106057199&f_TPR=r86400&sortBy=DD&start=<n>

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
    normalize_workplace,
)
from .base import JobSource


logger = logging.getLogger(__name__)

API_URL = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
)

# geoId do Brasil no LinkedIn. Ver o docstring: o nome do pais em portugues
# nao filtra nada e traz vagas dos EUA sem qualquer aviso.
GEO_ID_BRASIL = "106057199"

# As rodadas regulares sao incrementais. Como o projeto coleta tres vezes ao
# dia, 24 horas dao sobreposicao suficiente sem reler todo o historico em cada
# termo. A base consolidada preserva as vagas encontradas em rodadas anteriores.
FILTRO_ULTIMAS_24_HORAS = "r86400"
ORDENACAO_MAIS_RECENTES = "DD"

RESULTADOS_POR_PAGINA = 10

_ID_RE = re.compile(r"(\d+)$")
_WS_RE = re.compile(r"\s+")


DETAIL_API_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"


def parse_linkedin_description(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    node = soup.select_one(".show-more-less-html__markup, .description__text")
    return _WS_RE.sub(" ", node.get_text(" ", strip=True)).strip() if node else ""


class LinkedInSource(JobSource):

    name = "linkedin"
    label = "LinkedIn Jobs"
    COLLECTION_PROFILE = "last-24h-v1"
    # O portal entrega ate ~1.000 vagas por termo (medido: sem repeticao
    # pagina a pagina ate o start=990). O teto classico da busca guest.
    MAX_PAGES_PER_TERM = 100

    def fetch_term(self, term: str) -> list[Job]:
        jobs: list[Job] = []
        seen: set[str] = set()

        start_page = max(0, self.settings.start_page - 1)
        end_page = max(start_page + 1, self.page_limit())

        for page in range(start_page, end_page):
            response = self.session.get(
                API_URL,
                params={
                    "keywords": term,
                    "geoId": GEO_ID_BRASIL,
                    "f_TPR": FILTRO_ULTIMAS_24_HORAS,
                    "sortBy": ORDENACAO_MAIS_RECENTES,
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
        card_text = self._text(card)
        workplace_label = self._workplace_label(card)

        return Job(
            source=self.name,
            external_id=match.group(1),
            title=title,
            company=self._text(card.select_one("h4.base-search-card__subtitle")),
            url=url,
            description="",  # o card da busca nao traz a descricao
            location=location,
            workplace_type=self._modalidade(
                location,
                card_text,
                title,
                workplace_label=workplace_label,
            ),
            workplace_declared=bool(
                workplace_label
                and normalize_workplace(workplace_label) != NAO_INFORMADO
            ),
            published_date=publicada[:10],
            search_term=term,
        )

    @staticmethod
    def _modalidade(
        location: str,
        card_text: str = "",
        title: str = "",
        *,
        workplace_label: str = "",
    ) -> str:
        """Infere a modalidade com base no padrao do LinkedIn.

        - Campo de modalidade do card -> rotulo declarado pelo anunciante
        - Card/Local/Titulo contendo modalidade explicita -> modalidade indicada
        - Cidade sem modalidade -> Não informado

        A modalidade declarada no card tem prioridade sobre titulo, descricao
        resumida e localizacao. O titulo ainda cobre anuncios que escrevem
        "Trabalho Remoto" sem preencher o campo padrao.
        """
        declared = normalize_workplace(workplace_label)
        if declared != NAO_INFORMADO:
            return declared

        full_text = normalize(f"{location} {card_text} {title}")
        if not full_text:
            return NAO_INFORMADO
        if "hibrid" in full_text or "hybrid" in full_text:
            return HIBRIDO
        if "remoto" in full_text or "remote" in full_text:
            return REMOTO
        if "presencial" in full_text or "on site" in full_text or "onsite" in full_text:
            return PRESENCIAL
        return NAO_INFORMADO

    @classmethod
    def _workplace_label(cls, card) -> str:
        """Le o rotulo de modalidade que o LinkedIn inclui no card, quando ha."""
        selectors = (
            ".job-search-card__workplace-type",
            ".job-search-card__metadata-item",
            "[data-test*='workplace']",
        )
        for node in card.select(", ".join(selectors)):
            label = cls._text(node)
            if normalize_workplace(label) != NAO_INFORMADO:
                return label
        return ""




    @staticmethod
    def _text(node) -> str:
        if node is None:
            return ""
        return _WS_RE.sub(" ", node.get_text(" ", strip=True)).strip()
