"""Enriquecedor de descricoes para fontes com detalhe publico.

A listagem dessas fontes nao traz a descricao completa da vaga. Este
script busca o detalhe de cada vaga PENDENTE, atualiza a descricao no
banco e re-extrai as tecnologias com o skills.yml atual.

- Vagas.com: GET na propria URL da vaga (pagina server-rendered, sem
  login) e parse de `div.job-description__text`.
- Trampos: GET em https://trampos.co/api/v2/opportunities/{slug}, onde o
  slug e o ultimo segmento da URL da vaga; junta description,
  prerequisite, desirable e other_info.
- Gupy: GET na pagina publica de cada vaga ainda nao conferida. A descricao
  integral e o nome declarado da empresa vem no JSON-LD JobPosting ou no
  `__NEXT_DATA__`, conforme a versao do portal. A API global da Gupy nao
  reconhece vagas de todos os job boards e, por isso, nao e usada como fonte
  de 404.
- GeekHunter: o card da listagem so traz snippet; o detalhe (SSR, sem
  auth) tem um bloco JSON-LD JobPosting com description completa,
  hiringOrganization (nome real da empresa) e datePosted. Alem da
  descricao, corrige o `company` (o coletor so tinha o slug da URL).
- InfoJobs: o card traz um teaser fixo de 153 caracteres (sempre com
  "..."); o detalhe (SSR, sem auth) tem a descricao completa em
  `p.text-break.white-space-pre-line` dentro de `.js_vacancyDataPanels`.
  Resposta 200 sem o painel nao e tratada como encerramento, pois tambem
  pode ser bloqueio suave ou mudanca temporaria de layout. Somente HTTP
  404/410 real encerra a vaga.

A janela de 30 dias se aplica apenas ao Trampos. Nas demais fontes, o
criterio compartilhado seleciona registros ainda pendentes. O lock
serializa os GETs para respeitar o intervalo entre chamadas.
"""

from __future__ import annotations

import html
import json
import logging
import sqlite3
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from datetime import date
from pathlib import Path
from threading import Lock

from bs4 import BeautifulSoup
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.database import connect_sqlite, resolve_sqlite_path  # noqa: E402
from api.enrichment_state import EnrichmentStatus, record_attempt  # noqa: E402
from api.migrations import migrate_connection  # noqa: E402
from scraper.config import RULES_DIR, USER_AGENT  # noqa: E402
from scraper.consolidation import MIN_DATA_CORTE, canonical_company, consolidate_description  # noqa: E402
from scraper.enrichment import (  # noqa: E402
    BatchStopped, DetailResult, EnrichmentSummary, StopAwareSession, write_summary,
)
from scraper.enrichment_queries import (  # noqa: E402
    JANELA_TENTATIVA_DIAS, MIN_DESCRICAO_INFOJOBS, MIN_DESCRICAO_TRAMPOS,
    MIN_DESCRICAO_VAGAS_COM, QUERY_GEEKHUNTER_FORCADO, QUERY_GEEKHUNTER_PENDENTES,
    QUERY_GUPY_FORCADO, QUERY_GUPY_PENDENTES, QUERY_INFOJOBS_FORCADO,
    QUERY_INFOJOBS_PENDENTES, QUERY_TRAMPOS_PENDENTES, QUERY_VAGAS_PENDENTES,
)
from scraper.http_client import PoliteSession  # noqa: E402
from scraper.models import strip_html  # noqa: E402
from scraper.skills import SkillExtractor  # noqa: E402

logger = logging.getLogger("enrich_outras")

TRAMPOS_API_URL = "https://trampos.co/api/v2/opportunities/{slug}"

CHAVE_DIAGNOSTICO = "_diagnostico"
CHAVE_DETALHES = "_detalhes"


def fetch_vagas_com(session: PoliteSession, lock: Lock, url: str) -> tuple[str | dict, int | None]:
    with lock:
        response = session.get(url)
        status = session.last_status_code
    if response is None:
        return "", status
    soup = BeautifulSoup(response.text, "html.parser")
    el = soup.select_one("div.job-description__text, div.texto")
    if el is None:
        # O portal tambem indica remocao por uma pagina generica. Mantem
        # o criterio de encerramento sem inventar um codigo HTTP 404.
        titulo = soup.select_one("title")
        if titulo and "vagas de emprego para" in titulo.get_text(strip=True).lower():
            return {CHAVE_DIAGNOSTICO: "pagina_generica_sem_anuncio", "_indisponivel": True}, status
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


def fetch_gupy(session: PoliteSession, lock: Lock, url: str) -> tuple[dict, int | None]:
    """Extrai descricao e empresa declarada na pagina publica da Gupy.

    A API global de empregos retorna 404 para vagas ainda publicadas em
    job boards proprios (como o da Claro). O HTML server-rendered e a fonte
    usada aqui. Ausencia dos blocos conhecidos em uma resposta 200 e tratada
    como falha temporaria ou mudanca de layout, nunca como encerramento.
    """
    with lock:
        response = session.get(url)
        status = session.last_status_code
    if response is None:
        return {CHAVE_DIAGNOSTICO: "sem_resposta"}, status
    corpo = response.text or ""
    url_final = str(getattr(response, "url", url) or url)
    soup = BeautifulSoup(corpo, "html.parser")
    dados: dict[str, str] = {}
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(html.unescape(script.string or ""))
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict) and data.get("@type") == "JobPosting":
            descricao = strip_html(data.get("description") or "")
            if descricao:
                dados["description"] = descricao
            org = data.get("hiringOrganization") or {}
            if isinstance(org, dict):
                empresa = (org.get("name") or "").strip()
                if empresa:
                    dados["company"] = empresa
            break

    # Parte dos job boards usa uma versao anterior do front da Gupy. Nela,
    # nao ha JSON-LD: os campos completos estao no estado SSR do Next.js.
    next_data = soup.find("script", id="__NEXT_DATA__")
    if next_data is not None:
        try:
            payload = json.loads(next_data.string or "")
            job = payload["props"]["pageProps"]["job"]
        except (KeyError, TypeError, ValueError):
            job = {}
        if isinstance(job, dict):
            if not dados.get("description"):
                partes = [
                    strip_html(job.get(campo) or "")
                    for campo in (
                        "description", "responsibilities", "prerequisites"
                    )
                ]
                descricao = " ".join(parte for parte in partes if parte).strip()
                if descricao:
                    dados["description"] = descricao
            if not dados.get("company"):
                career_page = job.get("careerPage") or {}
                if isinstance(career_page, dict):
                    empresa = (career_page.get("name") or "").strip()
                    if empresa:
                        dados["company"] = empresa

    if not dados:
        motivo = (
            "redirecionamento_para_login"
            if "/candidates/signin" in url_final
            else "jobposting_ausente"
        )
        dados[CHAVE_DIAGNOSTICO] = motivo
        dados[CHAVE_DETALHES] = (
            f"url_final={url_final}; corpo={len(corpo)} caracteres"
        )

    return dados, status


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
    encontrou_vaga = False
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (ValueError, TypeError):
            continue
        if data.get("@type") != "JobPosting":
            continue
        encontrou_vaga = True
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
    # Mantem a decisao legada de indisponibilidade por conteudo, mas
    # preserva o HTTP real para nao atribuir um 404 ao servidor.
    if not encontrou_vaga and status == 200:
        return {CHAVE_DIAGNOSTICO: "pagina_institucional_sem_anuncio", "_indisponivel": True}, status
    return dados, status


def fetch_infojobs(session: PoliteSession, lock: Lock, url: str) -> tuple[dict, int | None]:
    """Busca o detalhe da vaga e extrai a descricao completa do painel.

    A listagem so traz teaser de 153 caracteres; o detalhe (SSR, sem auth)
    tem a descricao inteira em `p.text-break.white-space-pre-line` dentro
    de `.js_vacancyDataPanels`.

    Resposta 200 sem o painel ou com BODY VAZIO fica pendente. Isso pode
    ser bloqueio suave ou mudanca temporaria de layout; marcar como 404
    perderia uma descricao valida. Somente o status HTTP real e repassado.
    """
    with lock:
        response = session.get(url)
        status = session.last_status_code
    if response is None:
        return {CHAVE_DIAGNOSTICO: "sem_resposta"}, status
    corpo = response.text or ""
    url_final = str(getattr(response, "url", url) or url)
    detalhes = f"url_final={url_final}; corpo={len(corpo)} caracteres"
    if not corpo.strip():
        return {
            CHAVE_DIAGNOSTICO: "resposta_vazia",
            CHAVE_DETALHES: detalhes,
        }, status
    soup = BeautifulSoup(corpo, "html.parser")
    painel = soup.select_one(".js_vacancyDataPanels")
    if painel is None:
        return {
            CHAVE_DIAGNOSTICO: "painel_da_vaga_ausente",
            CHAVE_DETALHES: detalhes,
        }, status
    el = painel.select_one("p.text-break.white-space-pre-line")
    if el is None:
        return {
            CHAVE_DIAGNOSTICO: "descricao_ausente_no_painel",
            CHAVE_DETALHES: detalhes,
        }, status
    descricao = el.get_text(" ", strip=True)
    # O painel oficial tambem pode conter uma descricao completa e curta.
    # Reticencias no fim ainda indicam o teaser incompleto da listagem.
    if not descricao or descricao.endswith(("...", "…")):
        return {
            CHAVE_DIAGNOSTICO: "descricao_curta_ou_truncada",
            CHAVE_DETALHES: f"{detalhes}; descricao={len(descricao)} caracteres",
        }, status
    return {"description": descricao}, status


def _fetch_parando(parou: threading.Event, parar_em_429: bool, fetch):
    """Envolve o fetch para parar o lote no primeiro 429.

    O ThreadPoolExecutor enfileira todas as futures de uma vez: sem esta
    checagem, um 429 no meio do lote nao impediria as demais de continuar
    martelando o IP banido (o Cloudflare do Vagas.com bane por ~23h).
    """

    def wrapper(sess, lk, alvo):
        if parou.is_set():
            return DetailResult.stopped()
        guarded_session = StopAwareSession(sess, parou, stop_on_429=parar_em_429)
        try:
            resultado, status = fetch(guarded_session, lk, alvo)
        except BatchStopped:
            return DetailResult.stopped()
        if status == 429 and parar_em_429:
            parou.set()
            logger.warning(
                "429 detectado: interrompendo o lote desta fonte "
                "(a fila continua na proxima rodada)"
            )
        return DetailResult.from_response(resultado, status)

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
    fonte: str = "fonte",
    max_workers: int = 3,
    summaries: dict[str, EnrichmentSummary] | None = None,
) -> int:
    migrate_connection(c.connection)
    c.execute(query, args)
    rows = c.fetchall()
    summary = EnrichmentSummary(selected=len(rows))
    parou = threading.Event()
    fetch_com_parada = _fetch_parando(parou, parar_em_429, fetch)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(fetch_com_parada, session, lock, alvo): (vid, title, alvo)
            for vid, alvo, title in rows
        }
        for future in as_completed(futures):
            vid, title, alvo = futures[future]
            attempted = True
            try:
                result = future.result()
                attempted = result.attempted
                resultado, status = result.data, result.status
                diagnostico, detalhes = result.reason, result.details
                if not attempted:
                    summary.leave_pending(diagnostico, skipped=True)
                    logger.info(
                        "%s: vaga %s nao tentada | motivo=%s | titulo=%r | url=%s",
                        fonte, vid, diagnostico, title, alvo,
                    )
                    continue
                desc = (resultado.get("description") or "").strip()
                company = (resultado.get("company") or "").strip()
                pub = (resultado.get("published_date") or "").strip()
                if not desc and not company and not pub:
                    # 404/410 = anuncio encerrado na fonte: nada a fazer.
                    # A GeekHunter usa 410 em parte das vagas removidas.
                    if result.unavailable or status in (404, 410):
                        with c.connection:
                            c.execute(
                                "UPDATE vagas SET enrich_encerrada = 1, "
                                "updated_at = CURRENT_TIMESTAMP WHERE id = ?", (vid,),
                            )
                            record_attempt(c.connection, vid, EnrichmentStatus.UNAVAILABLE, diagnostico or f"http_{status}")
                        summary.closed += 1
                        logger.info(
                            "%s: vaga %s encerrada | http=%s | motivo=%s | titulo=%r | url=%s",
                            fonte, vid, status, diagnostico or f"http_{status}", title, alvo,
                        )
                    else:
                        if diagnostico:
                            motivo = diagnostico
                        elif status is None:
                            motivo = "sem_resposta"
                        elif status >= 400:
                            motivo = f"http_{status}"
                        else:
                            motivo = "conteudo_sem_dados_utilizaveis"
                        summary.leave_pending(motivo)
                        with c.connection:
                            record_attempt(c.connection, vid, EnrichmentStatus.FAILED, motivo)
                        complemento = f" | {detalhes}" if detalhes else ""
                        logger.warning(
                            "%s: vaga %s permaneceu pendente | motivo=%s | "
                            "http=%s | titulo=%r | url=%s%s",
                            fonte, vid, motivo, status, title, alvo, complemento,
                        )
                    continue
                with c.connection:
                    outcome = _save_other_detail(c, vid, title, desc, company, pub, extractor, tech_map)
                    if outcome != "removed":
                        record_attempt(c.connection, vid, EnrichmentStatus.SUCCEEDED)
                if outcome == "removed":
                    summary.removed += 1
                    logger.info(
                        "%s: vaga %s removida por data anterior ao corte | "
                        "data=%s | titulo=%r | url=%s", fonte, vid, pub, title, alvo,
                    )
                else:
                    summary.enriched += 1
            except Exception as exc:
                with c.connection:
                    record_attempt(c.connection, vid, EnrichmentStatus.FAILED, "erro_de_processamento")
                summary.leave_pending("erro_de_processamento", failed=True)
                logger.warning(
                    "%s: falha ao processar vaga %s | titulo=%r | url=%s | erro=%s",
                    fonte, vid, title, alvo, exc,
                )
            finally:
                summary.attempted += int(attempted)
    summary.log(logger, fonte)
    if summaries is not None:
        summaries[fonte] = summary
    return summary.enriched


def _save_other_detail(c, vid, title, desc, company, pub, extractor, tech_map):
    """Atualiza campos e skills na mesma transacao, sem contar antes do commit."""
    try:
        pub_iso = date.fromisoformat(pub[:10]) if pub else None
    except ValueError:
        pub_iso = None
    if pub_iso is not None and pub_iso < MIN_DATA_CORTE:
        c.execute("DELETE FROM vaga_tecnologia WHERE vaga_id = ?", (vid,))
        c.execute("DELETE FROM vagas WHERE id = ?", (vid,))
        return "removed"

    descricao_atual = c.execute("SELECT description FROM vagas WHERE id = ?", (vid,)).fetchone()[0] or ""
    descricao_final = consolidate_description(descricao_atual, desc, detail=True).text
    if descricao_final != descricao_atual:
        c.execute("UPDATE vagas SET description = ? WHERE id = ?", (descricao_final, vid))
    if company:
        company = canonical_company(company)
        if company:
            c.execute("UPDATE vagas SET company = ? WHERE id = ?", (company, vid))
    if pub:
        c.execute("UPDATE vagas SET published_date = ? WHERE id = ?", (pub, vid))
    for skill in extractor.extract(title, descricao_final):
        tid = tech_map.get(skill.lower())
        if tid:
            c.execute(
                "INSERT OR IGNORE INTO vaga_tecnologia (vaga_id, tecnologia_id) VALUES (?, ?)",
                (vid, tid),
            )
    c.execute(
        "UPDATE vagas SET enrich_encerrada = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (vid,),
    )
    return "enriched"


def enriquecer(
    limit: int | None = None,
    janela_dias: int = JANELA_TENTATIVA_DIAS,
    fonte: str | None = None,
    forcar: bool = False,
    db_path: str | Path | None = None,
    summary_path: str | Path | None = None,
) -> dict[str, EnrichmentSummary]:
    """Enriquece as fontes pendentes ou uma fonte selecionada manualmente."""
    fontes = {"vagas", "trampos", "gupy", "geekhunter", "infojobs"}
    if fonte is not None and fonte not in fontes:
        raise ValueError(f"Fonte invalida: {fonte}")
    if forcar and fonte not in {"geekhunter", "gupy", "infojobs"}:
        raise ValueError(
            "--forcar so pode ser usado com --fonte geekhunter, gupy ou infojobs"
        )
    if limit is not None and limit < 1:
        raise ValueError("O limite deve ser maior que zero.")
    if janela_dias < 0:
        raise ValueError("A janela de dias nao pode ser negativa.")

    with open(RULES_DIR / "skills.yml", encoding="utf-8") as fh:
        rules = yaml.safe_load(fh) or {}
    extractor = SkillExtractor(rules)

    destino = resolve_sqlite_path(db_path)
    logger.info("Banco selecionado: %s", destino)
    with closing(connect_sqlite(destino)) as conn:
        summaries = _enrich_other_connection(conn, extractor, limit, janela_dias, fonte, forcar)
    if summary_path is not None:
        write_summary(summary_path, summaries)
    return summaries


def _enrich_other_connection(conn, extractor, limit, janela_dias, fonte, forcar):
    summaries: dict[str, EnrichmentSummary] = {}
    c = conn.cursor()
    c.execute("SELECT id, nome FROM tecnologias")
    tech_map = {nome.lower(): tid for tid, nome in c.fetchall()}

    janela = [f"-{janela_dias} days"]
    lock = Lock()

    query_vagas = QUERY_VAGAS_PENDENTES
    args_vagas = [MIN_DESCRICAO_VAGAS_COM]

    query_trampos = QUERY_TRAMPOS_PENDENTES
    args_trampos = [MIN_DESCRICAO_TRAMPOS, *janela]

    query_gupy = (
        QUERY_GUPY_FORCADO
        if fonte == "gupy" and forcar
        else QUERY_GUPY_PENDENTES
    )
    args_gupy: list = []

    query_geekhunter = (
        QUERY_GEEKHUNTER_FORCADO
        if fonte == "geekhunter" and forcar
        else QUERY_GEEKHUNTER_PENDENTES
    )
    args_geekhunter: list = []

    query_infojobs = (
        QUERY_INFOJOBS_FORCADO
        if fonte == "infojobs" and forcar
        else QUERY_INFOJOBS_PENDENTES
    )
    args_infojobs = [MIN_DESCRICAO_INFOJOBS]

    # A opcao --fonte serve para uma revisao localizada sem gerar requests
    # para os demais portais. Mantem as consultas e os logs uniformes.
    consulta_vazia = "SELECT id, url, title FROM vagas WHERE 1 = 0"
    if fonte and fonte != "vagas":
        query_vagas, args_vagas = consulta_vazia, []
    if fonte and fonte != "trampos":
        query_trampos, args_trampos = consulta_vazia, []
    if fonte and fonte != "gupy":
        query_gupy, args_gupy = consulta_vazia, []
    if fonte and fonte != "geekhunter":
        query_geekhunter, args_geekhunter = consulta_vazia, []
    if fonte and fonte != "infojobs":
        query_infojobs, args_infojobs = consulta_vazia, []

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

    # Uma revisao forcada precisa desfazer o estado antigo antes dos GETs.
    # Assim, sucesso e 404/410 real voltam a marcar a vaga; resposta vazia,
    # bloqueio suave ou layout desconhecido deixam o item pendente.
    if fonte and forcar:
        consulta_fonte, argumentos_fonte = {
            "gupy": (query_gupy, args_gupy),
            "geekhunter": (query_geekhunter, args_geekhunter),
            "infojobs": (query_infojobs, args_infojobs),
        }[fonte]
        c.execute(consulta_fonte, argumentos_fonte)
        ids_reabertos = [(row[0],) for row in c.fetchall()]
        c.executemany(
            "UPDATE vagas SET enrich_encerrada = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            ids_reabertos,
        )
        conn.commit()
        logger.info("Revisao forcada reabriu %d registros.", len(ids_reabertos))

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
            fonte="vagas.com",
            summaries=summaries,
        )

        c.execute(query_trampos, args_trampos)
        logger.info("Trampos pendentes: %d", len(c.fetchall()))
        total_trampos = _enriquecer(
            c, session, lock, extractor, tech_map, query_trampos, args_trampos,
            lambda sess, lk, url: fetch_trampos(
                sess, lk, url.rstrip("/").split("/")[-1]
            ),
            parar_em_429=True,
            fonte="trampos",
            summaries=summaries,
        )

        c.execute(query_gupy, args_gupy)
        logger.info("Gupy pendentes de detalhe: %d", len(c.fetchall()))
        total_gupy = _enriquecer(
            c, session, lock, extractor, tech_map, query_gupy, args_gupy,
            lambda sess, lk, url: fetch_gupy(sess, lk, url),
            parar_em_429=True,
            fonte="gupy",
            summaries=summaries,
        )

        c.execute(query_geekhunter, args_geekhunter)
        logger.info("GeekHunter pendentes: %d", len(c.fetchall()))
        total_geekhunter = _enriquecer(
            c, session, lock, extractor, tech_map,
            query_geekhunter, args_geekhunter,
            lambda sess, lk, url: fetch_geekhunter(sess, lk, url),
            parar_em_429=True,
            fonte="geekhunter",
            summaries=summaries,
        )

        c.execute(query_infojobs, args_infojobs)
        logger.info("InfoJobs pendentes: %d", len(c.fetchall()))
        total_infojobs = _enriquecer(
            c, session_infojobs, lock, extractor, tech_map,
            query_infojobs, args_infojobs,
            lambda sess, lk, url: fetch_infojobs(sess, lk, url),
            parar_em_429=True,
            fonte="infojobs",
            summaries=summaries,
        )

    conn.commit()
    logger.info(
        "Enriquecimento concluido: %d vagas.com, %d trampos, %d gupy, "
        "%d geekhunter e %d infojobs.",
        total_vagas, total_trampos, total_gupy, total_geekhunter, total_infojobs,
    )
    return summaries


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
    parser = argparse.ArgumentParser(
        description="Enriquece descricoes de Vagas.com, Trampos, Gupy, GeekHunter e InfoJobs."
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--db", type=Path, default=None, help="Banco SQLite a atualizar.")
    parser.add_argument("--summary-json", type=Path, default=None, help="Grava contadores estruturados deste lote.")
    parser.add_argument("--janela", type=int, default=JANELA_TENTATIVA_DIAS,
                        help="Dias de janela de publicacao (padrao: 30).")
    parser.add_argument(
        "--fonte",
        choices=("vagas", "trampos", "gupy", "geekhunter", "infojobs"),
        help="Enriquece somente esta fonte.",
    )
    parser.add_argument(
        "--forcar",
        action="store_true",
        help=(
            "Revisa vagas ja resolvidas: todas da Gupy/GeekHunter ou os "
            "teasers do InfoJobs."
        ),
    )
    args = parser.parse_args()
    enriquecer(
        limit=args.limit,
        janela_dias=args.janela,
        fonte=args.fonte,
        forcar=args.forcar,
        db_path=args.db,
        summary_path=args.summary_json,
    )
