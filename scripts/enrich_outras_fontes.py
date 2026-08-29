"""Enriquecedor de descricoes para Vagas.com e Trampos.

A listagem dessas fontes nao traz a descricao completa da vaga. Este
script busca o detalhe de cada vaga PENDENTE, atualiza a descricao no
banco e re-extrai as tecnologias com o skills.yml atual.

- Vagas.com: GET na propria URL da vaga (pagina server-rendered, sem
  login) e parse de `div.job-description__text`.
- Trampos: GET em https://trampos.co/api/v2/opportunities/{slug}, onde o
  slug e o ultimo segmento da URL da vaga; junta description,
  prerequisite, desirable e other_info.
- Gupy: apenas as descricoes TRUNCADAS (exatamente 500 caracteres, legado
  do corte antigo do CSV). GET no endpoint publico de detalhe
  employability-portal.gupy.io/api/v1/jobs/{id}; vagas ja removidas
  respondem 404 e ficam como estao.
- GeekHunter: o card da listagem so traz snippet; o detalhe (SSR, sem
  auth) tem um bloco JSON-LD JobPosting com description completa,
  hiringOrganization (nome real da empresa) e datePosted. Alem da
  descricao, corrige o `company` (o coletor so tinha o slug da URL).

Vagas publicadas ha mais de 30 dias nao sao tentadas (anuncio quase
certamente expirado). PoliteSession com delay/retry; o lock serializa os
GETs para o delay valer de verdade.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

from bs4 import BeautifulSoup
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.config import RULES_DIR, USER_AGENT  # noqa: E402
from scraper.http_client import PoliteSession  # noqa: E402
from scraper.models import strip_html  # noqa: E402
from scraper.skills import SkillExtractor  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
logger = logging.getLogger("enrich_outras")

JANELA_TENTATIVA_DIAS = 30

TRAMPOS_API_URL = "https://trampos.co/api/v2/opportunities/{slug}"

GUPY_API_URL = "https://employability-portal.gupy.io/api/v1/jobs/{job_id}"

MIN_DESCRICAO_VAGAS_COM = 300
MIN_DESCRICAO_TRAMPOS = 100


def fetch_vagas_com(session: PoliteSession, lock: Lock, url: str) -> tuple[str, int | None]:
    with lock:
        response = session.get(url)
        status = session.last_status_code
    if response is None:
        return "", status
    soup = BeautifulSoup(response.text, "html.parser")
    el = soup.select_one("div.job-description__text, div.texto")
    return (el.get_text(" ", strip=True) if el else ""), status


def fetch_trampos(session: PoliteSession, lock: Lock, slug: str) -> tuple[str, int | None]:
    with lock:
        response = session.get(TRAMPOS_API_URL.format(slug=slug))
        status = session.last_status_code
    if response is None:
        return "", status
    try:
        opp = response.json().get("opportunity") or {}
    except ValueError:
        return "", status
    partes: list[str] = []
    for campo in ("description", "prerequisite", "desirable", "other_info"):
        valor = opp.get(campo)
        if isinstance(valor, str) and valor.strip():
            partes.append(valor.strip())
        elif isinstance(valor, list):
            texto = " ".join(str(v) for v in valor if v).strip()
            if texto:
                partes.append(texto)
    return " ".join(partes), status


def fetch_gupy(session: PoliteSession, lock: Lock, job_id: str) -> tuple[str, int | None]:
    with lock:
        response = session.get(GUPY_API_URL.format(job_id=job_id))
        status = session.last_status_code
    if response is None:
        return "", status
    try:
        desc = (response.json() or {}).get("description") or ""
    except ValueError:
        return "", status
    return strip_html(desc), status


def fetch_geekhunter(session: PoliteSession, lock: Lock, url: str) -> tuple[dict, int | None]:
    """Busca o detalhe da vaga e extrai do JSON-LD JobPosting.

    O card da listagem so tem snippet; o detalhe (SSR, sem auth) traz um
    bloco application/ld+json com description completa, hiringOrganization
    (nome real da empresa) e datePosted (data ISO real).
    """
    with lock:
        response = session.get(url)
        status = session.last_status_code
    if response is None:
        return {}, status
    soup = BeautifulSoup(response.text, "html.parser")
    dados: dict[str, str] = {}
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (ValueError, TypeError):
            continue
        if data.get("@type") != "JobPosting":
            continue
        descricao = strip_html(data.get("description") or "")
        # O JSON-LD tambem declara a lista curada de skills do portal
        # ("Angular 8+, AWS, Spring Boot..."); anexa ao texto para o
        # extrator nao perder nenhuma tecnologia.
        skills = (data.get("skills") or "").strip()
        if skills:
            descricao = f"{descricao} Skills: {skills}."
        dados["description"] = descricao
        org = data.get("hiringOrganization") or {}
        dados["company"] = (org.get("name") or "").strip()
        dados["published_date"] = (data.get("datePosted") or "")[:10]
        break
    return dados, status


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
                resultado, status = future.result()
                if isinstance(resultado, str):
                    # Fontes antigas devolvem (descricao, status).
                    resultado = {"description": resultado}
                desc = resultado.get("description", "")
                if not desc:
                    # 404 = anuncio encerrado na fonte: nunca mais buscar.
                    if status == 404:
                        c.execute(
                            "UPDATE vagas SET enrich_encerrada = 1 WHERE id = ?",
                            (vid,),
                        )
                    continue
                c.execute("UPDATE vagas SET description = ? WHERE id = ?", (desc, vid))
                company = resultado.get("company", "")
                if company:
                    c.execute(
                        "UPDATE vagas SET company = ? WHERE id = ?", (company, vid)
                    )
                pub = resultado.get("published_date", "")
                if pub:
                    c.execute(
                        "UPDATE vagas SET published_date = ? WHERE id = ?",
                        (pub, vid),
                    )
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


def enriquecer(limit: int | None = None, janela_dias: int = JANELA_TENTATIVA_DIAS) -> None:
    with open(RULES_DIR / "skills.yml", encoding="utf-8") as fh:
        rules = yaml.safe_load(fh) or {}
    extractor = SkillExtractor(rules)

    conn = sqlite3.connect(PROJECT_ROOT / "data" / "vagas.db")
    c = conn.cursor()
    c.execute("SELECT id, nome FROM tecnologias")
    tech_map = {nome.lower(): tid for tid, nome in c.fetchall()}

    janela = [f"-{janela_dias} days"]
    lock = Lock()

    query_vagas = """
        SELECT id, url, title FROM vagas
        WHERE source = 'vagas'
          AND COALESCE(enrich_encerrada, 0) = 0
          AND (description IS NULL OR LENGTH(description) < ?)
          AND (published_date IS NULL OR published_date >= date('now', ?))
    """
    args_vagas = [MIN_DESCRICAO_VAGAS_COM, *janela]

    query_trampos = """
        SELECT id, url, title FROM vagas
        WHERE source = 'trampos'
          AND COALESCE(enrich_encerrada, 0) = 0
          AND (description IS NULL OR LENGTH(description) < ?)
          AND (published_date IS NULL OR published_date >= date('now', ?))
    """
    args_trampos = [MIN_DESCRICAO_TRAMPOS, *janela]

    # Gupy: so as truncadas legadas (exatamente 500 caracteres). As vagas
    # atuais ja chegam com a descricao completa na listagem.
    query_gupy = """
        SELECT id, external_id, title FROM vagas
        WHERE source = 'gupy'
          AND COALESCE(enrich_encerrada, 0) = 0
          AND LENGTH(description) = 500
          AND (published_date IS NULL OR published_date >= date('now', ?))
    """
    args_gupy = list(janela)

    # GeekHunter: o card so traz um snippet; o detalhe tem a descricao
    # completa (Tarefas, Requisitos, Beneficios), o nome real da empresa
    # (o coletor grava o slug da URL) e a data de publicacao. Marca
    # pendente descricao curta, company ainda em formato de slug ou
    # published_date vazia.
    query_geekhunter = """
        SELECT id, url, title FROM vagas
        WHERE source = 'geekhunter'
          AND COALESCE(enrich_encerrada, 0) = 0
          AND (
              description IS NULL OR LENGTH(description) < 300
              OR company LIKE '%-%'
              OR published_date IS NULL
          )
    """
    args_geekhunter: list = []

    if limit:
        query_vagas += " LIMIT ?"
        args_vagas.append(limit)
        query_trampos += " LIMIT ?"
        args_trampos.append(limit)
        query_gupy += " LIMIT ?"
        args_gupy.append(limit)
        query_geekhunter += " LIMIT ?"
        args_geekhunter.append(limit)

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

        c.execute(query_gupy, args_gupy)
        logger.info("Gupy truncadas pendentes: %d", len(c.fetchall()))
        total_gupy = _enriquecer(
            c, session, lock, extractor, tech_map, query_gupy, args_gupy,
            lambda sess, lk, job_id: fetch_gupy(sess, lk, job_id),
        )

        c.execute(query_geekhunter, args_geekhunter)
        logger.info("GeekHunter pendentes: %d", len(c.fetchall()))
        total_geekhunter = _enriquecer(
            c, session, lock, extractor, tech_map,
            query_geekhunter, args_geekhunter,
            lambda sess, lk, url: fetch_geekhunter(sess, lk, url),
        )

    conn.commit()
    conn.close()
    logger.info(
        "Enriquecimento concluido: %d vagas.com, %d trampos, %d gupy e %d geekhunter.",
        total_vagas, total_trampos, total_gupy, total_geekhunter,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Enriquece descricoes de Vagas.com, Trampos, Gupy e GeekHunter."
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--janela", type=int, default=JANELA_TENTATIVA_DIAS,
                        help="Dias de janela de publicacao (padrao: 30).")
    args = parser.parse_args()
    enriquecer(limit=args.limit, janela_dias=args.janela)
