"""Estruturas de dados compartilhadas entre coleta, classificacao e exportacao."""

from __future__ import annotations

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
_WORKPLACE_DECLARATION_RE = re.compile(
    r"\b(?:modalidade|regime|modelo|formato|forma|modo|local|trabalho|atuacao|vaga)"
    r"(?: de (?:trabalho|atuacao))?\s+(hibrid[oa]|remot[oa]|presencial)\b"
)
_MIXED_WORKPLACE_RE = re.compile(
    r"\b(?:presencial\s+(?:e\s+)?remot[oa]"
    r"|remot[oa]\s+(?:e\s+)?presencial)\b"
)
_OPERATIONAL_REMOTE_RE = re.compile(
    r"\b(?:(?:acesso|atendimento|atender|chamados?|clientes?|implantacao|instalacao|"
    r"manutencao|monitoramento|suporte|telefone|treinamentos?|usuarios?)"
    r"(?:\s+[a-z0-9]+){0,12}\s+"
    r"(?:presencial\s+(?:(?:e|ou)\s+)?remot[oa]"
    r"|remot[oa]\s+(?:(?:e|ou)\s+)?presencial)"
    r"|(?:ferramentas? de )?(?:suporte|acesso|atendimento|assistencia|monitoramento)"
    r"(?: tecnico)? remot[oa])\b"
)
_REMOTO_RE = re.compile(
    r"\b(100 remoto|100 remota|totalmente remoto|totalmente remota|remoto|remota|remote|home office|trabalho remoto|modelo remoto|regime remoto|formato remoto|vaga remota|atuacao remota|teletrabalho|remotamente)\b"
)
_PRESENCIAL_RE = re.compile(
    r"\b(100 presencial|totalmente presencial|presencial|regime presencial|modelo presencial|trabalho presencial|formato presencial|atuacao presencial|in loco)\b"
)
_LINKEDIN_WORK_MODEL_RE = re.compile(
    r"\bwork model (onsite(?:onsite)?|hybrid(?:hybrid)?|remote(?:remote)?)\b"
)
_LINKEDIN_HYBRID_CONTEXT_RE = re.compile(
    r"\b(?:hybrid work model|hybrid in office setting|in office presence in a hybrid capacity)\b"
)
_LINKEDIN_MIXED_SCHEDULE_RE = re.compile(
    r"\b(?:[1-5]x(?: por semana)? home office e [1-5]x presencial"
    r"|[1-5]x presencial [1-5]x home office"
    r"|presencial no escritorio de segunda a sexta feira nos sabados e domingos home office)\b"
)
_LINKEDIN_ONSITE_CONTEXT_RE = re.compile(
    r"\b(?:contrato efetivo presencial|(?:expect to|will) work in office monday friday)\b"
)
_LINKEDIN_ONSITE_ADVERB_RE = re.compile(
    r"\b(?:atuar|trabalhar|estagiar|atuara|trabalhara) (?:100 )?presencialmente\b"
)
_LINKEDIN_PARTIAL_ONSITE_RE = re.compile(
    r" (?:conforme necessidade|(?:e|ou|e ou) remotamente|[1-4](?:x| dias?| vezes?))\b"
)
_LINKEDIN_BENEFIT_HOME_OFFICE_RE = re.compile(
    r"\bhome office para (?:maes|mamaes|pais|papais)\b"
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
    """Infere a modalidade usando rotulo, titulo, descricao e localizacao."""
    norm = normalize_workplace(explicit)
    if norm != NAO_INFORMADO:
        return norm

    title_text = normalize(title)
    if title_text:
        if _HIBRIDO_RE.search(title_text):
            return HIBRIDO
        title_remoto = _REMOTO_RE.search(title_text)
        title_presencial = _PRESENCIAL_RE.search(title_text)
        if title_remoto and not title_presencial:
            return REMOTO
        if title_presencial and not title_remoto:
            return PRESENCIAL

    description_text = _OPERATIONAL_REMOTE_RE.sub(" ", normalize(description))
    full_text = f"{title_text} {description_text}".strip()
    if full_text:
        # Hibrido mantem a prioridade historica do projeto: seus anuncios
        # frequentemente tambem citam dias ou atividades presenciais.
        if _HIBRIDO_RE.search(full_text):
            return HIBRIDO

        # Fora de atividades como suporte/atendimento, a combinacao dos dois
        # modos descreve um regime misto.
        if _MIXED_WORKPLACE_RE.search(full_text):
            return HIBRIDO

        declaration = _WORKPLACE_DECLARATION_RE.search(full_text)
        if declaration:
            declared = declaration.group(1)
            if declared.startswith("hibrid"):
                return HIBRIDO
            if declared.startswith("remot"):
                return REMOTO
            return PRESENCIAL

        remoto = _REMOTO_RE.search(full_text)
        presencial = _PRESENCIAL_RE.search(full_text)
        if remoto and not presencial:
            return REMOTO
        if presencial and not remoto:
            return PRESENCIAL

    if source == "linkedin":
        return NAO_INFORMADO

    loc_norm = normalize(location)
    if loc_norm:
        if "remoto" in loc_norm or "home office" in loc_norm:
            return REMOTO
        if "hibrid" in loc_norm:
            return HIBRIDO
        if "cidades proximas" in loc_norm or "apenas candidaturas" in loc_norm:
            return PRESENCIAL
        if loc_norm in ("brasil", "brazil", "nacional"):
            return NAO_INFORMADO
        return PRESENCIAL

    return NAO_INFORMADO


def infer_linkedin_workplace(
    current: str | None,
    declared: bool,
    *,
    location: str | None = None,
    title: str | None = None,
    description: str | None = None,
) -> str:
    """Preserva o campo oficial do LinkedIn e usa o texto como fallback."""
    explicit = current if declared else None
    text = normalize(description)
    inferred = infer_workplace(
        explicit,
        location=location,
        title=title,
        description=text,
        source="linkedin",
    )
    if not declared and inferred == REMOTO and _LINKEDIN_BENEFIT_HOME_OFFICE_RE.search(text):
        without_benefit = _LINKEDIN_BENEFIT_HOME_OFFICE_RE.sub("", text)
        if infer_workplace(
            location=location, title=title, description=without_benefit,
            source="linkedin",
        ) != REMOTO:
            inferred = NAO_INFORMADO
    if inferred != NAO_INFORMADO or declared:
        return inferred

    # O detalhe publico por vezes inclui metadados do portal de origem. Outros
    # termos (suporte remoto, beneficios do escritorio) descrevem atividades,
    # nao o regime da vaga, e nao devem definir a modalidade sozinhos.
    work_model = _LINKEDIN_WORK_MODEL_RE.search(text)
    if work_model:
        value = work_model.group(1)
        if value.startswith("hybrid"):
            return HIBRIDO
        if value.startswith("remote"):
            return REMOTO
        return PRESENCIAL
    if _LINKEDIN_HYBRID_CONTEXT_RE.search(text) or _LINKEDIN_MIXED_SCHEDULE_RE.search(text):
        return HIBRIDO
    if _LINKEDIN_ONSITE_CONTEXT_RE.search(text):
        return PRESENCIAL
    for match in _LINKEDIN_ONSITE_ADVERB_RE.finditer(text):
        if not _LINKEDIN_PARTIAL_ONSITE_RE.match(text[match.end():]):
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
    workplace_declared: bool = False
    published_date: str = ""
    search_term: str = ""
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
