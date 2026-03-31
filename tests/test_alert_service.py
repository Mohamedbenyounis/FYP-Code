"""
Tests for AlertService — Iteration 11b.

Verifies the three-tier suppression key strategy:
- Known person:     ``person:<person_id>``   ← stable across events
- Unknown tracked:  ``unknown_track:<track_key>``  ← stable within tracking session
- Fallback:         ``unknown:<event_id>``   ← unique, effectively no suppression

Key scenarios tested:
1. Authorised events are ignored
2. Known-person cooldown works
3. Same unknown entity (same track_key) is correctly suppressed
4. Different unknown entities (different track_keys) get independent alerts
5. Unknown without track_key falls back to event_id (no suppression)
6. Cooldown expiry allows re-alerting
"""

from unittest import mock
import pytest
from app import config
from app.core.models import Event
from app.services.alert_service import AlertService


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _make_service():
    """Create an AlertService with mock dependencies and a test-friendly cooldown."""
    repo_mock = mock.Mock()
    email_mock = mock.Mock()
    config.ALERTS_ENABLED = True
    config.EMAIL_ALERTS_ENABLED = False  # disable email for most tests
    config.ALERT_SUPPRESSION_SECONDS = 10.0
    return AlertService(repo_mock, email_mock), repo_mock, email_mock


def _event(
    event_id: str = "evt-1",
    status: str = "unauthorised",
    person_id: int | None = None,
    person_name: str | None = None,
    track_key: str | None = None,
) -> Event:
    """Build a minimal Event for testing."""
    return Event(
        event_id=event_id,
        created_at="2026-04-01T18:00:00Z",
        status=status,
        person_id=person_id,
        person_name=person_name,
        track_key=track_key,
    )


# -------------------------------------------------------------------
# Tests
# -------------------------------------------------------------------

class TestAuthorisedIgnored:

    def test_authorised_event_never_triggers(self):
        """Events with status='authorised' must be silently ignored."""
        svc, repo, _ = _make_service()
        svc.trigger_unauthorised_alert(_event(status="authorised", person_id=1))
        assert repo.add_alert.call_count == 0


class TestKnownPersonSuppression:

    def test_known_person_triggers_first_alert(self):
        """First unauthorised event for a known person fires an alert."""
        svc, repo, _ = _make_service()
        with mock.patch("app.services.alert_service.time.monotonic", return_value=100.0):
            svc.trigger_unauthorised_alert(_event(person_id=5, track_key="face_0"))
        assert repo.add_alert.call_count == 1

    def test_known_person_suppressed_within_cooldown(self):
        """Same person_id within cooldown window → suppressed."""
        svc, repo, _ = _make_service()
        with mock.patch("app.services.alert_service.time.monotonic", return_value=100.0):
            svc.trigger_unauthorised_alert(_event(event_id="e1", person_id=5, track_key="face_0"))
        with mock.patch("app.services.alert_service.time.monotonic", return_value=105.0):
            svc.trigger_unauthorised_alert(_event(event_id="e2", person_id=5, track_key="face_0"))
        assert repo.add_alert.call_count == 1  # second was suppressed

    def test_known_person_fires_after_cooldown_expires(self):
        """Same person_id after cooldown expires → fires again."""
        svc, repo, _ = _make_service()
        with mock.patch("app.services.alert_service.time.monotonic", return_value=100.0):
            svc.trigger_unauthorised_alert(_event(event_id="e1", person_id=5, track_key="face_0"))
        with mock.patch("app.services.alert_service.time.monotonic", return_value=111.0):
            svc.trigger_unauthorised_alert(_event(event_id="e2", person_id=5, track_key="face_0"))
        assert repo.add_alert.call_count == 2


class TestUnknownTrackKeySuppression:
    """
    THE CORE FIX: unknown entities with the same track_key must be
    suppressed within the cooldown window, while different track_keys
    must fire independently.
    """

    def test_same_unknown_track_key_suppressed(self):
        """Same unknown entity (same track_key) within cooldown → suppressed."""
        svc, repo, _ = _make_service()
        with mock.patch("app.services.alert_service.time.monotonic", return_value=100.0):
            svc.trigger_unauthorised_alert(
                _event(event_id="e1", person_id=None, track_key="face_2")
            )
        with mock.patch("app.services.alert_service.time.monotonic", return_value=105.0):
            svc.trigger_unauthorised_alert(
                _event(event_id="e2", person_id=None, track_key="face_2")
            )
        assert repo.add_alert.call_count == 1  # second suppressed by same track_key

    def test_different_unknown_track_keys_fire_independently(self):
        """Different unknown entities (different track_keys) → both fire."""
        svc, repo, _ = _make_service()
        with mock.patch("app.services.alert_service.time.monotonic", return_value=100.0):
            svc.trigger_unauthorised_alert(
                _event(event_id="e1", person_id=None, track_key="face_2")
            )
        with mock.patch("app.services.alert_service.time.monotonic", return_value=100.0):
            svc.trigger_unauthorised_alert(
                _event(event_id="e2", person_id=None, track_key="face_3")
            )
        assert repo.add_alert.call_count == 2  # different entities, independent

    def test_unknown_track_key_fires_after_cooldown(self):
        """Same unknown entity after cooldown expires → fires again."""
        svc, repo, _ = _make_service()
        with mock.patch("app.services.alert_service.time.monotonic", return_value=100.0):
            svc.trigger_unauthorised_alert(
                _event(event_id="e1", person_id=None, track_key="face_2")
            )
        with mock.patch("app.services.alert_service.time.monotonic", return_value=111.0):
            svc.trigger_unauthorised_alert(
                _event(event_id="e2", person_id=None, track_key="face_2")
            )
        assert repo.add_alert.call_count == 2

    def test_unknown_track_key_does_not_cross_suppress_known(self):
        """Known and unknown suppression keys are independent namespaces."""
        svc, repo, _ = _make_service()
        with mock.patch("app.services.alert_service.time.monotonic", return_value=100.0):
            # Fire for known person
            svc.trigger_unauthorised_alert(
                _event(event_id="e1", person_id=5, track_key="face_0")
            )
            # Fire for unknown entity — should NOT be suppressed by person:5
            svc.trigger_unauthorised_alert(
                _event(event_id="e2", person_id=None, track_key="face_1")
            )
        assert repo.add_alert.call_count == 2


class TestFallbackNoTrackKey:
    """When track_key is None (no tracking), falls back to event_id."""

    def test_no_track_key_uses_event_id(self):
        """Unknown events without track_key use event_id → effectively no suppression."""
        svc, repo, _ = _make_service()
        with mock.patch("app.services.alert_service.time.monotonic", return_value=100.0):
            svc.trigger_unauthorised_alert(
                _event(event_id="e1", person_id=None, track_key=None)
            )
        with mock.patch("app.services.alert_service.time.monotonic", return_value=100.0):
            svc.trigger_unauthorised_alert(
                _event(event_id="e2", person_id=None, track_key=None)
            )
        # Both fire because different event_ids → different keys
        assert repo.add_alert.call_count == 2


class TestAlertsDisabled:

    def test_alerts_disabled_skips_everything(self):
        """When ALERTS_ENABLED is False, nothing fires."""
        svc, repo, _ = _make_service()
        config.ALERTS_ENABLED = False
        with mock.patch("app.services.alert_service.time.monotonic", return_value=100.0):
            svc.trigger_unauthorised_alert(
                _event(event_id="e1", person_id=None, track_key="face_0")
            )
        assert repo.add_alert.call_count == 0


# ===================================================================
# EVALUATION TESTS — Multiple Unknown Alerts
# ===================================================================

class TestMultipleUnknownAlerts:
    """Two unknowns with different track_keys must BOTH fire, independently."""

    def test_two_unknowns_at_same_time_both_fire(self):
        """Two unknown entities detected simultaneously → 2 alerts."""
        svc, repo, _ = _make_service()
        with mock.patch("app.services.alert_service.time.monotonic", return_value=100.0):
            svc.trigger_unauthorised_alert(
                _event(event_id="e1", person_id=None, track_key="face_0")
            )
            svc.trigger_unauthorised_alert(
                _event(event_id="e2", person_id=None, track_key="face_1")
            )
        assert repo.add_alert.call_count == 2

    def test_three_unknowns_three_alerts(self):
        """Three unknown entities → 3 independent alerts."""
        svc, repo, _ = _make_service()
        with mock.patch("app.services.alert_service.time.monotonic", return_value=100.0):
            for i in range(3):
                svc.trigger_unauthorised_alert(
                    _event(event_id=f"e{i}", person_id=None, track_key=f"face_{i}")
                )
        assert repo.add_alert.call_count == 3

    def test_same_unknown_twice_only_one_alert(self):
        """Same unknown entity (same track_key) fired twice → only 1 alert."""
        svc, repo, _ = _make_service()
        with mock.patch("app.services.alert_service.time.monotonic", return_value=100.0):
            svc.trigger_unauthorised_alert(
                _event(event_id="e1", person_id=None, track_key="face_0")
            )
            svc.trigger_unauthorised_alert(
                _event(event_id="e2", person_id=None, track_key="face_0")
            )
        assert repo.add_alert.call_count == 1


# ===================================================================
# EVALUATION TESTS — Same Unknown Leave/Return Before Cooldown
# ===================================================================

class TestSameUnknownLeaveReturnBeforeCooldown:
    """Same unknown leaves and returns BEFORE cooldown → NO new alert."""

    def test_suppressed_within_cooldown_window(self):
        """
        t=100: alert fires for face_2
        t=105: same face_2 returns (within 10s cooldown) → suppressed
        """
        svc, repo, _ = _make_service()
        with mock.patch("app.services.alert_service.time.monotonic", return_value=100.0):
            svc.trigger_unauthorised_alert(
                _event(event_id="e1", person_id=None, track_key="face_2")
            )
        # Simulate "leave" and "return" — just trigger again at t=105
        with mock.patch("app.services.alert_service.time.monotonic", return_value=105.0):
            svc.trigger_unauthorised_alert(
                _event(event_id="e2", person_id=None, track_key="face_2")
            )
        assert repo.add_alert.call_count == 1, "Second alert should be suppressed"

    def test_suppressed_at_boundary(self):
        """Alert at t=100, retry at t=109.9 (within 10s cooldown) → suppressed."""
        svc, repo, _ = _make_service()
        with mock.patch("app.services.alert_service.time.monotonic", return_value=100.0):
            svc.trigger_unauthorised_alert(
                _event(event_id="e1", person_id=None, track_key="face_2")
            )
        with mock.patch("app.services.alert_service.time.monotonic", return_value=109.9):
            svc.trigger_unauthorised_alert(
                _event(event_id="e2", person_id=None, track_key="face_2")
            )
        assert repo.add_alert.call_count == 1


# ===================================================================
# EVALUATION TESTS — Same Unknown Leave/Return After Cooldown
# ===================================================================

class TestSameUnknownLeaveReturnAfterCooldown:
    """Same unknown leaves and returns AFTER cooldown → NEW alert fires."""

    def test_fires_after_cooldown_expiry(self):
        """
        t=100: alert fires for face_2
        t=111: same face_2 returns (after 10s cooldown) → new alert
        """
        svc, repo, _ = _make_service()
        with mock.patch("app.services.alert_service.time.monotonic", return_value=100.0):
            svc.trigger_unauthorised_alert(
                _event(event_id="e1", person_id=None, track_key="face_2")
            )
        with mock.patch("app.services.alert_service.time.monotonic", return_value=111.0):
            svc.trigger_unauthorised_alert(
                _event(event_id="e2", person_id=None, track_key="face_2")
            )
        assert repo.add_alert.call_count == 2

    def test_fires_at_exact_boundary(self):
        """Alert at t=100, retry at t=110.0 (exactly at cooldown boundary) → fires."""
        svc, repo, _ = _make_service()
        with mock.patch("app.services.alert_service.time.monotonic", return_value=100.0):
            svc.trigger_unauthorised_alert(
                _event(event_id="e1", person_id=None, track_key="face_2")
            )
        with mock.patch("app.services.alert_service.time.monotonic", return_value=110.0):
            svc.trigger_unauthorised_alert(
                _event(event_id="e2", person_id=None, track_key="face_2")
            )
        assert repo.add_alert.call_count == 2


# ===================================================================
# EVALUATION TESTS — Known Does Not Suppress Unknown
# ===================================================================

class TestKnownDoesNotSuppressUnknown:
    """Known person's cooldown must not affect unknown entity alerts."""

    def test_known_cooldown_independent_of_unknown(self):
        """
        Fire alert for known person (person_id=5) at t=100.
        Fire alert for unknown (track face_1) at t=102 (within person:5 cooldown).
        Unknown must fire because it uses a different suppression key.
        """
        svc, repo, _ = _make_service()
        with mock.patch("app.services.alert_service.time.monotonic", return_value=100.0):
            svc.trigger_unauthorised_alert(
                _event(event_id="e1", person_id=5, person_name="Alice", track_key="face_0")
            )
        with mock.patch("app.services.alert_service.time.monotonic", return_value=102.0):
            svc.trigger_unauthorised_alert(
                _event(event_id="e2", person_id=None, track_key="face_1")
            )
        assert repo.add_alert.call_count == 2

    def test_unknown_cooldown_independent_of_known(self):
        """
        Fire alert for unknown (face_1) at t=100.
        Fire alert for known (person_id=5) at t=102 (within face_1 cooldown).
        Known must fire because it uses a different suppression key.
        """
        svc, repo, _ = _make_service()
        with mock.patch("app.services.alert_service.time.monotonic", return_value=100.0):
            svc.trigger_unauthorised_alert(
                _event(event_id="e1", person_id=None, track_key="face_1")
            )
        with mock.patch("app.services.alert_service.time.monotonic", return_value=102.0):
            svc.trigger_unauthorised_alert(
                _event(event_id="e2", person_id=5, person_name="Alice", track_key="face_0")
            )
        assert repo.add_alert.call_count == 2

    def test_mixed_scenario_four_alerts_expected(self):
        """
        t=100: known person A fires
        t=100: unknown face_1 fires
        t=100: unknown face_2 fires
        t=102: unknown face_1 again → SUPPRESSED
        t=111: unknown face_1 again → FIRES (cooldown expired)
        """
        svc, repo, _ = _make_service()
        with mock.patch("app.services.alert_service.time.monotonic", return_value=100.0):
            svc.trigger_unauthorised_alert(
                _event(event_id="e1", person_id=5, person_name="Alice", track_key="face_0")
            )
            svc.trigger_unauthorised_alert(
                _event(event_id="e2", person_id=None, track_key="face_1")
            )
            svc.trigger_unauthorised_alert(
                _event(event_id="e3", person_id=None, track_key="face_2")
            )
        with mock.patch("app.services.alert_service.time.monotonic", return_value=102.0):
            svc.trigger_unauthorised_alert(
                _event(event_id="e4", person_id=None, track_key="face_1")
            )
        with mock.patch("app.services.alert_service.time.monotonic", return_value=111.0):
            svc.trigger_unauthorised_alert(
                _event(event_id="e5", person_id=None, track_key="face_1")
            )
        assert repo.add_alert.call_count == 4, (
            "Expected: e1 fires, e2 fires, e3 fires, e4 suppressed, e5 fires = 4 total"
        )
