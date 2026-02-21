"""
Tests for Iteration 2 — database repository layer.

Run with:  pytest tests/test_db_repo.py -v
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest

from app.core.models import EnrolledPerson
from app.db.migrations import init_db
from app.db.repo import (
    InMemoryPersonRepository,
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
