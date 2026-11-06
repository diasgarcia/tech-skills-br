"""Exporta o snapshot SQLite para o Parquet compartilhado pelos publicadores."""

from __future__ import annotations

import argparse
import logging
import sys
from contextlib import closing
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.database import connect_sqlite, resolve_sqlite_path
from api.snapshots import sha256

EXPORT_DIR = PROJECT_ROOT / "kaggle"
PARQUET_NAME = "vagas.parquet"
logger = logging.getLogger(__name__)

CATEGORICAL_COLUMNS = (
    "source",
    "area",
    "seniority",
    "workplace_type",
    "regiao",
)

ARQUIVOS_PARQUET_OBSOLETOS = (
    "tecnologias.parquet",
    "vaga_tecnologia.parquet",
    "analise_skills.parquet",
)

def _converter_data(df: pd.DataFrame, column: str = "published_date") -> None:
    """Converte uma data ISO do SQLite para date32 na gravacao Parquet."""
    df[column] = pd.to_datetime(df[column], errors="coerce").dt.date


def _categorizar(df: pd.DataFrame, columns: tuple[str, ...]) -> None:
    """Usa dictionary encoding nos vocabularios controlados."""
    for column in columns:
        df[column] = df[column].astype("category")


def _aplicar_tipos_vagas(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica tipos semanticos ao arquivo principal de vagas."""
    df = df.copy()

    # O SQLite devolve DATE como texto ISO e BOOLEAN como 0/1. Sem estas
    # conversoes, o Parquet replica esses tipos de armazenamento em vez dos
    # tipos reais dos dados.
    _converter_data(df)
    df["enrich_encerrada"] = df["enrich_encerrada"].astype("boolean")

    # Campos de vocabulario controlado sao gravados com codificacao dictionary
    # no Parquet. Isso preserva os rotulos e evita impor um ENUM rigido.
    _categorizar(df, CATEGORICAL_COLUMNS)

    return df


def exportar(
    db_path: Path | str | None = None,
    export_dir: Path = EXPORT_DIR,
) -> tuple[Path, int]:
    """Exporta uma linha por vaga para o Parquet do dataset."""
    with closing(connect_sqlite(db_path, read_only=True)) as conn:
        vagas = pd.read_sql_query(
            """
            SELECT v.source, v.external_id, v.title, v.company,
                   (SELECT GROUP_CONCAT(nome, '; ')
                      FROM (
                           SELECT t.nome AS nome
                             FROM vaga_tecnologia vt
                             JOIN tecnologias t ON t.id = vt.tecnologia_id
                            WHERE vt.vaga_id = v.id
                            ORDER BY t.nome COLLATE NOCASE
                      )) AS skills,
                   v.area, v.seniority, v.workplace_type, v.location,
                   v.regiao, v.polo, v.published_date, v.description, v.url,
                   v.search_term, v.enrich_encerrada
              FROM vagas v
             ORDER BY v.id
            """,
            conn,
        )

    vagas = _aplicar_tipos_vagas(vagas)

    export_dir.mkdir(parents=True, exist_ok=True)
    for nome in ARQUIVOS_PARQUET_OBSOLETOS:
        (export_dir / nome).unlink(missing_ok=True)

    caminho = export_dir / PARQUET_NAME
    vagas.to_parquet(caminho, index=False)
    logger.info("Parquet exportado: %d vagas em %s", len(vagas), caminho)

    return caminho, len(vagas)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="Arquivo SQLite; respeita DATABASE_URL e VAGAS_DB.")
    parser.add_argument("--output-dir", type=Path, default=EXPORT_DIR)
    args = parser.parse_args()
    logger.info("Banco selecionado: %s", resolve_sqlite_path(args.db))
    path, _ = exportar(args.db, args.output_dir)
    logger.info("Parquet SHA-256: %s", sha256(path))
