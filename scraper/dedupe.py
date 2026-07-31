"""Remocao de vagas duplicadas.

Duplicatas aparecem por dois motivos:
  1. o mesmo termo de busca traz a mesma vaga em paginas diferentes;
  2. termos diferentes ("desenvolvedor junior" e "desenvolvedor jr") trazem a
     mesma vaga -- e portais diferentes podem anunciar a mesma posicao.
"""

from __future__ import annotations

from .models import Job


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
        # Vagas sem empresa identificada nao sao seguras para cruzar entre
        # portais (titulos genericos colidiriam), entao mantemos como unicas.
        if not job.company:
            by_fingerprint[job.source_key] = job
            continue
        existing = by_fingerprint.get(job.fingerprint)
        if existing is None or len(job.description) > len(existing.description):
            by_fingerprint[job.fingerprint] = job

    unique = list(by_fingerprint.values())
    return unique, len(jobs) - len(unique)
