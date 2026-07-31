"""Normalizacao das datas de publicacao para um unico tipo DATE.

Os portais escrevem a data de tres jeitos diferentes:

    Gupy         2026-06-26     (ISO)
    Vagas.com    09/07/2026     (dd/mm/aaaa)
    Vagas.com    "Ontem", "Há 3 dias", "Há mais de 30 dias"   (relativo)

As datas relativas so significam alguma coisa em relacao ao momento da coleta.
Por isso a conversao recebe a **data de geracao do CSV** como referencia, e nao
a data de hoje: importar um CSV de duas semanas atras tem que produzir as mesmas
datas que produziria no dia da coleta.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path

# vagas_20260731_174407.csv -> 2026-07-31
_STAMP_RE = re.compile(r"(\d{8})_(\d{6})")
_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_BR_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_DAYS_AGO_RE = re.compile(r"h[aá]\s+(?:mais\s+de\s+)?(\d+)\s+dias?")
_MONTHS_AGO_RE = re.compile(r"h[aá]\s+(?:mais\s+de\s+)?(\d+)\s+m[eê]s(?:es)?")

# A ordem importa e o limite de palavra tambem: "anteontem" contem "ontem",
# entao a forma mais especifica precisa ser testada primeiro.
_RELATIVE_DAYS = (
    (re.compile(r"\banteontem\b"), 2),
    (re.compile(r"\bontem\b"), 1),
    (re.compile(r"\bhoje\b"), 0),
)


def reference_date_from_csv(path: str | Path) -> date:
    """Data de geracao do CSV, tirada do timestamp no nome do arquivo.

    Se o nome nao tiver timestamp, cai para a data de modificacao do arquivo.
    """
    path = Path(path)
    match = _STAMP_RE.search(path.name)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y%m%d").date()
        except ValueError:
            pass
    return datetime.fromtimestamp(path.stat().st_mtime).date()


def parse_published_date(raw: str | None, reference: date) -> date | None:
    """Converte o texto do portal em `date`. Devolve None se nao der para saber.

    `reference` e a data em que o dado foi gerado -- e sobre ela que as
    expressoes relativas ("Ontem", "Há 3 dias") sao resolvidas.
    """
    if not raw:
        return None

    text = raw.strip()
    if not text:
        return None

    iso = _ISO_RE.match(text)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None

    br = _BR_RE.match(text)
    if br:
        try:
            return date(int(br.group(3)), int(br.group(2)), int(br.group(1)))
        except ValueError:
            return None

    lowered = text.lower()

    for pattern, days in _RELATIVE_DAYS:
        if pattern.search(lowered):
            return reference - timedelta(days=days)

    days_ago = _DAYS_AGO_RE.search(lowered)
    if days_ago:
        return reference - timedelta(days=int(days_ago.group(1)))

    months_ago = _MONTHS_AGO_RE.search(lowered)
    if months_ago:
        return reference - timedelta(days=30 * int(months_ago.group(1)))

    return None
