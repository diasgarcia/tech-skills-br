"""Enriquecedor de descricoes para Vagas.com e Trampos.

A listagem dessas fontes nao traz a descricao completa da vaga. Este
script busca o detalhe de cada vaga PENDENTE, atualiza a descricao no
banco e re-extrai as tecnologias com o skills.yml atual.

- Vagas.com: GET na propria URL da vaga (pagina server-rendered, sem
  login) e parse de `div.job-description__text`.
- Trampos: GET em https://trampos.co/api/v2/opportunities/{slug}, onde o
  slug e o ultimo segmento da URL da vaga; junta description,
  prerequisite, desirable e other_info.
- ProgramaThor: reusa a cadeia do proprio coletor (Playwright -> curl_cffi
  -> PoliteSession) na pagina de detalhe da vaga e parse de
  `div.wrapper-content-job-show`. A descricao do card e sintetica
  (comeca com "Tecnologias:"), e e isso que marca a vaga como pendente.

Vagas publicadas ha mais de 30 dias nao sao tentadas (anuncio quase
certamente expirado). PoliteSession com delay/retry; o lock serializa os
GETs para o delay valer de verdade.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

from bs4 import BeautifulSoup
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.config import RULES_DIR, USER_AGENT, Settings  # noqa: E402
from scraper.http_client import PoliteSession  # noqa: E402
from scraper.skills import SkillExtractor  # noqa: E402
from scraper.sources.programathor import ProgramathorSource  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
logger = logging.getLogger("enrich_outras")

JANELA_TENTATIVA_DIAS = 30

TRAMPOS_API_URL = "https://trampos.co/api/v2/opportunities/{slug}"

# Descricao do card/API e um trecho curto; abaixo disso, vale buscar o detalhe.
MIN_DESCRICAO_VAGAS_COM = 300
MIN_DESCRICAO_TRAMPOS = 100


def fetch_vagas_com(session: PoliteSession, lock: Lock, url: str) -> str:
    with lock:
        response = session.get(url)
    if response is None:
        return ""
    soup = BeautifulSoup(response.text, "html.parser")
    el = soup.select_one("div.job-description__text, div.texto")
    return el.get_text(" ", strip=True) if el else ""


def fetch_trampos(session: PoliteSession, lock: Lock, slug: str) -> str:
    with lock:
        response = session.get(TRAMPOS_API_URL.format(slug=slug))
    if response is None:
        return ""
    try:
        opp = response.json().get("opportunity") or {}
    except ValueError:
        return ""
    partes: list[str] = []
    for campo in ("description", "prerequisite", "desirable", "other_info"):
        valor = opp.get(campo)
        if isinstance(valor, str) and valor.strip():
            partes.append(valor.strip())
        elif isinstance(valor, list):
            texto = " ".join(str(v) for v in valor if v).strip()
            if texto:
                partes.append(texto)
    return " ".join(partes)


def fetch_programathor(source: ProgramathorSource, lock: Lock, url: str) -> str:
    with lock:
        html = source._get_page_html(url, {})
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    el = soup.select_one("div.wrapper-content-job-show, div[class*=content]")
    return el.get_text(" ", strip=True) if el else ""


def _enriquecer(
    c: sqlite3.Cursor,
    session: PoliteSession,
    lock: Lock,
    extractor: SkillExtractor,
    tech_map: dict[str, int],
    query: str,
    args: list,
    fetch,
) -> int:
    c.execute(query, args)
    rows = c.fetchall()
    total = 0

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(fetch, session, lock, alvo): (vid, title)
            for vid, alvo, title in rows
        }
        for future in as_completed(futures):
            vid, title = futures[future]
            try:
                desc = future.result()
                if not desc:
                    continue
                c.execute("UPDATE vagas SET description = ? WHERE id = ?", (desc, vid))
                for s in extractor.extract(title, desc):
                    tid = tech_map.get(s.lower())
                    if tid:
                        c.execute(
                            "INSERT OR IGNORE INTO vaga_tecnologia (vaga_id, tecnologia_id) VALUES (?, ?)",
                            (vid, tid),
                        )
                total += 1
            except Exception as exc:
                logger.warning("Falha ao processar vaga %s: %s", vid, exc)
    return total


def enriquecer(limit: int | None = None) -> None:
    with open(RULES_DIR / "skills.yml", encoding="utf-8") as fh:
        rules = yaml.safe_load(fh) or {}
    extractor = SkillExtractor(rules)

    conn = sqlite3.connect(PROJECT_ROOT / "data" / "vagas.db")
    c = conn.cursor()
    c.execute("SELECT id, nome FROM tecnologias")
    tech_map = {nome.lower(): tid for tid, nome in c.fetchall()}

    janela = [f"-{JANELA_TENTATIVA_DIAS} days"]
    lock = Lock()

    query_vagas = """
        SELECT id, url, title FROM vagas
        WHERE source = 'vagas'
          AND (description IS NULL OR LENGTH(description) < ?)
          AND (published_date IS NULL OR published_date >= date('now', ?))
    """
    args_vagas = [MIN_DESCRICAO_VAGAS_COM, *janela]

    query_trampos = """
        SELECT id, url, title FROM vagas
        WHERE source = 'trampos'
          AND (description IS NULL OR LENGTH(description) < ?)
          AND (published_date IS NULL OR published_date >= date('now', ?))
    """
    args_trampos = [MIN_DESCRICAO_TRAMPOS, *janela]

    # A descricao sintetica do card comeca com "Tecnologias:"; a completa,
    # vinda da pagina de detalhe, nao.
    query_programathor = """
        SELECT id, url, title FROM vagas
        WHERE source = 'programathor'
          AND (description IS NULL OR description LIKE 'Tecnologias:%')
          AND (published_date IS NULL OR published_date >= date('now', ?))
    """
    args_programathor = list(janela)

    if limit:
        query_vagas += " LIMIT ?"
        args_vagas.append(limit)
        query_trampos += " LIMIT ?"
        args_trampos.append(limit)
        query_programathor += " LIMIT ?"
        args_programathor.append(limit)

    with PoliteSession(
        user_agent=USER_AGENT,
        delay_seconds=1.0,
        timeout_seconds=12,
        max_retries=2,
        backoff_factor=1.5,
    ) as session:
        c.execute(query_vagas, args_vagas)
        logger.info("Vagas.com pendentes: %d", len(c.fetchall()))
        total_vagas = _enriquecer(
            c, session, lock, extractor, tech_map, query_vagas, args_vagas,
            lambda sess, lk, url: fetch_vagas_com(sess, lk, url),
        )

        c.execute(query_trampos, args_trampos)
        logger.info("Trampos pendentes: %d", len(c.fetchall()))
        total_trampos = _enriquecer(
            c, session, lock, extractor, tech_map, query_trampos, args_trampos,
            lambda sess, lk, url: fetch_trampos(
                sess, lk, url.rstrip("/").split("/")[-1]
            ),
        )

        # O ProgramaThor reusa a cadeia Playwright/curl_cffi do coletor.
        fonte = ProgramathorSource(session=session, settings=Settings())
        c.execute(query_programathor, args_programathor)
        logger.info("ProgramaThor pendentes: %d", len(c.fetchall()))
        total_programathor = _enriquecer(
            c, session, lock, extractor, tech_map,
            query_programathor, args_programathor,
            lambda sess, lk, url: fetch_programathor(fonte, lk, url),
        )

    conn.commit()
    conn.close()
    logger.info(
        "Enriquecimento concluido: %d vagas.com, %d trampos e %d programathor.",
        total_vagas, total_trampos, total_programathor,
    )


if __name__ == "__main__":
    enriquecer()
