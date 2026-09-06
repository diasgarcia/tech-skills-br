"""Exporta a base para Parquet e sobe no Kaggle (dataset tech-skills-br).

Uso:
    python scripts/export_kaggle.py

Requisitos:
- KAGGLE_API_TOKEN no ambiente (secret do repo).
- pacotes pandas, pyarrow e kagglehub (instalados pelo workflow).
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "vagas.db"
EXPORT_DIR = PROJECT_ROOT / "kaggle"
HANDLE = "diasgarcia/tech-skills-br"

logger = logging.getLogger(__name__)


def exportar() -> Path:
    """Grava kaggle/vagas.parquet a partir do banco."""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        """
        SELECT v.source, v.external_id, v.title, v.company, v.location,
               v.workplace_type, v.published_date, v.url, v.description,
               v.area, v.seniority, v.regiao, v.polo, v.search_term,
               v.enrich_encerrada,
               (SELECT GROUP_CONCAT(t.nome, '; ')
                  FROM vaga_tecnologia vt
                  JOIN tecnologias t ON t.id = vt.tecnologia_id
                 WHERE vt.vaga_id = v.id) AS skills
          FROM vagas v
        """,
        conn,
    )
    conn.close()
    EXPORT_DIR.mkdir(exist_ok=True)
    caminho = EXPORT_DIR / "vagas.parquet"
    df.to_parquet(caminho, index=False)
    logger.info("Parquet exportado: %d vagas em %s", len(df), caminho)
    return caminho


def subir(notas: str | None = None) -> None:
    if not os.getenv("KAGGLE_API_TOKEN"):
        raise SystemExit("KAGGLE_API_TOKEN nao definido no ambiente")

    exportar()
    import kagglehub

    notas = notas or f"Snapshot de {date.today().isoformat()}"
    try:
        kagglehub.dataset_upload(
            handle=HANDLE,
            local_dataset_dir=str(EXPORT_DIR),
            version_notes=notas,
        )
        logger.info("Versao enviada para o Kaggle: %s", HANDLE)
    except Exception as exc:
        logger.warning("Upload falhou (%s); tentando criar o dataset", exc)
        dono, slug = HANDLE.split("/")
        kagglehub.dataset_create(
            owner_slug=dono,
            dataset_slug=slug,
            files=[str(EXPORT_DIR / "vagas.parquet")],
            license_name="MIT",
        )
        kagglehub.dataset_upload(
            handle=HANDLE,
            local_dataset_dir=str(EXPORT_DIR),
            version_notes=notas,
        )
        logger.info("Dataset criado e versao enviada: %s", HANDLE)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
    subir()
