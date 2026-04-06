from __future__ import annotations

import pytest
from flask import session
from app.db.repo import SQLiteAlertRepository

def test_auth_protection_redirects(client):
    """GET protected route without login redirects to /login."""
    res = client.get("/", follow_redirects=False)
    assert res.status_code in (301, 302)
    assert "/login" in res.headers["Location"]

def test_login_success(client):
    """Valid login redirects and creates a session with role."""
    with client:
        res = client.post(
            "/login",
            data={"username": "admin", "password": "test-admin-pass"},
            follow_redirects=False,
        )
        assert res.status_code in (302, 303)
        # Verify session
        assert session.get("user_id") is not None
        assert session.get("role") == "admin"

def test_login_invalid_password(client):
    """Invalid password fails safely."""
    with client:
        res = client.post(
            "/login",
            data={"username": "admin", "password": "wrong-password"},
            follow_redirects=False,
        )
        assert res.status_code == 401
        assert session.get("user_id") is None

def test_login_nonexistent_user(client):
    """Non-existent user fails safely."""
    with client:
        res = client.post(
            "/login",
            data={"username": "notadmin", "password": "test-admin-pass"},
            follow_redirects=False,
        )
        assert res.status_code == 401
        assert session.get("user_id") is None

def test_flow_login_dashboard_acknowledge(client, db):
    """Mini E2E Flow: Login, load dashboard, acknowledge an alert."""
    from app.db.repo import SQLiteEventRepository
    from app.core.models import Event
    from datetime import datetime, timezone
    
    event_repo = SQLiteEventRepository(db)
    event_repo.add_event(Event(event_id="test-event-id", created_at=datetime.now(timezone.utc).isoformat(), status="unauthorised", person_name=None, person_id=None, score=0.0, bbox_json=None, snapshot_path=None, clip_path=None, track_key=None))

    # Setup test alert
    alert_repo = SQLiteAlertRepository(db)
    alert_repo.add_alert(
        alert_type="unauthorised_person",
        event_id="test-event-id",
        message="Test alert"
    )
    
    # Get the generated ID
    alerts = alert_repo.list_alerts()
    alert_id = [a['id'] for a in alerts if a['message'] == "Test alert"][0]
    
    with client:
        # 1. Login
        login_res = client.post(
            "/login",
            data={"username": "admin", "password": "test-admin-pass"},
            follow_redirects=False,
        )
        assert login_res.status_code in (302, 303)
        
        # 2. Access dashboard
        dash_res = client.get("/")
        assert dash_res.status_code == 200
        assert f"alert-{alert_id}".encode() in dash_res.data
        
        # 3. Acknowledge alert
        ack_res = client.post(f"/alerts/{alert_id}/acknowledge", follow_redirects=False)
        assert ack_res.status_code in (302, 303)
        
        # Verify DB
        alerts = alert_repo.list_alerts(include_acknowledged=False)
        assert len([a for a in alerts if a['id'] == alert_id]) == 0
