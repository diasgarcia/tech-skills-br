"""Enriquecedor de descricoes e tecnologias para vagas do LinkedIn.

Busca a descricao apenas de vagas PENDENTES (sem descricao no banco, com
descricao muito curta ou truncada em 500 caracteres legada), com
PoliteSession (delay + retry em 429/5xx). O lock serializa os GETs para o
delay valer; o parse roda em paralelo.

Nao ha janela de dias: vaga pendente e tentada em toda rodada ate dar
certo (descricao salva) ou 404 (marcada como encerrada e nunca mais
buscada). Vagas antigas continuam vivas no LinkedIn por meses; cortar por
data deixava descricao e skills perdidas para sempre.

Descricoes com exatamente 500 caracteres tambem entram na fila: sao as que o
CSV de coleta truncava antes de o projeto passar a salvar o texto completo.
"""

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

from api.database import SessionLocal, init_db  # noqa: E402
from api.models import Tecnologia, Vaga, vaga_tecnologia  # noqa: E402
from scraper.config import RULES_DIR, USER_AGENT  # noqa: E402
from scraper.geo import default_geo_classifier  # noqa: E402
from scraper.http_client import PoliteSession  # noqa: E402
from scraper.models import NAO_INFORMADO, infer_workplace  # noqa: E402
from scraper.skills import SkillExtractor  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
logger = logging.getLogger("enrich")

DETAIL_API_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

QUERY_PENDENTES = """
    SELECT id, external_id, title, url, location, workplace_type
    FROM vagas
    WHERE source = 'linkedin'
      AND COALESCE(enrich_encerrada, 0) = 0
      AND (description IS NULL OR LENGTH(description) < 30
           OR LENGTH(description) = 500)
"""


def fetch_one_description(session: PoliteSession, lock: Lock, job_id: str) -> tuple[str, str, int | None]:
    url = DETAIL_API_URL.format(job_id=job_id)
    status = None
    try:
        with lock:
            response = session.get(url)
            status = session.last_status_code
        if response is None:
            return job_id, "", status
        soup = BeautifulSoup(response.text, "html.parser")
        el = soup.select_one(".show-more-less-html__markup, .description__text")
        if el:
            return job_id, el.get_text(" ", strip=True), status
        logger.warning("[enrich] Descricao nao encontrada na vaga %s", job_id)
    except Exception as e:
        logger.warning("[enrich] Falha ao buscar a vaga %s: %s", job_id, e)
    return job_id, "", status


def enrich_linkedin_jobs(
    limit: int | None = None,
    max_workers: int = 3,
    janela_dias: int | None = None,
):
    del janela_dias  # mantido por compatibilidade; a janela foi removida

    init_db()
    with open(RULES_DIR / "skills.yml", encoding="utf-8") as fh:
        rules = yaml.safe_load(fh) or {}
    extractor = SkillExtractor(rules)
    geo = default_geo_classifier()

    conn = sqlite3.connect(PROJECT_ROOT / "data" / "vagas.db")
    c = conn.cursor()

    query = QUERY_PENDENTES
    args: list = []
    if limit:
        query += f" LIMIT {limit}"

    c.execute(query, args)
    jobs_to_enrich = c.fetchall()
    logger.info("Total de vagas do LinkedIn para enriquecer: %d", len(jobs_to_enrich))

    if not jobs_to_enrich:
        logger.info("Nenhuma vaga pendente de enriquecimento.")
        return

    c.execute("SELECT id, nome FROM tecnologias")
    tech_map = {nome.lower(): tid for tid, nome in c.fetchall()}
    enriched_count = 0
    lock = Lock()

    with PoliteSession(
        user_agent=USER_AGENT,
        delay_seconds=1.0,
        timeout_seconds=12,
        max_retries=2,
        backoff_factor=1.5,
    ) as session:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(fetch_one_description, session, lock, ext_id): (db_id, ext_id, title, location, workplace)
                for db_id, ext_id, title, url, location, workplace in jobs_to_enrich
            }

            for future in as_completed(futures):
                db_id, ext_id, title, location, workplace = futures[future]
                try:
                    _, desc, status = future.result()
                    if desc:
                        c.execute("UPDATE vagas SET description = ? WHERE id = ?", (desc, db_id))

                        # A descricao completa e mais confiavel que o palpite
                        # de modalidade feito no card da busca.
                        modalidade = infer_workplace(
                            None, location=location, title=title, description=desc
                        )
                        if (
                            modalidade
                            and modalidade != NAO_INFORMADO
                            and modalidade != (workplace or "")
                        ):
                            polo, regiao = geo.classify(location, modalidade)
                            c.execute(
                                "UPDATE vagas SET workplace_type = ?, polo = ?, regiao = ? WHERE id = ?",
                                (modalidade, polo, regiao, db_id),
                            )

                        full_text = f"{title} {desc}"
                        extracted_skills = extractor.extract(full_text)

                        for s in extracted_skills:
                            tid = tech_map.get(s.lower())
                            if tid:
                                c.execute(
                                    "INSERT OR IGNORE INTO vaga_tecnologia (vaga_id, tecnologia_id) VALUES (?, ?)",
                                    (db_id, tid),
                                )

                        enriched_count += 1
                        if enriched_count % 25 == 0:
                            conn.commit()
                            logger.info("Enriquecidas %d / %d vagas...", enriched_count, len(jobs_to_enrich))
                    elif status == 404:
                        # Anuncio encerrado: marca para nunca mais buscar.
                        c.execute(
                            "UPDATE vagas SET enrich_encerrada = 1 WHERE id = ?",
                            (db_id,),
                        )
                except Exception as e:
                    logger.warning("Falha ao processar job %s: %s", ext_id, e)

    conn.commit()
    conn.close()
    logger.info("Enriquecimento concluido com sucesso: %d vagas enriquecidas!", enriched_count)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Enriquece descricoes de vagas do LinkedIn pendentes."
    )
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    enrich_linkedin_jobs(limit=args.limit)
