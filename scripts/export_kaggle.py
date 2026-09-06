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
HANDLE = "rafaeldiasgarcia/tech-skills-br"

logger = logging.getLogger(__name__)


def exportar() -> tuple[Path, int]:
    """Grava kaggle/vagas.parquet a partir do banco. Devolve (caminho, n de vagas)."""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        """
        SELECT v.source, v.external_id, v.title, v.company,
               (SELECT GROUP_CONCAT(t.nome, '; ')
                  FROM vaga_tecnologia vt
                  JOIN tecnologias t ON t.id = vt.tecnologia_id
                 WHERE vt.vaga_id = v.id) AS skills,
               v.area, v.seniority, v.workplace_type, v.location,
               v.regiao, v.polo, v.published_date, v.description, v.url,
               v.search_term, v.enrich_encerrada
          FROM vagas v
        """,
        conn,
    )
    conn.close()
    EXPORT_DIR.mkdir(exist_ok=True)
    caminho = EXPORT_DIR / "vagas.parquet"
    df.to_parquet(caminho, index=False)
    logger.info("Parquet exportado: %d vagas em %s", len(df), caminho)
    return caminho, len(df)


def _nota_padrao(n_vagas: int) -> str:
    data = os.getenv("DATA_HOJE") or date.today().strftime("%d/%m/%Y")
    rodada = (os.getenv("RODADA") or "").strip() or "manual"
    horarios = {"1": "09:16 BRT", "2": "14:16 BRT", "3": "19:16 BRT"}
    sufixo = horarios.get(rodada, "manual")
    return f"Coleta {data} · rodada {rodada} ({sufixo}) · {n_vagas} vagas"


def subir(notas: str | None = None) -> None:
    if not os.getenv("KAGGLE_API_TOKEN"):
        raise SystemExit("KAGGLE_API_TOKEN nao definido no ambiente")

    _, n_vagas = exportar()
    import kagglehub

    notas = notas or _nota_padrao(n_vagas)
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
