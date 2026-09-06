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
import glob
import logging
import re
import sys
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import func, select
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
from scraper.classifier import default_classifier  # noqa: E402
from scraper.config import PROJECT_ROOT  # noqa: E402
from scraper.geo import default_geo_classifier  # noqa: E402
from scraper.models import infer_workplace, normalize  # noqa: E402


logger = logging.getLogger("import_csv")

# Campos copiados direto do CSV. `title` e `area` ficam de fora porque sao
# obrigatorios e recebem tratamento proprio (nao podem virar None).
CAMPOS_TEXTO = [
    "company", "seniority", "location", "workplace_type",
    "url", "description", "area_matches", "search_term",
    "regiao", "polo",
]

MIN_DATA_CORTE = date(2026, 1, 1)

# A mesma empresa com grafias diferentes entre portais. A chave e o
# nome normalizado; o valor e o rotulo canonico exibido no ranking.
_EMPRESAS_CANONICAS = {
    "randstad matriz": "Randstad",
    "nava tech for business": "Nava Technology for Business",
    "minsait brasil": "Minsait",
    "minsait an indra company": "Minsait",
}


def _canonical_company(nome: str) -> str:
    """Junta variantes de grafia de empresa numa forma unica.

    Cada portal grafa a mesma coisa do seu jeito: "Empresa confidencial"
    na Solides, "confidencial" no InfoJobs, "Confidencial430" na Gupy;
    "Randstad - Matriz" no InfoJobs e "Randstad" no GeekHunter. Sem a
    normalizacao, o ranking de empresas conta a mesma empresa como
    entidades diferentes.
    """
    chave = normalize(nome)
    if re.search(r"\bconfidencial\d*\b", chave):
        return "Confidencial"
    return _EMPRESAS_CANONICAS.get(chave, nome)




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


def _garantir_colunas(engine) -> None:
    """Garante que colunas novas (regiao, polo) existam em bancos pre-existentes."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "vagas" not in inspector.get_table_names():
        return
    cols = {col["name"] for col in inspector.get_columns("vagas")}
    with engine.connect() as conn:
        if "regiao" not in cols:
            conn.execute(text("ALTER TABLE vagas ADD COLUMN regiao VARCHAR(40)"))
        if "polo" not in cols:
            conn.execute(text("ALTER TABLE vagas ADD COLUMN polo VARCHAR(60)"))
        if "enrich_encerrada" not in cols:
            conn.execute(
                text("ALTER TABLE vagas ADD COLUMN enrich_encerrada INTEGER DEFAULT 0")
            )
        conn.commit()


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

                url_csv = (linha.get("url") or "").strip()
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
                for campo in CAMPOS_TEXTO:
                    novo = (linha.get(campo) or "").strip() or None
                    if campo == "company" and novo:
                        novo = _canonical_company(novo)
                    if campo == "description" and not novo and vaga.description:
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
                    if campo == "description" and novo and vaga.description:
                        velha_cheia = (
                            len(vaga.description) >= 500
                            and not vaga.description.endswith("...")
                        )
                        nova_snippet = (
                            len(novo) < 500 or novo.endswith("...")
                        )
                        if velha_cheia and nova_snippet:
                            continue
                    setattr(vaga, campo, novo)

                # Marcacao de anúncio encerrado so liga, nunca desliga:
                # o CSV da rodada nao traz o campo, e um 404 nao reabre.
                if (linha.get("enrich_encerrada") or "").strip() in ("1", "true", "True"):
                    vaga.enrich_encerrada = True

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

                nomes = [
                    n.strip() for n in (linha.get("skills") or "").split(",") if n.strip()
                ]
                if nomes:
                    # Linha COM skills substitui as do banco. Linha SEM skills
                    # (ex.: LinkedIn re-coletado com --no-enrich, em que o card
                    # nao traz descricao) nao pode apagar as tecnologias ja
                    # acumuladas no banco pelo enriquecimento.
                    vaga.tecnologias = [
                        conhecidas[n.lower()] for n in nomes if n.lower() in conhecidas
                    ]

        if limite_data:
            from sqlalchemy import delete
            db.execute(delete(Vaga).where(Vaga.published_date < limite_data))


        todas_vagas = db.scalars(select(Vaga)).all()
        for v in todas_vagas:
            # No LinkedIn o card nao informa modalidade: o palpite feito na
            # coleta (cidade -> Presencial) pode contradizer a descricao
            # completa ("Modalidade 100% remota"). A descricao e autoridade.
            if v.source == "linkedin" and v.description:
                reavaliada = infer_workplace(
                    None, location=v.location, title=v.title,
                    description=v.description,
                )
                if reavaliada and reavaliada != "Não informado" and reavaliada != v.workplace_type:
                    v.workplace_type = reavaliada
                    v.polo, v.regiao = geo.classify(v.location, reavaliada)

            if not v.workplace_type or v.workplace_type == "Não informado":
                v.workplace_type = infer_workplace(
                    v.workplace_type,
                    location=v.location,
                    title=v.title,
                    description=v.description,
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

    try:
        from scripts.export_pages_data import export_all_pages_data
        export_all_pages_data()
    except Exception as exc:
        logging.warning(f"Nao foi possivel exportar endpoints estaticos do Pages: {exc}")

    return 0


if __name__ == "__main__":

    raise SystemExit(main())
