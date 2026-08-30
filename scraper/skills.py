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


def normalize_tech(text: str | None) -> str:
    """Minusculas, sem acento, mantendo '#' e '+'. Pontuacao vira espaco."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = _KEEP_RE.sub(" ", text.lower())
    return _WS_RE.sub(" ", text).strip()


def _compile_alias(alias: str) -> re.Pattern:
    token = normalize_tech(alias)
    if not token:
        return re.compile(r"(?!x)x")
    return re.compile(rf"(?<!{_BOUNDARY}){re.escape(token)}(?!{_BOUNDARY})")


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
        for group, entries in (rules or {}).items():
            for canonical, aliases in (entries or {}).items():
                patterns = []
                case_patterns = []
                for a in (aliases or [canonical]):
                    case_only = a.startswith("~")
                    if case_only:
                        a = a[1:]
                    if any(c.isupper() for c in a):
                        # Alias com maiuscula casa no texto original preservando
                        # caixa ("Go" != "go" != "GO"). A nao ser que o alias
                        # comece com "~" (so caixa exata), mantem tambem o
                        # casamento normal, insensivel a caixa (ex.: "pfSense").
                        case_patterns.append(_compile_case_alias(a))
                        if not case_only:
                            patterns.append(_compile_alias(a))
                    else:
                        patterns.append(_compile_alias(a))
                self.skills[canonical] = patterns
                self.case_sensitive[canonical] = case_patterns
                self.groups[canonical] = group

    @classmethod
    def from_file(cls, path: Path | None = None) -> "SkillExtractor":
        path = path or (RULES_DIR / "skills.yml")
        with open(path, encoding="utf-8") as fh:
            return cls(yaml.safe_load(fh) or {})

    def _recortar_secoes_finais(self, texto_normalizado: str) -> str:
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
        for secao in self.secoes_descarte:
            posicao = texto_normalizado.find(secao)
            if posicao != -1 and posicao < fim and posicao > limite:
                fim = posicao
        return texto_normalizado[:fim].strip()

    def _recortar_contextos_descarte(self, texto_normalizado: str) -> str:
        """Remove mencoes a empresa/setor que nao sao a skill (falsos positivos)."""
        for padroes in self.contextos_descarte.values():
            for padrao in padroes:
                texto_normalizado = padrao.sub(" ", texto_normalizado)
        return texto_normalizado

    def extract(self, *texts: str) -> list[str]:
        """Tecnologias citadas nos textos, sem repetir, em ordem alfabetica."""
        raw = " ".join(t for t in texts if t)
        haystack = normalize_tech(raw)
        if not haystack:
            return []
        haystack = self._recortar_secoes_finais(haystack)
        if not haystack:
            return []
        haystack = self._recortar_contextos_descarte(haystack)
        if not haystack:
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
    """Quantas vagas de cada area citam ao menos uma tecnologia.

    E a base correta para percentuais: nem toda vaga informa tecnologia. O
    LinkedIn nao traz descricao no card, entao areas cheias de vaga vinda de la
    tem base bem menor que o total -- em "Outros/TI Geral", 31 de 144.
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
