"""Coletor da Abler (portal publico de vagas, SSR em Nuxt).

A API de busca (hulk-smash.abler.com.br/api/...) e fechada para
integracao de empresas: responde 403 ORIGIN_NOT_ALLOWED mesmo com
fingerprint de navegador e cookies do portal. O caminho publico e o
sitemap de SEO:

    GET https://candidatos.abler.com.br/sitemap.xml

Indexa todas as vagas (~13.6k) com <lastmod>, e cada pagina
/vagas/{slug}-{id} e renderizada no servidor com o objeto completo da
vaga no payload window.__NUXT__: companyName, title, description (HTML
completo), address (cidade/UF), salary, createdAt/publishedAt (ISO
-03:00) e skills. A descricao ja vem completa: a fonte NAO entra na
fila de enriquecimento.

Detalhes descobertos testando ao vivo:

- Sem paginacao: o sitemap e o indice (1 request) e cada vaga e 1
  request. A coleta filtra o sitemap por keyword no slug (recorte de
  tecnologia; o restante o portao do pipeline descarta) e por janela
  de dias (padrao: 24h para a rodada diaria; --abler-days N amplia).
- O payload nao traz modalidade de trabalho: fica para o
  infer_workplace do pipeline (titulo/descricao).
- O portal publica essas paginas de proposito para indexadores
  (robots.txt com Allow: /): consumir o sitemap nao e contorno de
  bloqueio, e consumir o que a fonte expoe publicamente.
- Ritmo testado: 12 paginas com 1.5s de espaco, todas 200, sem ban do
  Cloudflare.
"""

from __future__ import annotations

import csv
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..models import Job
from .base import JobSource

logger = logging.getLogger(__name__)

PORTAL_URL = "https://candidatos.abler.com.br"
SITEMAP_URL = f"{PORTAL_URL}/sitemap.xml"

CHECKPOINT_NAME = "abler_partial.csv"

# O sitemap mistura todo tipo de vaga (advogado, vendedora, estoquista...).
# A coleta so visita slugs com cara de tecnologia/entrada; o portao de
# relevancia do pipeline descarta o resto do ruido.
_TECH_SLUG_RE = re.compile(
    r"(estagi|junior|\bjr\b|trainee|aprendiz|desenvolvedor|programador|"
    r"analista|\bdev\b|suporte|infraestrutura|dados|backend|frontend|"
    r"fullstack|\bqa\b|devops|informatica|tecnologia|sistemas|\bredes\b|"
    r"seguranca|ciberseguranca|\bti\b)",
    re.I,
)

_CAMPO_RE = re.compile(r'([a-zA-Z_]+):"((?:[^"\\]|\\.)*)"')


def _extrair_campo(payload: str, chave: str, inicio: int) -> str:
    """Extrai chave:"valor" (com escapes JSON) a partir da posicao dada."""
    m = re.search(
        rf'{re.escape(chave)}:"((?:[^"\\]|\\.)*)"', payload[inicio:]
    )
    if not m:
        return ""
    return json.loads(f'"{m.group(1)}"')


class AblerSource(JobSource):
    name = "abler"
    label = "Abler"
    MAX_PAGES_PER_TERM = 1  # sem paginacao; o indice e o sitemap

    def fetch(self, terms: list[str]) -> list[Job]:
        """Ignora os termos do projeto: o recorte vem do filtro do sitemap."""
        if terms:
            logger.debug(
                "[%s] termos ignorados; usando o sitemap com filtro de slug",
                self.name,
            )
        return self._coletar()

    def fetch_term(self, term: str) -> list[Job]:
        """Sem busca por termo: o indice e o sitemap, nao o termo."""
        del term
        return []

    def _checkpoint_path(self) -> Path:
        return Path(self.settings.output_dir) / CHECKPOINT_NAME

    def _ler_checkpoint(self) -> set[str]:
        """Ids ja coletados em rodada anterior interrompida."""
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

    def _coletar(self) -> list[Job]:
        response = self.session.get(SITEMAP_URL)
        if response is None or not response.text.strip():
            logger.warning("[%s] sitemap inacessivel; abortando a coleta", self.name)
            return []

        alvos = self._filtrar_sitemap(response.text)
        if self.settings.parallel_sources:
            logger.debug("[%s] sitemap: %d paginas dentro da janela", self.name, len(alvos))
        else:
            logger.info("[%s] sitemap: %d paginas dentro da janela", self.name, len(alvos))

        checkpoint = self._checkpoint_path()
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        seen = self._ler_checkpoint()
        if seen and not self.settings.parallel_sources:
            logger.info("[%s] retomando checkpoint com %d vagas ja coletadas",
                        self.name, len(seen))
        novo_checkpoint = not checkpoint.is_file()

        jobs: list[Job] = []
        completou = False
        try:
            with open(checkpoint, "a", encoding="utf-8-sig", newline="") as fh:
                writer = None
                for idx, url in enumerate(alvos, 1):
                    vid_url = url.rstrip("/").rsplit("-", 1)[-1]
                    if vid_url.isdigit() and vid_url in seen:
                        continue  # ja esta no checkpoint: nao refaz o GET
                    page = self.session.get(url)
                    if page is None:
                        continue
                    if not page.text.strip():
                        # Bloqueio suave: para e mantem o checkpoint.
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
                        if self.settings.parallel_sources:
                            logger.debug("[%s] progresso: %d vagas novas",
                                         self.name, len(jobs))
                        else:
                            logger.info("[%s] progresso: %d vagas novas",
                                        self.name, len(jobs))
                        self.report(
                            len(jobs),
                            current_term=f"{len(jobs)} vagas novas",
                            progresso=idx / len(alvos),
                        )
                else:
                    completou = True
        finally:
            if completou:
                checkpoint.unlink(missing_ok=True)
                logger.info("[%s] coleta completa; checkpoint removido", self.name) if not self.settings.parallel_sources else logger.debug(
                    "[%s] coleta completa; checkpoint removido", self.name
                )

        self.stats.raw_jobs = len(jobs)
        self.stats.requests_made = self.session.request_count
        return jobs

    def _filtrar_sitemap(self, xml: str) -> list[str]:
        """URLs de vaga tech dentro da janela configurada.

        O corte de 2026 (data minima do projeto) vale SEMPRE: o sitemap
        guarda historico desde 2018 e nao ha por que visitar pagina
        anterior ao escopo. A recencia em dias vale por cima (rodada
        diaria: 24h; coleta completa: valor grande via --abler-days).
        """
        dias = max(1, int(getattr(self.settings, "abler_days_back", 1) or 1))
        recencia = datetime.now(timezone.utc) - timedelta(days=dias)
        corte = datetime(2026, 1, 1, tzinfo=timezone.utc)
        limite = max(recencia, corte)

        alvos: list[str] = []
        for loc, lastmod in re.findall(
            r"<loc>([^<]+)</loc>\s*<lastmod>([^<]+)</lastmod>", xml
        ):
            if "/vagas/" not in loc or not _TECH_SLUG_RE.search(loc):
                continue
            try:
                data = datetime.fromisoformat(lastmod.replace("Z", "+00:00"))
            except ValueError:
                continue
            if data < limite:
                continue
            alvos.append(loc)
        return alvos

    def _parse_page(self, html: str, url: str) -> Job | None:
        m = re.search(r"window\.__NUXT__=.*?vacancy:\{vacancy:\{", html, re.S)
        if m is None:
            return None
        inicio = m.end() - len("vacancy:{vacancy:{")

        # O id vem do proprio slug da URL (/vagas/{slug}-{id}): no payload
        # ha outros campos com "id:" (areas de interesse, empresa) antes
        # do id da vaga, entao o suffixo da URL e mais confiavel.
        vid = url.rstrip("/").rsplit("-", 1)[-1]
        if not vid.isdigit():
            return None

        title = _extrair_campo(html, "title", inicio)
        if not title:
            return None

        published = _extrair_campo(html, "publishedAt", inicio)
        if not published:
            published = _extrair_campo(html, "createdAt", inicio)
        published = (published or "")[:10]
        if published and published < "2026-01-01":
            return None

        company = _extrair_campo(html, "companyName", inicio)
        description = _extrair_campo(html, "description", inicio)

        cidade = _extrair_campo(html, "cityName", inicio)
        estado = _extrair_campo(html, "stateAbbr", inicio) or _extrair_campo(
            html, "stateName", inicio
        )
        local = ", ".join(p for p in (cidade, estado) if p)

        return Job(
            source=self.name,
            external_id=vid,
            title=title,
            company=company,
            url=url,
            description=description,
            location=local,
            workplace_type="",
            published_date=published,
            search_term="sitemap",
        )
