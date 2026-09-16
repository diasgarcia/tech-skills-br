"""Migracoes aditivas do SQLite, executadas apenas pelos comandos de escrita."""

from contextlib import closing

from api.database import connect_sqlite

SCHEMA_VERSION = 2
ADDITIONAL_COLUMNS = {
    "regiao": "VARCHAR(40)",
    "polo": "VARCHAR(60)",
    "enrich_encerrada": "INTEGER DEFAULT 0",
    "enrichment_status": "VARCHAR(24) DEFAULT 'pending'",
    "enrichment_reason": "TEXT",
    "enrichment_attempted_at": "DATETIME",
    "advertisement_status": "VARCHAR(24) DEFAULT 'unknown'",
    "workplace_declared": "INTEGER NOT NULL DEFAULT 0",
}


def migrate_connection(conn) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(vagas)")}
    if not columns:
        raise ValueError("O banco selecionado nao possui a tabela vagas.")
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current > SCHEMA_VERSION:
        raise ValueError("O banco usa uma versao de esquema mais nova que este codigo.")
    if current == SCHEMA_VERSION and set(ADDITIONAL_COLUMNS) <= columns:
        return
    if conn.in_transaction:
        raise ValueError("Conclua a transacao atual antes de migrar o esquema.")
    conn.execute("BEGIN IMMEDIATE")
    with conn:
        for name, sql_type in ADDITIONAL_COLUMNS.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE vagas ADD COLUMN {name} {sql_type}")
        if "enrichment_status" not in columns:
            conn.execute(
                "UPDATE vagas SET enrichment_status = 'legacy_resolved' "
                "WHERE COALESCE(enrich_encerrada, 0) = 1"
            )
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def migrate_database(db_path=None) -> None:
    with closing(connect_sqlite(db_path)) as conn:
        migrate_connection(conn)
