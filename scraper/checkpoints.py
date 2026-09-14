"""Checkpoints completos de coleta, confirmados somente apos exportacao.

O CSV parcial continua legivel por ferramentas locais. Uma substituicao atomica
impede que uma interrupcao durante a escrita destrua o checkpoint anterior.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Iterator, TextIO

from .models import Job

CHECKPOINT_NAMES = {
    "abler": "abler_partial.csv",
    "recrutei": "recrutei_partial.csv",
}
_JOB_FIELDS = [field.name for field in fields(Job)]


class CheckpointError(ValueError):
    """Checkpoint invalido: preservar o arquivo e interromper a retomada."""


@contextmanager
def atomic_csv_file(path: Path) -> Iterator[TextIO]:
    """Grava e sincroniza um temporario no mesmo volume antes de substituir."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as stream:
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class JobCheckpoint:
    """Armazena registros completos de uma fonte pela identidade externa."""

    def __init__(self, path: Path, source: str) -> None:
        self.path = path
        self.source = source

    def load(self) -> list[Job]:
        if not self.path.exists():
            return []
        jobs: dict[str, Job] = {}
        try:
            with self.path.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream, strict=True)
                if reader.fieldnames != _JOB_FIELDS:
                    raise ValueError("cabecalho incompleto ou desconhecido")
                for row in reader:
                    if None in row or any(value is None for value in row.values()):
                        raise ValueError(f"linha incompleta em {reader.line_num}")
                    if row["source"] != self.source or not row["external_id"] or not row["title"]:
                        raise ValueError(f"identidade invalida em {reader.line_num}")
                    skills = row["skills"]
                    row["skills"] = json.loads(skills) if skills.startswith("[") else [
                        skill.strip() for skill in skills.split(",") if skill.strip()
                    ]
                    if not isinstance(row["skills"], list) or any(
                        not isinstance(skill, str) for skill in row["skills"]
                    ):
                        raise ValueError(f"skills invalidas em {reader.line_num}")
                    row["area_score"] = float(row["area_score"])
                    job = Job(**row)
                    # A descricao ja e texto plano: nao remover tags literais
                    # ou decodificar entidades pela segunda vez ao retomar.
                    job.description = row["description"]
                    if job.external_id in jobs and jobs[job.external_id] != job:
                        raise ValueError(f"identidade duplicada divergente: {job.external_id}")
                    jobs[job.external_id] = job
        except (ValueError, TypeError, csv.Error, UnicodeError) as exc:
            raise CheckpointError(
                f"Checkpoint invalido em {self.path}; arquivo preservado: {exc}"
            ) from exc
        return list(jobs.values())

    def save(self, jobs: list[Job]) -> None:
        unique = {job.source_key: job for job in jobs}
        if any(job.source != self.source for job in unique.values()):
            raise ValueError("O checkpoint so pode conter vagas da propria fonte")
        with atomic_csv_file(self.path) as stream:
            writer = csv.DictWriter(stream, fieldnames=_JOB_FIELDS)
            writer.writeheader()
            for job in unique.values():
                row = job.to_row()
                row["skills"] = json.dumps(job.skills, ensure_ascii=False)
                writer.writerow(row)


@dataclass(frozen=True)
class CheckpointReceipt:
    path: Path
    digest: str

    def confirm(self) -> bool:
        """Nao apaga dados substituidos/adicionados depois da captura."""
        if not self.path.exists() or hashlib.sha256(self.path.read_bytes()).hexdigest() != self.digest:
            return False
        self.path.unlink()
        return True


def checkpoint_receipts(jobs: list[Job], output_dir: Path) -> list[CheckpointReceipt]:
    """Captura somente checkpoints integralmente recebidos pelo pipeline.

    Deve rodar antes dos filtros e das mutacoes dos objetos Job. Um checkpoint
    de fonte que falhou ou nao participou da coleta nao pode ser confirmado.
    """
    received = {job.source_key: job for job in jobs}
    receipts = []
    for source, filename in CHECKPOINT_NAMES.items():
        path = output_dir / filename
        if not path.exists() or not any(job.source == source for job in jobs):
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        stored = JobCheckpoint(path, source).load()
        if stored and all(received.get(job.source_key) == job for job in stored):
            receipts.append(CheckpointReceipt(path, digest))
    return receipts
