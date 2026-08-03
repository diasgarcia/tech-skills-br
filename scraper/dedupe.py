"""Remocao de vagas duplicadas.

Duplicatas aparecem por tres motivos:
  1. o mesmo termo de busca traz a mesma vaga em paginas diferentes;
  2. termos diferentes ("desenvolvedor junior" e "desenvolvedor jr") trazem a
     mesma vaga;
  3. portais diferentes anunciam a mesma vaga -- e cada um escreve o nome da
     empresa do seu jeito ("Minsait" na Gupy, "Minsait an Indra Company" no
     LinkedIn; "FEI" e "Centro Universitario FEI").

O caso 3 e o mais escorregadio. Nao da para casar so por titulo: "Analista de
Sistemas Junior" aparece em dezenas de empresas diferentes, e uni-las seria
muito pior que manter a duplicata. A regra usada exige titulo normalizado
IDENTICO e nomes de empresa compativeis -- um conjunto de palavras contido no
outro, depois de descartar sufixos societarios e palavras genericas.
"""

from __future__ import annotations

from .models import Job, normalize

# Palavras que nao ajudam a identificar a empresa: sufixos societarios, termos
# genericos de ramo e rotulos de anonimato. "Confidencial" precisa entrar aqui,
# senao duas vagas confidenciais de empresas diferentes virariam a mesma.
_RUIDO_EMPRESA = {
    "ltda", "sa", "eireli", "epp", "me", "mei", "inc", "llc", "corp",
    "group", "grupo", "company", "holding", "participacoes",
    "brasil", "brazil", "do", "da", "de", "dos", "das", "e", "em",
    "solucoes", "servicos", "sistemas", "tecnologia", "tecnologias",
    "informatica", "consultoria", "consultores", "associados",
    "confidencial", "empresa", "multinacional", "vagas",
}


def _identidade_empresa(nome: str) -> frozenset[str]:
    """Palavras que realmente identificam a empresa."""
    return frozenset(
        p for p in normalize(nome).split()
        if p not in _RUIDO_EMPRESA and len(p) > 2
    )


def _mesma_empresa(a: str, b: str) -> bool:
    """Um nome e uma variacao do outro? (subconjunto de palavras identificadoras)"""
    pa, pb = _identidade_empresa(a), _identidade_empresa(b)
    if not pa or not pb:
        return False
    return pa <= pb or pb <= pa


def deduplicate(jobs: list[Job]) -> tuple[list[Job], int]:
    """Devolve (vagas unicas, quantidade removida).

    Passo 1: identidade exata dentro do portal (`source:external_id`).
    Passo 2: mesma vaga anunciada em portais diferentes -- mesmo titulo
             normalizado + mesma empresa normalizada.

    Em empate, vence a ocorrencia com descricao mais longa (mais informacao
    para o classificador).
    """
    by_source_key: dict[str, Job] = {}
    for job in jobs:
        existing = by_source_key.get(job.source_key)
        if existing is None or len(job.description) > len(existing.description):
            if existing is not None:
                job.search_term = existing.search_term or job.search_term
            by_source_key[job.source_key] = job

    by_fingerprint: dict[str, Job] = {}
    for job in by_source_key.values():
        # Vagas sem empresa identificavel nao sao seguras para cruzar entre
        # portais (titulos genericos colidiriam), entao mantemos como unicas.
        # Vale tanto para o campo vazio quanto para rotulos que nao identificam
        # ninguem: duas vagas "Confidencial" com o mesmo titulo sao de empresas
        # diferentes ate prova em contrario.
        if not _identidade_empresa(job.company):
            by_fingerprint[job.source_key] = job
            continue
        existing = by_fingerprint.get(job.fingerprint)
        if existing is None or len(job.description) > len(existing.description):
            by_fingerprint[job.fingerprint] = job

    # Passo 3: mesma vaga em portais diferentes, com o nome da empresa escrito
    # de outro jeito. Exige titulo identico -- ver o docstring do modulo.
    por_titulo: dict[str, list[Job]] = {}
    for job in by_fingerprint.values():
        por_titulo.setdefault(normalize(job.title), []).append(job)

    unique: list[Job] = []
    for grupo in por_titulo.values():
        representantes: list[Job] = []
        for job in grupo:
            for i, escolhido in enumerate(representantes):
                if _mesma_empresa(job.company, escolhido.company):
                    if len(job.description) > len(escolhido.description):
                        representantes[i] = job
                    break
            else:
                representantes.append(job)
        unique.extend(representantes)

    return unique, len(jobs) - len(unique)
