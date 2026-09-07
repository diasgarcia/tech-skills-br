"""Exporta a base para Parquet e sobe no Kaggle (dataset tech-skills-br).

Uso:
    python scripts/export_kaggle.py

Requisitos:
- KAGGLE_API_TOKEN no ambiente (secret do repo).
- pacotes pandas, pyarrow e kagglehub (instalados pelo workflow).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import subprocess
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "vagas.db"
EXPORT_DIR = PROJECT_ROOT / "kaggle"
HANDLE = "rafaeldiasgarcia/tech-skills-br"

# Metadata completo do dataset. O upload de versao via kagglehub LIMPA as
# keywords (tags) do dataset, entao todo envio reaplica este arquivo depois
# via `kaggle datasets metadata --update`. Formato das keywords: minusculas
# com espaco (slug e rejeitado). O titulo e obrigatorio no update (6-50).
METADATA = {
    "title": "tech-skills-br",
    "id": HANDLE,
    "subtitle": "Base diaria de vagas de entrada em tecnologia no Brasil.",
    "description": (
        "Esta base registra vagas de entrada em tecnologia no Brasil. Ela "
        "cobre os niveis junior, estagio, trainee e aprendiz. A coleta usa "
        "nove portais publicos brasileiros. Cada registro tem titulo, "
        "empresa, local, modalidade, senioridade, area e tecnologias. A base "
        "e atualizada tres vezes por dia. Ela apoia a pesquisa PIBIC/CNPq "
        "'Mapeamento de Skills em Tecnologia no Brasil'. Codigo e "
        "metodologia: https://github.com/diasgarcia/tech-skills-br "
        "— Dashboard: https://diasgarcia.github.io/tech-skills-br/"
    ),
    "licenses": [{"name": "MIT"}],
    "keywords": [
        "jobs and career",
        "science and technology",
        "brazil",
        "education",
        "research",
    ],
    "expectedUpdateFrequency": "daily",
    "userSpecifiedSources": (
        "Os dados sao coletados automaticamente de nove portais publicos de "
        "empregos no Brasil: LinkedIn, Gupy, Solides, InfoJobs, Vagas.com, "
        "GeekHunter, Abler, Recrutei e Trampos. A coleta roda tres vezes por "
        "dia (09:16, 14:16 e 19:16, horario de Brasilia) e mantem apenas "
        "vagas de nivel de entrada: junior, estagio, trainee e aprendiz."
    ),
}

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


def _reaplicar_metadata() -> None:
    """Reaplica keywords e demais metadados apos o upload da versao.

    O `kagglehub.dataset_upload` zera as keywords do dataset (comprovado em
    07/09: tags sumiam toda vez que a rodada subia uma versao). A CLI oficial
    `kaggle datasets metadata --update` restaura tudo a partir do METADATA.
    """
    with tempfile.TemporaryDirectory() as tmp:
        caminho = Path(tmp) / "dataset-metadata.json"
        caminho.write_text(
            json.dumps(METADATA, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        resultado = subprocess.run(
            [
                "kaggle", "datasets", "metadata", HANDLE,
                "-p", str(Path(tmp)), "--update",
            ],
            capture_output=True,
            text=True,
        )
        if resultado.returncode != 0:
            logger.warning(
                "Reaplicacao de metadata falhou (%s): %s",
                resultado.returncode, resultado.stderr.strip(),
            )
        else:
            logger.info("Metadata reaplicado (tags preservadas): %s", HANDLE)


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

    _reaplicar_metadata()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
    subir()
