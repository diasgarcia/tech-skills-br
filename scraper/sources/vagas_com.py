"""Coletor do Vagas.com.br.

Diferente do que se costuma supor, a listagem de busca do Vagas.com e renderizada
no servidor -- os cards ja vem no HTML. Nao e preciso Selenium/Playwright aqui;
`requests` + BeautifulSoup bastam (verificado ao vivo).

URL de busca:  https://www.vagas.com.br/vagas-de-<termo-com-hifen>?pagina=<n>

Estrutura de cada card (`<li class="vaga">`):
    h2.cargo > a.link-detalhes-vaga[data-id-vaga][title][href]
    span.emprVaga            -> empresa
    span.nivelVaga           -> nivel declarado pelo anunciante
    div.detalhes p           -> trecho da descricao
    div.vaga-local           -> cidade / UF
    span.data-publicacao     -> data
"""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from ..models import NAO_INFORMADO, REMOTO, Job, normalize
from .base import JobSource

logger = logging.getLogger(__name__)

BASE_URL = "https://www.vagas.com.br"
_WS_RE = re.compile(r"\s+")


def slugify_term(term: str) -> str:
    """'desenvolvedor junior' -> 'desenvolvedor-junior' (formato da URL do site)."""
    return re.sub(r"\s+", "-", normalize(term)).strip("-")


class VagasComSource(JobSource):
    name = "vagas"
    label = "Vagas.com.br"

    def fetch_term(self, term: str) -> list[Job]:
        jobs: list[Job] = []
        seen_ids: set[str] = set()
        url = f"{BASE_URL}/vagas-de-{slugify_term(term)}"

        for page in range(1, self.settings.max_pages_per_term + 1):
            response = self.session.get(url, params={"pagina": page})
            if response is None:
                break

            batch = self._parse_page(response.text, term)
            if not batch:
                break  # sem mais resultados

            new_in_page = 0
            for job in batch:
                if job.external_id in seen_ids:
                    continue
                seen_ids.add(job.external_id)
                jobs.append(job)
                new_in_page += 1

            if new_in_page == 0:
                break  # o site repetiu a pagina anterior

        return jobs

    def _parse_page(self, html: str, term: str) -> list[Job]:
        soup = BeautifulSoup(html, "html.parser")
        jobs: list[Job] = []

        for card in soup.select("li.vaga"):
            link = card.select_one("a.link-detalhes-vaga")
            if link is None:
                continue

            location = self._text(card.select_one(".vaga-local"))

            job_id = link.get("data-id-vaga")
            title = link.get("title") or self._text(link)
            if not job_id or not title:
                continue

            href = link.get("href") or ""
            url = href if href.startswith("http") else f"{BASE_URL}{href}"

            jobs.append(
                Job(
                    source=self.name,
                    external_id=str(job_id),
                    title=title,
                    company=self._text(card.select_one("span.emprVaga")),
                    url=url,
                    description=self._text(card.select_one("div.detalhes")),
                    location=location,
                    workplace_type=self._workplace(location),
                    published_date=self._text(card.select_one("span.data-publicacao")),
                    search_term=term,
                )
            )
        return jobs

    @staticmethod
    def _workplace(location: str) -> str:
        """Modalidade de trabalho a partir do campo de local do card.

        O Vagas.com classifica as vagas em tres modalidades ("Na empresa",
        "Na empresa e Home Office", "100% Home Office"), mas o card da listagem
        so mostra "100% Home Office" ou o nome da cidade -- um card hibrido e
        um presencial sao indistinguiveis aqui. Por isso so o remoto e afirmado;
        o resto fica como nao informado em vez de ser adivinhado.

        (As tres modalidades existem como filtro de busca, mas os resultados
        filtrados nao reconciliam com a paginacao da busca normal: para alguns
        termos o filtro "Na empresa" sozinho ja devolve a pagina inteira.)
        """
        return REMOTO if "home office" in normalize(location) else NAO_INFORMADO

    @staticmethod
    def _text(node) -> str:
        if node is None:
            return ""
        return _WS_RE.sub(" ", node.get_text(" ", strip=True)).strip()
