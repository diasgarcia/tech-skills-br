"""Coletor da GeekHunter (portal de vagas de tecnologia).

O site e SSR (server-side rendering): a listagem publica de vagas vem no
proprio HTML, sem API e sem autenticacao.

    GET https://www.geekhunter.com.br/pt/vagas?page=N

Detalhes praticos descobertos testando ao vivo:

- A paginacao `?page=N` SO funciona no path `/pt/vagas` (sem o `/pt`, o
  parametro e ignorado e a pagina 1 vem sempre).
- Sao ~803 vagas anunciadas em ~81 paginas de 10 cards.
- NAO existe filtro de nivel de senioridade via URL: a listagem mistura
  junior/pleno/senior. O corte fica para o portao de relevancia e o
  filtro de senioridade do projeto (esperar taxa alta de descarte).
- O card traz: titulo, link do detalhe, senioridade, modalidade,
  localizacao e um snippet da descricao. A descricao completa esta no
  detalhe (`/pt/<empresa>/jobs/<slug>-<n>`) -- enriquecimento possivel,
  mesmo modelo do ProgramaThor.
"""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from ..models import Job, normalize_workplace
from .base import JobSource

logger = logging.getLogger(__name__)

BASE_URL = "https://www.geekhunter.com.br"
JOBS_URL = f"{BASE_URL}/pt/vagas"

_CARD_RE = re.compile(r"^job-")
_WS_RE = re.compile(r"\s+")
_HORA_RE = re.compile(r"há \d+ (horas|dias)", re.I)


class GeekHunterSource(JobSource):
    name = "geekhunter"
    label = "GeekHunter"

    def fetch(self, terms: list[str]) -> list[Job]:
        """Ignora os termos do projeto: o portal nao tem busca por termo.

        A listagem e unica (sem filtro de nivel via URL); o recorte de
        nivel de entrada e feito pelo filtro de senioridade do projeto.
        """
        if terms:
            logger.debug(
                "[%s] termos ignorados (listagem unica do portal, sem "
                "filtro de nivel); coletando tudo e cortando no pipeline",
                self.name,
            )
        return super().fetch(["todas"])

    def fetch_term(self, term: str) -> list[Job]:
        """Coleta a listagem publica pagina por pagina."""
        jobs: list[Job] = []
        seen: set[str] = set()

        start_page = max(1, self.settings.start_page)
        end_page = max(start_page, self.settings.max_pages_per_term)

        for page in range(start_page, end_page + 1):
            response = self.session.get(JOBS_URL, params={"page": page})
            if response is None:
                break

            batch = self._parse_page(response.text, term)
            if not batch:
                break  # fim real da paginacao

            new_in_page = 0
            for job in batch:
                if job.external_id in seen:
                    continue
                seen.add(job.external_id)
                jobs.append(job)
                new_in_page += 1

            if new_in_page == 0:
                break  # paginacao repetindo; evita loop inutil

        return jobs

    def _parse_page(self, html: str, term: str) -> list[Job]:
        soup = BeautifulSoup(html, "html.parser")
        jobs: list[Job] = []
        for card in soup.select('li[id^="job-"]'):
            job = self._parse_card(card, term)
            if job is not None:
                jobs.append(job)
        return jobs

    def _parse_card(self, card, term: str) -> Job | None:
        link = card.select_one("h3 a[href]")
        if link is None:
            return None

        title = _WS_RE.sub(" ", link.get_text(" ", strip=True)).strip()
        href = link.get("href") or ""
        if not title or "/jobs/" not in href:
            return None

        # O slug da URL e estavel e identifica a vaga (o id numerico real
        # nao aparece no card).
        external_id = href.rstrip("/").split("/")[-1]

        # A empresa aparece como segmento do caminho (/pt/<empresa>/jobs/...).
        match = re.search(r"/pt/([^/]+)/jobs/", href)
        company_slug = match.group(1) if match else ""

        textos: list[str] = []
        for p in card.select("p.chakra-text"):
            texto = _WS_RE.sub(" ", p.get_text(" ", strip=True)).strip()
            if texto:
                textos.append(texto)

        senioridade = ""
        modalidade = ""
        location = ""
        descricao = ""
        for texto in textos:
            if texto in {"Júnior", "Pleno", "Sênior", "Estágio", "Trainee"}:
                # So confia no rotulo do portal quando ele declara nivel de
                # entrada. Para pleno/senior, deixa o filtro de senioridade
                # decidir pelo titulo (ex.: "Júnior/Pleno" ainda aceita
                # candidatos juniores e deve permanecer).
                if texto in {"Júnior", "Estágio", "Trainee"}:
                    senioridade = texto
            elif len(texto) <= 30 and normalize_workplace(texto) != "Não informado":
                modalidade = texto
            elif len(texto) <= 30 and texto.endswith("Brasil"):
                location = texto
            elif texto == "Tarefas e Responsabilidades":
                continue
            elif len(texto) > 120:
                descricao = texto

        return Job(
            source=self.name,
            external_id=external_id,
            title=title,
            company=company_slug,
            url=href if href.startswith("http") else f"{BASE_URL}{href}",
            description=descricao,
            location=location,
            workplace_type=normalize_workplace(modalidade),
            published_date="",
            search_term=term,
            seniority=senioridade,
        )
