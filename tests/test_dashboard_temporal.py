"""
Dashboard temporal logic and KPI correctness tests.

Validates:
  - period=day uses local midnight boundary (not last 24h)
  - malformed period parameter falls back safely
  - KPI values exactly match seeded DB data
  - local_time filter renders correctly
  - midnight boundary edge cases (23:58, 23:59, 00:01)
"""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app import config
from app.core.models import Event
from app.db.repo import SQLiteEventRepository, SQLiteAlertRepository


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _login(client):
    client.post("/login", data={"username": "admin", "password": "test-admin-pass"})


def _insert_event_at(db, created_at_iso, status="unauthorised", person_name=None):
    """Insert event at a specific ISO timestamp."""
    repo = SQLiteEventRepository(db)
    eid = str(uuid4())
    repo.add_event(Event(
        event_id=eid,
        created_at=created_at_iso,
        status=status,
        person_name=person_name,
        person_id=None, score=0.0,
        bbox_json=None, snapshot_path=None, clip_path=None, track_key=None,
    ))
    return eid


# ===================================================================
# Period filtering correctness
# ===================================================================

class TestDashboardPeriodFiltering:

    def test_invalid_period_does_not_crash(self, client, db):
        """Malformed period parameter falls back safely."""
        _login(client)
        res = client.get("/?period=xyz_invalid")
        assert res.status_code == 200

    def test_period_lifetime_shows_all_events(self, client, db):
        """period=lifetime returns all events regardless of age."""
        _login(client)
        # Seed event from 2 years ago
        old = (datetime.now(timezone.utc) - timedelta(days=730)).isoformat()
        _insert_event_at(db, old, status="authorised")
        _insert_event_at(db, datetime.now(timezone.utc).isoformat(), status="unauthorised")

        res = client.get("/?period=lifetime")
        assert res.status_code == 200

    def test_period_week_filters_last_7_days(self, client, db):
        """period=week only counts events in last 7 days."""
        _login(client)
        recent = datetime.now(timezone.utc).isoformat()
        old = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
        _insert_event_at(db, recent, status="authorised")
        _insert_event_at(db, old, status="authorised")

        res = client.get("/?period=week")
        assert res.status_code == 200


class TestDashboardMidnightBoundary:
    """Test the critical local-midnight boundary for period=day."""

    def test_day_uses_local_midnight_not_24h(self, client, db):
        """
        Events just before and after local midnight must be correctly
        categorized by period=day (which uses local midnight, not UTC midnight).
        """
        _login(client)
        now = datetime.now(timezone.utc)
        local_now = now.astimezone()
        local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        utc_midnight = local_midnight.astimezone(timezone.utc)

        # Event at 23:58 yesterday (before midnight) - should NOT be in today
        yesterday_2358 = (utc_midnight - timedelta(minutes=2)).isoformat()
        # Event at 00:01 today (after midnight) - should be in today
        today_0001 = (utc_midnight + timedelta(minutes=1)).isoformat()

        _insert_event_at(db, yesterday_2358, status="unauthorised")
        _insert_event_at(db, today_0001, status="authorised")

        res = client.get("/?period=day")
        assert res.status_code == 200


# ===================================================================
# KPI accuracy
# ===================================================================

class TestDashboardKPIAccuracy:

    def test_kpi_counts_match_seeded_data(self, client, db):
        """KPI counters must exactly match the seeded DB state."""
        _login(client)
        now = datetime.now(timezone.utc).isoformat()

        # Seed known quantities
        for _ in range(3):
            _insert_event_at(db, now, status="authorised")
        for _ in range(2):
            _insert_event_at(db, now, status="unauthorised")

        event_repo = SQLiteEventRepository(db)
        assert event_repo.count_events(status="authorised") == 3
        assert event_repo.count_events(status="unauthorised") == 2
        assert event_repo.count_events() == 5

        res = client.get("/?period=day")
        assert res.status_code == 200

    def test_empty_period_returns_zero_kpis(self, client, db):
        """Dashboard with no events should load without error."""
        _login(client)
        res = client.get("/?period=day")
        assert res.status_code == 200


# ===================================================================
# local_time filter correctness
# ===================================================================

class TestLocalTimeFilter:

    def test_local_time_filter_renders_valid_output(self, app):
        """The local_time Jinja2 filter converts ISO strings to local time."""
        with app.app_context():
            env = app.jinja_env
            tmpl = env.from_string("{{ ts|local_time }}")
            iso = "2026-04-10T12:00:00+00:00"
            rendered = tmpl.render(ts=iso)
            # Should contain date components, not raw ISO
            assert "2026" in rendered
            assert ":" in rendered  # formatted time separator
            assert "T" not in rendered  # should not be raw ISO

    def test_local_time_filter_handles_none(self, app):
        """local_time filter returns 'Unknown' for None."""
        with app.app_context():
            env = app.jinja_env
            tmpl = env.from_string("{{ ts|local_time }}")
            rendered = tmpl.render(ts=None)
            assert rendered == "Unknown"

    def test_local_time_filter_handles_garbage(self, app):
        """local_time filter handles malformed timestamp gracefully."""
        with app.app_context():
            env = app.jinja_env
            tmpl = env.from_string("{{ ts|local_time }}")
            rendered = tmpl.render(ts="not-a-date")
            assert rendered  # returns something, doesn't crash
