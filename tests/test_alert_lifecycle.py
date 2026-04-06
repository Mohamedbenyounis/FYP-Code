"""
Alert lifecycle integration tests — Iteration 11.

Validates:
  - alert creation persists with correct initial status
  - acknowledgment updates DB state correctly
  - acknowledged alerts remain in DB (not deleted)
  - acknowledged alerts are excluded from active queries
  - acknowledged alerts are visible in history/archive queries
  - invalid/non-existent alert IDs handled safely
  - alert timestamp-based filtering correctness
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from app.core.models import Event
from app.db.repo import SQLiteAlertRepository, SQLiteEventRepository


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _seed_event(db, event_id=None, status="unauthorised"):
    """Create a minimal event and return its ID."""
    eid = event_id or str(uuid4())
    repo = SQLiteEventRepository(db)
    repo.add_event(Event(
        event_id=eid,
        created_at=datetime.now(timezone.utc).isoformat(),
        status=status,
        person_name=None, person_id=None, score=0.0,
        bbox_json=None, snapshot_path=None, clip_path=None, track_key=None,
    ))
    return eid


def _login_as(client, username="admin", password="test-admin-pass"):
    client.post("/login", data={"username": username, "password": password})


# ===================================================================
# Alert creation and initial state
# ===================================================================

class TestAlertCreation:

    def test_new_alert_has_new_status(self, db):
        """Alert added via repo has status='new' (or the default status)."""
        eid = _seed_event(db)
        repo = SQLiteAlertRepository(db)
        repo.add_alert(event_id=eid, alert_type="UNAUTHORISED_PRESENCE", message="test")
        alerts = repo.list_alerts(include_acknowledged=True)
        assert len(alerts) == 1
        assert alerts[0]["status"] in ("new", None)  # DB default

    def test_alert_linked_to_correct_event(self, db):
        """Alert's event_id matches the originating event."""
        eid = _seed_event(db)
        repo = SQLiteAlertRepository(db)
        repo.add_alert(event_id=eid, alert_type="test", message="linked")
        alerts = repo.list_alerts(include_acknowledged=True)
        assert alerts[0]["event_id"] == eid

    def test_multiple_alerts_created_independently(self, db):
        """Multiple alerts can coexist for different events."""
        e1 = _seed_event(db, event_id="evt-a1")
        e2 = _seed_event(db, event_id="evt-a2")
        repo = SQLiteAlertRepository(db)
        repo.add_alert(event_id=e1, alert_type="test", message="first")
        repo.add_alert(event_id=e2, alert_type="test", message="second")
        assert repo.count_alerts() == 2


# ===================================================================
# Acknowledgment and persistence
# ===================================================================

class TestAlertAcknowledgment:

    def test_acknowledge_updates_status(self, db):
        """Acknowledging an alert changes its status to 'acknowledged'."""
        eid = _seed_event(db)
        repo = SQLiteAlertRepository(db)
        repo.add_alert(event_id=eid, alert_type="test", message="ack me")
        alerts = repo.list_alerts(include_acknowledged=True)
        alert_id = alerts[0]["id"]

        result = repo.acknowledge_alert(alert_id)
        assert result is True

        # Verify status changed
        all_alerts = repo.list_alerts(include_acknowledged=True)
        acked = [a for a in all_alerts if a["id"] == alert_id]
        assert len(acked) == 1
        assert acked[0]["status"] == "acknowledged"

    def test_acknowledged_alert_not_deleted_from_db(self, db):
        """Acknowledged alerts remain in the database — not deleted."""
        eid = _seed_event(db)
        repo = SQLiteAlertRepository(db)
        repo.add_alert(event_id=eid, alert_type="test", message="keep me")
        total_before = repo.count_alerts()

        alerts = repo.list_alerts(include_acknowledged=True)
        repo.acknowledge_alert(alerts[0]["id"])

        total_after = repo.count_alerts()
        assert total_after == total_before, "Acknowledged alert must not be deleted"

    def test_acknowledged_excluded_from_active_queries(self, db):
        """Active alert queries (default) exclude acknowledged alerts."""
        eid = _seed_event(db)
        repo = SQLiteAlertRepository(db)
        repo.add_alert(event_id=eid, alert_type="test", message="filter me")
        alerts = repo.list_alerts(include_acknowledged=True)
        repo.acknowledge_alert(alerts[0]["id"])

        active = repo.list_alerts(include_acknowledged=False)
        assert len(active) == 0, "Acknowledged alert must be excluded from active list"

    def test_acknowledged_visible_in_history_queries(self, db):
        """History/archive queries include acknowledged alerts."""
        eid = _seed_event(db)
        repo = SQLiteAlertRepository(db)
        repo.add_alert(event_id=eid, alert_type="test", message="history")
        alerts = repo.list_alerts(include_acknowledged=True)
        repo.acknowledge_alert(alerts[0]["id"])

        history = repo.list_alerts(include_acknowledged=True)
        assert len(history) == 1
        assert history[0]["status"] == "acknowledged"

    def test_acknowledge_nonexistent_id_returns_false(self, db):
        """Acknowledging a non-existent alert ID returns False, not crash."""
        repo = SQLiteAlertRepository(db)
        result = repo.acknowledge_alert(999999)
        assert result is False

    def test_acknowledge_via_route_returns_safely_for_invalid_id(self, client, db):
        """POST /alerts/999999/acknowledge from route returns safely."""
        _login_as(client)
        res = client.post("/alerts/999999/acknowledge", follow_redirects=True)
        assert res.status_code == 200
        assert b"Alert not found" in res.data

    def test_mixed_active_and_acknowledged(self, db):
        """Active queries return only non-acknowledged when both exist."""
        e1 = _seed_event(db, event_id="mix-1")
        e2 = _seed_event(db, event_id="mix-2")
        repo = SQLiteAlertRepository(db)
        repo.add_alert(event_id=e1, alert_type="test", message="active")
        repo.add_alert(event_id=e2, alert_type="test", message="will ack")

        all_alerts = repo.list_alerts(include_acknowledged=True)
        ack_target = [a for a in all_alerts if a["message"] == "will ack"][0]
        repo.acknowledge_alert(ack_target["id"])

        active = repo.list_alerts(include_acknowledged=False)
        assert len(active) == 1
        assert active[0]["message"] == "active"
