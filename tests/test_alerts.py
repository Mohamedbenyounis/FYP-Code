from __future__ import annotations

import pytest
import smtplib
from app.db.repo import SQLiteAlertRepository
from app.services.alert_service import AlertService
from app.core.models import Event
from unittest.mock import patch
from datetime import datetime, timezone

def _login_as(client, username, password):
    client.post("/login", data={"username": username, "password": password})

def test_create_and_acknowledge_alert_integration(client, db):
    """Test full alert creation using repo and acknowledgement using route."""
    from app.db.repo import SQLiteEventRepository
    event_repo = SQLiteEventRepository(db)
    event_repo.add_event(Event(event_id="evt-123", created_at=datetime.now(timezone.utc).isoformat(), status="unauthorised", person_name=None, person_id=None, score=0.0, bbox_json=None, snapshot_path=None, clip_path=None, track_key=None))
    
    repo = SQLiteAlertRepository(db)
    
    # Create Alert
    repo.add_alert(
        alert_type="unauthorised_person",
        event_id="evt-123",
        message="Integration Test Alert"
    )
    
    # Assert DB contains alert and get its ID
    alerts = repo.list_alerts(include_acknowledged=False)
    alert = next((a for a in alerts if a['message'] == "Integration Test Alert"), None)
    assert alert is not None
    alert_id = alert['id']
    
    # Acknowledge via route
    _login_as(client, "admin", "test-admin-pass")
    res = client.post(f"/alerts/{alert_id}/acknowledge", follow_redirects=True)
    assert res.status_code == 200
    
    # Assert DB is updated
    updated_alerts = repo.list_alerts(include_acknowledged=False)
    assert len([a for a in updated_alerts if a['id'] == alert_id]) == 0

def test_acknowledge_invalid_alert_id(client):
    """Acknowledging non-existent ID handled safely without 500 error."""
    _login_as(client, "admin", "test-admin-pass")
    invalid_id = 99999
    res = client.post(f"/alerts/{invalid_id}/acknowledge", follow_redirects=True)
    assert res.status_code == 200
    assert b"Alert not found" in res.data

@patch("app.services.email_service.smtplib.SMTP_SSL")
def test_email_service_failure_handled(mock_smtp, db):
    """Mock SMTP failure to ensure AlertService doesn't crash on triggering alerts."""
    # Setup mock to throw exception
    mock_smtp.side_effect = smtplib.SMTPException("Simulated SMTP Server down")
    
    # Create required objects
    from app.services.email_service import EmailService
    from app.config import EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, EMAIL_USERNAME, EMAIL_PASSWORD
    
    email_service = EmailService(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, EMAIL_USERNAME, EMAIL_PASSWORD)
    repo = SQLiteAlertRepository(db)
    alert_service = AlertService(repo, email_service)
    
    # Make dummy event
    evt = Event(
        event_id="fail-evt",
        created_at=datetime.now(timezone.utc).isoformat(),
        status="unauthorised",
        person_name="Fail Test",
        person_id=None,
        score=0.9,
        bbox_json=None,
        snapshot_path=None,
        clip_path=None,
        track_key=None
    )
    from app.db.repo import SQLiteEventRepository
    event_repo = SQLiteEventRepository(db)
    event_repo.add_event(evt)
    
    # Trigger alert should catch exception inside `trigger_unauthorised_alert` or `EmailService`
    # without propagating out to crash the system
    alert_service.trigger_unauthorised_alert(evt)
    
    # Assert alert was created in DB despite email failure
    repo = SQLiteAlertRepository(db)
    active_alerts = repo.list_alerts()
    assert len(active_alerts) > 0
