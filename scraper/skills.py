"""Extracao das tecnologias/habilidades citadas em cada vaga.

As regras vivem em `scraper/rules/skills.yml` -- edite la, nao aqui.

Diferente do resto do projeto, aqui o texto passa por uma normalizacao propria
que PRESERVA "#" e "+": com a normalizacao padrao, "C#" viraria "c" e casaria
com qualquer "c" solto no texto.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from functools import lru_cache
from pathlib import Path

import yaml

from .config import RULES_DIR
from .models import Job

_WS_RE = re.compile(r"\s+")
_URL_RE = re.compile(
    r"(?:https?://|www\.)\S+|\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b", re.IGNORECASE,
)
_KEEP_RE = re.compile(r"[^a-z0-9#+ ]+")
_BOUNDARY = r"[a-z0-9#+]"
_CASE_BOUNDARY = r"[A-Za-z0-9#+]"

ARQUIVO_SECOES_DESCARTE = RULES_DIR / "secoes_descarte.yml"
ARQUIVO_CONTEXTOS_DESCARTE = RULES_DIR / "contextos_descarte.yml"


def _carregar_secoes_descarte() -> tuple[str, ...]:
    """Secoes finais (beneficios/termos) que o extrator deve ignorar."""
    try:
        with open(ARQUIVO_SECOES_DESCARTE, encoding="utf-8") as fh:
            dados = yaml.safe_load(fh) or {}
    except OSError:
        return ()
    secoes = dados.get("secoes_descarte") or []
    return tuple(s.strip() for s in secoes if isinstance(s, str) and s.strip())


def _carregar_secoes_conteudo() -> tuple[str, ...]:
    """Marcadores de conteudo (requisitos/atividades) que adiam o corte."""
    try:
        with open(ARQUIVO_SECOES_DESCARTE, encoding="utf-8") as fh:
            dados = yaml.safe_load(fh) or {}
    except OSError:
        return ()
    secoes = dados.get("secoes_conteudo") or []
    return tuple(s.strip() for s in secoes if isinstance(s, str) and s.strip())


def _carregar_contextos_descarte() -> dict[str, list[re.Pattern]]:
    """Regex que removem mencoes a EMPRESA (nao a skill), por tecnologia.

    Ex.: "uma gigante brasileira de hardware e servicos" fala da empresa
    contratante; "hardware" ali nao e uma habilidade pedida.
    """
    try:
        with open(ARQUIVO_CONTEXTOS_DESCARTE, encoding="utf-8") as fh:
            dados = yaml.safe_load(fh) or {}
    except OSError:
        return {}
    regras = dados.get("descartar") or {}
    compiladas: dict[str, list[re.Pattern]] = {}
    for tecnologia, padroes in regras.items():
        lista = []
        for p in padroes or []:
            token = normalize_tech(p)
            if token:
                lista.append(re.compile(rf"(?<!{_BOUNDARY}){re.escape(token)}(?!{_BOUNDARY})"))
        if lista:
            compiladas[tecnologia] = lista
    return compiladas


def _carregar_exclusoes_sufixo_alias() -> dict[str, dict[str, tuple[str, ...]]]:
    """Carrega excecoes contextuais especificas de cada alias.

    Exemplo: o alias "node" de Node.js nao deve casar quando vier antes de
    "red", mas "node red" precisa continuar disponivel para Node-RED.
    """
    try:
        with open(ARQUIVO_CONTEXTOS_DESCARTE, encoding="utf-8") as fh:
            dados = yaml.safe_load(fh) or {}
    except OSError:
        return {}

    resultado: dict[str, dict[str, tuple[str, ...]]] = {}
    for tecnologia, aliases in (dados.get("aliases_contextuais") or {}).items():
        por_alias: dict[str, tuple[str, ...]] = {}
        for alias, configuracao in (aliases or {}).items():
            if not isinstance(configuracao, dict):
                continue
            alias_normalizado = normalize_tech(alias)
            sufixos = tuple(
                token
                for item in (configuracao.get("nao_seguido_por") or [])
                if (token := normalize_tech(item))
            )
            if alias_normalizado and sufixos:
                por_alias[alias_normalizado] = sufixos
        if por_alias:
            resultado[tecnologia] = por_alias
    return resultado


def normalize_tech(text: str | None) -> str:
    """Minusculas, sem acento, mantendo '#' e '+'. Pontuacao vira espaco."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = _KEEP_RE.sub(" ", text.lower())
    return _WS_RE.sub(" ", text).strip()


def _normalized_offsets(raw: str) -> list[int]:
    """Mapeia cada caractere normalizado para sua posicao no texto original.

    NFKD pode expandir caracteres e a compactacao de espacos muda os indices.
    O mapa permite aplicar os mesmos descartes sem perder a caixa dos aliases.
    """
    offsets: list[int] = []
    pending_space: int | None = None
    for index, original in enumerate(raw):
        decomposed = unicodedata.normalize("NFKD", original)
        characters = "".join(c for c in decomposed if not unicodedata.combining(c)).lower()
        for char in characters:
            if "a" <= char <= "z" or "0" <= char <= "9" or char in "#+":
                if pending_space is not None:
                    offsets.append(pending_space)
                    pending_space = None
                offsets.append(index)
            elif offsets and pending_space is None:
                pending_space = index
    return offsets


def _compile_alias(alias: str, suffixes: tuple[str, ...] = ()) -> re.Pattern:
    token = normalize_tech(alias)
    if not token:
        return re.compile(r"(?!x)x")
    suffix_guard = ""
    if suffixes:
        alternatives = "|".join(re.escape(suffix) for suffix in suffixes)
        suffix_guard = rf"(?!\s+(?:{alternatives})(?!{_BOUNDARY}))"
    return re.compile(
        rf"(?<!{_BOUNDARY}){re.escape(token)}{suffix_guard}(?!{_BOUNDARY})"
    )


def _compile_case_alias(alias: str) -> re.Pattern:
    """Alias casado no texto original, preservando maiusculas/minusculas."""
    token = _WS_RE.sub(" ", alias).strip()
    if not token:
        return re.compile(r"(?!x)x")
    return re.compile(rf"(?<!{_CASE_BOUNDARY}){re.escape(token)}(?!{_CASE_BOUNDARY})")


class SkillExtractor:
    """Encontra tecnologias no texto da vaga, a partir de `skills.yml`."""

    def __init__(
        self,
        rules: dict,
        secoes_descarte: list[str] | None = None,
        secoes_conteudo: list[str] | None = None,
        contextos_descarte: dict[str, list[re.Pattern]] | None = None,
        exclusoes_sufixo_alias: dict[str, dict[str, tuple[str, ...]]] | None = None,
    ) -> None:
        self.skills: dict[str, list[re.Pattern]] = {}
        self.case_sensitive: dict[str, list[re.Pattern]] = {}
        self.groups: dict[str, str] = {}
        self.secoes_descarte = (
            tuple(s.strip() for s in secoes_descarte if s.strip())
            if secoes_descarte is not None
            else _carregar_secoes_descarte()
        )
        self.secoes_conteudo = (
            tuple(s.strip() for s in secoes_conteudo if s.strip())
            if secoes_conteudo is not None
            else _carregar_secoes_conteudo()
        )
        self.contextos_descarte = (
            contextos_descarte
            if contextos_descarte is not None
            else _carregar_contextos_descarte()
        )
        self.exclusoes_sufixo_alias = (
            exclusoes_sufixo_alias
            if exclusoes_sufixo_alias is not None
            else _carregar_exclusoes_sufixo_alias()
        )
        for group, entries in (rules or {}).items():
            for canonical, aliases in (entries or {}).items():
                patterns = []
                case_patterns = []
                exclusoes_canonicas = self.exclusoes_sufixo_alias.get(canonical, {})
                for a in (aliases or [canonical]):
                    case_only = a.startswith("~")
                    if case_only:
                        a = a[1:]
                    suffixes = exclusoes_canonicas.get(normalize_tech(a), ())
                    if any(c.isupper() for c in a):
                        # Alias com maiuscula casa no texto original preservando
                        # caixa ("Go" != "go" != "GO"). A nao ser que o alias
                        # comece com "~" (so caixa exata), mantem tambem o
                        # casamento normal, insensivel a caixa (ex.: "pfSense").
                        case_patterns.append(_compile_case_alias(a))
                        if not case_only:
                            patterns.append(_compile_alias(a, suffixes))
                    else:
                        patterns.append(_compile_alias(a, suffixes))
                self.skills[canonical] = patterns
                self.case_sensitive[canonical] = case_patterns
                self.groups[canonical] = group

    @classmethod
    def from_file(cls, path: Path | None = None) -> "SkillExtractor":
        path = path or (RULES_DIR / "skills.yml")
        with open(path, encoding="utf-8") as fh:
            return cls(yaml.safe_load(fh) or {})

    @staticmethod
    def _e_titulo_de_secao(raw: str, inicio: int, fim: int) -> bool:
        """Distingue cabecalho de uma palavra no meio de uma frase."""
        antes = raw[:inicio].rstrip(" \t")
        depois = raw[fim:].lstrip(" \t")
        inicio_de_linha = not antes or antes.endswith(("\n", "\r"))
        rotulo = raw[inicio:fim]
        titulo = rotulo[:1].isupper()
        delimitado = depois.startswith((":", "\n", "\r", "|", "-", "–"))
        # Os portais frequentemente achatam o HTML: "Benefícios Vale transporte".
        proxima_letra = re.search(r"[^\W\d_]", depois)
        proximo_titulo = bool(proxima_letra and proxima_letra[0].isupper())
        titulo_composto = titulo and len(rotulo.split()) > 1
        return inicio_de_linha or delimitado or (titulo and proximo_titulo) or titulo_composto

    def _recortar_secoes_finais(
        self, texto_normalizado: str, raw: str,
    ) -> tuple[str, list[int] | None]:
        """Corta na primeira secao de beneficios/termos que vier DEPOIS do
        ultimo marcador de conteudo (requisitos/atividades).

        O LinkedIn as vezes coloca "Beneficios" no meio do texto, antes de
        "Requisitos": cortar ali descartaria os proprios requisitos. Entao o
        corte so acontece quando a secao de descarte aparece apos todo o
        conteudo.
        """
        limite = -1
        for secao in self.secoes_conteudo:
            posicao = texto_normalizado.rfind(secao)
            if posicao > limite:
                limite = posicao
        fim = len(texto_normalizado)
        offsets = None
        for secao in self.secoes_descarte:
            # O HTML pode colar "ITILInformações adicionaisBenefícios".
            # A validacao no texto original distingue cabecalho de prosa.
            pattern = re.compile(re.escape(normalize_tech(secao)))
            for match in pattern.finditer(texto_normalizado, limite + 1):
                if match.start() >= fim:
                    break
                if offsets is None:
                    offsets = _normalized_offsets(raw)
                if self._e_titulo_de_secao(
                    raw, offsets[match.start()], offsets[match.end() - 1] + 1,
                ):
                    fim = match.start()
                    break
        return texto_normalizado[:fim].strip(), offsets

    def _textos_permitidos(self, raw: str) -> tuple[str, str]:
        """Aplica os mesmos trechos de descarte nas duas formas do texto."""
        normalized = normalize_tech(raw)
        retained, offsets = self._recortar_secoes_finais(normalized, raw)
        excluded = []
        if len(retained) < len(normalized):
            excluded.append((len(retained), len(normalized)))
        for padroes in self.contextos_descarte.values():
            for padrao in padroes:
                excluded.extend(match.span() for match in padrao.finditer(retained))
        if not excluded:
            return raw, normalized
        if offsets is None:
            offsets = _normalized_offsets(raw)
        raw_chars = list(raw)
        normalized_chars = list(normalized)
        for start, end in excluded:
            if start == end:
                continue
            normalized_chars[start:end] = " " * (end - start)
            raw_start, raw_end = offsets[start], offsets[end - 1] + 1
            raw_chars[raw_start:raw_end] = " " * (raw_end - raw_start)
        return "".join(raw_chars), "".join(normalized_chars)

    def extract(self, *texts: str) -> list[str]:
        """Tecnologias citadas nos textos, sem repetir, em ordem alfabetica."""
        raw = _URL_RE.sub(" ", " ".join(t for t in texts if t))
        raw, haystack = self._textos_permitidos(raw)
        if not haystack.strip():
            return []
        found = [
            name
            for name, patterns in self.skills.items()
            if any(p.search(haystack) for p in patterns)
            or any(p.search(raw) for p in self.case_sensitive.get(name, ()))
        ]
        return sorted(found)


@lru_cache(maxsize=1)
def default_extractor() -> SkillExtractor:
    return SkillExtractor.from_file()


def attach_skills(jobs: list[Job], extractor: SkillExtractor | None = None) -> list[Job]:
    """Preenche `job.skills`. Deve rodar ANTES da exportacao, que trunca a descricao."""
    extractor = extractor or default_extractor()
    for job in jobs:
        job.skills = extractor.extract(job.title, job.description)
    return jobs


def skills_by_area(jobs: list[Job], top_n: int = 8) -> dict[str, list[tuple[str, int]]]:
    """Top-N tecnologias por area: {area: [(tecnologia, n_vagas), ...]}."""
    counters: dict[str, Counter] = {}
    for job in jobs:
        counters.setdefault(job.area, Counter()).update(job.skills)
    return {
        area: counter.most_common(top_n)
        for area, counter in counters.items()
        if counter
    }


def jobs_with_skills_by_area(jobs: list[Job]) -> dict[str, int]:
    """Quantas vagas de cada area possuem ao menos uma skill identificada.

    Base dos percentuais condicionais do ranking. Ausencia de match nao
    prova ausencia de requisito: pode haver texto incompleto ou termo
    desconhecido pelo vocabulario. Nao equivale ao total de anuncios da area.
    """
    base: dict[str, int] = {}
    for job in jobs:
        if job.skills:
            base[job.area] = base.get(job.area, 0) + 1
    return base


def overall_skill_counts(jobs: list[Job], top_n: int = 20) -> list[tuple[str, int]]:
    counter: Counter = Counter()
    for job in jobs:
        counter.update(job.skills)
    return counter.most_common(top_n)
