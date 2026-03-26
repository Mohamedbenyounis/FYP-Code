"""
Tests for AlertService.
"""

from unittest import mock
import pytest
from app import config
from app.core.models import Event
from app.services.alert_service import AlertService


def test_alert_service_cooldown_and_trigger():
    repo_mock = mock.Mock()
    email_mock = mock.Mock()
    
    # Configure test environment
    config.ALERTS_ENABLED = True
    config.EMAIL_ALERTS_ENABLED = True
    config.EMAIL_RECIPIENT = "admin@test.local"
    config.ALERT_SUPPRESSION_SECONDS = 10.0
    
    service = AlertService(repo_mock, email_mock)
    
    event_unauthorised = Event(
        event_id="evt-1",
        created_at="2026-03-31T20:00:00Z",
        status="unauthorised",
        person_id=99
    )
    
    event_authorised = Event(
        event_id="evt-2",
        created_at="2026-03-31T20:00:10Z",
        status="authorised",
        person_id=1
    )
    
    # 1. Authorised should be ignored
    service.trigger_unauthorised_alert(event_authorised)
    assert repo_mock.add_alert.call_count == 0
    
    # We need to mock time.monotonic to test cooldown reliably
    with mock.patch("app.services.alert_service.time.monotonic", return_value=100.0):
        # 2. Unauthorised known-person should trigger
        service.trigger_unauthorised_alert(event_unauthorised)
        assert repo_mock.add_alert.call_count == 1
        
    with mock.patch("app.services.alert_service.time.monotonic", return_value=105.0):
        # 3. Suppressed (only 5s elapsed, cooldown is 10s for same person)
        service.trigger_unauthorised_alert(event_unauthorised)
        assert repo_mock.add_alert.call_count == 1  # Still 1

    with mock.patch("app.services.alert_service.time.monotonic", return_value=106.0):
        # 4. Unknown event should trigger individually (not suppressed by 'unknown' global bucket)
        event_unknown = Event(
            event_id="evt-unknown",
            created_at="2026-03-31T20:00:15Z",
            status="unauthorised",
            person_id=None
        )
        service.trigger_unauthorised_alert(event_unknown)
        assert repo_mock.add_alert.call_count == 2
        
    with mock.patch("app.services.alert_service.time.monotonic", return_value=111.0):
        # 5. Known triggered again (11s elapsed)
        service.trigger_unauthorised_alert(event_unauthorised)
        assert repo_mock.add_alert.call_count == 3
