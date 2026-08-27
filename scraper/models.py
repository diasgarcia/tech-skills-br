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


REMOTO = "Remoto"
HIBRIDO = "Híbrido"
PRESENCIAL = "Presencial"
NAO_INFORMADO = "Não informado"

WORKPLACE_ORDER = [REMOTO, HIBRIDO, PRESENCIAL, NAO_INFORMADO]

# Como cada portal nomeia a modalidade de trabalho.
_WORKPLACE_MAP = {
    "remote": REMOTO,
    "remoto": REMOTO,
    "home office": REMOTO,
    "hybrid": HIBRIDO,
    "hibrido": HIBRIDO,
    "on-site": PRESENCIAL,
    "on site": PRESENCIAL,
    "onsite": PRESENCIAL,
    "presencial": PRESENCIAL,
}


_HIBRIDO_RE = re.compile(
    r"\b(hibrid[oa]|regime hibrido|modelo hibrido|trabalho hibrido|formato hibrido|escala hibrida|dias presenciais)\b"
)
_REMOTO_RE = re.compile(
    r"\b(100 remoto|100 remota|totalmente remoto|totalmente remota|remoto|remota|home office|trabalho remoto|modelo remoto|regime remoto|formato remoto|vaga remota|atuacao remota|teletrabalho|remotamente)\b"
)
_PRESENCIAL_RE = re.compile(
    r"\b(100% presencial|totalmente presencial|presencial|regime presencial|modelo presencial|trabalho presencial|formato presencial|atuacao presencial|in loco)\b"
)


def normalize_workplace(raw: str | None) -> str:
    """Converte o rotulo de modalidade do portal para o vocabulario do projeto."""
    key = normalize(raw)
    if not key:
        return NAO_INFORMADO
    if key in _WORKPLACE_MAP:
        return _WORKPLACE_MAP[key]
    if "home office" in key or "remoto" in key:
        return REMOTO
    if "hibrid" in key:
        return HIBRIDO
    if "presencial" in key:
        return PRESENCIAL
    return NAO_INFORMADO


def infer_workplace(
    explicit: str | None = None,
    location: str | None = None,
    title: str | None = None,
    description: str | None = None,
    source: str | None = None,
) -> str:
    """Infere a modalidade combinando rotulo explicito, localizacao, titulo, descricao e fonte."""
    # 1. Rotulo explicito normalizado
    norm = normalize_workplace(explicit)
    if norm != NAO_INFORMADO:
        return norm

    # 2. Analise textual no titulo e descricao
    full_text = normalize(f"{title or ''} {description or ''}")
    if full_text:
        # Hibrido tem prioridade se mencionado (pois muitas vagas hibridas tambem citam dias presenciais)
        if _HIBRIDO_RE.search(full_text):
            return HIBRIDO
        if _REMOTO_RE.search(full_text):
            return REMOTO
        if _PRESENCIAL_RE.search(full_text):
            return PRESENCIAL

    # 3. Localizacao informada
    loc_norm = normalize(location)
    if loc_norm:
        if "remoto" in loc_norm or "home office" in loc_norm:
            return REMOTO
        if "hibrid" in loc_norm:
            return HIBRIDO
        if "cidades proximas" in loc_norm or "apenas candidaturas" in loc_norm:
            return PRESENCIAL
        if loc_norm in ("brasil", "brazil", "nacional"):
            if source == "linkedin":
                return REMOTO
            return NAO_INFORMADO
        # Cidade fisica identificada
        return PRESENCIAL

    return NAO_INFORMADO




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
    regiao: str = ""
    polo: str = ""


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

    def to_row(self, description_chars: int | None = None) -> dict[str, Any]:
        row = asdict(self)
        if description_chars is not None:
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
