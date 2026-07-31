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
import sys
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api import vocabulary  # noqa: E402
from api.database import DEFAULT_DB_PATH, Base, make_engine  # noqa: E402
from api.dates import parse_published_date, reference_date_from_csv  # noqa: E402
from api.models import Tecnologia, Vaga  # noqa: E402
from scraper.config import PROJECT_ROOT  # noqa: E402

logger = logging.getLogger("import_csv")

# Campos copiados direto do CSV. `title` e `area` ficam de fora porque sao
# obrigatorios e recebem tratamento proprio (nao podem virar None).
CAMPOS_TEXTO = [
    "company", "seniority", "location", "workplace_type",
    "url", "description", "area_matches", "search_term",
]


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


def importar(csv_path: Path, db_path: Path, recriar: bool = False) -> dict:
    engine = make_engine(db_path)
    if recriar:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    # Datas relativas ("Ontem", "Há 3 dias") so fazem sentido contra a data em
    # que o CSV foi gerado -- nao contra hoje.
    referencia = reference_date_from_csv(csv_path)
    logger.info("Data de referência do CSV: %s", referencia)

    criadas = atualizadas = sem_data = 0

    with Session(engine) as db:
        tecnologias = semear_tecnologias(db)
        conhecidas = {n.lower(): t for n, t in tecnologias.items()}

        with open(csv_path, encoding="utf-8-sig", newline="") as fh:
            for linha in csv.DictReader(fh):
                source = (linha.get("source") or "").strip()
                external_id = (linha.get("external_id") or "").strip()
                if not source or not external_id or not (linha.get("title") or "").strip():
                    continue

                vaga = db.scalar(
                    select(Vaga).where(
                        Vaga.source == source, Vaga.external_id == external_id
                    )
                )
                if vaga is None:
                    vaga = Vaga(source=source, external_id=external_id)
                    db.add(vaga)
                    criadas += 1
                else:
                    atualizadas += 1

                for campo in CAMPOS_TEXTO:
                    setattr(vaga, campo, (linha.get(campo) or "").strip() or None)

                vaga.title = (linha.get("title") or "").strip()
                vaga.area = (linha.get("area") or "").strip() or "Outros/TI Geral"
                vaga.area_score = _float_ou_none(linha.get("area_score"))
                vaga.published_date = parse_published_date(
                    linha.get("published_date"), referencia
                )
                if vaga.published_date is None:
                    sem_data += 1

                nomes = [
                    n.strip() for n in (linha.get("skills") or "").split(",") if n.strip()
                ]
                vaga.tecnologias = [
                    conhecidas[n.lower()] for n in nomes if n.lower() in conhecidas
                ]

        db.commit()
        total_vagas = db.scalar(select(func.count()).select_from(Vaga)) or 0

    return {
        "csv": csv_path.name,
        "referencia": referencia,
        "criadas": criadas,
        "atualizadas": atualizadas,
        "sem_data": sem_data,
        "total": total_vagas,
        "db": db_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Importa o CSV de vagas do scraper para o SQLite.",
    )
    parser.add_argument("--csv", type=Path, default=None,
                        help="CSV a importar (padrão: o mais recente em output/).")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH,
                        help=f"Banco de destino (padrão: {DEFAULT_DB_PATH}).")
    parser.add_argument("--recriar", action="store_true",
                        help="Apaga e recria as tabelas antes de importar.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)-7s %(message)s", stream=sys.stdout
    )

    csv_path = args.csv or csv_mais_recente(PROJECT_ROOT / "output")
    resultado = importar(csv_path, args.db, recriar=args.recriar)

    print()
    print(f"  CSV .............. {resultado['csv']}")
    print(f"  Data de referência {resultado['referencia']}")
    print(f"  Criadas .......... {resultado['criadas']}")
    print(f"  Atualizadas ...... {resultado['atualizadas']}")
    print(f"  Sem data ......... {resultado['sem_data']}")
    print(f"  Total no banco ... {resultado['total']}")
    print(f"  Banco ............ {resultado['db']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
