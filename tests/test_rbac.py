"""
RBAC enforcement matrix — Iteration 13.

Validates that every admin-only route correctly:
  - allows Admin access
  - returns 403 for Operator access
  - redirects to /login for unauthenticated users

Tests cover GET and POST separately for each sensitive route.
"""

from __future__ import annotations

import pytest
from uuid import uuid4
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash

from app.core.models import Event
from app.db.repo import UserRepository, SQLiteEventRepository, SQLiteAlertRepository


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _login_as(client, username, password):
    """Log a user into the Flask test client session."""
    client.post("/login", data={"username": username, "password": password})


def _seed_operator(db):
    """Create an operator user for RBAC testing."""
    repo = UserRepository(db)
    repo.add_user("operator_rbac", generate_password_hash("oppass"), "operator")


def _seed_event_and_alert(db):
    """Seed a minimal event and alert for delete/acknowledge tests."""
    event_repo = SQLiteEventRepository(db)
    event_id = str(uuid4())
    event_repo.add_event(Event(
        event_id=event_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        status="unauthorised",
        person_name=None, person_id=None, score=0.0,
        bbox_json=None, snapshot_path=None, clip_path=None, track_key=None,
    ))
    alert_repo = SQLiteAlertRepository(db)
    alert_repo.add_alert(event_id=event_id, alert_type="test", message="test alert")
    alerts = alert_repo.list_alerts()
    alert_id = alerts[0]["id"]
    return event_id, alert_id


# ===================================================================
# Unauthenticated access — must redirect to /login
# ===================================================================

class TestUnauthenticatedRedirects:
    """Every protected route must redirect unauthenticated users to /login."""

    @pytest.mark.parametrize("path", [
        "/",
        "/events",
        "/persons",
        "/alerts",
        "/enroll",
        "/settings/users",
    ])
    def test_get_redirects_to_login(self, client, path):
        res = client.get(path, follow_redirects=False)
        assert res.status_code in (301, 302), f"GET {path} should redirect"
        assert "/login" in res.headers["Location"]

    @pytest.mark.parametrize("path", [
        "/enroll",
        "/settings/users",
    ])
    def test_post_redirects_to_login(self, client, path):
        res = client.post(path, data={}, follow_redirects=False)
        assert res.status_code in (301, 302), f"POST {path} should redirect"
        assert "/login" in res.headers["Location"]

    def test_delete_person_unauth_redirects(self, client):
        res = client.post("/persons/1/delete", follow_redirects=False)
        assert res.status_code in (301, 302)
        assert "/login" in res.headers["Location"]

    def test_delete_user_unauth_redirects(self, client):
        res = client.post("/delete_user/1", follow_redirects=False)
        assert res.status_code in (301, 302)
        assert "/login" in res.headers["Location"]

    def test_acknowledge_alert_unauth_redirects(self, client):
        res = client.post("/alerts/1/acknowledge", follow_redirects=False)
        assert res.status_code in (301, 302)
        assert "/login" in res.headers["Location"]


# ===================================================================
# Operator access — 403 on admin-only routes, 200 on shared routes
# ===================================================================

class TestOperatorAccess:
    """Operator must get 403 on admin-only routes and 200 on shared routes."""

    def test_operator_can_view_dashboard(self, client, db):
        _seed_operator(db)
        _login_as(client, "operator_rbac", "oppass")
        res = client.get("/")
        assert res.status_code == 200

    def test_operator_can_view_events(self, client, db):
        _seed_operator(db)
        _login_as(client, "operator_rbac", "oppass")
        res = client.get("/events")
        assert res.status_code == 200

    def test_operator_can_view_persons(self, client, db):
        _seed_operator(db)
        _login_as(client, "operator_rbac", "oppass")
        res = client.get("/persons")
        assert res.status_code == 200

    def test_operator_can_view_alerts(self, client, db):
        _seed_operator(db)
        _login_as(client, "operator_rbac", "oppass")
        res = client.get("/alerts")
        assert res.status_code == 200

    def test_operator_can_acknowledge_alert(self, client, db):
        _seed_operator(db)
        _, alert_id = _seed_event_and_alert(db)
        _login_as(client, "operator_rbac", "oppass")
        res = client.post(f"/alerts/{alert_id}/acknowledge", follow_redirects=True)
        assert res.status_code == 200

    # --- Admin-only: GET ---
    def test_operator_blocked_enroll_get(self, client, db):
        _seed_operator(db)
        _login_as(client, "operator_rbac", "oppass")
        assert client.get("/enroll").status_code == 403

    def test_operator_blocked_settings_users_get(self, client, db):
        _seed_operator(db)
        _login_as(client, "operator_rbac", "oppass")
        assert client.get("/settings/users").status_code == 403

    # --- Admin-only: POST ---
    def test_operator_blocked_enroll_post(self, client, db):
        _seed_operator(db)
        _login_as(client, "operator_rbac", "oppass")
        assert client.post("/enroll", data={}).status_code == 403

    def test_operator_blocked_settings_users_post(self, client, db):
        _seed_operator(db)
        _login_as(client, "operator_rbac", "oppass")
        res = client.post("/settings/users", data={"username": "h", "password": "h"})
        assert res.status_code == 403

    def test_operator_blocked_delete_person(self, client, db):
        _seed_operator(db)
        _login_as(client, "operator_rbac", "oppass")
        assert client.post("/persons/1/delete").status_code == 403

    def test_operator_blocked_delete_user(self, client, db):
        _seed_operator(db)
        _login_as(client, "operator_rbac", "oppass")
        assert client.post("/delete_user/1").status_code == 403


# ===================================================================
# Admin access — allowed on all routes
# ===================================================================

class TestAdminAccess:
    """Admin must be allowed on all admin-only routes."""

    def test_admin_enroll_get(self, client):
        _login_as(client, "admin", "test-admin-pass")
        assert client.get("/enroll").status_code == 200

    def test_admin_enroll_post_no_data(self, client):
        """POST with missing data returns 400 (not 403/500)."""
        _login_as(client, "admin", "test-admin-pass")
        res = client.post("/enroll", data={"name": ""})
        assert res.status_code == 400

    def test_admin_settings_users_get(self, client):
        _login_as(client, "admin", "test-admin-pass")
        assert client.get("/settings/users").status_code == 200

    def test_admin_settings_users_post_creates_user(self, client, db):
        _login_as(client, "admin", "test-admin-pass")
        res = client.post(
            "/settings/users",
            data={"username": "newadmin", "password": "pass", "role": "admin"},
            follow_redirects=True,
        )
        assert res.status_code == 200
        user_repo = UserRepository(db)
        assert user_repo.get_by_username("newadmin") is not None

    def test_admin_delete_user(self, client, db):
        _login_as(client, "admin", "test-admin-pass")
        # Create a user to delete
        user_repo = UserRepository(db)
        user_repo.add_user("todelete", generate_password_hash("p"), "operator")
        user = user_repo.get_by_username("todelete")
        res = client.post(f"/delete_user/{user['id']}", follow_redirects=True)
        assert res.status_code == 200
        assert user_repo.get_by_username("todelete") is None

    def test_admin_acknowledge_alert(self, client, db):
        _login_as(client, "admin", "test-admin-pass")
        _, alert_id = _seed_event_and_alert(db)
        res = client.post(f"/alerts/{alert_id}/acknowledge", follow_redirects=True)
        assert res.status_code == 200
