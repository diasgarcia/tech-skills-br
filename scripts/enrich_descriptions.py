"""Enriquecedor de descricoes e tecnologias para vagas do LinkedIn.

Busca a descricao apenas de vagas PENDENTES (sem descricao no banco, com
descricao muito curta ou truncada em 500 caracteres legada), com
PoliteSession (delay + retry em 429/5xx). O lock serializa os GETs para o
delay valer; o parse roda em paralelo.

`enrich_encerrada` marca o caso RESOLVIDO: busca com sucesso (descricao
salvada) ou 404 (anuncio encerrado na fonte). 429 nao marca.

Nao ha janela de dias: vaga pendente e tentada em toda rodada ate dar
certo (descricao salva) ou 404 (marcada como encerrada e nunca mais
buscada). Vagas antigas continuam vivas no LinkedIn por meses; cortar por
data deixava descricao e skills perdidas para sempre.

O criterio "exatamente 500 caracteres" (truncamento legado do CSV antigo)
foi removido: descricoes reais com 500 chars ficavam na fila para sempre
(loop observado na vaga 4446807020).
"""

import logging
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from pathlib import Path
from threading import Lock

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.database import connect_sqlite, resolve_sqlite_path  # noqa: E402
from api.enrichment_state import EnrichmentStatus, record_attempt  # noqa: E402
from api.migrations import migrate_connection  # noqa: E402
from scraper.classifier import default_classifier  # noqa: E402
from scraper.config import RULES_DIR, USER_AGENT  # noqa: E402
from scraper.consolidation import consolidate_description  # noqa: E402
from scraper.enrichment import BatchStopped, DetailResult, EnrichmentSummary, write_summary  # noqa: E402
from scraper.enrichment_queries import QUERY_LINKEDIN_PENDENTES as QUERY_PENDENTES  # noqa: E402
from scraper.geo import default_geo_classifier  # noqa: E402
from scraper.http_client import PoliteSession  # noqa: E402
from scraper.models import NAO_INFORMADO, infer_workplace  # noqa: E402
from scraper.skills import SkillExtractor  # noqa: E402
from scraper.sources.linkedin import DETAIL_API_URL, parse_linkedin_description  # noqa: E402

logger = logging.getLogger("enrich")

def fetch_one_description(
    session: PoliteSession,
    lock: Lock,
    job_id: str,
    parou: threading.Event,
) -> DetailResult:
    url = DETAIL_API_URL.format(job_id=job_id)
    status = None
    try:
        with lock:
            if parou.is_set():
                return DetailResult.stopped()
            response = session.get(url)
            status = session.last_status_code
            if status == 429:
                parou.set()
                logger.warning(
                    "429 detectado: interrompendo o lote do LinkedIn "
                    "(a fila continua na proxima rodada)"
                )
        if response is None:
            return DetailResult(status=status, reason="sem_resposta")
        description = parse_linkedin_description(response.text)
        if description:
            return DetailResult(data={"description": description}, status=status)
        logger.warning("[enrich] Descricao nao encontrada na vaga %s", job_id)
    except BatchStopped:
        return DetailResult.stopped()
    except Exception as e:
        logger.warning("[enrich] Falha ao buscar a vaga %s: %s", job_id, e)
        return DetailResult(status=status, reason="erro_de_busca", details=str(e))
    return DetailResult(status=status, reason="descricao_ausente")


def enrich_linkedin_jobs(
    limit: int | None = None,
    max_workers: int = 3,
    janela_dias: int | None = None,
    db_path: str | Path | None = None,
    summary_path: str | Path | None = None,
):
    del janela_dias  # mantido por compatibilidade; a janela foi removida

    if limit is not None and limit < 1:
        raise ValueError("O limite deve ser maior que zero.")
    if max_workers < 1:
        raise ValueError("O numero de workers deve ser maior que zero.")
    destino = resolve_sqlite_path(db_path)
    logger.info("Banco selecionado: %s", destino)
    with open(RULES_DIR / "skills.yml", encoding="utf-8") as fh:
        rules = yaml.safe_load(fh) or {}
    extractor = SkillExtractor(rules)
    classifier = default_classifier()
    geo = default_geo_classifier()

    with closing(connect_sqlite(destino)) as conn:
        summary = _enrich_linkedin_connection(conn, extractor, classifier, geo, limit, max_workers)
    if summary_path is not None:
        write_summary(summary_path, {"linkedin": summary})
    return summary


def _enrich_linkedin_connection(conn, extractor, classifier, geo, limit, max_workers):
    migrate_connection(conn)
    c = conn.cursor()

    query = QUERY_PENDENTES
    args: list = []
    if limit:
        query += " LIMIT ?"
        args.append(limit)

    c.execute(query, args)
    jobs_to_enrich = c.fetchall()
    summary = EnrichmentSummary(selected=len(jobs_to_enrich))
    logger.info("Total de vagas do LinkedIn para enriquecer: %d", len(jobs_to_enrich))

    if not jobs_to_enrich:
        logger.info("Nenhuma vaga pendente de enriquecimento.")
        summary.log(logger, "linkedin")
        return summary

    c.execute("SELECT id, nome FROM tecnologias")
    tech_map = {nome.lower(): tid for tid, nome in c.fetchall()}
    lock = Lock()
    parou = threading.Event()

    with PoliteSession(
        user_agent=USER_AGENT,
        delay_seconds=1.0,
        timeout_seconds=12,
        max_retries=2,
        backoff_factor=1.5,
    ) as session:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(
                    fetch_one_description, session, lock, ext_id, parou
                ): (db_id, ext_id, title, url, location, workplace)
                for db_id, ext_id, title, url, location, workplace in jobs_to_enrich
            }

            for future in as_completed(futures):
                db_id, ext_id, title, url, location, workplace = futures[future]
                attempted = True
                try:
                    result = future.result()
                    attempted = result.attempted
                    desc = result.data.get("description", "").strip()
                    status = result.status
                    if not attempted:
                        summary.leave_pending(result.reason, skipped=True)
                        logger.info(
                            "linkedin: vaga %s nao tentada | motivo=%s | titulo=%r | url=%s",
                            ext_id, result.reason, title, url,
                        )
                        continue
                    if desc:
                        with conn:
                            outcome = _save_linkedin_detail(
                                c, db_id, title, location, workplace, desc,
                                extractor, classifier, geo, tech_map,
                            )
                            if outcome != "removed":
                                record_attempt(conn, db_id, EnrichmentStatus.SUCCEEDED)
                        if outcome == "removed":
                            logger.info(
                                "Vaga %s removida apos descricao confirmar "
                                "contexto fora de TI.",
                                ext_id,
                            )
                            summary.removed += 1
                            continue
                        summary.enriched += 1
                        if summary.enriched % 25 == 0:
                            logger.info("Enriquecidas %d / %d vagas...", summary.enriched, len(jobs_to_enrich))
                    elif status in (404, 410):
                        # Anuncio encerrado: marca para nunca mais buscar.
                        with conn:
                            c.execute(
                                "UPDATE vagas SET enrich_encerrada = 1, "
                                "updated_at = CURRENT_TIMESTAMP WHERE id = ?", (db_id,),
                            )
                            record_attempt(conn, db_id, EnrichmentStatus.UNAVAILABLE, f"http_{status}")
                        summary.closed += 1
                        logger.info(
                            "linkedin: vaga %s encerrada | http=%s | "
                            "titulo=%r | url=%s",
                            ext_id, status, title, url,
                        )
                    else:
                        if status is not None and status >= 400:
                            motivo = f"http_{status}"
                        else:
                            motivo = result.reason or "descricao_ausente"
                        summary.leave_pending(motivo, failed=result.reason == "erro_de_busca")
                        with conn:
                            record_attempt(conn, db_id, EnrichmentStatus.FAILED, motivo)
                        logger.warning(
                            "linkedin: vaga %s permaneceu pendente | "
                            "motivo=%s | http=%s | titulo=%r | url=%s | detalhes=%s",
                            ext_id, motivo, status, title, url, result.details,
                        )
                except Exception as e:
                    with conn:
                        record_attempt(conn, db_id, EnrichmentStatus.FAILED, "erro_de_processamento")
                    summary.leave_pending("erro_de_processamento", failed=True)
                    logger.warning(
                        "Falha ao processar job %s | titulo=%r | url=%s | erro=%s",
                        ext_id, title, url, e,
                    )
                finally:
                    summary.attempted += int(attempted)

    logger.info("Enriquecimento concluido com sucesso: %d vagas enriquecidas!", summary.enriched)
    summary.log(logger, "linkedin")
    return summary


def _save_linkedin_detail(c, db_id, title, location, workplace, desc, extractor, classifier, geo, tech_map):
    """Grava uma vaga dentro da transacao aberta pelo chamador."""
    saved_description = c.execute("SELECT description FROM vagas WHERE id = ?", (db_id,)).fetchone()[0]
    description = consolidate_description(saved_description, desc, detail=True).text
    if not classifier.is_tech(title, description):
        c.execute("DELETE FROM vaga_tecnologia WHERE vaga_id = ?", (db_id,))
        c.execute("DELETE FROM vagas WHERE id = ?", (db_id,))
        return "removed"

    c.execute("UPDATE vagas SET description = ? WHERE id = ?", (description, db_id))
    modalidade = infer_workplace(None, location=location, title=title, description=description)
    if modalidade and modalidade != NAO_INFORMADO and modalidade != (workplace or ""):
        polo, regiao = geo.classify(location, modalidade)
        c.execute(
            "UPDATE vagas SET workplace_type = ?, polo = ?, regiao = ? WHERE id = ?",
            (modalidade, polo, regiao, db_id),
        )
    for skill in extractor.extract(title, description):
        tid = tech_map.get(skill.lower())
        if tid:
            c.execute(
                "INSERT OR IGNORE INTO vaga_tecnologia (vaga_id, tecnologia_id) VALUES (?, ?)",
                (db_id, tid),
            )
    c.execute(
        "UPDATE vagas SET enrich_encerrada = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (db_id,),
    )
    return "enriched"


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
    parser = argparse.ArgumentParser(
        description="Enriquece descricoes de vagas do LinkedIn pendentes."
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--db", type=Path, default=None, help="Banco SQLite a atualizar.")
    parser.add_argument("--summary-json", type=Path, default=None, help="Grava contadores estruturados deste lote.")
    args = parser.parse_args()
    enrich_linkedin_jobs(limit=args.limit, db_path=args.db, summary_path=args.summary_json)
