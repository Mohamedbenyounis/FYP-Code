"""
Repository pattern for person, embedding, and event persistence.

All SQL lives here — no other module imports ``sqlite3``.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional

import numpy as np

from app import config
from app.core.models import EnrolledPerson, Event
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

    def list_person_summaries(self) -> List[dict]:
        """
        Return safe person metadata for dashboard display.

        This intentionally excludes raw embedding blob data.
        """
        cursor = self._conn.execute(
            "SELECT p.id, p.name, p.created_at, "
            "       COUNT(pe.id) AS embedding_count "
            "FROM persons p "
            "LEFT JOIN person_embeddings pe ON pe.person_id = p.id "
            "GROUP BY p.id, p.name, p.created_at "
            "ORDER BY p.id"
        )
        rows = cursor.fetchall()
        return [
            {
                "person_id": row[0],
                "name": row[1],
                "created_at": row[2],
                "embedding_count": row[3],
            }
            for row in rows
        ]

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

    def count_persons(self) -> int:
        """Return total number of enrolled persons."""
        cursor = self._conn.execute("SELECT COUNT(*) FROM persons")
        return cursor.fetchone()[0]

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
# SQLite embedding repository  (ML Integration — raw per-shot storage)
# =====================================================================

class SQLiteEmbeddingRepository:
    """
    Stores the raw per-shot embeddings for each enrolled person.

    ``persons.embedding`` holds the **computed template** (mean of raw
    embeddings, L2-normalised).  This table keeps every individual capture
    so that the template can be recomputed when new shots are added.

    The ``MAX_GALLERY_EMBEDDINGS`` cap is enforced on insert: when the
    limit is reached the oldest row for that person is deleted before the
    new one is written.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._log = get_logger()

    # ------------------------------------------------------------------ read

    def get_embeddings(self, person_id: int) -> List[np.ndarray]:
        """Return all raw embeddings for *person_id*, oldest-first."""
        cursor = self._conn.execute(
            "SELECT embedding, embedding_dim, dtype "
            "FROM person_embeddings WHERE person_id = ? "
            "ORDER BY created_at ASC",
            (person_id,),
        )
        results: List[np.ndarray] = []
        for blob, dim, dtype_str in cursor.fetchall():
            try:
                emb = np.frombuffer(blob, dtype=np.dtype(dtype_str))
                if emb.shape[0] == dim:
                    results.append(emb.copy())
            except Exception:  # noqa: BLE001
                self._log.warning(
                    "Skipping corrupt embedding for person_id=%d", person_id
                )
        return results

    def count_embeddings(self, person_id: int) -> int:
        """Return the number of raw embeddings stored for *person_id*."""
        cursor = self._conn.execute(
            "SELECT COUNT(*) FROM person_embeddings WHERE person_id = ?",
            (person_id,),
        )
        return cursor.fetchone()[0]

    # ------------------------------------------------------------------ write

    def add_embedding(self, person_id: int, embedding: np.ndarray) -> None:
        """
        Insert a new raw embedding.

        If the person already has ``MAX_GALLERY_EMBEDDINGS`` rows, the
        oldest is deleted first so the cap is never exceeded.
        """
        max_emb = config.MAX_GALLERY_EMBEDDINGS
        current = self.count_embeddings(person_id)

        if current >= max_emb:
            # Delete the oldest row(s) that exceed the limit
            excess = current - max_emb + 1
            self._conn.execute(
                "DELETE FROM person_embeddings WHERE id IN ("
                "  SELECT id FROM person_embeddings "
                "  WHERE person_id = ? ORDER BY created_at ASC LIMIT ?"
                ")",
                (person_id, excess),
            )

        blob = embedding.astype(np.float32).tobytes()
        dim = embedding.shape[0]
        now_iso = datetime.now(timezone.utc).isoformat()

        self._conn.execute(
            "INSERT INTO person_embeddings "
            "(person_id, embedding, embedding_dim, dtype, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (person_id, blob, dim, "float32", now_iso),
        )
        self._conn.commit()
        self._log.info(
            "Stored raw embedding for person_id=%d (dim=%d, count=%d/%d)",
            person_id, dim, min(current + 1, max_emb), max_emb,
        )

    def delete_embeddings(self, person_id: int) -> int:
        """Delete all raw embeddings for *person_id*.  Returns rows deleted."""
        cursor = self._conn.execute(
            "DELETE FROM person_embeddings WHERE person_id = ?",
            (person_id,),
        )
        self._conn.commit()
        return cursor.rowcount


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


# =====================================================================
# SQLite event repository  (Iteration 3)
# =====================================================================

class SQLiteEventRepository:
    """
    SQLite-backed event repository.

    Persists ``Event`` objects emitted by the ``EventManager``.
    Shares the same ``sqlite3.Connection`` as ``SQLitePersonRepository``
    (single-thread MVP model — see architecture docs).
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._log = get_logger()

    def add_event(self, event: Event) -> None:
        """Insert a confirmed presence event."""
        self._conn.execute(
            "INSERT INTO events "
            "(id, status, person_name, person_id, score, bbox_json, "
            " snapshot_path, clip_path, track_key, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event.event_id,
                event.status,
                event.person_name,
                event.person_id,
                event.score,
                event.bbox_json,
                event.snapshot_path,
                event.clip_path,
                event.track_key,
                event.created_at,
            ),
        )
        self._conn.commit()
        self._log.info(
            "Persisted event %s  status=%s  person=%s  track=%s",
            event.event_id,
            event.status,
            event.person_name or "unknown",
            event.track_key or "-",
        )

    def list_events(
        self,
        limit: int = 50,
        status: Optional[str] = None,
    ) -> List[Event]:
        """
        Return the most recent events, newest first.

        Parameters
        ----------
        limit : int
            Maximum rows to return.
        status : str | None
            If supplied, filter to this status only (e.g. ``"authorised"``).
        """
        if status is not None:
            cursor = self._conn.execute(
                "SELECT id, status, person_name, person_id, score, "
                "       bbox_json, snapshot_path, clip_path, track_key, "
                "       created_at "
                "FROM events WHERE status = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            )
        else:
            cursor = self._conn.execute(
                "SELECT id, status, person_name, person_id, score, "
                "       bbox_json, snapshot_path, clip_path, track_key, "
                "       created_at "
                "FROM events ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )

        results: List[Event] = []
        for row in cursor.fetchall():
            results.append(
                Event(
                    event_id=row[0],
                    created_at=row[9],
                    status=row[1],
                    person_name=row[2],
                    person_id=row[3],
                    score=row[4],
                    bbox_json=row[5],
                    snapshot_path=row[6],
                    clip_path=row[7],
                    track_key=row[8],
                )
            )
        return results

    def update_event_snapshot(self, event_id: str, snapshot_path: str) -> bool:
        """Update the snapshot path for an existing event row."""
        cursor = self._conn.execute(
            "UPDATE events SET snapshot_path = ? WHERE id = ?",
            (snapshot_path, event_id),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def update_event_clip(self, event_id: str, clip_path: str) -> bool:
        """Update the clip path for an existing event row."""
        cursor = self._conn.execute(
            "UPDATE events SET clip_path = ? WHERE id = ?",
            (clip_path, event_id),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def get_event_by_id(self, event_id: str) -> Optional[Event]:
        """Fetch a single event by its UUID primary key."""
        cursor = self._conn.execute(
            "SELECT id, status, person_name, person_id, score, "
            "       bbox_json, snapshot_path, clip_path, track_key, "
            "       created_at "
            "FROM events WHERE id = ?",
            (event_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return Event(
            event_id=row[0],
            status=row[1],
            person_name=row[2],
            person_id=row[3],
            score=row[4],
            bbox_json=row[5],
            snapshot_path=row[6],
            clip_path=row[7],
            track_key=row[8],
            created_at=row[9],
        )

    def count_events(self, status: Optional[str] = None) -> int:
        """Return total event count, optionally filtered by status."""
        if status is not None:
            cursor = self._conn.execute(
                "SELECT COUNT(*) FROM events WHERE status = ?", (status,)
            )
        else:
            cursor = self._conn.execute("SELECT COUNT(*) FROM events")
        return cursor.fetchone()[0]

    def count_events_since(self, dt: datetime, status: Optional[str] = None) -> int:
        """Return the number of events recorded after the given datetime."""
        iso_str = dt.isoformat()
        if status is not None:
            cursor = self._conn.execute(
                "SELECT COUNT(*) FROM events WHERE status = ? AND created_at >= ?", 
                (status, iso_str)
            )
        else:
            cursor = self._conn.execute(
                "SELECT COUNT(*) FROM events WHERE created_at >= ?", 
                (iso_str,)
            )
        return cursor.fetchone()[0]

# =====================================================================
# Admin user repository  (Iteration 5 — Dashboard auth)
# =====================================================================

class AdminRepository:
    """
    Repository for ``admin_users`` table.

    All dashboard authentication SQL lives here.
    Routes interact only via the public methods below.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_by_username(self, username: str) -> Optional[dict]:
        """
        Return a minimal admin record or ``None`` if not found.

        Returned dict keys: ``id``, ``username``, ``password_hash``.
        Raw embedding blobs or other internals are never exposed.
        """
        cursor = self._conn.execute(
            "SELECT id, username, password_hash, role, email "
            "FROM admin_users WHERE username = ?",
            (username,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        # Fallback to 'admin' if the role column is unexpectedly missing/null during migration
        role_val = row[3] if len(row) > 3 and row[3] else 'admin'
        email_val = row[4] if len(row) > 4 else None
        return {
            "id": row[0], 
            "username": row[1], 
            "password_hash": row[2], 
            "role": role_val,
            "email": email_val
        }

    def add_user(self, username: str, password_hash: str, role: str, email: str | None = None) -> None:
        """Insert a new user with a specific role and optional email."""
        now_iso = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO admin_users (username, password_hash, role, email, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (username, password_hash, role, email, now_iso),
        )
        self._conn.commit()

    def list_users(self) -> list[dict]:
        """Return a list of all users, excluding password hashes."""
        cursor = self._conn.execute(
            "SELECT id, username, role, email, created_at FROM admin_users ORDER BY id"
        )
        return [
            {
                "id": row[0], 
                "username": row[1], 
                "role": row[2], 
                "email": row[3],
                "created_at": row[4]
            } 
            for row in cursor.fetchall()
        ]

    def update_user_email(self, user_id: int, email: str | None) -> bool:
        """Update a user's email address. Returns True if successful."""
        cursor = self._conn.execute(
            "UPDATE admin_users SET email = ? WHERE id = ?",
            (email, user_id)
        )
        self._conn.commit()
        return cursor.rowcount > 0
        
    def delete_user(self, user_id: int) -> bool:
        """Delete a user by ID. Returns True if successful."""
        cursor = self._conn.execute("DELETE FROM admin_users WHERE id = ?", (user_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    def count(self) -> int:
        """Return total number of admin users."""
        cursor = self._conn.execute("SELECT COUNT(*) FROM admin_users")
        return cursor.fetchone()[0]


# =====================================================================
# Alert repository  (Iteration 11)
# =====================================================================

class SQLiteAlertRepository:
    """
    Repository for the alerts table.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add_alert(self, event_id: str, alert_type: str, message: str) -> None:
        """Insert a new alert linked to an event."""
        now_iso = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO alerts (event_id, alert_type, message, created_at) "
            "VALUES (?, ?, ?, ?)",
            (event_id, alert_type, message, now_iso),
        )
        self._conn.commit()

    def list_alerts(self, limit: int = 50, include_acknowledged: bool = False) -> List[dict]:
        """Fetch latest alerts. Default excludes acknowledged alerts."""
        if include_acknowledged:
            cursor = self._conn.execute(
                "SELECT id, event_id, alert_type, message, created_at, status "
                "FROM alerts ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
        else:
            cursor = self._conn.execute(
                "SELECT id, event_id, alert_type, message, created_at, status "
                "FROM alerts WHERE status != 'acknowledged' ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
            
        return [
            {
                "id": row[0],
                "event_id": row[1],
                "alert_type": row[2],
                "message": row[3],
                "created_at": row[4],
                "status": row[5] if len(row) > 5 else 'new'
            }
            for row in cursor.fetchall()
        ]

    def acknowledge_alert(self, alert_id: int) -> bool:
        """Mark an alert as acknowledged."""
        now_iso = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            "UPDATE alerts SET status = 'acknowledged', acknowledged_at = ? WHERE id = ?",
            (now_iso, alert_id)
        )
        self._conn.commit()
        return cursor.rowcount > 0
        
    def count_alerts(self) -> int:
        """Return total number of alerts."""
        cursor = self._conn.execute("SELECT COUNT(*) FROM alerts")
        return cursor.fetchone()[0]

    def count_alerts_since(self, dt: datetime) -> int:
        """Return the number of alerts recorded after the given datetime."""
        cursor = self._conn.execute(
            "SELECT COUNT(*) FROM alerts WHERE created_at >= ?", 
            (dt.isoformat(),)
        )
        return cursor.fetchone()[0]
