"""Seletores compartilhados da fila de enriquecimento.

O flag legado indica tentativa resolvida, nao necessariamente anuncio expirado.
"""

JANELA_TENTATIVA_DIAS = 30
MIN_DESCRICAO_VAGAS_COM = 500
MIN_DESCRICAO_TRAMPOS = 100
MIN_DESCRICAO_INFOJOBS = 160

QUERY_LINKEDIN_PENDENTES = """
    SELECT id, external_id, title, url, location, workplace_type,
           workplace_declared
    FROM vagas
    WHERE source = 'linkedin'
      AND COALESCE(enrich_encerrada, 0) = 0
      AND (description IS NULL OR LENGTH(description) < 30)
"""

QUERY_VAGAS_PENDENTES = """
    SELECT id, url, title FROM vagas
    WHERE source = 'vagas'
      AND COALESCE(enrich_encerrada, 0) = 0
      AND (description IS NULL OR LENGTH(description) < ?
           OR description LIKE '%...')
"""

QUERY_TRAMPOS_PENDENTES = """
    SELECT id, url, title FROM vagas
    WHERE source = 'trampos'
      AND COALESCE(enrich_encerrada, 0) = 0
      AND (description IS NULL OR LENGTH(description) < ?)
      AND (published_date IS NULL OR published_date >= date('now', ?))
"""

QUERY_GUPY_PENDENTES = """
    SELECT id, url, title FROM vagas
    WHERE source = 'gupy'
      AND COALESCE(enrich_encerrada, 0) = 0
      AND url LIKE '%://%.gupy.io/%'
"""

QUERY_GEEKHUNTER_PENDENTES = """
    SELECT id, url, title FROM vagas
    WHERE source = 'geekhunter'
      AND COALESCE(enrich_encerrada, 0) = 0
      AND (
          description IS NULL OR LENGTH(description) < 300
          OR company LIKE '%-%'
          OR published_date IS NULL
      )
"""

QUERY_INFOJOBS_PENDENTES = """
    SELECT id, url, title FROM vagas
    WHERE source = 'infojobs'
      AND COALESCE(enrich_encerrada, 0) = 0
      AND (description IS NULL OR LENGTH(description) < ?
           OR description LIKE '%...')
"""

QUERY_GUPY_FORCADO = "SELECT id, url, title FROM vagas WHERE source = 'gupy'"
QUERY_GEEKHUNTER_FORCADO = "SELECT id, url, title FROM vagas WHERE source = 'geekhunter'"
QUERY_INFOJOBS_FORCADO = """
    SELECT id, url, title FROM vagas
    WHERE source = 'infojobs'
      AND (
          description IS NULL OR LENGTH(description) <= ?
          OR description LIKE '%...'
      )
"""


def pending_queries(window_days: int = JANELA_TENTATIVA_DIAS) -> dict[str, tuple[str, tuple]]:
    """Devolve as filas normais, com os parametros usados pelos comandos."""
    return {
        "vagas.com": (QUERY_VAGAS_PENDENTES, (MIN_DESCRICAO_VAGAS_COM,)),
        "trampos": (QUERY_TRAMPOS_PENDENTES, (MIN_DESCRICAO_TRAMPOS, f"-{window_days} days")),
        "gupy": (QUERY_GUPY_PENDENTES, ()),
        "geekhunter": (QUERY_GEEKHUNTER_PENDENTES, ()),
        "linkedin": (QUERY_LINKEDIN_PENDENTES, ()),
        "infojobs": (QUERY_INFOJOBS_PENDENTES, (MIN_DESCRICAO_INFOJOBS,)),
    }
