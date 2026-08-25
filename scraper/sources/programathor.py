"""Coletor da ProgramaThor (programathor.com.br).

Portal 100% de vagas de tecnologia. A listagem e renderizada no servidor, entao
`requests` + BeautifulSoup bastam (verificado ao vivo).

Duas particularidades descobertas testando o site, e que mudam a integracao:

1. **O parametro `?search=` e ignorado.** Buscar `?search=python` devolve
   exatamente o mesmo conjunto de vagas que a listagem sem filtro -- conferido
   comparando os ids retornados. Ja `?expertise=` e `?page=` funcionam.

   Por isso esta fonte NAO percorre os termos de busca do projeto: repetir 13
   consultas que o site ignora seria 13x mais requests para o mesmo resultado.
   Em vez disso ela usa os filtros nativos de nivel de entrada, o que da o
   mesmo dado com duas consultas.

2. **Vagas expiradas continuam na listagem**, marcadas com um selo "Vencida"
   dentro do titulo. Sao descartadas: nao sao posicoes abertas.

O card traz senioridade e tecnologias declaradas pelo proprio portal, o que
torna esta fonte util para conferir a classificacao por keywords do projeto
contra uma categorizacao nativa.
"""

from __future__ import annotations

import logging
import re
from bs4 import BeautifulSoup


try:
    from curl_cffi import requests as cffi_requests
    _HAS_CURL_CFFI = True
except ImportError:
    _HAS_CURL_CFFI = False

from ..models import REMOTO, Job, normalize_workplace
from .base import JobSource

logger = logging.getLogger(__name__)

BASE_URL = "https://programathor.com.br"
JOBS_URL = f"{BASE_URL}/jobs"


# Filtros nativos que correspondem a nivel de entrada. As chaves viram os
# "termos" desta fonte (ver `fetch`).
FILTROS_NIVEL_ENTRADA: dict[str, dict[str, str]] = {
    "Júnior": {"expertise": "Júnior"},
    "Estágio": {"contract_type": "Estágio"},
}

# Cada campo do card e identificado pelo icone, e nao pela posicao: vagas sem
# salario ou sem aviso de mudanca deslocam a ordem dos spans.
CAMPOS_POR_ICONE = {
    "fa-briefcase": "company",
    "fa-map-marker-alt": "location",
    "fa-building": "company_type",
    "fa-chart-bar": "expertise",
    "fa-file-alt": "contract",
    "fa-money-bill-alt": "salary",
}

_ID_RE = re.compile(r"/jobs/(\d+)")
_MODALIDADE_RE = re.compile(r"\(([^)]+)\)\s*$")
_WS_RE = re.compile(r"\s+")


class ProgramathorSource(JobSource):
    name = "programathor"
    label = "ProgramaThor"

    def fetch(self, terms: list[str]) -> list[Job]:
        """Ignora os termos do projeto e usa os filtros nativos do portal.

        O site nao tem busca textual funcional (ver o docstring do modulo), e
        como ele so publica vaga de tecnologia, filtrar por nivel de entrada ja
        entrega o recorte que o projeto quer.
        """
        if terms:
            logger.debug(
                "[%s] termos ignorados (o portal nao tem busca textual); "
                "usando os filtros nativos %s",
                self.name, list(FILTROS_NIVEL_ENTRADA),
            )
        return super().fetch(list(FILTROS_NIVEL_ENTRADA))

    def _get_page_html(self, url: str, params: dict) -> str | None:
        """Faz a requisicao contornando Cloudflare TLS fingerprinting com curl_cffi quando disponivel."""
        if _HAS_CURL_CFFI:
            try:
                with cffi_requests.Session(impersonate="chrome124") as s:
                    r = s.get(url, params=params, timeout=20)
                    if r.status_code == 200:
                        return r.text
                    logger.warning("[%s] HTTP %s em %s (params=%s)", self.name, r.status_code, url, params)
                    return None
            except Exception as e:
                logger.warning("[%s] Erro com curl_cffi: %s, tentando fallback", self.name, e)

        # Fallback para PoliteSession padrao
        if self.session:
            response = self.session.get(url, params=params)
            return response.text if response is not None else None
        return None

    def fetch_term(self, term: str) -> list[Job]:
        """Coleta um filtro nativo (`term` e uma chave de FILTROS_NIVEL_ENTRADA)."""
        params = FILTROS_NIVEL_ENTRADA.get(term, {"expertise": term})

        jobs: list[Job] = []
        seen: set[str] = set()
        anterior: set[str] = set()

        start_page = max(1, self.settings.start_page)
        end_page = max(start_page, self.settings.max_pages_per_term)

        for page in range(start_page, end_page + 1):
            html = self._get_page_html(JOBS_URL, params={**params, "page": page})

            if not html:
                break

            batch = self._parse_page(html, term)

            ids_pagina = {job.external_id for job in batch}
            if not ids_pagina or ids_pagina == anterior:
                break  # fim da lista, ou o site repetiu a pagina anterior

            for job in batch:
                if job.external_id in seen:
                    continue
                seen.add(job.external_id)
                jobs.append(job)

            anterior = ids_pagina

        return jobs

    def _parse_page(self, html: str, term: str) -> list[Job]:
        soup = BeautifulSoup(html, "html.parser")
        jobs: list[Job] = []

        for card in soup.select('.wrapper-jobs-list a[href^="/jobs/"]'):
            job = self._parse_card(card, term)
            if job is not None:
                jobs.append(job)
        return jobs

    def _parse_card(self, card, term: str) -> Job | None:
        heading = card.select_one("h3")
        if heading is None:
            return None

        href = card.get("href") or ""
        match = _ID_RE.search(href)
        if match is None:
            return None

        # O selo "Vencida" fica dentro do h3; some do titulo e descarta a vaga.
        selo = heading.select_one("span.color-red")
        expirada = selo is not None and "vencida" in selo.get_text(strip=True).lower()
        if selo is not None:
            selo.extract()
        if expirada:
            return None

        title = self._text(heading)
        if not title:
            return None

        campos = self._campos(card)
        location, workplace = self._local_e_modalidade(campos.get("location", ""))
        tecnologias = [self._text(t) for t in card.select(".tag-list")]

        return Job(
            source=self.name,
            external_id=match.group(1),
            title=title,
            company=campos.get("company", ""),
            url=f"{BASE_URL}{href}",
            description=self._descricao(campos, tecnologias),
            location=location,
            workplace_type=workplace,
            published_date="",  # o card da listagem nao informa a data
            search_term=term,
            # O portal declara o nivel; e mais confiavel que adivinhar pelo
            # titulo ("Programador(a) PHP" nao tem marca de senioridade).
            seniority=self._senioridade(campos),
        )

    def _campos(self, card) -> dict[str, str]:
        """Le os metadados do card usando o icone de cada span como chave."""
        campos: dict[str, str] = {}
        for span in card.select(".cell-list-content-icon span"):
            icone = span.find("i")
            classes = icone.get("class", []) if icone else []
            for classe in classes:
                nome = CAMPOS_POR_ICONE.get(classe)
                if nome:
                    campos[nome] = self._text(span)
                    break
        return campos

    @staticmethod
    def _local_e_modalidade(bruto: str) -> tuple[str, str]:
        """'São Paulo  (Híbrido)' -> ('São Paulo', 'Híbrido'); 'Remoto' -> ('', 'Remoto')."""
        texto = _WS_RE.sub(" ", bruto).strip()
        if not texto:
            return "", ""

        match = _MODALIDADE_RE.search(texto)
        if match:
            modalidade = normalize_workplace(match.group(1))
            local = texto[: match.start()].strip()
            return local, modalidade

        if normalize_workplace(texto) == REMOTO:
            return "", REMOTO
        return texto, ""

    @staticmethod
    def _senioridade(campos: dict[str, str]) -> str:
        """Nivel declarado pelo portal.

        Contrato de estagio vence a senioridade: o portal marca estagio como
        `expertise=Júnior` com `contract_type=Estágio`.
        """
        if campos.get("contract", "").strip().lower().startswith("est"):
            return "Estágio"
        expertise = campos.get("expertise", "").strip()
        return expertise or ""

    @staticmethod
    def _descricao(campos: dict[str, str], tecnologias: list[str]) -> str:
        """Monta um texto com o que o card oferece.

        O card nao traz a descricao da vaga, mas traz as tecnologias declaradas
        -- que sao justamente o sinal que o classificador e o extrator de
        skills consomem.
        """
        partes: list[str] = []
        if tecnologias:
            partes.append("Tecnologias: " + ", ".join(tecnologias) + ".")
        if campos.get("contract"):
            partes.append(f"Contrato: {campos['contract']}.")
        if campos.get("company_type"):
            partes.append(f"Empresa: {campos['company_type']}.")
        if campos.get("salary"):
            partes.append(f"Faixa salarial: {campos['salary']}.")
        return " ".join(partes)

    @staticmethod
    def _text(node) -> str:
        if node is None:
            return ""
        return _WS_RE.sub(" ", node.get_text(" ", strip=True)).strip()
