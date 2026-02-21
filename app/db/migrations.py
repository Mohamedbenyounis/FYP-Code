"""
Database initialisation and migrations.

Iteration 2: ``init_db`` creates the SQLite file (if absent), applies the
schema, and enables WAL + foreign-key pragmas.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.services.logging_service import get_logger

_SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"


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
    conn = sqlite3.connect(str(db_path))

    # Pragmas -----------------------------------------------------------
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")

    # Apply schema (idempotent thanks to IF NOT EXISTS) -----------------
    schema_sql = _SCHEMA_FILE.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.commit()

    log.info("Database ready (WAL mode, FK enabled)")
    return conn


def run_migrations(db_path: Path) -> sqlite3.Connection:
    """
    Convenience wrapper kept for backward compat.

    Currently just delegates to :func:`init_db`.  Future iterations can add
    version-based ALTER TABLE logic here.
    """
    return init_db(db_path)
