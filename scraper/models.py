"""Estruturas de dados compartilhadas entre coleta, classificacao e exportacao."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9 ]+")


def strip_html(raw: str | None) -> str:
    """Remove tags e entidades HTML, devolvendo texto plano de uma linha."""
    if not raw:
        return ""
    import html as _html

    text = _TAG_RE.sub(" ", raw)
    text = _html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def normalize(text: str | None) -> str:
    """Minusculas, sem acentos e sem pontuacao. Usado em regex e deduplicacao."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = _NON_ALNUM_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


@dataclass
class Job:
    """Uma vaga normalizada, independente do portal de origem."""

    source: str
    external_id: str
    title: str
    company: str = ""
    url: str = ""
    description: str = ""
    location: str = ""
    workplace_type: str = ""
    published_date: str = ""
    search_term: str = ""
    # Preenchidos pelo pipeline:
    area: str = ""
    area_score: float = 0.0
    area_matches: str = ""
    seniority: str = ""
    skills: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.title = _WS_RE.sub(" ", (self.title or "")).strip()
        self.company = _WS_RE.sub(" ", (self.company or "")).strip()
        self.description = strip_html(self.description)

    @property
    def fingerprint(self) -> str:
        """Chave estavel para deduplicar a mesma vaga vinda de termos/portais diferentes."""
        base = f"{normalize(self.title)}|{normalize(self.company)}"
        return hashlib.sha1(base.encode("utf-8")).hexdigest()

    @property
    def source_key(self) -> str:
        """Identidade exata dentro de um portal."""
        return f"{self.source}:{self.external_id}"

    def searchable_text(self) -> str:
        return normalize(f"{self.title} {self.description}")

    def to_row(self, description_chars: int = 500) -> dict[str, Any]:
        row = asdict(self)
        row["description"] = self.description[:description_chars]
        row["skills"] = ", ".join(self.skills)
        return row


@dataclass
class SourceStats:
    """Contadores por portal, para o relatorio final."""

    source: str
    requests_made: int = 0
    raw_jobs: int = 0
    errors: list[str] = field(default_factory=list)
