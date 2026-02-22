"""
Repository pattern for person (enrolled-identity) persistence.

All SQL lives here — no other module imports ``sqlite3``.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional

import numpy as np

from app.core.models import EnrolledPerson
from app.services.logging_service import get_logger


# =====================================================================
# In-memory repository  (kept for unit tests / ML-disabled mode)
# =====================================================================

class InMemoryPersonRepository:
    """In-memory person repository — useful for tests and Iteration 1 compat."""

    def __init__(self) -> None:
        self._persons: List[EnrolledPerson] = []
        self._next_id: int = 1

    def get_all(self) -> List[EnrolledPerson]:
        """Return a copy of all enrolled persons."""
        return self._persons.copy()

    def get_by_id(self, person_id: int) -> Optional[EnrolledPerson]:
        """Get person by ID."""
        for p in self._persons:
            if p.person_id == person_id:
                return p
        return None

    def get_by_name(self, name: str) -> Optional[EnrolledPerson]:
        """Get person by name (case-insensitive)."""
        lower = name.lower()
        for p in self._persons:
            if p.name.lower() == lower:
                return p
        return None

    def add_person(self, name: str, embedding: np.ndarray) -> EnrolledPerson:
        """Add and return a new enrolled person."""
        person = EnrolledPerson(
            person_id=self._next_id,
            name=name,
            embedding=embedding,
        )
        self._persons.append(person)
        self._next_id += 1
        return person

    def delete_person(self, person_id: int) -> bool:
        """Delete a person by ID.  Returns True if found."""
        before = len(self._persons)
        self._persons = [p for p in self._persons if p.person_id != person_id]
        return len(self._persons) < before

    def clear(self) -> None:
        """Remove all persons."""
        self._persons.clear()
        self._next_id = 1


# =====================================================================
# SQLite repository  (Iteration 2)
# =====================================================================

class SQLitePersonRepository:
    """
    SQLite-backed person repository.

    The ``conn`` must already be initialised via :func:`db.migrations.init_db`
    so that tables exist and pragmas are set.

    **Threading / lifecycle note:**  ``sqlite3.Connection`` objects are
    **not** thread-safe by default.  The current MVP uses a single
    connection owned by ``main.py`` and shared with this repository.
    When the Flask dashboard (Iteration 5) introduces a second thread,
    each thread must own its own connection — or use
    ``check_same_thread=False`` with external locking.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._log = get_logger()

    # ------------------------------------------------------------------ read

    def get_all(self) -> List[EnrolledPerson]:
        """Return every enrolled person with their embedding restored."""
        cursor = self._conn.execute(
            "SELECT id, name, embedding, embedding_dim, dtype FROM persons "
            "ORDER BY id"
        )
        results: List[EnrolledPerson] = []
        for row in cursor.fetchall():
            person = self._row_to_person(row)
            if person is not None:
                results.append(person)
        return results

    def get_by_id(self, person_id: int) -> Optional[EnrolledPerson]:
        """Get a single person by primary key."""
        cursor = self._conn.execute(
            "SELECT id, name, embedding, embedding_dim, dtype "
            "FROM persons WHERE id = ?",
            (person_id,),
        )
        row = cursor.fetchone()
        return self._row_to_person(row) if row else None

    def get_by_name(self, name: str) -> Optional[EnrolledPerson]:
        """Get a person by exact name (case-insensitive via COLLATE NOCASE)."""
        cursor = self._conn.execute(
            "SELECT id, name, embedding, embedding_dim, dtype "
            "FROM persons WHERE name = ? COLLATE NOCASE",
            (name,),
        )
        row = cursor.fetchone()
        return self._row_to_person(row) if row else None

    # ------------------------------------------------------------------ write

    def add_person(self, name: str, embedding: np.ndarray) -> EnrolledPerson:
        """
        Insert a new enrolled person.

        Stores the embedding as ``np.float32.tobytes()`` alongside dimension
        and dtype metadata for safe round-tripping.

        Raises
        ------
        sqlite3.IntegrityError
            If ``name`` already exists (UNIQUE constraint).
        """
        blob = embedding.astype(np.float32).tobytes()
        dim = embedding.shape[0]
        now_iso = datetime.now(timezone.utc).isoformat()

        cursor = self._conn.execute(
            "INSERT INTO persons (name, embedding, embedding_dim, dtype, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, blob, dim, "float32", now_iso),
        )
        self._conn.commit()

        person_id = cursor.lastrowid
        self._log.info("Enrolled '%s' (id=%d, dim=%d)", name, person_id, dim)
        return EnrolledPerson(person_id=person_id, name=name, embedding=embedding)

    def update_embedding(self, person_id: int, embedding: np.ndarray) -> bool:
        """Replace the embedding for an existing person.  Returns True if found."""
        blob = embedding.astype(np.float32).tobytes()
        dim = embedding.shape[0]

        cursor = self._conn.execute(
            "UPDATE persons SET embedding = ?, embedding_dim = ? WHERE id = ?",
            (blob, dim, person_id),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def delete_person(self, person_id: int) -> bool:
        """Delete a person by primary key.  Returns True if a row was deleted."""
        cursor = self._conn.execute(
            "DELETE FROM persons WHERE id = ?", (person_id,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    # ------------------------------------------------------------------ helpers

    # Allowed dtypes for embedding storage — extend if needed.
    _ALLOWED_DTYPES = frozenset({"float32", "float64"})

    @staticmethod
    def _row_to_person(row: tuple) -> Optional[EnrolledPerson]:
        """Convert a raw DB row → EnrolledPerson, restoring the numpy array."""
        log = get_logger()
        pid, name, blob, dim, dtype_str = row

        if dim is None or dim <= 0:
            log.warning("Skipping person id=%s: invalid dim=%s", pid, dim)
            return None

        if dtype_str not in SQLitePersonRepository._ALLOWED_DTYPES:
            log.warning(
                "Skipping person id=%s: unsupported dtype '%s'", pid, dtype_str
            )
            return None

        try:
            dt = np.dtype(dtype_str)
            emb = np.frombuffer(blob, dtype=dt)
            if emb.shape[0] != dim:
                log.warning(
                    "Skipping person id=%s: shape mismatch %s vs dim=%d",
                    pid, emb.shape, dim,
                )
                return None
            return EnrolledPerson(person_id=pid, name=name, embedding=emb)
        except Exception:  # noqa: BLE001
            log.warning("Skipping person id=%s: failed to decode embedding", pid)
            return None


# =====================================================================
# Provider factory — used by FacePipeline for dependency injection
# =====================================================================

def make_enrolled_provider(
    repo: SQLitePersonRepository,
) -> Callable[[], List[EnrolledPerson]]:
    """
    Return a zero-arg callable that the ML pipeline calls to refresh its
    enrolled gallery.  This keeps SQL out of ``ml/pipeline.py``.
    """
    def _provider() -> List[EnrolledPerson]:
        return repo.get_all()
    return _provider
