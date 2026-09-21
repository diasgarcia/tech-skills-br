"""Migracoes aditivas do SQLite, executadas apenas pelos comandos de escrita."""

from contextlib import closing

from api.database import connect_sqlite

SCHEMA_VERSION = 3
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
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    if (
        current == SCHEMA_VERSION
        and set(ADDITIONAL_COLUMNS) <= columns
        and "coleta_execucoes" in tables
    ):
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS coleta_execucoes (
                id INTEGER PRIMARY KEY,
                run_key VARCHAR(120) NOT NULL UNIQUE,
                coletada_em DATETIME NOT NULL,
                status VARCHAR(20) NOT NULL,
                escopo_completo BOOLEAN NOT NULL,
                vagas_brutas INTEGER NOT NULL,
                vagas_elegiveis INTEGER NOT NULL,
                requisicoes INTEGER NOT NULL,
                fontes_json TEXT NOT NULL,
                alertas_json TEXT NOT NULL DEFAULT '[]'
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_coleta_execucoes_coletada_em "
            "ON coleta_execucoes (coletada_em)"
        )
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def migrate_database(db_path=None) -> None:
    with closing(connect_sqlite(db_path)) as conn:
        migrate_connection(conn)
