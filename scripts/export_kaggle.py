"""Exporta a base para Parquet e sobe no Kaggle (dataset tech-skills-br).

Uso:
    python scripts/export_kaggle.py

Requisitos:
- KAGGLE_API_TOKEN no ambiente (secret do repo).
- pacotes pandas, pyarrow e kagglehub (instalados pelo workflow).
"""

from __future__ import annotations

import json
import argparse
import logging
import os
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.database import resolve_sqlite_path
from api.snapshots import sha256
from scripts.export_dataset import EXPORT_DIR, PARQUET_NAME, _aplicar_tipos_vagas, exportar

# Mantem os imports existentes de scripts e testes.
__all__ = ["_aplicar_tipos_vagas", "exportar", "subir"]
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
        "dez portais publicos brasileiros. Cada registro tem titulo, "
        "empresa, local, modalidade, senioridade, area e tecnologias. A base "
        "e atualizada tres vezes por dia.\n\n"
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
        "Os dados sao coletados automaticamente de dez portais publicos de "
        "empregos no Brasil: LinkedIn, Gupy, Solides, InfoJobs, Vagas.com, "
        "GeekHunter, Abler, Recrutei, Trampos e Jobbol. A coleta roda tres vezes por "
        "dia (09:16, 14:16 e 19:16, horario de Brasilia) e mantem apenas "
        "vagas de nivel de entrada: junior, estagio, trainee e aprendiz."
    ),
}

logger = logging.getLogger(__name__)

# Quando a conexao cai depois de enviar o Parquet, o Kaggle pode ter aceitado
# a versao e estar apenas processando o arquivo. Antes de tentar novo envio,
# consultamos a versao atual para nao criar duplicatas.
_ESPERAS_CONFIRMACAO = (0, 15, 30, 60, 120)


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
            timeout=120,
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
        timeout=60,
    )
    if resultado.returncode != 0:
        logger.warning("Nao foi possivel consultar o status do Kaggle: %s", resultado.stderr.strip())
        return None
    # O CLI escreve avisos de versao no stdout, mesmo com --format json.
    # Aceitar apenas os avisos iniciais; a resposta restante deve ser um JSON completo.
    linhas = resultado.stdout.strip().splitlines()
    while linhas and linhas[0].startswith("Warning:"):
        logger.warning("Aviso do CLI Kaggle: %s", linhas.pop(0))
    try:
        dados = json.loads("\n".join(linhas))
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


def _arquivo_confirmado(versao: int, expected_sha256: str) -> bool:
    import kagglehub

    try:
        with tempfile.TemporaryDirectory(prefix="tech-skills-kaggle-confirm-") as temporary:
            path = kagglehub.dataset_download(
                f"{HANDLE}/versions/{versao}", path="vagas.parquet",
                force_download=True, output_dir=temporary,
            )
            return sha256(Path(path)) == expected_sha256
    except Exception as exc:
        logger.warning("Nao foi possivel conferir o arquivo da versao %s: %s", versao, exc)
        return False


def _aguardar_confirmacao(versao_anterior: int | None, expected_sha256: str) -> bool:
    """Uma versao nova so confirma o envio se contem o mesmo Parquet."""
    if versao_anterior is None:
        logger.warning("Versao anterior indisponivel; nao ha como confirmar o upload com seguranca.")
        return False

    for espera in _ESPERAS_CONFIRMACAO:
        if espera:
            time.sleep(espera)
        try:
            status = _status_dataset()
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("Consulta ao Kaggle sem confirmacao: %s", exc)
            continue
        versao = _versao_atual(status)
        if versao is not None and versao > versao_anterior and _arquivo_confirmado(versao, expected_sha256):
            logger.info(
                "Kaggle confirmou a versao %d com o mesmo Parquet (status: %s).",
                versao,
                status.get("status", "desconhecido") if status else "desconhecido",
            )
            return True
    return False


def subir(
    notas: str | None = None,
    *,
    db_path: Path | str | None = None,
    export_dir: Path = EXPORT_DIR,
    usar_parquet_existente: bool = False,
) -> None:
    from scraper.config import _load_dotenv

    _load_dotenv()
    if not os.getenv("KAGGLE_API_TOKEN"):
        raise SystemExit("KAGGLE_API_TOKEN nao definido no ambiente")

    if usar_parquet_existente:
        from pyarrow.parquet import read_metadata

        path = export_dir / PARQUET_NAME
        n_vagas = read_metadata(path).num_rows
    else:
        path, n_vagas = exportar(db_path, export_dir)
    expected_sha256 = sha256(path)
    import kagglehub

    notas = (notas or _nota_padrao(n_vagas)) + f" · parquet sha256:{expected_sha256}"
    versao_anterior = _versao_atual(_status_dataset())
    if versao_anterior is None:
        raise RuntimeError("Status do Kaggle indisponivel; envio adiado para evitar uma versao sem confirmacao.")
    if _arquivo_confirmado(versao_anterior, expected_sha256):
        logger.info("O Kaggle ja contem este Parquet; nenhuma versao duplicada sera criada.")
        _reaplicar_metadata()
        return
    try:
        kagglehub.dataset_upload(
            handle=HANDLE,
            local_dataset_dir=str(export_dir),
            version_notes=notas,
        )
        logger.info("Versao enviada para o Kaggle: %s", HANDLE)
    except Exception as exc:
        logger.warning("Upload sem confirmacao (%s); aguardando o Kaggle processar a versao.", exc)
    if not _aguardar_confirmacao(versao_anterior, expected_sha256):
        raise RuntimeError("Kaggle nao confirmou o mesmo Parquet apos o upload.")

    _reaplicar_metadata()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="Arquivo SQLite; respeita DATABASE_URL e VAGAS_DB.")
    parser.add_argument("--output-dir", type=Path, default=EXPORT_DIR)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--export-only", action="store_true", help="Gera o Parquet local sem publicar.")
    mode.add_argument("--publish-only", action="store_true", help="Publica o Parquet ja exportado.")
    args = parser.parse_args()
    if not args.publish_only:
        logger.info("Banco selecionado: %s", resolve_sqlite_path(args.db))
    if args.export_only:
        exportar(args.db, args.output_dir)
    else:
        subir(db_path=args.db, export_dir=args.output_dir, usar_parquet_existente=args.publish_only)
