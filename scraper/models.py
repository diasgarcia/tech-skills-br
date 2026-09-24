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
    r"\b(?:hybrid work model|hybrid in office setting|in office presence in a hybrid capacity"
    r"|hybrid (?:internship|job|position|role)"
    r"|hibrid[oa]\s+[1-5](?:\s*x| dias?| vezes?)\s+(?:na|por) semana"
    r"|hibrid[oa] com [1-5] dias? presenciais?"
    r"|remote with [1-5] days? in (?:the )?office"
    r"|[1-9][0-9]? remote work from)\b"
)
_LINKEDIN_HYBRID_DECLARATION_RE = re.compile(
    r"\b(?:(?:modalidade|regime|modelo|formato)(?: de (?:trabalho|atuacao))?\s+"
    r"(?:presencial\s+(?:e|ou|e ou)\s+remot[oa]"
    r"|remot[oa]\s+(?:e|ou|e ou)\s+presencial)"
    r"|(?:modalidade|regime|modelo(?: de trabalho)?|formato(?: de trabalho)?|jornada"
    r"|posicao|oportunidade|localizacao|localidade(?: e modalidade)?"
    r"|local(?: de (?:trabalho|atuacao))?)"
    r"(?: [a-z0-9]+){0,8} (?:e |eh )?hibrid[oa])\b"
)
_LINKEDIN_MIXED_SCHEDULE_RE = re.compile(
    r"\b(?:[1-5]x(?: por semana)? home office e [1-5]x presencial"
    r"|[1-5]x presencial [1-5]x home office"
    r"|[1-5] dias? presenciais?(?: na [a-z0-9 ]+)? e [1-5] dias? (?:de |em )?home office"
    r"|[1-5] dias? (?:de |em )?home office e [1-5] dias? presenciais?"
    r"|[1-5] (?:dias?|vezes?) presencia(?:l|is) e (?:[1-5]|um) "
    r"(?:dias?|vezes?) (?:de )?home office"
    r"|[1-5] dias? presenciais? (?:e )?(?:[1-5]|um) dias? (?:de )?home office"
    r"|hibrid[oa] [1-5] dias? presencial [1-5] dias? home office"
    r"|presencial no escritorio de segunda a sexta feira nos sabados e domingos home office)\b"
)
_LINKEDIN_EXPLICIT_WORKPLACE_RE = re.compile(
    r"\b(?:modalidade|regime|modelo|formato)(?: de (?:trabalho|atuacao))? "
    r"(?P<value>hibrid[oa]|remot[oa]|presencial|home office)\b"
    r"|\b(?:forma de (?:trabalho|atuacao)|trabalho|atuacao|vaga"
    r"|local(?: de (?:trabalho|atuacao))?) "
    r"(?P<direct>hibrid[oa]|remot[oa]|presencial|home office)\b"
)
_LINKEDIN_ONSITE_CONTEXT_RE = re.compile(
    r"\b(?:contrato(?: de trabalho)? "
    r"(?:aprendiz |estagio |trainee |clt |pj |temporario |efetivo )?presencial"
    r"|regime de contratacao presencial"
    r"|tipo de contrato(?: clt)? presencial"
    r"|modelo de trabalho (?<!\d)100 presencial"
    r"|modelo de trabalho(?: [a-z0-9]+){1,12} presencial"
    r"|modelo full presencial"
    r"|(?<!\d)100 presencial"
    r"|[1-9][0-9]h(?:rs|oras)? semanais presencial(?: em| no| na)?"
    r"|(?:a )?vaga (?:e|eh|sera) presencial"
    r"|atuacao (?:e|eh|sera) presencial"
    r"|disponibilidade para (?:atuar|estagiar)(?: [a-z0-9]+){0,10} presencial(?: em| no| na)?"
    r"|disponibilidade presencial para (?:atuar|estagiar|estagio)"
    r"|disponibilidade para inicio imediato em rotina presencial"
    r"|escala(?: [a-z0-9]+){0,12} presencial(?: em| no| na)?"
    r"|(?:este e um )?cargo (?:e )?(?:full time |totalmente )?presencial"
    r"|atividade presencial(?: das| de segunda)"
    r"|estagio (?:e |remunerado )?presencial"
    r"|vaga aberta(?: [a-z0-9]+){0,8} presencial"
    r"|vaga efetiva e presencial(?! (?:e|ou|e ou) remot)"
    r"|vaga para atuar presencial(?: em| no| na)?"
    r"|(?:o )?trabalho sera presencial"
    r"|local de trabalho [a-z0-9 /]{0,80} presencial"
    r"|(?:horario|turno|jornada)(?: de trabalho)? [a-z0-9 /~]{0,80} presencial"
    r"|estagio presencial(?: em| no| na| cidade)?"
    r"|(?:expect to|will) work in office monday friday)\b"
)
_LINKEDIN_ONSITE_ADVERB_RE = re.compile(
    r"\b(?:atuar|trabalhar|estagiar|atuara|trabalhara)"
    r" (?:de maneira |de forma |em regime |100 )?presencial(?:mente)?\b"
)
_LINKEDIN_PARTIAL_ONSITE_RE = re.compile(
    r" (?:conforme necessidade|(?:e|ou|e ou) remotamente|[1-4](?:x| dias?| vezes?))\b"
)
_LINKEDIN_BENEFIT_HOME_OFFICE_RE = re.compile(
    r"\b(?:home office para (?:maes|mamaes|pais|papais)"
    r"|(?:auxilio|ajuda de custo|kit|vale) (?:para |de )?home office"
    r"(?: apenas para (?:as )?vagas (?<!\d)100 remot[oa]s?"
    r"| para (?:contratos|modalidades) hibrid[oa]s? (?:e|ou) remot[oa]s?)?)\b"
)
_LINKEDIN_REMOTE_CONTEXT_RE = re.compile(
    r"(?:\b|(?<!\d))(?:(?<!\d)100 remot(?:e|[oa])|(?<!\d)100 home office"
    r"|totalmente remot[oa]|trabalho remot[oa]|modelo(?: de trabalho)? (?:100 )?home office"
    r"|regime(?: clt)? remot[oa]|formato remot[oa]|modalidade home office"
    r"|vaga remot[oa]|atuacao remot[oa]"
    r"|local de trabalho home office|atuacao (?:e|eh) (?:100 )?home office"
    r"|(?:horario|jornada)(?: de trabalho)? [a-z0-9 ]{0,80} home office"
    r"|oportunidade (?:e|eh) remot[oa]|trabalh(?:a|e|ar|ando|ara) remotamente"
    r"|atuar remotamente(?: [a-z0-9]+){0,8} em ambiente home office"
    r"|jornada(?: [a-z0-9]+){0,8} de forma remota"
    r"|para atuar em home office|^home office\b"
    r"|fully remote|remote first|remote work model|workplace remote"
    r"|remote (?:internship|job|position|role)"
    r"|^clt [a-z ]{2,40} remote\b"
    r"|work(?:ing)? remotely)\b"
)
_LINKEDIN_HYBRID_WORD_RE = re.compile(r"\b(?:hibrid[oa]|hybrid)\b")
_LINKEDIN_TECHNICAL_HYBRID_RE = re.compile(
    r"\b(?:(?:nuvem|cloud|ambientes?|arquitetura|infraestrutura|solucoes?"
    r"|aplicacoes?|plataformas?|web|mobile|android|ios)(?: [a-z0-9]+){0,3} "
    r"(?:hibrid[oa]|hybrid)|(?:hibrid[oa]|hybrid) "
    r"(?:cloud|search|react|native|entre (?:codigo|plataformas?)))\b"
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
    if declared:
        return normalize_workplace(current)

    title_inferred = infer_workplace(title=title, source="linkedin")
    if title_inferred != NAO_INFORMADO:
        return title_inferred

    location_inferred = normalize_workplace(location)
    if location_inferred in (REMOTO, HIBRIDO):
        return location_inferred
    location_text = normalize(location)
    if location_inferred == PRESENCIAL and any(
        marker in location_text for marker in ("presencial", "on site", "onsite")
    ):
        return PRESENCIAL

    text = normalize(description)
    text_without_benefits = _LINKEDIN_BENEFIT_HOME_OFFICE_RE.sub("", text)
    work_model = _LINKEDIN_WORK_MODEL_RE.search(text_without_benefits)
    if work_model:
        value = work_model.group(1)
        if value.startswith("hybrid"):
            return HIBRIDO
        if value.startswith("remote"):
            return REMOTO
        return PRESENCIAL

    if (
        _LINKEDIN_HYBRID_CONTEXT_RE.search(text_without_benefits)
        or _LINKEDIN_HYBRID_DECLARATION_RE.search(text_without_benefits)
        or _LINKEDIN_MIXED_SCHEDULE_RE.search(text_without_benefits)
    ):
        return HIBRIDO

    declaration = _LINKEDIN_EXPLICIT_WORKPLACE_RE.search(text_without_benefits)
    if declaration:
        value = declaration.group("value") or declaration.group("direct")
        if value.startswith("hibrid"):
            return HIBRIDO
        if value.startswith("remot") or value == "home office":
            return REMOTO
        return PRESENCIAL

    for match in _LINKEDIN_HYBRID_WORD_RE.finditer(text_without_benefits):
        context = text_without_benefits[
            max(0, match.start() - 60):match.end() + 60
        ]
        if not _LINKEDIN_TECHNICAL_HYBRID_RE.search(context):
            return HIBRIDO

    if _LINKEDIN_REMOTE_CONTEXT_RE.search(text_without_benefits):
        return REMOTO
    if _LINKEDIN_ONSITE_CONTEXT_RE.search(text_without_benefits):
        return PRESENCIAL
    for match in _LINKEDIN_ONSITE_ADVERB_RE.finditer(text_without_benefits):
        if not _LINKEDIN_PARTIAL_ONSITE_RE.match(text_without_benefits[match.end():]):
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
    collection_profile: str | None = None
