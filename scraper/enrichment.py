"""Resultados de detalhe e contagens compartilhados pelos enriquecedores."""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Event


class BatchStopped(Exception):
    """A fila parou antes de iniciar a chamada HTTP desta vaga."""


class StopAwareSession:
    """Confere a parada dentro do lock usado pelos adaptadores de detalhe.

    Cada worker recebe seu proxy. O HTTP continua serializado pelo lock do
    adaptador, e o parse pode continuar em paralelo depois de liberar o lock.
    """

    def __init__(self, session, stopped: Event, *, stop_on_429: bool = True):
        self._session = session
        self._stopped = stopped
        self._stop_on_429 = stop_on_429

    @property
    def last_status_code(self):
        return self._session.last_status_code

    def get(self, url):
        if self._stopped.is_set():
            raise BatchStopped
        response = self._session.get(url)
        if self._stop_on_429 and self.last_status_code == 429:
            self._stopped.set()
        return response


@dataclass(frozen=True)
class DetailResult:
    data: dict[str, str] = field(default_factory=dict)
    status: int | None = None
    attempted: bool = True
    unavailable: bool = False
    reason: str = ""
    details: str = ""

    @classmethod
    def stopped(cls) -> DetailResult:
        return cls(attempted=False, reason="lote_interrompido_apos_429")

    @classmethod
    def from_response(cls, data: str | dict, status: int | None) -> DetailResult:
        payload = {"description": data} if isinstance(data, str) else dict(data)
        return cls(
            data=payload,
            status=status,
            unavailable=bool(payload.pop("_indisponivel", False)),
            reason=str(payload.pop("_diagnostico", "") or "").strip(),
            details=str(payload.pop("_detalhes", "") or "").strip(),
        )


@dataclass
class EnrichmentSummary:
    selected: int
    attempted: int = 0
    enriched: int = 0
    closed: int = 0
    removed: int = 0
    pending: int = 0
    failures: int = 0
    skipped: int = 0
    reasons: Counter[str] = field(default_factory=Counter)

    def to_dict(self) -> dict:
        return {**vars(self), "reasons": dict(self.reasons)}

    def leave_pending(self, reason: str, *, skipped: bool = False, failed: bool = False):
        self.pending += 1
        self.skipped += int(skipped)
        self.failures += int(failed)
        self.reasons[reason] += 1

    def log(self, logger: logging.Logger, source: str) -> None:
        logger.info(
            "Resumo enriquecimento %s: tentadas=%d | enriquecidas=%d | "
            "encerradas=%d | removidas=%d | pendentes=%d | falhas=%d | "
            "selecionadas=%d | nao_tentadas=%d",
            source, self.attempted, self.enriched, self.closed, self.removed,
            self.pending, self.failures, self.selected, self.skipped,
        )
        if self.reasons:
            logger.warning(
                "Pendencias %s por motivo: %s", source,
                " | ".join(f"{reason}={count}" for reason, count in sorted(self.reasons.items())),
            )


def write_summary(path: str | Path, summaries: dict[str, EnrichmentSummary]) -> None:
    """Grava um artefato independente por comando, substituindo-o atomicamente."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "sources": {source: summary.to_dict() for source, summary in summaries.items()},
    }
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        temporary.replace(destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def read_summaries(paths: list[str | Path]) -> dict[str, dict]:
    """Le contadores validados; arquivo ausente/invalido nao vira sucesso zero."""
    result = {}
    count_fields = ("selected", "attempted", "enriched", "closed", "removed", "pending", "failures", "skipped")
    for path in paths:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != 1 or not isinstance(payload.get("sources"), dict):
            raise ValueError(f"Resumo de enriquecimento invalido: {path}")
        for source, counts in payload["sources"].items():
            if source in result:
                raise ValueError(f"Fonte repetida nos resumos de enriquecimento: {source}")
            if not isinstance(counts, dict) or any(
                type(counts.get(field)) is not int or counts[field] < 0 for field in count_fields
            ):
                raise ValueError(f"Contadores invalidos para {source}: {path}")
            if (
                counts["selected"] != counts["enriched"] + counts["closed"] + counts["removed"] + counts["pending"]
                or counts["selected"] != counts["attempted"] + counts["skipped"]
                or counts["failures"] + counts["skipped"] > counts["pending"]
            ):
                raise ValueError(f"Contadores inconsistentes para {source}: {path}")
            result[source] = counts
    return result
