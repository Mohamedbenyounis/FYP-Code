"""
Database initialisation and migrations.

Iteration 3: ``init_db`` creates the SQLite file (if absent), applies the
schema, migrates the events table if the old Iteration 2 schema is detected,
and enables WAL + foreign-key pragmas.

Iteration 5: Adds ``_bootstrap_default_admin`` which seeds one admin user
the first time the database is opened (when ``admin_users`` is empty).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from datetime import datetime, timezone

from app import config
from app.services.logging_service import get_logger

_SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"


def _migrate_events_table(conn: sqlite3.Connection, log) -> None:
    """
    Detect the old Iteration 2 events schema and replace it.

    The old table had columns: id (INTEGER), person_id, event_type,
    confidence, similarity_score, snapshot_path, created_at.

    The new Iteration 3 table has: id (TEXT UUID), status, person_name,
    person_id, score, bbox_json, snapshot_path, clip_path, created_at.

    Since the table held no production data (no code populated it before
    Iteration 3), we simply DROP + recreate.
    """
    cursor = conn.execute("PRAGMA table_info(events);")
    columns = {row[1] for row in cursor.fetchall()}

    if "event_type" in columns and "status" not in columns:
        log.info("Migrating events table from Iteration 2 → 3 schema")
        conn.execute("DROP TABLE IF EXISTS events;")
        # Also drop old indices that reference removed columns
        conn.execute("DROP INDEX IF EXISTS idx_events_person_id;")
        conn.commit()


def init_db(db_path: Path) -> sqlite3.Connection:
    """
    Ensure the database exists, apply schema, and return a ready connection.

    * Creates parent directories if needed.
    * Sets ``journal_mode=WAL`` for safe concurrent reads.
    * Enables ``foreign_keys=ON``.
    * Executes ``schema.sql`` via ``executescript`` (IF NOT EXISTS is safe to
      re-run on every startup).

    Parameters
    ----------
    db_path : Path
        Full path to the SQLite database file.

    Returns
    -------
    sqlite3.Connection
        An open connection with pragmas already applied.
    """
    log = get_logger()

    # Ensure directory tree exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    log.info("Opening database at %s", db_path)
    # The dashboard serves requests in a threaded dev server; allow one
    # process-owned connection to be accessed across those request threads.
    conn = sqlite3.connect(str(db_path), check_same_thread=False)

    # Pragmas -----------------------------------------------------------
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")

    # Migrate old events table (Iteration 2 → 3) ----------------------
    _migrate_events_table(conn, log)

    # Apply schema (idempotent thanks to IF NOT EXISTS) -----------------
    schema_sql = _SCHEMA_FILE.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.commit()

    # Bootstrap default admin if none exists (Iteration 5) ------------
    _bootstrap_default_admin(conn, log)

    log.info("Database ready (WAL mode, FK enabled)")
    return conn


def run_migrations(db_path: Path) -> sqlite3.Connection:
    """
    Convenience wrapper kept for backward compat.

    Currently just delegates to :func:`init_db`.  Future iterations can add
    version-based ALTER TABLE logic here.
    """
    return init_db(db_path)


def _bootstrap_default_admin(conn: sqlite3.Connection, log) -> None:
    """
    Seed one initial admin user if the ``admin_users`` table is empty.

    Credentials are read from env vars:
    - ``SV_BOOTSTRAP_ADMIN_USERNAME``
    - ``SV_BOOTSTRAP_ADMIN_PASSWORD``

    If either value is missing, bootstrap is skipped to avoid insecure
    hardcoded defaults.

    This function is idempotent — it checks ``COUNT(*)`` before inserting,
    so running it many times is safe.
    """
    # Lazy import to avoid heavy dependency for non-dashboard code paths
    from werkzeug.security import generate_password_hash

    cursor = conn.execute("SELECT COUNT(*) FROM admin_users")
    count = cursor.fetchone()[0]
    if count > 0:
        return

    default_username = config.BOOTSTRAP_ADMIN_USERNAME
    default_password = config.BOOTSTRAP_ADMIN_PASSWORD

    if not default_username or not default_password:
        log.warning(
            "SECURITY: admin_users is empty but bootstrap credentials are not "
            "configured. Set SV_BOOTSTRAP_ADMIN_USERNAME and "
            "SV_BOOTSTRAP_ADMIN_PASSWORD to create the first admin."
        )
        return

    password_hash = generate_password_hash(default_password)
    now_iso = datetime.now(timezone.utc).isoformat()

    conn.execute(
        "INSERT INTO admin_users (username, password_hash, created_at) "
        "VALUES (?, ?, ?)",
        (default_username, password_hash, now_iso),
    )
    conn.commit()

    log.warning(
        "SECURITY: Bootstrap admin created (username='%s'). "
        "Rotate this password after first login.",
        default_username,
    )
