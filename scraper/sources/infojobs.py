"""Coletor do InfoJobs (busca publica renderizada no servidor).

A listagem de busca e renderizada no servidor (como o Vagas.com): os cards
ja vem no HTML, sem JS. Endpoint publico, sem autenticacao:

    GET https://www.infojobs.com.br/vagas-de-emprego.aspx

Parametros descobertos testando o site ao vivo:

- `Palabra=<termo>` faz busca textual (titulo + descricao), com espacos
  como `+`; o match e frouxo (nao e literal do titulo).
- Filtros nativos (funcionam sem termo): `categoria=74` (Informatica, TI,
  Telecomunicacoes), `tipocontrato` (4=Estagio, 15=Trainee, 19=Jovem
  Aprendiz), `im` (nivel: 1=Estagiario, 5=Trainee), `idw` (1=presencial,
  2=home office, 3=hibrido).
- `Page=<n>` pagina de 20 em 20; pagina alem do fim devolve 200 com a
  lista vazia (seguro para parar). Nao ha teto artificial antes do fim
  natural (categoria=74 tem ~150 paginas; medido ate a ultima).
- A ordenacao padrao e por data decrescente (pagina 1 = mais recentes).

Detalhes praticos descobertos testando ao vivo:

- O card da listagem traz um teaser de EXATOS 153 caracteres, sempre
  terminando em "...". A descricao completa esta na pagina da vaga
  (`p.text-break.white-space-pre-line` dentro de `.js_vacancyDataPanels`);
  quem busca ela e o enriquecimento (scripts/enrich_outras_fontes.py).
- O portal nao tem filtro nativo de "Junior" (o facet de senioridade so
  tem Estagiario, Operacional, Auxiliar, Assistente, Trainee...). Junior
  entra pela busca textual `Palabra=` com os termos do projeto; estagio/
  trainee/aprendiz entram pelos filtros nativos de contrato.
- Bloqueio suave por IP: rajadas de requests (medido ~12 em segundos)
  devolvem 200 com BODY VAZIO por alguns minutos, para qualquer
  User-Agent. O coletor trata body vazio como falha e para o termo (o
  retry do PoliteSession nao pega 200 vazio). Com delay >= 2s o ritmo
  nao dispara o bloqueio (medido 15 requests saudaveis).
- Vaga encerrada responde 200 com o fallback da home (sem o painel de
  dados da vaga): o enriquecimento usa isso para marcar a vaga.
"""

from __future__ import annotations

import logging
import re

import yaml
from bs4 import BeautifulSoup

from ..config import RULES_DIR
from ..models import Job, normalize_workplace
from .base import JobSource

logger = logging.getLogger(__name__)

BASE_URL = "https://www.infojobs.com.br"
SEARCH_URL = f"{BASE_URL}/vagas-de-emprego.aspx"

# As buscas textuais de junior ganham o recorte de area nativo do portal:
# sem ele, termos como "assistente de ti" devolvem ruido de outras areas.
CATEGORIA_TI = "74"

# Palavras que indicam nivel coberto pelos filtros nativos: esses termos
# nao precisam de busca textual (a deduplicacao juntaria as vagas, mas as
# requests nao voltariam).
_PALAVRAS_FILTRO_NATIVO = ("estagio", "estagiario", "trainee", "aprendiz")

_WS_RE = re.compile(r"\s+")
# Sufixo do card: "Cidade - UF , 0 Km de voce." (o portal repete o trecho
# "X Km de voce" quando a busca tem geo; o numero pode variar).
_KM_RE = re.compile(r"\s*,?\s*\d+\s*km\s+de\s+\S+\.?\s*$", re.I)


def _carregar_filtros() -> dict[str, dict[str, str]]:
    """Filtros nativos de nivel de entrada declarados em coletores.yml."""
    with open(RULES_DIR / "coletores.yml", encoding="utf-8") as fh:
        dados = yaml.safe_load(fh) or {}
    filtros = (dados.get("infojobs") or {}).get("filtros") or {}
    return {
        str(k): {str(p): str(v) for p, v in (val or {}).items()}
        for k, val in filtros.items()
    }


FILTROS_NIVEL_ENTRADA = _carregar_filtros()

PAGE_SIZE = 20  # a listagem devolve 20 cards por pagina, fixos


class InfoJobsSource(JobSource):
    name = "infojobs"
    label = "InfoJobs"
    # Categoria TI sozinha tem ~150 paginas, mas os filtros de nivel de
    # entrada e os termos junior devolvem conjuntos muito menores; 50
    # paginas (1000 vagas) e folga de sobra sem varreduras desnecessarias.
    MAX_PAGES_PER_TERM = 50

    def fetch(self, terms: list[str]) -> list[Job]:
        """Filtros nativos (estagio/trainee/aprendiz) + busca textual (junior).

        Junior nao tem filtro nativo no portal: entra pelos termos do
        projeto que nao sao de estagio/trainee/aprendiz (esses ja vem dos
        filtros nativos de contrato).
        """
        termos_junior = [
            term for term in terms
            if not any(palavra in term for palavra in _PALAVRAS_FILTRO_NATIVO)
        ]
        if not termos_junior:
            logger.debug("[%s] sem termos junior para busca textual", self.name)
        jobs = super().fetch(list(FILTROS_NIVEL_ENTRADA))
        jobs += super().fetch(termos_junior)
        self.stats.raw_jobs = len(jobs)
        self.stats.requests_made = self.session.request_count
        return jobs

    def fetch_term(self, term: str) -> list[Job]:
        """Coleta um filtro nativo (chave de FILTROS_NIVEL_ENTRADA) ou um termo textual."""
        if term in FILTROS_NIVEL_ENTRADA:
            params = dict(FILTROS_NIVEL_ENTRADA[term])
        else:
            params = {"Palabra": term, "categoria": CATEGORIA_TI}

        jobs: list[Job] = []
        seen: set[str] = set()

        start_page = max(1, self.settings.start_page)
        end_page = max(start_page, self.page_limit())

        for page in range(start_page, end_page + 1):
            response = self.session.get(SEARCH_URL, params={**params, "Page": page})
            if response is None:
                break
            if not response.text.strip():
                # 200 com body vazio = bloqueio suave do portal por alguns
                # minutos; parar o termo evita martelar o IP ja marcado.
                logger.warning(
                    "[%s] body vazio em %s (bloqueio suave?); parando o termo",
                    self.name, term,
                )
                break

            batch = self._parse_page(response.text, term)
            if not batch:
                break  # pagina alem do fim (lista vazia)

            new_in_page = 0
            for job in batch:
                if job.external_id in seen:
                    continue
                seen.add(job.external_id)
                jobs.append(job)
                new_in_page += 1

            if new_in_page == 0:
                break  # o portal repetiu a pagina anterior

        return jobs

    def _parse_page(self, html: str, term: str) -> list[Job]:
        soup = BeautifulSoup(html, "html.parser")
        # `div[id^=vacancy]` pega tambem os contêineres "vacancylistDetail*":
        # o filtro por js_cardLink/data-id garante so os cards reais.
        cards = soup.select('div.js_cardLink[id^="vacancy"][data-id]')
        jobs: list[Job] = []
        for card in cards:
            job = self._parse_card(card, term)
            if job is not None:
                jobs.append(job)
        return jobs

    def _parse_card(self, card, term: str) -> Job | None:
        job_id = (card.get("data-id") or "").strip()
        title_el = card.select_one(".js_vacancyTitle")
        title = title_el.get_text(" ", strip=True) if title_el else ""
        if not job_id or not title:
            return None

        href = card.get("data-href") or ""
        if not href:
            link = card.select_one("a.text-decoration-none[href]")
            href = link.get("href") or "" if link else ""
        url = href if href.startswith("http") else f"{BASE_URL}{href}"

        anchor = card.select_one("div.text-body a.text-body")
        if anchor is not None:
            company = anchor.get_text(" ", strip=True)
        else:
            # Empresa confidencial: o nome fica num span, sem link.
            span = card.select_one("div.text-body span.text-nowrap")
            company = span.get_text(" ", strip=True) if span else ""

        loc_el = card.select_one(".mb-8")
        if loc_el is not None:
            location = _KM_RE.sub("", loc_el.get_text(" ", strip=True)).strip()
        else:
            location = ""

        date_el = card.select_one(".js_date")
        published = ""
        if date_el is not None:
            raw_date = (date_el.get("data-value") or "").strip()
            published = raw_date[:10].replace("/", "-")
        if published and published < "2026-01-01":
            return None

        modelo = ""
        model_icon = card.select_one(".icon-house-and-building")
        if model_icon is not None:
            bloco = model_icon.find_parent("div")
            if bloco is not None:
                modelo = bloco.get_text(" ", strip=True)

        # Teaser de 153 chars ("...") ou, raramente, nada. O card com
        # "div.text-medium small" e a data relativa ("Ontem"), nao o teaser.
        snippets = [
            s for s in card.select("div.text-medium")
            if "small" not in (s.get("class") or [])
        ]
        snippet = snippets[-1].get_text(" ", strip=True) if snippets else ""

        return Job(
            source=self.name,
            external_id=job_id,
            title=title,
            company=_WS_RE.sub(" ", company).strip(),
            url=url,
            description=snippet,
            location=location,
            workplace_type=normalize_workplace(modelo),
            published_date=published,
            search_term=term,
            # So confia nos filtros nativos de contrato; os termos textuais
            # casam de forma frouxa no portal e o filtro de senioridade do
            # pipeline decide pelo titulo nesses casos.
            seniority=term if term in FILTROS_NIVEL_ENTRADA else "",
        )
