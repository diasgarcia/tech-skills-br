"""Coletor do Recrutei Empregos (empregos.recrutei.com.br).

Tudo renderizado no servidor, sem autenticacao:

- O detalhe da vaga (/vaga/{empresa}/{id}-{slug}) traz um bloco
  JSON-LD JobPosting completo: titulo, descricao integral (requisitos,
  atividades e beneficios), datePosted (ISO, data real), validThrough,
  employmentType, hiringOrganization (empresa) e jobLocation
  (cidade/UF). A descricao ja vem completa: a fonte NAO entra na fila
  de enriquecimento.
- A descoberta usa duas vias publicas:
  - Diario (padrao): sitemap-vagas-1.xml com <lastmod> -- pega so as
    vagas mudadas na janela de dias (recrutei_days_back, padrao 24h).
  - Coleta completa (--recrutei-full): paginacao SSR de /vagas?page=N
    (12 por pagina, rel=next). O sitemap cobre so as ~1.000 vagas mais
    recentes; a listagem expoe todas as ativas (~3,7k).
- Checkpoint incremental em output/recrutei_partial.csv: cada vaga
  gravada na hora; rodada interrompida retoma sem refazer GET e a
  rodada completa remove o arquivo.

Detalhes descobertos testando ao vivo:

- Sem rate limit (12 requests em rajada, tudo 200) e sem bot-check:
  requests puro funciona.
- robots.txt tem Disallow em /api/ (a API e off-limits), mas sitemap e
  paginas SSR sao publicas de proposito para indexadores: consumir
  essas vias nao e contorno de bloqueio.
- Categorias tech da listagem: tecnologia (609 vagas), dados (297) e
  ti (163); o total ativo e ~3.701.
"""

from __future__ import annotations

import csv
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

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

PORTAL_URL = "https://empregos.recrutei.com.br"
SITEMAP_URL = f"{PORTAL_URL}/sitemap-vagas-1.xml"
LISTAGEM_URL = f"{PORTAL_URL}/vagas"

CHECKPOINT_NAME = "recrutei_partial.csv"

_VAGA_URL_RE = re.compile(r'<loc>([^<]+/vaga/[^<]+)</loc>')
_LASTMOD_RE = re.compile(r"<lastmod>([^<]+)</lastmod>")
# A listagem nao usa ancoras para os cards: as URLs das vagas vem num
# bloco JSON-LD ItemList (e, em menor escala, em hrefs absolutos).
_CARD_ABS_RE = re.compile(r'https://empregos\.recrutei\.com\.br/vaga/[^"\']+')
_CARD_REL_RE = re.compile(r'href="(/vaga/[a-z0-9-]+/[^"]+)"')


def _vid_da_url(url: str) -> str:
    """Id estavel da vaga a partir da URL (/vaga/{empresa}/{id}[-slug]).

    O portal usa dois formatos: numerico (156991-motorista...) e UUID
    (7b2d9a38-9099-...). No numerico, o prefixo antes do primeiro hifen
    e o id; no UUID, o segmento inteiro e o id.
    """
    seg = url.rstrip("/").rsplit("/", 1)[-1]
    if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f-]{20,36}", seg):
        return seg
    return seg.split("-", 1)[0]


class RecruteiSource(JobSource):
    name = "recrutei"
    label = "Recrutei"
    MAX_PAGES_PER_TERM = 1  # sem paginacao por termo; a descoberta e propria

    def fetch(self, terms: list[str]) -> list[Job]:
        """Ignora os termos do projeto: o recorte vem do sitemap/listing."""
        if terms:
            logger.debug("[%s] termos ignorados; descoberta via sitemap/listing", self.name)
        if getattr(self.settings, "recrutei_full", False):
            return self._coletar_completa()
        return self._coletar_sitemap()

    def fetch_term(self, term: str) -> list[Job]:
        del term
        return []

    def _checkpoint_path(self) -> Path:
        return Path(self.settings.output_dir) / CHECKPOINT_NAME

    def _ler_checkpoint(self) -> set[str]:
        path = self._checkpoint_path()
        if not path.is_file():
            return set()
        ids: set[str] = set()
        with open(path, encoding="utf-8-sig", newline="") as fh:
            for linha in csv.DictReader(fh):
                vid = (linha.get("external_id") or "").strip()
                if vid:
                    ids.add(vid)
        return ids

    def _coletar_sitemap(self) -> list[Job]:
        response = self.session.get(SITEMAP_URL)
        if response is None or not response.text.strip():
            logger.warning("[%s] sitemap inacessivel; abortando a coleta", self.name)
            return []

        dias = max(1, int(getattr(self.settings, "recrutei_days_back", 1) or 1))
        recencia = datetime.now(timezone.utc) - timedelta(days=dias)
        corte = datetime(2026, 1, 1, tzinfo=timezone.utc)
        limite = max(recencia, corte)

        alvos: list[str] = []
        for m in _VAGA_URL_RE.finditer(response.text):
            lm = _LASTMOD_RE.search(response.text, m.end())
            if lm is None:
                continue
            try:
                data = datetime.fromisoformat(lm.group(1).replace("Z", "+00:00"))
            except ValueError:
                continue
            if data < limite:
                continue
            alvos.append(m.group(1))

        logger.info("[%s] sitemap: %d vagas dentro da janela", self.name, len(alvos))
        return self._coletar_detalhes(alvos)

    def _coletar_completa(self) -> list[Job]:
        alvos: list[str] = []
        seen_urls: set[str] = set()
        page = 1
        while True:
            response = self.session.get(LISTAGEM_URL, params={"page": page})
            if response is None or not response.text.strip():
                break
            novos = 0
            for url in _CARD_ABS_RE.findall(response.text):
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                alvos.append(url)
                novos += 1
            for href in _CARD_REL_RE.findall(response.text):
                url = f"{PORTAL_URL}{href}"
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                alvos.append(url)
                novos += 1
            if novos == 0:
                break
            if page % 20 == 0:
                logger.info("[%s] listing: %d paginas, %d vagas", self.name, page, len(alvos))
            page += 1
            if page > 600:
                break

        logger.info("[%s] listing completa: %d vagas", self.name, len(alvos))
        return self._coletar_detalhes(alvos)

    def _coletar_detalhes(self, alvos: list[str]) -> list[Job]:
        checkpoint = self._checkpoint_path()
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        seen = self._ler_checkpoint()
        if seen:
            logger.info("[%s] retomando checkpoint com %d vagas ja coletadas",
                        self.name, len(seen))
        novo_checkpoint = not checkpoint.is_file()

        jobs: list[Job] = []
        completou = False
        try:
            with open(checkpoint, "a", encoding="utf-8-sig", newline="") as fh:
                writer = None
                for url in alvos:
                    if _vid_da_url(url) in seen:
                        continue  # ja esta no checkpoint: nao refaz o GET
                    page = self.session.get(url)
                    if page is None:
                        continue
                    if not page.text.strip():
                        logger.warning(
                            "[%s] body vazio em %s; parando a coleta "
                            "(o checkpoint fica para retomar)", self.name, url,
                        )
                        break
                    job = self._parse_page(page.text, url)
                    if job is None or job.external_id in seen:
                        continue
                    seen.add(job.external_id)
                    jobs.append(job)
                    if writer is None:
                        writer = csv.DictWriter(fh, fieldnames=list(job.to_row()))
                        if novo_checkpoint:
                            writer.writeheader()
                    writer.writerow(job.to_row())
                    fh.flush()
                    if len(jobs) % 25 == 0:
                        logger.info("[%s] progresso: %d vagas novas",
                                    self.name, len(jobs))
                else:
                    completou = True
        finally:
            if completou:
                checkpoint.unlink(missing_ok=True)
                logger.info("[%s] coleta completa; checkpoint removido", self.name)

        self.stats.raw_jobs = len(jobs)
        self.stats.requests_made = self.session.request_count
        return jobs

    def _parse_page(self, html: str, url: str) -> Job | None:
        for m in re.finditer(
            r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S
        ):
            try:
                data = json.loads(m.group(1))
            except ValueError:
                continue
            if data.get("@type") != "JobPosting":
                continue

            title = (data.get("title") or "").strip()
            if not title:
                return None

            published = (data.get("datePosted") or "")[:10]
            if published and published < "2026-01-01":
                return None

            org = data.get("hiringOrganization") or {}
            local = data.get("jobLocation") or {}
            endereco = local.get("address") or {}
            cidade = endereco.get("addressLocality") or ""
            uf = endereco.get("addressRegion") or ""
            location = ", ".join(p for p in (cidade, uf) if p)

            # A modalidade/lugar fica no bloco do header da pagina, e nao no
            # JSON-LD (que costuma vir sem address para vagas remotas).
            workplace = self._modalidade_do_header(
                html, title, data.get("description") or ""
            )
            if not location:
                location = self._local_do_header(html)

            vid = _vid_da_url(url)
            if not vid:
                return None

            return Job(
                source=self.name,
                external_id=vid,
                title=title,
                company=(org.get("name") or "").strip(),
                url=url,
                description=data.get("description") or "",
                location=location,
                workplace_type=workplace,
                published_date=published,
                search_term="sitemap" if "sitemap" in url else "listing",
            )
        return None

    @staticmethod
    def _texto_do_header(html: str) -> str:
        """Texto do bloco do header da vaga (<h6 ... text-center pb-2> com o
        icone de mapa), onde o portal coloca "Remoto"/"Hibrido"/"Presencial"
        ou a cidade. Devolve "" quando o bloco nao existe."""
        m = re.search(
            r'<h6[^>]*class="[^"]*text-muted text-center pb-2[^"]*"[^>]*>(.*?)</h6>',
            html,
            re.S,
        )
        if not m:
            return ""
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1))).strip()

    @classmethod
    def _modalidade_do_header(cls, html: str, titulo: str = "", descricao: str = "") -> str:
        texto = cls._texto_do_header(html)
        if not texto:
            return NAO_INFORMADO
        alvo = normalize(texto)
        if "remot" in alvo or "home office" in alvo:
            return REMOTO
        if "hibrid" in alvo:
            return HIBRIDO
        if "presencial" in alvo:
            return PRESENCIAL
        if "informado" in alvo:
            return NAO_INFORMADO
        # O header mostra so a cidade; a modalidade (quando nao e presencial)
        # aparece no titulo ou numa frase explicita da descricao. Mencoes
        # soltas de "home office"/"remoto" na descricao sao armadilha:
        # "Auxilio Home Office" e beneficio e "suporte remoto a clientes"
        # e atividade, nao modalidade de trabalho.
        pistas_titulo = normalize(titulo)
        if "hibrid" in pistas_titulo:
            return HIBRIDO
        if "remot" in pistas_titulo or "home office" in pistas_titulo:
            return REMOTO
        if "presencial" in pistas_titulo:
            return PRESENCIAL
        # O JSON-LD costuma colar texto ("JuniorAtuacao Hibrida"): separar
        # maiuscula colada em minuscula antes de casar as palavras-chave.
        alvo_desc = normalize(
            re.sub(r"([a-z])([A-ZÀ-Ú])", r"\1 \2", descricao or "")
        )
        for m in re.finditer(
            r"\b(modelo|atuacao|trabalho|regime|local|forma|modalidade|jornada)\b",
            alvo_desc,
        ):
            trecho = alvo_desc[m.end(): m.end() + 60]
            if "hibrid" in trecho:
                return HIBRIDO
            if "remot" in trecho or "home office" in trecho:
                return REMOTO
            if "presencial" in trecho:
                return PRESENCIAL
        return PRESENCIAL

    @classmethod
    def _local_do_header(cls, html: str) -> str:
        texto = cls._texto_do_header(html)
        if not texto:
            return ""
        alvo = normalize(texto)
        if alvo in ("remoto", "hibrido", "presencial", "nao informado"):
            return ""
        return texto
