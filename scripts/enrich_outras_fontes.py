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
- InfoJobs: o card traz um teaser fixo de 153 caracteres (sempre com
  "..."); o detalhe (SSR, sem auth) tem a descricao completa em
  `p.text-break.white-space-pre-line` dentro de `.js_vacancyDataPanels`.
  Vaga encerrada responde 200 com o fallback da home (sem o painel):
  nesse caso o status e tratado como 404 para marcar a vaga.

Vagas publicadas ha mais de 30 dias nao sao tentadas (anuncio quase
certamente expirado). PoliteSession com delay/retry; o lock serializa os
GETs para o delay valer de verdade.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
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
from scripts.import_csv import MIN_DATA_CORTE  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
logger = logging.getLogger("enrich_outras")

JANELA_TENTATIVA_DIAS = 30

TRAMPOS_API_URL = "https://trampos.co/api/v2/opportunities/{slug}"

GUPY_API_URL = "https://employability-portal.gupy.io/api/v1/jobs/{job_id}"

# O card do Vagas.com traz um snippet do portal (ate ~400 chars, as vezes
# terminando com "..."), longe da descricao completa (1825+ chars quando
# enriquecida). O corte precisa cobrir esses snippets: abaixo de 500 ou
# terminando com "...". Sem janela de dias: pendente e tentada em toda
# rodada ate dar certo ou 404 (encerrada), como no LinkedIn.
MIN_DESCRICAO_VAGAS_COM = 500
MIN_DESCRICAO_TRAMPOS = 100

QUERY_VAGAS_PENDENTES = """
    SELECT id, url, title FROM vagas
    WHERE source = 'vagas'
      AND COALESCE(enrich_encerrada, 0) = 0
      AND (description IS NULL OR LENGTH(description) < ?
           OR description LIKE '%...')
"""

QUERY_TRAMPOS_PENDENTES = """
    SELECT id, url, title FROM vagas
    WHERE source = 'trampos'
      AND COALESCE(enrich_encerrada, 0) = 0
      AND (description IS NULL OR LENGTH(description) < ?)
      AND (published_date IS NULL OR published_date >= date('now', ?))
"""

# Gupy: so as truncadas legadas (exatamente 500 caracteres). As vagas
# atuais ja chegam com a descricao completa na listagem.
QUERY_GUPY_PENDENTES = """
    SELECT id, external_id, title FROM vagas
    WHERE source = 'gupy'
      AND COALESCE(enrich_encerrada, 0) = 0
      AND LENGTH(description) = 500
      AND (published_date IS NULL OR published_date >= date('now', ?))
"""

# GeekHunter: o card so traz um snippet; o detalhe tem a descricao
# completa (Tarefas, Requisitos, Beneficios), o nome real da empresa
# (o coletor grava o slug da URL) e a data de publicacao. Marca
# pendente descricao curta, company ainda em formato de slug ou
# published_date vazia.
QUERY_GEEKHUNTER_PENDENTES = """
    SELECT id, url, title FROM vagas
    WHERE source = 'geekhunter'
      AND COALESCE(enrich_encerrada, 0) = 0
      AND (
          description IS NULL OR LENGTH(description) < 300
          OR company LIKE '%-%'
          OR published_date IS NULL
      )
"""

# InfoJobs: o teaser da listagem tem exatos 153 caracteres e termina em
# "..."; a descricao completa esta no detalhe. O corte cobre qualquer
# teaser (menor que 160 ou terminando em "..."). Sem janela de dias:
# pendente e tentada em toda rodada ate dar certo ou virar 404 (como no
# Vagas.com e no LinkedIn).
MIN_DESCRICAO_INFOJOBS = 160

QUERY_INFOJOBS_PENDENTES = """
    SELECT id, url, title FROM vagas
    WHERE source = 'infojobs'
      AND COALESCE(enrich_encerrada, 0) = 0
      AND (description IS NULL OR LENGTH(description) < ?
           OR description LIKE '%...')
"""


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


def fetch_infojobs(session: PoliteSession, lock: Lock, url: str) -> tuple[dict, int | None]:
    """Busca o detalhe da vaga e extrai a descricao completa do painel.

    A listagem so traz teaser de 153 caracteres; o detalhe (SSR, sem auth)
    tem a descricao inteira em `p.text-break.white-space-pre-line` dentro
    de `.js_vacancyDataPanels`.

    Vaga encerrada responde 200 com o fallback da home (sem o painel de
    dados da vaga): devolve status 404 para o enriquecedor marca-la como
    encerrada (mesmo tratamento de um 404 real nas outras fontes).
    """
    with lock:
        response = session.get(url)
        status = session.last_status_code
    if response is None:
        return {}, status
    soup = BeautifulSoup(response.text, "html.parser")
    painel = soup.select_one(".js_vacancyDataPanels")
    if painel is None:
        return {"description": ""}, 404
    el = painel.select_one("p.text-break.white-space-pre-line")
    if el is None:
        return {"description": ""}, 404
    return {"description": el.get_text(" ", strip=True)}, status


def _fetch_parando(parou: threading.Event, parar_em_429: bool, fetch):
    """Envolve o fetch para parar o lote no primeiro 429.

    O ThreadPoolExecutor enfileira todas as futures de uma vez: sem esta
    checagem, um 429 no meio do lote nao impediria as demais de continuar
    martelando o IP banido (o Cloudflare do Vagas.com bane por ~23h).
    """

    def wrapper(sess, lk, alvo):
        if parou.is_set():
            return {"description": ""}, 429
        resultado, status = fetch(sess, lk, alvo)
        if status == 429 and parar_em_429:
            if not parou.is_set():
                parou.set()
                logger.warning(
                    "429 detectado: interrompendo o lote desta fonte "
                    "(a fila continua na proxima rodada)"
                )
        return resultado, status

    return wrapper


def _enriquecer(
    c: sqlite3.Cursor,
    session: PoliteSession,
    lock: Lock,
    extractor: SkillExtractor,
    tech_map: dict[str, int],
    query: str,
    args: list,
    fetch,
    parar_em_429: bool = False,
) -> int:
    c.execute(query, args)
    rows = c.fetchall()
    total = 0
    parou = threading.Event()
    fetch_com_parada = _fetch_parando(parou, parar_em_429, fetch)

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(fetch_com_parada, session, lock, alvo): (vid, title)
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
                    # 404 = anuncio encerrado na fonte: nada a fazer.
                    if status == 404:
                        c.execute(
                            "UPDATE vagas SET enrich_encerrada = 1 WHERE id = ?",
                            (vid,),
                        )
                    continue
                pub = resultado.get("published_date", "")
                if pub:
                    # A data do JSON-LD (GeekHunter) chega aqui sem passar
                    # pelo corte do import_csv. Vaga mais antiga que a
                    # janela do projeto entra sem data no card e o detalhe
                    # revela a data real: nesse caso ela nao deveria estar
                    # na base. Remove antes de atualizar qualquer campo.
                    try:
                        pub_iso = date.fromisoformat(pub[:10])
                    except ValueError:
                        pub_iso = None
                    if pub_iso is not None and pub_iso < MIN_DATA_CORTE:
                        c.execute("DELETE FROM vagas WHERE id = ?", (vid,))
                        continue
                c.execute("UPDATE vagas SET description = ? WHERE id = ?", (desc, vid))
                company = resultado.get("company", "")
                if company:
                    c.execute(
                        "UPDATE vagas SET company = ? WHERE id = ?", (company, vid)
                    )
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
                # Resolvida (descricao salva, mesmo curta): sai da fila.
                c.execute(
                    "UPDATE vagas SET enrich_encerrada = 1 WHERE id = ?",
                    (vid,),
                )
                if total % 10 == 0:
                    # Persiste o progresso em lote: abortar por rate limit
                    # nao perde o que ja foi preenchido.
                    c.connection.commit()
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

    query_vagas = QUERY_VAGAS_PENDENTES
    args_vagas = [MIN_DESCRICAO_VAGAS_COM]

    query_trampos = QUERY_TRAMPOS_PENDENTES
    args_trampos = [MIN_DESCRICAO_TRAMPOS, *janela]

    query_gupy = QUERY_GUPY_PENDENTES
    args_gupy = list(janela)

    query_geekhunter = QUERY_GEEKHUNTER_PENDENTES
    args_geekhunter: list = []

    query_infojobs = QUERY_INFOJOBS_PENDENTES
    args_infojobs = [MIN_DESCRICAO_INFOJOBS]

    if limit:
        query_vagas += " LIMIT ?"
        args_vagas.append(limit)
        query_trampos += " LIMIT ?"
        args_trampos.append(limit)
        query_gupy += " LIMIT ?"
        args_gupy.append(limit)
        query_geekhunter += " LIMIT ?"
        args_geekhunter.append(limit)
        query_infojobs += " LIMIT ?"
        args_infojobs.append(limit)

    with PoliteSession(
        user_agent=USER_AGENT,
        delay_seconds=1.0,
        timeout_seconds=12,
        max_retries=2,
        backoff_factor=1.5,
    ) as session, PoliteSession(
        # Vagas.com e protegido por Cloudflare com bot-check: o fingerprint
        # de navegador (curl_cffi) e necessario; delay maior para nao
        # estourar o rate limit por IP.
        user_agent=USER_AGENT,
        delay_seconds=2.0,
        timeout_seconds=12,
        max_retries=2,
        backoff_factor=1.5,
        impersonate="chrome",
    ) as session_vagas, PoliteSession(
        # O InfoJobs faz bloqueio suave por IP em rajadas (200 com body
        # vazio por alguns minutos); delay maior para nao disparar.
        user_agent=USER_AGENT,
        delay_seconds=2.0,
        timeout_seconds=12,
        max_retries=2,
        backoff_factor=1.5,
    ) as session_infojobs:
        c.execute(query_vagas, args_vagas)
        pendentes_vagas = c.fetchall()
        logger.info("Vagas.com pendentes: %d", len(pendentes_vagas))
        # Experimento: visita uma listagem antes dos detalhes, na mesma
        # sessao. O Cloudflare pode liberar detalhes para sessoes que
        # "navegaram" o site (cookies de visitante/cf_clearance).
        if pendentes_vagas:
            session_vagas.get(
                "https://www.vagas.com.br/vagas-de-desenvolvedor-junior"
            )
        total_vagas = _enriquecer(
            c, session_vagas, lock, extractor, tech_map, query_vagas, args_vagas,
            lambda sess, lk, url: fetch_vagas_com(sess, lk, url),
            parar_em_429=True,
        )

        c.execute(query_trampos, args_trampos)
        logger.info("Trampos pendentes: %d", len(c.fetchall()))
        total_trampos = _enriquecer(
            c, session, lock, extractor, tech_map, query_trampos, args_trampos,
            lambda sess, lk, url: fetch_trampos(
                sess, lk, url.rstrip("/").split("/")[-1]
            ),
            parar_em_429=True,
        )

        c.execute(query_gupy, args_gupy)
        logger.info("Gupy truncadas pendentes: %d", len(c.fetchall()))
        total_gupy = _enriquecer(
            c, session, lock, extractor, tech_map, query_gupy, args_gupy,
            lambda sess, lk, job_id: fetch_gupy(sess, lk, job_id),
            parar_em_429=True,
        )

        c.execute(query_geekhunter, args_geekhunter)
        logger.info("GeekHunter pendentes: %d", len(c.fetchall()))
        total_geekhunter = _enriquecer(
            c, session, lock, extractor, tech_map,
            query_geekhunter, args_geekhunter,
            lambda sess, lk, url: fetch_geekhunter(sess, lk, url),
            parar_em_429=True,
        )

        c.execute(query_infojobs, args_infojobs)
        logger.info("InfoJobs pendentes: %d", len(c.fetchall()))
        total_infojobs = _enriquecer(
            c, session_infojobs, lock, extractor, tech_map,
            query_infojobs, args_infojobs,
            lambda sess, lk, url: fetch_infojobs(sess, lk, url),
        )

    conn.commit()
    conn.close()
    logger.info(
        "Enriquecimento concluido: %d vagas.com, %d trampos, %d gupy, "
        "%d geekhunter e %d infojobs.",
        total_vagas, total_trampos, total_gupy, total_geekhunter, total_infojobs,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Enriquece descricoes de Vagas.com, Trampos, Gupy, GeekHunter e InfoJobs."
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--janela", type=int, default=JANELA_TENTATIVA_DIAS,
                        help="Dias de janela de publicacao (padrao: 30).")
    args = parser.parse_args()
    enriquecer(limit=args.limit, janela_dias=args.janela)
