"""Coletor da GeekHunter (portal de vagas de tecnologia).

O site e SSR (server-side rendering): a listagem publica de vagas vem no
proprio HTML, sem API e sem autenticacao.

    GET https://www.geekhunter.com.br/pt/vagas?page=N

Detalhes praticos descobertos testando ao vivo:

- A paginacao `?page=N` SO funciona no path `/pt/vagas` (sem o `/pt`, o
  parametro e ignorado e a pagina 1 vem sempre).
- O total de paginas muda com frequencia. A ultima pagina e lida dos
  controles de paginacao do proprio portal.
- O portal responde 404 na primeira pagina depois do fim, em vez de
  devolver uma pagina vazia. Esse 404 e fim normal de paginacao.
- NAO existe filtro de nivel de senioridade via URL: a listagem mistura
  junior/pleno/senior. O corte fica para o portao de relevancia e o
  filtro de senioridade do projeto (esperar taxa alta de descarte).
- O card traz: titulo, link do detalhe, senioridade, modalidade,
  localizacao e um snippet da descricao. A descricao completa esta no
  detalhe (`/pt/<empresa>/jobs/<slug>-<n>`) -- enriquecimento possivel.
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
_PAGE_RE = re.compile(r"(?:[?&])page=(\d+)")


class GeekHunterSource(JobSource):
    name = "geekhunter"
    label = "GeekHunter"
    MAX_PAGES_PER_TERM = 200

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
        end_page = max(start_page, self.page_limit())

        page = start_page
        while page <= end_page:
            response = self.session.get(JOBS_URL, params={"page": page})
            if response is None:
                # Sem os controles de paginacao, a unica forma de descobrir
                # o fim e consultar a pagina seguinte. A GeekHunter responde
                # 404 nesse caso; depois de paginas validas, isso nao e erro.
                if jobs and self.session.last_status_code == 404:
                    logger.debug(
                        "[%s] fim da paginacao na pagina %d (HTTP 404 esperado)",
                        self.name,
                        page,
                    )
                    self.session.last_status_code = None
                break

            if page == start_page:
                ultima_pagina = self._ultima_pagina(response.text)
                if ultima_pagina is not None:
                    end_page = min(end_page, max(page, ultima_pagina))

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

            page += 1

        return jobs

    @staticmethod
    def _ultima_pagina(html: str) -> int | None:
        """Le o maior numero declarado nos links de paginacao."""
        soup = BeautifulSoup(html, "html.parser")
        paginas: list[int] = []
        for link in soup.select('a[href*="page="]'):
            match = _PAGE_RE.search(link.get("href") or "")
            if match:
                paginas.append(int(match.group(1)))
        return max(paginas, default=None)

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
        publicada = ""
        for texto in textos:
            if texto in {"Júnior", "Pleno", "Sênior", "Estágio", "Trainee"}:
                # So confia no rotulo do portal quando ele declara nivel de
                # entrada. Para pleno/senior, deixa o filtro de senioridade
                # decidir pelo titulo (ex.: "Júnior/Pleno" ainda aceita
                # candidatos juniores e deve permanecer).
                if texto in {"Júnior", "Estágio", "Trainee"}:
                    senioridade = texto
            elif re.search(r"(?:publicada|atualizada)\s+h[aá]\s+\d+\s+horas?", texto, re.I):
                publicada = texto
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
            published_date=publicada,
            search_term=term,
            seniority=senioridade,
        )
