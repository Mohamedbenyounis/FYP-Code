"""
Tests for Iteration 2 — database repository layer.

Run with:  pytest tests/test_db_repo.py -v
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest

from app.core.models import EnrolledPerson, Event
from app.db.migrations import init_db
from app.db.repo import (
    InMemoryPersonRepository,
    SQLiteEmbeddingRepository,
    SQLiteEventRepository,
    SQLitePersonRepository,
    make_enrolled_provider,
)


# ===================================================================
# Helpers
# ===================================================================

def _random_embedding(dim: int = 512) -> np.ndarray:
    """Return a random unit-length float32 embedding."""
    vec = np.random.randn(dim).astype(np.float32)
    vec /= np.linalg.norm(vec)
    return vec


def _make_sqlite_repo(tmp_path: Path) -> tuple[sqlite3.Connection, SQLitePersonRepository]:
    """Create a fresh SQLite repo backed by a temp file."""
    db_path = tmp_path / "test.sqlite"
    conn = init_db(db_path)
    return conn, SQLitePersonRepository(conn)


# ===================================================================
# init_db
# ===================================================================

class TestInitDb:
    """Database initialisation must create tables and set pragmas."""

    def test_creates_db_file(self, tmp_path: Path) -> None:
        db_path = tmp_path / "subdir" / "test.sqlite"
        conn = init_db(db_path)
        assert db_path.exists()
        conn.close()

    def test_wal_mode(self, tmp_path: Path) -> None:
        conn = init_db(tmp_path / "test.sqlite")
        mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        assert mode.lower() == "wal"
        conn.close()

    def test_foreign_keys_on(self, tmp_path: Path) -> None:
        conn = init_db(tmp_path / "test.sqlite")
        fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        assert fk == 1
        conn.close()

    def test_persons_table_exists(self, tmp_path: Path) -> None:
        conn = init_db(tmp_path / "test.sqlite")
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='persons'"
        )
        assert cur.fetchone() is not None
        conn.close()

    def test_events_table_exists(self, tmp_path: Path) -> None:
        conn = init_db(tmp_path / "test.sqlite")
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='events'"
        )
        assert cur.fetchone() is not None
        conn.close()

    def test_idempotent(self, tmp_path: Path) -> None:
        """Calling init_db twice must not fail."""
        db_path = tmp_path / "test.sqlite"
        conn1 = init_db(db_path)
        conn1.close()
        conn2 = init_db(db_path)
        conn2.close()


# ===================================================================
# InMemoryPersonRepository
# ===================================================================

class TestInMemoryRepo:
    def test_add_and_get_all(self) -> None:
        repo = InMemoryPersonRepository()
        emb = _random_embedding()
        person = repo.add_person("Alice", emb)
        assert person.name == "Alice"
        assert len(repo.get_all()) == 1

    def test_get_by_id(self) -> None:
        repo = InMemoryPersonRepository()
        p = repo.add_person("Bob", _random_embedding())
        assert repo.get_by_id(p.person_id) is not None
        assert repo.get_by_id(999) is None

    def test_get_by_name_case_insensitive(self) -> None:
        repo = InMemoryPersonRepository()
        repo.add_person("Charlie", _random_embedding())
        assert repo.get_by_name("charlie") is not None
        assert repo.get_by_name("CHARLIE") is not None
        assert repo.get_by_name("Nope") is None

    def test_delete(self) -> None:
        repo = InMemoryPersonRepository()
        p = repo.add_person("Dave", _random_embedding())
        assert repo.delete_person(p.person_id) is True
        assert repo.get_all() == []
        assert repo.delete_person(p.person_id) is False

    def test_clear(self) -> None:
        repo = InMemoryPersonRepository()
        repo.add_person("A", _random_embedding())
        repo.add_person("B", _random_embedding())
        repo.clear()
        assert repo.get_all() == []


# ===================================================================
# SQLitePersonRepository
# ===================================================================

class TestSQLiteRepo:
    def test_add_and_get_all(self, tmp_path: Path) -> None:
        conn, repo = _make_sqlite_repo(tmp_path)
        emb = _random_embedding()
        person = repo.add_person("Alice", emb)

        assert person.person_id is not None
        assert person.name == "Alice"

        all_persons = repo.get_all()
        assert len(all_persons) == 1
        assert all_persons[0].name == "Alice"
        np.testing.assert_allclose(all_persons[0].embedding, emb, atol=1e-6)
        conn.close()

    def test_get_by_id(self, tmp_path: Path) -> None:
        conn, repo = _make_sqlite_repo(tmp_path)
        p = repo.add_person("Bob", _random_embedding())
        found = repo.get_by_id(p.person_id)
        assert found is not None
        assert found.name == "Bob"
        assert repo.get_by_id(999) is None
        conn.close()

    def test_get_by_name(self, tmp_path: Path) -> None:
        conn, repo = _make_sqlite_repo(tmp_path)
        repo.add_person("Charlie", _random_embedding())
        assert repo.get_by_name("Charlie") is not None
        assert repo.get_by_name("charlie") is not None  # case-insensitive
        assert repo.get_by_name("Nope") is None
        conn.close()

    def test_duplicate_name_raises(self, tmp_path: Path) -> None:
        conn, repo = _make_sqlite_repo(tmp_path)
        repo.add_person("Dave", _random_embedding())
        with pytest.raises(sqlite3.IntegrityError):
            repo.add_person("Dave", _random_embedding())
        conn.close()

    def test_update_embedding(self, tmp_path: Path) -> None:
        conn, repo = _make_sqlite_repo(tmp_path)
        old_emb = _random_embedding()
        p = repo.add_person("Eve", old_emb)

        new_emb = _random_embedding()
        assert repo.update_embedding(p.person_id, new_emb) is True

        updated = repo.get_by_id(p.person_id)
        assert updated is not None
        np.testing.assert_allclose(updated.embedding, new_emb, atol=1e-6)
        conn.close()

    def test_update_nonexistent(self, tmp_path: Path) -> None:
        conn, repo = _make_sqlite_repo(tmp_path)
        assert repo.update_embedding(999, _random_embedding()) is False
        conn.close()

    def test_delete(self, tmp_path: Path) -> None:
        conn, repo = _make_sqlite_repo(tmp_path)
        p = repo.add_person("Frank", _random_embedding())
        assert repo.delete_person(p.person_id) is True
        assert repo.get_all() == []
        assert repo.delete_person(p.person_id) is False
        conn.close()

    def test_embedding_round_trip(self, tmp_path: Path) -> None:
        """Embedding stored as blob must survive save → load exactly."""
        conn, repo = _make_sqlite_repo(tmp_path)
        emb = _random_embedding()
        repo.add_person("Grace", emb)

        loaded = repo.get_all()[0]
        assert loaded.embedding.dtype == np.float32
        assert loaded.embedding.shape == (512,)
        np.testing.assert_array_equal(loaded.embedding, emb)
        conn.close()

    def test_multiple_persons(self, tmp_path: Path) -> None:
        conn, repo = _make_sqlite_repo(tmp_path)
        repo.add_person("A", _random_embedding())
        repo.add_person("B", _random_embedding())
        repo.add_person("C", _random_embedding())
        assert len(repo.get_all()) == 3
        conn.close()


# ===================================================================
# make_enrolled_provider
# ===================================================================

class TestEnrolledProvider:
    def test_returns_callable(self, tmp_path: Path) -> None:
        conn, repo = _make_sqlite_repo(tmp_path)
        provider = make_enrolled_provider(repo)
        assert callable(provider)
        conn.close()

    def test_provider_returns_persons(self, tmp_path: Path) -> None:
        conn, repo = _make_sqlite_repo(tmp_path)
        repo.add_person("Alice", _random_embedding())
        repo.add_person("Bob", _random_embedding())

        provider = make_enrolled_provider(repo)
        persons = provider()
        assert len(persons) == 2
        names = {p.name for p in persons}
        assert names == {"Alice", "Bob"}
        conn.close()

    def test_provider_empty_db(self, tmp_path: Path) -> None:
        conn, repo = _make_sqlite_repo(tmp_path)
        provider = make_enrolled_provider(repo)
        assert provider() == []
        conn.close()


# ===================================================================
# Helpers  (events)
# ===================================================================

def _make_event(
    event_id: str = "00000000-0000-0000-0000-000000000001",
    status: str = "authorised",
    person_name: str | None = "Alice",
    person_id: int | None = None,
    score: float | None = 0.85,
    created_at: str = "2026-03-09T12:00:00+00:00",
) -> Event:
    return Event(
        event_id=event_id,
        created_at=created_at,
        status=status,
        person_name=person_name,
        person_id=person_id,
        score=score,
        bbox_json='{"x1":10,"y1":20,"x2":110,"y2":120}',
        snapshot_path=None,
        clip_path=None,
    )


def _make_event_repo(tmp_path: Path) -> tuple[sqlite3.Connection, SQLiteEventRepository]:
    db_path = tmp_path / "test.sqlite"
    conn = init_db(db_path)
    return conn, SQLiteEventRepository(conn)


# ===================================================================
# SQLiteEventRepository  (Iteration 3)
# ===================================================================

class TestSQLiteEventRepo:
    def test_add_and_list(self, tmp_path: Path) -> None:
        conn, repo = _make_event_repo(tmp_path)
        ev = _make_event()
        repo.add_event(ev)

        events = repo.list_events()
        assert len(events) == 1
        assert events[0].event_id == ev.event_id
        assert events[0].status == "authorised"
        assert events[0].person_name == "Alice"
        assert events[0].score == 0.85
        assert events[0].bbox_json is not None
        conn.close()

    def test_list_respects_limit(self, tmp_path: Path) -> None:
        conn, repo = _make_event_repo(tmp_path)
        for i in range(5):
            repo.add_event(
                _make_event(
                    event_id=f"id-{i}",
                    created_at=f"2026-03-09T12:0{i}:00+00:00",
                )
            )
        events = repo.list_events(limit=3)
        assert len(events) == 3
        conn.close()

    def test_list_newest_first(self, tmp_path: Path) -> None:
        conn, repo = _make_event_repo(tmp_path)
        repo.add_event(_make_event(event_id="old", created_at="2026-01-01T00:00:00+00:00"))
        repo.add_event(_make_event(event_id="new", created_at="2026-03-09T23:59:59+00:00"))

        events = repo.list_events()
        assert events[0].event_id == "new"
        assert events[1].event_id == "old"
        conn.close()

    def test_filter_by_status(self, tmp_path: Path) -> None:
        conn, repo = _make_event_repo(tmp_path)
        repo.add_event(_make_event(event_id="a", status="authorised"))
        repo.add_event(_make_event(event_id="u", status="unauthorised"))

        auth = repo.list_events(status="authorised")
        assert len(auth) == 1
        assert auth[0].event_id == "a"

        unauth = repo.list_events(status="unauthorised")
        assert len(unauth) == 1
        assert unauth[0].event_id == "u"
        conn.close()

    def test_empty_list(self, tmp_path: Path) -> None:
        conn, repo = _make_event_repo(tmp_path)
        assert repo.list_events() == []
        conn.close()

    def test_snapshot_and_clip_nullable(self, tmp_path: Path) -> None:
        conn, repo = _make_event_repo(tmp_path)
        ev = _make_event()
        repo.add_event(ev)
        loaded = repo.list_events()[0]
        assert loaded.snapshot_path is None
        assert loaded.clip_path is None
        conn.close()


# ===================================================================
# SQLiteEmbeddingRepository  (ML Integration)
# ===================================================================

def _make_emb_repos(tmp_path: Path):
    """Create SQLitePersonRepository + SQLiteEmbeddingRepository."""
    db_path = tmp_path / "test.sqlite"
    conn = init_db(db_path)
    return conn, SQLitePersonRepository(conn), SQLiteEmbeddingRepository(conn)


class TestSQLiteEmbeddingRepository:
    """CRUD operations on the person_embeddings table."""

    def test_add_and_get_embeddings(self, tmp_path: Path) -> None:
        conn, person_repo, emb_repo = _make_emb_repos(tmp_path)
        person = person_repo.add_person("Alice", _random_embedding())
        e1 = _random_embedding()
        e2 = _random_embedding()
        emb_repo.add_embedding(person.person_id, e1)
        emb_repo.add_embedding(person.person_id, e2)

        embs = emb_repo.get_embeddings(person.person_id)
        assert len(embs) == 2
        np.testing.assert_allclose(embs[0], e1.astype(np.float32), atol=1e-6)
        np.testing.assert_allclose(embs[1], e2.astype(np.float32), atol=1e-6)
        conn.close()

    def test_count_embeddings(self, tmp_path: Path) -> None:
        conn, person_repo, emb_repo = _make_emb_repos(tmp_path)
        person = person_repo.add_person("Bob", _random_embedding())
        assert emb_repo.count_embeddings(person.person_id) == 0
        emb_repo.add_embedding(person.person_id, _random_embedding())
        assert emb_repo.count_embeddings(person.person_id) == 1
        emb_repo.add_embedding(person.person_id, _random_embedding())
        assert emb_repo.count_embeddings(person.person_id) == 2
        conn.close()

    def test_delete_embeddings(self, tmp_path: Path) -> None:
        conn, person_repo, emb_repo = _make_emb_repos(tmp_path)
        person = person_repo.add_person("Carol", _random_embedding())
        emb_repo.add_embedding(person.person_id, _random_embedding())
        emb_repo.add_embedding(person.person_id, _random_embedding())
        deleted = emb_repo.delete_embeddings(person.person_id)
        assert deleted == 2
        assert emb_repo.count_embeddings(person.person_id) == 0
        conn.close()

    def test_max_gallery_enforced(self, tmp_path: Path, monkeypatch) -> None:
        """Adding beyond MAX_GALLERY_EMBEDDINGS drops the oldest."""
        monkeypatch.setattr("app.config.MAX_GALLERY_EMBEDDINGS", 3)
        conn, person_repo, emb_repo = _make_emb_repos(tmp_path)
        person = person_repo.add_person("Dave", _random_embedding())

        embeddings = [_random_embedding() for _ in range(5)]
        for e in embeddings:
            emb_repo.add_embedding(person.person_id, e)

        stored = emb_repo.get_embeddings(person.person_id)
        assert len(stored) == 3
        # The oldest two should have been evicted — only last 3 remain
        np.testing.assert_allclose(
            stored[-1], embeddings[-1].astype(np.float32), atol=1e-6
        )
        conn.close()

    def test_empty_get(self, tmp_path: Path) -> None:
        conn, person_repo, emb_repo = _make_emb_repos(tmp_path)
        person = person_repo.add_person("Eve", _random_embedding())
        assert emb_repo.get_embeddings(person.person_id) == []
        conn.close()

    def test_person_embeddings_table_created(self, tmp_path: Path) -> None:
        conn, _, _ = _make_emb_repos(tmp_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='person_embeddings'"
        )
        assert cursor.fetchone() is not None
        conn.close()
