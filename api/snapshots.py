"""Identificacao e verificacao local dos artefatos de uma mesma publicacao."""

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from api.database import connect_sqlite

ARTIFACT_NAMES = ("vagas.db", "vagas.csv")
MANIFEST_NAME = "snapshot.json"


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_sha256(value: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError("Identificador SHA-256 invalido.")
    return value


def validate_database(path: Path) -> None:
    with closing(connect_sqlite(path, read_only=True)) as conn:
        if conn.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise ValueError("Snapshot SQLite com falha de integridade.")
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Snapshot SQLite com relacoes orfas.")


def build_manifest(directory: Path, parent_sha256: str) -> dict:
    validate_sha256(parent_sha256)
    validate_database(directory / "vagas.db")
    artifacts = {name: sha256(directory / name) for name in ARTIFACT_NAMES}
    return {
        "schema_version": 1,
        "snapshot_id": artifacts["vagas.db"],
        "parent_sha256": parent_sha256,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": artifacts,
    }


def verify_manifest(directory: Path) -> dict:
    manifest = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("Versao de manifesto nao suportada.")
    validate_sha256(manifest.get("parent_sha256"))
    expected = manifest.get("artifacts", {})
    if not isinstance(expected, dict) or set(expected) != set(ARTIFACT_NAMES):
        raise ValueError("Manifesto deve identificar vagas.db e vagas.csv.")
    for name in ARTIFACT_NAMES:
        validate_sha256(expected[name])
        if sha256(directory / name) != expected[name]:
            raise ValueError(f"Snapshot inconsistente: hash divergente de {name}.")
    if manifest.get("snapshot_id") != expected["vagas.db"]:
        raise ValueError("Identificador do snapshot nao corresponde ao banco.")
    validate_database(directory / "vagas.db")
    return manifest


def assert_current_parent(expected: str, current: str) -> None:
    validate_sha256(expected)
    validate_sha256(current)
    if expected != current:
        raise ValueError(
            "A release mudou desde o download. Publicacao recusada; "
            "baixe a base atual e consolide os resultados novamente."
        )
