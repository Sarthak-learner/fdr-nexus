"""Non-destructive, versioned SQLite compatibility migrations.

The project currently uses SQLAlchemy metadata plus small SQLite migrations
instead of Alembic.  This module makes that existing approach explicit and
auditable without changing existing tables destructively.
"""

from datetime import datetime

from sqlalchemy import inspect


SCHEMA_VERSION = 2


def _record_version(conn, version: int, description: str):
    exists = conn.exec_driver_sql(
        "SELECT 1 FROM schema_migrations WHERE version = ?", (version,)
    ).fetchone()
    if not exists:
        conn.exec_driver_sql(
            "INSERT INTO schema_migrations(version, applied_at, description) VALUES (?, ?, ?)",
            (version, datetime.utcnow().isoformat(), description),
        )


def apply_schema_migrations(engine, metadata):
    """Apply safe upgrades and create missing current-schema tables.

    Existing rows and tables are never dropped, renamed, or rewritten.  A
    failed migration is raised to the caller so the application does not run
    against a partially upgraded schema.
    """
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version INTEGER PRIMARY KEY, "
            "applied_at DATETIME NOT NULL, "
            "description TEXT NOT NULL)"
        )

        inspector = inspect(conn)
        additions = {
            "institutions": {
                "source_details": "TEXT DEFAULT ''",
                "import_job_id": "INTEGER",
            },
            "fdr_records": {
                "source_details": "TEXT DEFAULT ''",
                "import_job_id": "INTEGER",
            },
            "import_jobs": {
                "skipped": "INTEGER DEFAULT 0",
                "status": "TEXT DEFAULT 'completed'",
                "column_mapping": "TEXT DEFAULT '{}'",
                "file_sha256": "TEXT",
                "completed_at": "DATETIME",
                "created_by_user_id": "INTEGER",
            },
            "audit_logs": {
                "actor_user_id": "INTEGER",
                "actor_username": "TEXT",
            },
        }
        for table, columns in additions.items():
            if not inspector.has_table(table):
                continue
            existing = {column["name"] for column in inspect(conn).get_columns(table)}
            for column, definition in columns.items():
                if column not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

        _record_version(conn, 1, "SQLite compatibility columns")

    # SQLAlchemy's create_all is additive: it creates missing tables and
    # indexes while preserving all existing records and table definitions.
    metadata.create_all(engine)

    with engine.begin() as conn:
        _record_version(conn, 2, "Current SQLAlchemy schema and maturity reminders")
