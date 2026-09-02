"""Classificacao de vagas em areas de tecnologia via keywords ponderadas.

As regras vivem em `scraper/rules/areas.yml` -- edite la, nao aqui.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .config import RULES_DIR
from .models import Job, normalize


@dataclass
class AreaScore:
    area: str
    score: float
    matches: list[str]
    title_score: float = 0.0
    # True quando um keyword de peso alto casou no TITULO -- o sinal mais
    # especifico e confiavel que existe. Usado para a area especifica
    # vencer o generico ("Desenvolvedor de Software Fullstack" nao deve
    # cair em Engenharia de Software so porque a descricao repete o
    # boilerplate de "engenharia de software").
    title_strong: bool = False


def _compile_keyword(keyword: str) -> re.Pattern:
    """Casa a keyword como palavra/frase inteira no texto normalizado."""
    kw = normalize(keyword)
    if not kw:
        return re.compile(r"(?!x)x")
    return re.compile(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])")


class AreaClassifier:
    """Pontua cada area por keywords e escolhe a de maior pontuacao."""

    def __init__(self, rules: dict) -> None:
        settings = rules.get("settings") or {}
        self.title_boost: float = float(settings.get("title_boost", 3.0))
        self.min_score: float = float(settings.get("min_score", 1.0))
        self.fallback_area: str = settings.get("fallback_area", "Outros/TI Geral")

        weights = rules.get("weights") or {}
        self.tiers: dict[str, float] = {k: float(v) for k, v in weights.items()}

        gate = rules.get("tech_gate") or {}
        if isinstance(gate, list):  # formato antigo: lista unica
            gate = {"titulo": gate, "descricao": gate}
        self.gate_title: list[re.Pattern] = [
            _compile_keyword(kw) for kw in (gate.get("titulo") or [])
        ]
        self.gate_body: list[re.Pattern] = [
            _compile_keyword(kw) for kw in (gate.get("descricao") or [])
        ]
        self.gate_exclude: list[re.Pattern] = [
            _compile_keyword(kw) for kw in (gate.get("excluir") or [])
        ]

        self.strong_weight: float = self.tiers.get("peso_alto", 4.0)

        self.areas: dict[str, list[tuple[re.Pattern, float, str]]] = {}
        for area, tiers in (rules.get("areas") or {}).items():
            compiled: list[tuple[re.Pattern, float, str]] = []
            for tier_name, keywords in (tiers or {}).items():
                weight = self.tiers.get(tier_name, 1.0)
                for kw in keywords or []:
                    compiled.append((_compile_keyword(kw), weight, kw))
            # Da keyword mais longa para a mais curta: `score_all` usa essa
            # ordem para nao contar duas vezes o mesmo trecho de texto.
            compiled.sort(key=lambda item: -len(normalize(item[2])))
            self.areas[area] = compiled

    @staticmethod
    def _primeiro_livre(
        pattern: re.Pattern, texto: str, usados: list[tuple[int, int]]
    ) -> tuple[int, int] | None:
        """Primeira ocorrencia da keyword que nao caia num trecho ja pontuado.

        Devolve o intervalo (inicio, fim) do casamento, ou None se todas as
        ocorrencias estiverem dentro de trechos ja contados nesta area.
        """
        if not texto:
            return None
        for match in pattern.finditer(texto):
            span = match.span()
            if not any(ini <= span[0] and span[1] <= fim for ini, fim in usados):
                return span
        return None

    def _strong_patterns(self):
        for keywords in self.areas.values():
            for pattern, weight, _kw in keywords:
                if weight >= self.strong_weight:
                    yield pattern

    @classmethod
    def from_file(cls, path: Path | None = None) -> "AreaClassifier":
        path = path or (RULES_DIR / "areas.yml")
        with open(path, encoding="utf-8") as fh:
            return cls(yaml.safe_load(fh) or {})

    @property
    def area_names(self) -> list[str]:
        return list(self.areas.keys()) + [self.fallback_area]

    def score_all(self, title: str, description: str = "") -> list[AreaScore]:
        """Pontuacao de todas as areas, da maior para a menor."""
        title_text = normalize(title)
        body_text = normalize(description)

        results: list[AreaScore] = []
        for area, keywords in self.areas.items():
            total = 0.0
            title_total = 0.0
            title_strong = False
            matches: list[str] = []
            # Trechos ja pontuados nesta area, para nao contar o mesmo texto
            # duas vezes: "suporte tecnico" (peso alto) contem "suporte"
            # (peso medio), e sem isso a area somaria os dois pelo mesmo trecho.
            usados_titulo: list[tuple[int, int]] = []
            usados_corpo: list[tuple[int, int]] = []

            for pattern, weight, raw_kw in keywords:
                no_titulo = self._primeiro_livre(pattern, title_text, usados_titulo)
                if no_titulo is not None:
                    usados_titulo.append(no_titulo)
                    total += weight * self.title_boost
                    title_total += weight * self.title_boost
                    matches.append(f"{raw_kw}(t)")
                    if weight >= self.strong_weight:
                        title_strong = True
                    continue

                no_corpo = self._primeiro_livre(pattern, body_text, usados_corpo)
                if no_corpo is not None:
                    usados_corpo.append(no_corpo)
                    total += weight
                    matches.append(raw_kw)
            if total > 0:
                results.append(
                    AreaScore(
                        area,
                        round(total, 2),
                        matches,
                        round(title_total, 2),
                        title_strong,
                    )
                )

        # Empate de pontuacao: vence a area com evidencias mais especificas
        # (maior soma de caracteres das keywords casadas). "Desenvolvedor de
        # Software Android" empata entre Engenharia de Software ("desenvolvedor
        # de software") e Mobile ("software android") -- a mais especifica
        # decide.
        results.sort(
            key=lambda r: (
                -r.score,
                -sum(len(m) for m in r.matches),
                r.area,
            )
        )
        return results

    def is_tech(self, title: str, description: str = "") -> bool:
        """A vaga e de tecnologia?

        Descarta o lixo que a busca solta dos portais devolve ("Analista
        Contábil Jr", "Analista Fiscal Jr", ...). Ver `tech_gate` em areas.yml:
        o titulo aceita sinais amplos, a descricao so aceita sinais estritos --
        porque a descricao curta do Vagas.com e cheia de palavra generica.
        """
        title_text = normalize(title)
        if any(p.search(title_text) for p in self.gate_exclude):
            return False
        if any(p.search(title_text) for p in self.gate_title):
            return True
        if any(p.search(title_text) for p in self._strong_patterns()):
            return True

        body_text = normalize(description)
        if not body_text:
            return False
        if any(p.search(body_text) for p in self.gate_body):
            return True
        return any(p.search(body_text) for p in self._strong_patterns())

    # Areas de desenvolvimento generico: nao contam como "especificas" na
    # precedencia de titulo abaixo. Um titulo "Desenvolvedor de Software
    # Fullstack" tem os dois sinais; sem esta lista, a generica e a
    # especifica empatariam e o desempate por tamanho de keyword faria a
    # generica vencer.
    GENERIC_DEV_AREAS = ("Engenharia de Software",)

    # Titulos que so rotulam o papel, sem stack: "Analista de Sistemas
    # Junior" cuja descricao inteira e atendimento/chamados e suporte,
    # nao desenvolvimento. So estes titulos podem cair na regra de
    # suporte disfarcado abaixo -- um "Desenvolvedor de Software" com
    # mencao a suporte na descricao NAO vira suporte.
    _SUPORTE_TITULOS_GENERICOS = frozenset(
        {
            "analista de sistemas",
            "analise de sistemas",
            "analista de desenvolvimento",
            "analista desenvolvedor",
        }
    )

    # Sinais de sustentacao no TITULO: "Analista de Sustentacao de
    # Sistemas" e suporte/manutencao, nao desenvolvimento novo. Ficam
    # fora do YAML de proposito: como peso alto no corpo do texto,
    # derrubavam vaga de dev cuja descricao cita sustentacao de passagem
    # ("DESENVOLVEDOR(A) DE SOFTWARE JUNIOR" em empresa de cobranca).
    _SUPORTE_TITULO_SUSTENTACAO = (
        "sustentacao de sistemas",
        "analista de sustentacao",
        "sustentacao de aplicacoes",
    )

    # Areas de stack: se a descricao tiver duas ou mais keywords destas
    # areas, a vaga NAO e suporte disfarcado -- fica para o generico (ou
    # para uma regra futura de stack por descricao).
    _SUPORTE_STACKS_GUARD = frozenset(
        {
            "Backend",
            "Frontend",
            "Fullstack",
            "Mobile",
            "Data",
            "Inteligência Artificial",
            "DevOps",
            "QA",
        }
    )

    def classify(self, title: str, description: str = "") -> AreaScore:
        """Escolhe a area da vaga.

        Regra do titulo dominante: se ALGUMA area foi sinalizada pelo titulo
        com forca acima do piso, so essas areas disputam. Sem isso, uma
        descricao longa da Gupy que cita "dados" de passagem ("protecao de
        dados", "dados cadastrais") faria uma vaga de Governanca de TI virar
        vaga de Data.

        Titulo exatamente no piso (como "Desenvolvedor Júnior") nao domina:
        ai a descricao ainda pode decidir ("...pipelines de ETL e SQL" -> Data).

        Precedencia do titulo especifico: entre as areas sinalizadas pelo
        titulo, a que casou keyword de peso alto no titulo vence as genericas
        ("Estagio em Desenvolvimento de Software - Android" vai para Mobile,
        nao para Engenharia de Software so porque a descricao repete o
        boilerplate de "engenharia de software").
        """
        ranked = self.score_all(title, description)
        if not ranked:
            return AreaScore(self.fallback_area, 0.0, [])

        titled = [r for r in ranked if r.title_score > self.min_score]
        candidates = titled or ranked  # `ranked` ja vem ordenado por pontuacao

        if len(candidates) > 1:
            especificos = [
                r
                for r in candidates
                if r.title_strong and r.area not in self.GENERIC_DEV_AREAS
            ]
            best = (especificos or candidates)[0]
        else:
            best = candidates[0]

        if best.score < self.min_score:
            return AreaScore(self.fallback_area, 0.0, [])

        if best.area in self.GENERIC_DEV_AREAS:
            suporte = self._suporte_disjarcado(ranked, title)
            if suporte is not None:
                return suporte

        return best

    def _suporte_disjarcado(
        self, ranked: list[AreaScore], title: str
    ) -> AreaScore | None:
        """Detecta vaga de suporte com titulo de papel generico.

        Casos reais: "Analista de Sistemas Junior" cuja descricao fala
        apenas de atendimento, chamados e suporte tecnico; e "Analista de
        Sustentacao de Sistemas" (manutencao/suporte, nao desenvolvimento).

        Caminho do papel generico: o titulo rotula o papel generico (que
        pontua alto) e a area de Suporte nunca disputa. So aplica quando:
          - todas as keywords de titulo da area generica sao do conjunto
            de papeis genericos (analista de sistemas etc.);
          - a descricao tem 3+ sinais de suporte;
          - a descricao NAO tem stack de desenvolvimento (2+ keywords de
            Backend/Frontend/etc.), para nao roubar vaga de dev que cita
            suporte de passagem.

        Caminho da sustentacao: o proprio titulo entrega ("sustentacao de
        sistemas"); dispensa os sinais da descricao.
        """
        eng = next((r for r in ranked if r.area in self.GENERIC_DEV_AREAS), None)
        if eng is None:
            return None

        titulo_eng = {m[:-3] for m in eng.matches if m.endswith("(t)")}
        titulo_norm = normalize(title)

        caminho_generico = bool(titulo_eng) and titulo_eng <= self._SUPORTE_TITULOS_GENERICOS
        caminho_sustentacao = any(
            sinal in titulo_norm for sinal in self._SUPORTE_TITULO_SUSTENTACAO
        )
        if not caminho_generico and not caminho_sustentacao:
            return None

        # Guard so para o papel generico: "Analista de Sustentacao de
        # Sistemas" cita banco de dados/mysql na descricao com naturalidade
        # (sustenta esses sistemas), sem deixar de ser suporte.
        if caminho_generico:
            for r in ranked:
                if r.area in self._SUPORTE_STACKS_GUARD:
                    corpo = [m for m in r.matches if not m.endswith("(t)")]
                    if len(corpo) >= 2:
                        return None

        sinais: list[str] = []
        for r in ranked:
            if r.area in ("Suporte Técnico", "Service Desk / Help Desk"):
                sinais.extend(m for m in r.matches if not m.endswith("(t)"))
        unicos = sorted(set(sinais))
        if not caminho_sustentacao and len(unicos) < 3:
            return None

        score = sum(
            r.score
            for r in ranked
            if r.area in ("Suporte Técnico", "Service Desk / Help Desk")
        )
        return AreaScore("Suporte Técnico", round(score, 2), unicos)


@lru_cache(maxsize=1)
def default_classifier() -> AreaClassifier:
    return AreaClassifier.from_file()


def classify_jobs(jobs: list[Job], clf: AreaClassifier | None = None) -> list[Job]:
    """Preenche `area`, `area_score` e `area_matches` em cada vaga."""
    clf = clf or default_classifier()
    for job in jobs:
        result = clf.classify(job.title, job.description)
        job.area = result.area
        job.area_score = result.score
        job.area_matches = ", ".join(result.matches[:12])
    return jobs


def filter_tech(
    jobs: list[Job], clf: AreaClassifier | None = None
) -> tuple[list[Job], list[Job]]:
    """Separa (vagas de tecnologia, vagas descartadas por nao serem de tech)."""
    clf = clf or default_classifier()
    tech, non_tech = [], []
    for job in jobs:
        (tech if clf.is_tech(job.title, job.description) else non_tech).append(job)
    return tech, non_tech
