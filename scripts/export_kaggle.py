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
import time
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
        "'Mapeamento de Skills em Tecnologia no Brasil'.\n\n"
        "Codigo e metodologia: https://github.com/diasgarcia/tech-skills-br  \n\n"
        "Dashboard: https://diasgarcia.github.io/tech-skills-br/"
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

CATEGORICAL_VAGAS = (
    "source",
    "area",
    "seniority",
    "workplace_type",
    "regiao",
)

CATEGORICAL_ANALISE = (
    "skill",
    "categoria_skill",
    *CATEGORICAL_VAGAS,
)

# Quando a conexao cai depois de enviar o Parquet, o Kaggle pode ter aceitado
# a versao e estar apenas processando o arquivo. Antes de tentar novo envio,
# consultamos a versao atual para nao criar duplicatas.
_ESPERAS_CONFIRMACAO = (0, 15, 30, 60, 120)


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
    _categorizar(df, CATEGORICAL_VAGAS)

    return df


def _aplicar_tipos_analise(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica tipos semanticos a visao desnormalizada de skills."""
    df = df.copy()
    _converter_data(df)
    _categorizar(df, CATEGORICAL_ANALISE)

    return df


def exportar(
    db_path: Path = DB_PATH,
    export_dir: Path = EXPORT_DIR,
) -> tuple[Path, int]:
    """Exporta as tres tabelas do SQLite e uma visao analitica para o Kaggle."""
    conn = sqlite3.connect(db_path)
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
               v.search_term, v.enrich_encerrada, v.id
          FROM vagas v
         ORDER BY v.id
        """,
        conn,
    )
    tecnologias = pd.read_sql_query(
        """
        SELECT id, nome, grupo
          FROM tecnologias
         ORDER BY id
        """,
        conn,
    )
    relacionamentos = pd.read_sql_query(
        """
        SELECT vaga_id, tecnologia_id
          FROM vaga_tecnologia
         ORDER BY vaga_id, tecnologia_id
        """,
        conn,
    )
    analise = pd.read_sql_query(
        """
        SELECT t.nome AS skill, t.grupo AS categoria_skill,
               v.source, v.area, v.seniority, v.workplace_type,
               v.regiao, v.polo, v.published_date, v.company, v.title,
               v.search_term, v.id AS vaga_id, t.id AS tecnologia_id,
               v.external_id, v.url
          FROM vaga_tecnologia vt
          JOIN vagas v ON v.id = vt.vaga_id
          JOIN tecnologias t ON t.id = vt.tecnologia_id
         ORDER BY t.nome COLLATE NOCASE, v.id
        """,
        conn,
    )
    conn.close()

    vagas = _aplicar_tipos_vagas(vagas)
    tecnologias["grupo"] = tecnologias["grupo"].astype("category")
    analise = _aplicar_tipos_analise(analise)

    export_dir.mkdir(exist_ok=True)
    arquivos = {
        "vagas": (vagas, export_dir / "vagas.parquet"),
        "tecnologias": (tecnologias, export_dir / "tecnologias.parquet"),
        "vaga_tecnologia": (
            relacionamentos,
            export_dir / "vaga_tecnologia.parquet",
        ),
        "analise_skills": (analise, export_dir / "analise_skills.parquet"),
    }
    for nome, (dados, caminho) in arquivos.items():
        dados.to_parquet(caminho, index=False)
        logger.info("Parquet %s exportado: %d linhas em %s", nome, len(dados), caminho)

    return arquivos["vagas"][1], len(vagas)


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


def _status_dataset() -> dict[str, object] | None:
    """Le o estado e a versao atual pelo CLI oficial do Kaggle."""
    resultado = subprocess.run(
        ["kaggle", "datasets", "status", HANDLE, "--format", "json"],
        capture_output=True,
        text=True,
    )
    if resultado.returncode != 0:
        logger.warning("Nao foi possivel consultar o status do Kaggle: %s", resultado.stderr.strip())
        return None
    try:
        dados = json.loads(resultado.stdout)
    except json.JSONDecodeError:
        logger.warning("Status do Kaggle nao retornou JSON valido: %s", resultado.stdout.strip())
        return None
    return dados if isinstance(dados, dict) else None


def _versao_atual(status: dict[str, object] | None) -> int | None:
    if not status:
        return None
    try:
        return int(status["current_version_number"])
    except (KeyError, TypeError, ValueError):
        return None


def _aguardar_confirmacao(versao_anterior: int | None) -> bool:
    """Confirma se uma versao nova apareceu apos erro de conexao."""
    if versao_anterior is None:
        logger.warning("Versao anterior indisponivel; nao ha como confirmar o upload com seguranca.")
        return False

    for espera in _ESPERAS_CONFIRMACAO:
        if espera:
            time.sleep(espera)
        status = _status_dataset()
        versao = _versao_atual(status)
        if versao is not None and versao > versao_anterior:
            logger.info(
                "Kaggle confirmou a versao %d apos erro de conexao (status: %s).",
                versao,
                status.get("status", "desconhecido") if status else "desconhecido",
            )
            return True
    return False


def subir(notas: str | None = None) -> None:
    if not os.getenv("KAGGLE_API_TOKEN"):
        raise SystemExit("KAGGLE_API_TOKEN nao definido no ambiente")

    _, n_vagas = exportar()
    import kagglehub

    notas = notas or _nota_padrao(n_vagas)
    versao_anterior = _versao_atual(_status_dataset())
    try:
        kagglehub.dataset_upload(
            handle=HANDLE,
            local_dataset_dir=str(EXPORT_DIR),
            version_notes=notas,
        )
        logger.info("Versao enviada para o Kaggle: %s", HANDLE)
    except Exception as exc:
        logger.warning("Upload sem confirmacao (%s); aguardando o Kaggle processar a versao.", exc)
        if not _aguardar_confirmacao(versao_anterior):
            raise RuntimeError("Kaggle nao confirmou uma nova versao apos o upload.") from exc

    _reaplicar_metadata()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
    subir()
