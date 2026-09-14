"""Estado da tentativa e disponibilidade da pagina, separados do booleano legado."""

from enum import StrEnum


class EnrichmentStatus(StrEnum):
    SUCCEEDED = "succeeded"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


def record_attempt(conn, job_id: int, status: EnrichmentStatus, reason: str = "") -> None:
    availability = {
        EnrichmentStatus.SUCCEEDED: "available",
        EnrichmentStatus.UNAVAILABLE: "unavailable",
    }.get(status)
    conn.execute(
        "UPDATE vagas SET enrichment_status = ?, enrichment_reason = ?, "
        "enrichment_attempted_at = CURRENT_TIMESTAMP, "
        "advertisement_status = COALESCE(?, advertisement_status) WHERE id = ?",
        (str(status), reason or None, availability, job_id),
    )
