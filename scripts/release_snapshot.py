"""Baixa snapshots verificados e publica somente sobre a base de origem esperada.

A serializacao dos escritores e feita pelos workflows, em um grupo comum.
A verificacao de hash detecta base antiga, mas nao substitui uma trava remota.
"""

from __future__ import annotations

import argparse
from contextlib import closing
import json
import logging
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.database import connect_sqlite, resolve_sqlite_path
from api.snapshots import (
    ARTIFACT_NAMES, MANIFEST_NAME, assert_current_parent, build_manifest,
    sha256, validate_database, validate_sha256, verify_manifest,
)
from scripts.export_seed import exportar_seed

logger = logging.getLogger(__name__)
DEFAULT_STATE = PROJECT_ROOT / "data" / "snapshot-base.json"


class GitHubRelease:
    def __init__(self, tag: str = "latest"):
        self.tag = tag

    def _run(self, *args: str) -> str:
        result = subprocess.run(
            ["gh", "release", *args], check=True, capture_output=True,
            text=True, encoding="utf-8", timeout=180,
        )
        return result.stdout

    def download(self, directory: Path, *, allow_legacy: bool = False) -> str:
        directory.mkdir(parents=True, exist_ok=True)
        info = json.loads(self._run("view", self.tag, "--json", "assets"))
        names = {asset["name"] for asset in info["assets"]}
        if MANIFEST_NAME not in names and not allow_legacy:
            raise ValueError("Release sem manifesto. Use --allow-legacy somente na transicao inicial.")
        required = (*ARTIFACT_NAMES, MANIFEST_NAME) if MANIFEST_NAME in names else ("vagas.db",)
        if not set(required).issubset(names):
            raise ValueError("Release incompleta: faltam artefatos do snapshot.")
        for name in required:
            self._run("download", self.tag, "--pattern", name, "--dir", str(directory), "--clobber")
        if MANIFEST_NAME in names:
            verify_manifest(directory)
        else:
            logger.warning("Snapshot legado sem manifesto: validando SQLite e registrando hash de origem.")
            validate_database(directory / "vagas.db")
        return sha256(directory / "vagas.db")

    def upload(self, directory: Path) -> None:
        verify_manifest(directory)
        self._run(
            "upload", self.tag,
            *(str(directory / name) for name in ARTIFACT_NAMES),
            str(directory / MANIFEST_NAME), "--clobber",
        )


def _atomic_copy(source: Path, destination: Path) -> None:
    """Substitui um arquivo completo; o temporario fica no mesmo volume."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=f".{destination.name}.", delete=False) as stream:
            temporary = Path(stream.name)
            with source.open("rb") as source_stream:
                shutil.copyfileobj(source_stream, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _write_state(state_path: Path, parent: str) -> None:
    validate_sha256(parent)
    with tempfile.TemporaryDirectory(prefix="tech-skills-state-") as tmp:
        state = Path(tmp) / "state.json"
        state.write_text(json.dumps({"parent_sha256": parent}), encoding="utf-8")
        _atomic_copy(state, state_path)


def download_snapshot(client, db_path: Path, state_path: Path, *, allow_legacy: bool = False) -> None:
    if db_path.resolve() == state_path.resolve():
        raise ValueError("Banco e estado precisam de arquivos diferentes.")
    with tempfile.TemporaryDirectory(prefix="tech-skills-download-") as tmp:
        downloaded = Path(tmp)
        parent = client.download(downloaded, allow_legacy=allow_legacy)
        validate_database(downloaded / "vagas.db")
        assert_current_parent(parent, sha256(downloaded / "vagas.db"))
        # Nao substituir uma base com WAL ativo: os sidecars pertencem a outra conexao.
        if any(Path(str(db_path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
            raise ValueError("Feche as conexoes do banco local antes de substituir o snapshot.")
        _atomic_copy(downloaded / "vagas.db", db_path)
        # Cada arquivo e atomico, nao o par. O estado so avanca depois do banco;
        # uma falha aqui deve ser resolvida antes de retomar a manutencao.
        _write_state(state_path, parent)


def prepare_snapshot(db_path: Path, directory: Path, parent: str) -> dict:
    validate_sha256(parent)
    if db_path.resolve() == (directory / "vagas.db").resolve():
        raise ValueError("Prepare o snapshot em outro diretorio, sem sobrescrever a origem.")
    directory.mkdir(parents=True, exist_ok=True)
    with closing(connect_sqlite(db_path, read_only=True)) as source:
        with closing(sqlite3.connect(directory / "vagas.db")) as target:
            source.backup(target)
    exportar_seed(directory / "vagas.db", directory / "vagas.csv")
    manifest = build_manifest(directory, parent)
    (directory / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return manifest


def publish_snapshot(client, db_path: Path, state_path: Path, *, allow_legacy: bool = False) -> str:
    if db_path.resolve() == state_path.resolve():
        raise ValueError("Banco e estado precisam de arquivos diferentes.")
    parent = json.loads(state_path.read_text(encoding="utf-8"))["parent_sha256"]
    validate_sha256(parent)
    with tempfile.TemporaryDirectory(prefix="tech-skills-publish-") as tmp:
        directory = Path(tmp)
        prepared = directory / "prepared"
        manifest = prepare_snapshot(db_path, prepared, parent)
        recovery = db_path.parent / "snapshots" / manifest["snapshot_id"]
        recovery.mkdir(parents=True, exist_ok=True)
        for filename in (*ARTIFACT_NAMES, MANIFEST_NAME):
            _atomic_copy(prepared / filename, recovery / filename)
        logger.info("Copia de recuperacao do snapshot: %s", recovery)
        current = directory / "current"
        current.mkdir()
        current_hash = client.download(current, allow_legacy=allow_legacy)
        assert_current_parent(parent, current_hash)
        client.upload(recovery)
        confirmed = directory / "confirmed"
        confirmed.mkdir()
        confirmed_hash = client.download(confirmed)
        confirmed_manifest = verify_manifest(confirmed)
        if confirmed_hash != manifest["snapshot_id"] or confirmed_manifest != manifest:
            raise ValueError("A release nao confirmou o snapshot enviado; preserve o banco local.")
        _write_state(state_path, confirmed_hash)
        if verify_manifest(recovery) == manifest:
            for filename in (*ARTIFACT_NAMES, MANIFEST_NAME):
                (recovery / filename).unlink()
            if not any(recovery.iterdir()):
                recovery.rmdir()
        return confirmed_hash


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("download", "publish"))
    parser.add_argument("--db", help="Arquivo SQLite local; respeita a configuracao do projeto.")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--allow-legacy", action="store_true")
    args = parser.parse_args(argv)
    path = resolve_sqlite_path(args.db)
    if path == ":memory:":
        parser.error("Snapshots requerem um arquivo SQLite.")
    client = GitHubRelease()
    if args.operation == "download":
        download_snapshot(client, path, args.state, allow_legacy=args.allow_legacy)
    else:
        snapshot_id = publish_snapshot(client, path, args.state, allow_legacy=args.allow_legacy)
        print(f"Snapshot confirmado: {snapshot_id}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
