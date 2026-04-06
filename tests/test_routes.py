from __future__ import annotations

import pytest
from uuid import uuid4
from datetime import datetime, timezone
from app.core.models import Event
from app.db.repo import AdminRepository, SQLiteEventRepository

def _login_as(client, username, password):
    client.post("/login", data={"username": username, "password": password})

def test_dashboard_renders(client, db):
    """Seed DB with events, assert dashboard loads 200 and shows data."""
    event_repo = SQLiteEventRepository(db)
    event_id = str(uuid4())
    event_repo.add_event(
        Event(
            event_id=event_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            status="authorised",
            person_name="Test Person",
            person_id=None,
            score=0.9,
            bbox_json=None,
            snapshot_path=None,
            clip_path=None,
            track_key=None,
        )
    )
    
    _login_as(client, "admin", "test-admin-pass")
    res = client.get("/")
    assert res.status_code == 200
    assert b"Test Person" in res.data

def test_events_page_renders(client):
    """Events page returns 200."""
    _login_as(client, "admin", "test-admin-pass")
    res = client.get("/events")
    assert res.status_code == 200

def test_admin_create_user(client, db):
    """Admin can create a new user and role persists."""
    _login_as(client, "admin", "test-admin-pass")
    res = client.post(
        "/settings/users", 
        data={"username": "newop", "password": "pass", "role": "operator"},
        follow_redirects=True
    )
    assert res.status_code == 200
    assert b"User &#39;newop&#39; created successfully" in res.data
    
    admin_repo = AdminRepository(db)
    user = admin_repo.get_by_username("newop")
    assert user is not None
    assert user["role"] == "operator"

def test_rbac_operator_access_blocked(client, db):
    """Operator receives 403 on protected admin routes."""
    admin_repo = AdminRepository(db)
    admin_repo.add_user("optest", "pbkdf2:sha256:...", "operator")
    # For simplicity, we create without valid hash, we just need the DB record.
    # Wait, we need them to actually login, so provide real hash.
    from werkzeug.security import generate_password_hash
    admin_repo.add_user("optest2", generate_password_hash("pass"), "operator")
    
    _login_as(client, "optest2", "pass")
    
    res_enroll = client.get("/enroll")
    assert res_enroll.status_code == 403
    
    res_users = client.get("/settings/users")
    assert res_users.status_code == 403

def test_rbac_admin_access_allowed(client):
    """Admin receives 200 on protected admin routes."""
    _login_as(client, "admin", "test-admin-pass")
    
    res_enroll = client.get("/enroll")
    assert res_enroll.status_code == 200
    
    res_users = client.get("/settings/users")
    assert res_users.status_code == 200

def test_admin_self_delete_blocked(client, db):
    """Admin attempting self-delete via /delete_user/<id> fails safely."""
    _login_as(client, "admin", "test-admin-pass")
    admin_repo = AdminRepository(db)
    admin_user = admin_repo.get_by_username("admin")
    
    res = client.post(f"/delete_user/{admin_user['id']}", follow_redirects=True)
    assert res.status_code == 200
    assert b"Action Denied" in res.data
    
    still_exists = admin_repo.get_by_username("admin")
    assert still_exists is not None

def test_invalid_period_fallback(client):
    """Invalid period query string shouldn't crash."""
    _login_as(client, "admin", "test-admin-pass")
    res = client.get("/?period=invalid_period_format")
    assert res.status_code == 200

def test_missing_form_data(client):
    """Missing form data handles without 500 crashes."""
    _login_as(client, "admin", "test-admin-pass")
    res = client.post("/settings/users", data={"username": ""})
    assert res.status_code == 200 # Handles by returning to template w/ error
