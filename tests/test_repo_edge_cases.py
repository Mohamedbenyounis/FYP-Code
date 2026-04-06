"""
Repository-level edge case tests.

Validates:
  - AdminRepository: role persistence, duplicate rejection, safe deletion
  - SQLiteAlertRepository: filtering, counting, missing lookups
  - SQLiteEventRepository: timestamp-based filtering
  - Safe handling of non-existent entities
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from werkzeug.security import generate_password_hash

from app.core.models import Event
from app.db.migrations import init_db
from app.db.repo import (
    AdminRepository,
    SQLiteAlertRepository,
    SQLiteEventRepository,
    SQLitePersonRepository,
)

import numpy as np


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _make_repos(tmp_path):
    """Create fresh repositories for testing."""
    db_path = tmp_path / "test.sqlite"
    conn = init_db(db_path)
    return conn, AdminRepository(conn), SQLiteEventRepository(conn), SQLiteAlertRepository(conn)


def _seed_admin_user(admin_repo, username="testuser", role="operator"):
    """Create a test user."""
    admin_repo.add_user(username, generate_password_hash("pass"), role)


# ===================================================================
# AdminRepository edge cases
# ===================================================================

class TestAdminRepoEdgeCases:

    def test_role_persists_correctly(self, tmp_path):
        """User created with 'operator' role retains that role on lookup."""
        conn, repo, _, _ = _make_repos(tmp_path)
        repo.add_user("op_user", generate_password_hash("pw"), "operator")
        user = repo.get_by_username("op_user")
        assert user is not None
        assert user["role"] == "operator"
        conn.close()

    def test_admin_role_persists(self, tmp_path):
        """User created with 'admin' role retains that role on lookup."""
        conn, repo, _, _ = _make_repos(tmp_path)
        repo.add_user("admin2", generate_password_hash("pw"), "admin")
        user = repo.get_by_username("admin2")
        assert user["role"] == "admin"
        conn.close()

    def test_duplicate_username_raises(self, tmp_path):
        """Adding a user with the same username must raise IntegrityError."""
        conn, repo, _, _ = _make_repos(tmp_path)
        repo.add_user("dup_user", generate_password_hash("pw"), "admin")
        with pytest.raises(sqlite3.IntegrityError):
            repo.add_user("dup_user", generate_password_hash("pw2"), "operator")
        conn.close()

    def test_get_nonexistent_user_returns_none(self, tmp_path):
        """Looking up a non-existent username returns None."""
        conn, repo, _, _ = _make_repos(tmp_path)
        assert repo.get_by_username("ghost_user") is None
        conn.close()

    def test_delete_nonexistent_user_returns_false(self, tmp_path):
        """Deleting a non-existent user ID returns False."""
        conn, repo, _, _ = _make_repos(tmp_path)
        result = repo.delete_user(99999)
        assert result is False
        conn.close()

    def test_delete_existing_user_returns_true(self, tmp_path):
        """Deleting an existing user ID returns True."""
        conn, repo, _, _ = _make_repos(tmp_path)
        repo.add_user("del_user", generate_password_hash("p"), "operator")
        user = repo.get_by_username("del_user")
        result = repo.delete_user(user["id"])
        assert result is True
        assert repo.get_by_username("del_user") is None
        conn.close()

    def test_list_users_excludes_password_hash(self, tmp_path):
        """list_users returns user info WITHOUT password_hash exposed."""
        conn, repo, _, _ = _make_repos(tmp_path)
        repo.add_user("safe_user", generate_password_hash("p"), "admin")
        users = repo.list_users()
        for u in users:
            assert "password_hash" not in u
        conn.close()

    def test_count_users(self, tmp_path):
        """count() returns accurate user count."""
        conn, repo, _, _ = _make_repos(tmp_path)
        initial = repo.count()
        repo.add_user("counted", generate_password_hash("p"), "admin")
        assert repo.count() == initial + 1
        conn.close()


# ===================================================================
# AlertRepository edge cases
# ===================================================================

class TestAlertRepoEdgeCases:

    def test_count_alerts_empty(self, tmp_path):
        """Alert count is 0 when no alerts exist."""
        conn, _, _, alert_repo = _make_repos(tmp_path)
        assert alert_repo.count_alerts() == 0
        conn.close()

    def test_list_alerts_empty_no_crash(self, tmp_path):
        """list_alerts on empty DB returns empty list."""
        conn, _, _, alert_repo = _make_repos(tmp_path)
        assert alert_repo.list_alerts() == []
        conn.close()

    def test_acknowledge_nonexistent_returns_false(self, tmp_path):
        """Acknowledging non-existent alert returns False."""
        conn, _, _, alert_repo = _make_repos(tmp_path)
        assert alert_repo.acknowledge_alert(12345) is False
        conn.close()

    def test_count_alerts_since(self, tmp_path):
        """count_alerts_since filters by timestamp correctly."""
        conn, _, event_repo, alert_repo = _make_repos(tmp_path)
        now = datetime.now(timezone.utc)
        old = (now - timedelta(days=10)).isoformat()
        recent = now.isoformat()

        # Seed events first (FK constraint)
        event_repo.add_event(Event(
            event_id="old-evt", created_at=old, status="unauthorised",
        ))
        event_repo.add_event(Event(
            event_id="new-evt", created_at=recent, status="unauthorised",
        ))

        # We can't directly set alert created_at, but the repo uses now()
        alert_repo.add_alert(event_id="new-evt", alert_type="test", message="recent")

        # Count since yesterday should include the recent alert
        yesterday = (now - timedelta(days=1))
        count = alert_repo.count_alerts_since(yesterday)
        assert count >= 1
        conn.close()


# ===================================================================
# EventRepository edge cases
# ===================================================================

class TestEventRepoEdgeCases:

    def test_get_nonexistent_event_returns_none(self, tmp_path):
        """Looking up a non-existent event ID returns None."""
        conn, _, event_repo, _ = _make_repos(tmp_path)
        result = event_repo.get_event_by_id("nonexistent-uuid")
        assert result is None
        conn.close()

    def test_count_events_since_with_status(self, tmp_path):
        """count_events_since with status filter works correctly."""
        conn, _, event_repo, _ = _make_repos(tmp_path)
        now = datetime.now(timezone.utc)
        event_repo.add_event(Event(
            event_id="auth-1", created_at=now.isoformat(),
            status="authorised",
        ))
        event_repo.add_event(Event(
            event_id="unauth-1", created_at=now.isoformat(),
            status="unauthorised",
        ))

        yesterday = now - timedelta(days=1)
        auth_count = event_repo.count_events_since(yesterday, status="authorised")
        unauth_count = event_repo.count_events_since(yesterday, status="unauthorised")

        assert auth_count == 1
        assert unauth_count == 1
        conn.close()

    def test_update_event_snapshot_nonexistent(self, tmp_path):
        """Updating snapshot for non-existent event returns False."""
        conn, _, event_repo, _ = _make_repos(tmp_path)
        result = event_repo.update_event_snapshot("ghost-id", "path.jpg")
        assert result is False
        conn.close()


# ===================================================================
# PersonRepository — safe deletion
# ===================================================================

class TestPersonRepoSafeDeletion:

    def test_delete_nonexistent_person_returns_false(self, tmp_path):
        """Deleting a non-existent person returns False."""
        db_path = tmp_path / "test.sqlite"
        conn = init_db(db_path)
        repo = SQLitePersonRepository(conn)
        assert repo.delete_person(99999) is False
        conn.close()
