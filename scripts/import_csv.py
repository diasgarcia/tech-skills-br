"""Importa o CSV de vagas gerado pelo scraper para o SQLite.

    python scripts/import_csv.py                  # pega o CSV mais recente
    python scripts/import_csv.py --csv caminho.csv
    python scripts/import_csv.py --db data/outro.db --recriar

O CSV nao e alterado: o pipeline de raspagem continua sendo a fonte dos dados, e
este script so espelha o ultimo resultado no banco.

A importacao e **idempotente**: a identidade da vaga e o par (source,
external_id), entao rodar de novo atualiza as linhas existentes em vez de
duplicar.
"""

from __future__ import annotations

import argparse
import csv
from contextlib import closing
import glob
import logging
import sys
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api import vocabulary  # noqa: E402
from api.database import (  # noqa: E402
    Base,
    database_url,
    make_engine,
    url_sem_senha,
)
from api.dates import parse_published_date, reference_date_from_csv  # noqa: E402
from api.models import Tecnologia, Vaga  # noqa: E402
from api.migrations import migrate_connection  # noqa: E402
from scraper.classifier import default_classifier  # noqa: E402
from scraper.consolidation import (  # noqa: E402
    MIN_DATA_CORTE, canonical_company as _canonical_company, consolidate_description,
)
from scraper.config import PROJECT_ROOT  # noqa: E402
from scraper.geo import default_geo_classifier  # noqa: E402
from scraper.models import infer_linkedin_workplace, infer_workplace  # noqa: E402
from scraper.skills import default_extractor  # noqa: E402


logger = logging.getLogger("import_csv")

# Campos copiados direto do CSV. `title` e `area` ficam de fora porque sao
# obrigatorios e recebem tratamento proprio (nao podem virar None).
CAMPOS_TEXTO = [
    "company", "seniority", "location", "workplace_type",
    "url", "description", "area_matches", "search_term",
    "regiao", "polo",
]

def _data_iso(valor: str) -> date:
    """Valida --referencia no formato AAAA-MM-DD."""
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Data inválida: {valor!r}. Use o formato AAAA-MM-DD."
        ) from None


def csv_mais_recente(output_dir: Path) -> Path:
    encontrados = sorted(glob.glob(str(output_dir / "vagas_*.csv")))
    if not encontrados:
        raise SystemExit(
            f"Nenhum CSV de vagas em {output_dir}. Rode `python main.py` primeiro."
        )
    return Path(encontrados[-1])


def semear_tecnologias(db: Session) -> dict[str, Tecnologia]:
    """Garante uma linha para cada tecnologia de skills.yml."""
    existentes = {t.nome: t for t in db.scalars(select(Tecnologia))}
    for nome, grupo in vocabulary.technologies().items():
        atual = existentes.get(nome)
        if atual is None:
            atual = Tecnologia(nome=nome, grupo=grupo)
            db.add(atual)
            existentes[nome] = atual
        elif atual.grupo != grupo:
            atual.grupo = grupo
    db.flush()
    return existentes


def _float_ou_none(valor: str | None) -> float | None:
    try:
        return float(valor) if valor not in (None, "") else None
    except ValueError:
        return None


def _bool_csv(valor: str | None) -> bool:
    return (valor or "").strip().lower() in {"1", "true", "sim", "yes"}


def _garantir_colunas(engine) -> None:
    with closing(engine.raw_connection()) as conn:
        migrate_connection(conn.driver_connection)


def ler_csv(csv_path: Path):
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        yield from csv.DictReader(fh)


def importar(
    csv_path: Path,
    db_path: Path | str | None = None,
    recriar: bool = False,
    referencia: date | None = None,
    data_minima: date | None = MIN_DATA_CORTE,
) -> dict:
    engine = make_engine(db_path)
    try:
        return _importar_com_engine(engine, csv_path, db_path, recriar, referencia, data_minima)
    finally:
        engine.dispose()


def _importar_com_engine(engine, csv_path, db_path, recriar, referencia, data_minima) -> dict:
    if recriar:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    _garantir_colunas(engine)

    if referencia is None:
        referencia = reference_date_from_csv(csv_path)
    logger.info("Data de referência do CSV: %s", referencia)

    limite_data = data_minima if (referencia is None or referencia >= MIN_DATA_CORTE) else None

    criadas = atualizadas = sem_data = nao_tech = 0

    clf = default_classifier()
    geo = default_geo_classifier()
    skill_extractor = default_extractor()
    valid_areas = set(vocabulary.areas())

    lote_seen_ids: set[tuple[str, str]] = set()

    with Session(engine) as db:
        tecnologias = semear_tecnologias(db)
        conhecidas = {n.lower(): t for n, t in tecnologias.items()}

        with open(csv_path, encoding="utf-8-sig", newline="") as fh:
            for linha in csv.DictReader(fh):
                source = (linha.get("source") or "").strip()
                external_id = (linha.get("external_id") or "").strip()
                if not source or not external_id or not (linha.get("title") or "").strip():
                    continue

                if (source, external_id) in lote_seen_ids:
                    continue
                lote_seen_ids.add((source, external_id))

                if not clf.is_tech(linha.get("title") or "", linha.get("description") or ""):
                    nao_tech += 1
                    continue

                pub_date = parse_published_date(
                    linha.get("published_date"), referencia
                )
                if limite_data and pub_date is not None and pub_date < limite_data:
                    continue

                vaga = db.scalar(
                    select(Vaga).where(
                        Vaga.source == source, Vaga.external_id == external_id
                    )
                )


                if vaga is None:
                    vaga = Vaga(source=source, external_id=external_id)
                    # Restaura o id persistido no seed (coluna db_id);
                    # so vale na CRIACAO -- atualizacao nunca troca id.
                    db_id = (linha.get("db_id") or "").strip()
                    if db_id.isdigit() and int(db_id) > 0:
                        if db.get(Vaga, int(db_id)) is None:
                            vaga.id = int(db_id)
                    db.add(vaga)
                    criadas += 1
                else:
                    atualizadas += 1


                # Linha da rodada sem descricao nao pode apagar uma
                # descricao ja salva (pipeline --no-enrich deixa o campo
                # vazio para vagas do LinkedIn).
                descricao_preservada = False
                for campo in CAMPOS_TEXTO:
                    novo = (linha.get(campo) or "").strip() or None
                    if campo == "company" and novo:
                        novo = _canonical_company(novo) or None
                        # Cards incompletos do LinkedIn podem devolver apenas
                        # uma letra no lugar da empresa. Esse valor nao pode
                        # apagar um nome valido que ja esteja consolidado.
                        if novo is None and vaga.company:
                            continue
                    # Slug de URL como empresa (ex.: GeekHunter grava o
                    # segmento do caminho) nao regride um nome real ja
                    # corrigido pelo enriquecimento ("Code Group").
                    if (
                        campo == "company"
                        and novo
                        and "-" in novo
                        and " " not in novo
                        and novo == novo.lower()
                        and vaga.company
                        and " " in vaga.company
                    ):
                        continue
                    # Snippet novo nao regride descricao enriquecida: o
                    # card do Vagas.com traz ~400 chars (com ou sem "...").
                    if campo == "description":
                        decision = consolidate_description(vaga.description, novo)
                        descricao_preservada = decision.preserved
                        novo = decision.text or None
                    setattr(vaga, campo, novo)

                # Marcacao de anúncio encerrado so liga, nunca desliga:
                # o CSV da rodada nao traz o campo, e um 404 nao reabre.
                if (linha.get("enrich_encerrada") or "").strip() in ("1", "true", "True"):
                    vaga.enrich_encerrada = True

                workplace_declared = linha.get("workplace_declared")
                if workplace_declared not in (None, ""):
                    vaga.workplace_declared = _bool_csv(workplace_declared)

                vaga.title = (linha.get("title") or "").strip()

                area_csv = (linha.get("area") or "").strip()
                if not area_csv or area_csv not in valid_areas or area_csv == "Outros/TI Geral":
                    # Nao deixa uma linha SEM descricao rebaixar uma area ja
                    # bem classificada: o pipeline roda com --no-enrich, entao
                    # o CSV da rodada traz area de fallback (so titulo) para
                    # vagas do LinkedIn. A area boa fica; quando houver
                    # descricao, a reclassificacao pode corrigir para melhor.
                    ja_tem_area_valida = (
                        vaga.area in valid_areas and vaga.area != "Outros/TI Geral"
                    )
                    if ja_tem_area_valida and not (vaga.description or "").strip():
                        pass
                    else:
                        classified = clf.classify(vaga.title, vaga.description or "")
                        vaga.area = classified.area
                        vaga.area_score = classified.score
                        vaga.area_matches = ", ".join(classified.matches)
                else:
                    vaga.area = area_csv
                    vaga.area_score = _float_ou_none(linha.get("area_score"))

                vaga.published_date = pub_date
                if vaga.published_date is None:
                    sem_data += 1


                if vaga.source == "linkedin":
                    vaga.workplace_type = infer_linkedin_workplace(
                        vaga.workplace_type,
                        vaga.workplace_declared,
                        location=vaga.location,
                        title=vaga.title,
                        description=vaga.description,
                    )
                else:
                    vaga.workplace_type = infer_workplace(
                        vaga.workplace_type,
                        location=vaga.location,
                        title=vaga.title,
                        description=vaga.description,
                    )
                if not vaga.regiao or vaga.regiao == "Não informado":
                    polo, regiao = geo.classify(vaga.location, vaga.workplace_type)
                    vaga.polo = polo
                    vaga.regiao = regiao

                nomes_csv = [
                    n.strip() for n in (linha.get("skills") or "").split(",") if n.strip()
                ]
                nomes_extraidos = (
                    skill_extractor.extract(vaga.title, vaga.description or "")
                    if descricao_preservada
                    else []
                )
                nomes = sorted(set(nomes_csv) | set(nomes_extraidos))
                if nomes:
                    # O CSV pode vir de um card resumido. As skills precisam
                    # considerar a descricao FINAL preservada acima; usar so
                    # a lista parcial da rodada apagava vinculos validos como
                    # Node-RED e n8n. Skills encontradas antes do truncamento
                    # do CSV tambem sao mantidas por meio de nomes_csv.
                    #
                    # Sem descricao e sem skills novas, nao ha evidencia para
                    # substituir os vinculos acumulados pelo enriquecimento.
                    # Sincronizacao por SQL direto: o diff de colecao do ORM
                    # inseriu pares repetidos em vaga_tecnologia e derrubou
                    # a rodada de 06/09 com UNIQUE. DELETE + INSERT OR IGNORE
                    # nao pode duplicar.
                    ids_novas = [
                        conhecidas[n.lower()].id
                        for n in nomes
                        if n.lower() in conhecidas
                    ]
                    if not ids_novas:
                        continue  # nomes desconhecidos nao invalidam as relacoes existentes
                    db.flush()  # garante o id da vaga recem-criada
                    vid = vaga.id
                    db.execute(
                        text("DELETE FROM vaga_tecnologia WHERE vaga_id = :vid"),
                        {"vid": vid},
                    )
                    for tid in ids_novas:
                        db.execute(
                            text(
                                "INSERT OR IGNORE INTO vaga_tecnologia "
                                "(vaga_id, tecnologia_id) VALUES (:vid, :tid)"
                            ),
                            {"vid": vid, "tid": tid},
                        )

        if limite_data:
            from sqlalchemy import delete
            db.execute(delete(Vaga).where(Vaga.published_date < limite_data))


        todas_vagas = db.scalars(select(Vaga)).all()
        for v in todas_vagas:
            if v.company:
                v.company = _canonical_company(v.company)

            # A label oficial do LinkedIn e autoridade. Sem ela, apenas texto
            # explicito pode definir a modalidade; uma cidade nao prova que a
            # vaga seja presencial.
            if v.source == "linkedin":
                reavaliada = infer_linkedin_workplace(
                    v.workplace_type,
                    v.workplace_declared,
                    location=v.location,
                    title=v.title,
                    description=v.description,
                )
                if reavaliada != v.workplace_type:
                    v.workplace_type = reavaliada
                    v.polo, v.regiao = geo.classify(v.location, reavaliada)

            if not v.workplace_type or v.workplace_type == "Não informado":
                v.workplace_type = infer_workplace(
                    v.workplace_type,
                    location=v.location,
                    title=v.title,
                    description=v.description,
                    source=v.source,
                )

            if not v.regiao or v.regiao == "Não informado":
                polo, regiao = geo.classify(v.location, v.workplace_type)
                v.polo = polo
                v.regiao = regiao


        db.commit()

        total_vagas = db.scalar(select(func.count()).select_from(Vaga)) or 0

    return {
        "csv": csv_path.name,
        "referencia": referencia,
        "criadas": criadas,
        "atualizadas": atualizadas,
        "sem_data": sem_data,
        "nao_tech": nao_tech,
        "total": total_vagas,
        "db": url_sem_senha(database_url(db_path)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Importa o CSV de vagas do scraper para o SQLite.",
    )
    parser.add_argument("--csv", type=Path, default=None,
                        help="CSV a importar (padrão: o mais recente em output/).")
    parser.add_argument(
        "--db", default=None, metavar="DESTINO",
        help="Banco de destino: caminho de arquivo SQLite. "
             "Padrão: DATABASE_URL, ou data/vagas.db.",
    )
    parser.add_argument("--recriar", action="store_true",
                        help="Apaga e recria as tabelas antes de importar.")
    parser.add_argument(
        "--referencia", type=_data_iso, default=None, metavar="AAAA-MM-DD",
        help=(
            "Data da coleta, usada para resolver datas relativas "
            "('Ontem', 'Há 3 dias'). Padrão: o timestamp no nome do arquivo. "
            "Fixe este valor ao importar um snapshot versionado."
        ),
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)-7s %(message)s", stream=sys.stdout
    )

    csv_path = args.csv or csv_mais_recente(PROJECT_ROOT / "output")
    resultado = importar(
        csv_path, args.db, recriar=args.recriar, referencia=args.referencia
    )

    print()
    print(f"  CSV .............. {resultado['csv']}")
    print(f"  Data de referência {resultado['referencia']}")
    print(f"  Criadas .......... {resultado['criadas']}")
    print(f"  Atualizadas ...... {resultado['atualizadas']}")
    print(f"  Sem data ......... {resultado['sem_data']}")
    print(f"  Fora do escopo ... {resultado['nao_tech']}")
    print(f"  Total no banco ... {resultado['total']}")
    print(f"  Banco ............ {resultado['db']}")

    return 0


if __name__ == "__main__":

    raise SystemExit(main())
