"""
Tests for Iteration 3 — EventManager state machine.

Run with:  pytest tests/test_event_manager.py -v
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from app.core.event_manager import EventManager
from app.core.models import BoundingBox, Event, Observation


# ===================================================================
# Helpers
# ===================================================================

def _obs(
    face: bool = True,
    name: str | None = None,
    person_id: int | None = None,
    score: float = 0.0,
) -> Observation:
    """Build a minimal Observation for testing."""
    bbox = BoundingBox(10, 20, 110, 120) if face else None
    return Observation(
        timestamp=time.monotonic(),
        face_present=face,
        person_name=name,
        person_id=person_id,
        score=score,
        bbox=bbox,
    )


def _make_em(**kwargs) -> EventManager:
    """Convenience constructor with small defaults for fast tests."""
    defaults = dict(
        window_n=5,
        confirm_k=3,
        lost_frames=3,
        cooldown_seconds=2.0,
        score_threshold=0.4,
    )
    defaults.update(kwargs)
    return EventManager(**defaults)


# ===================================================================
# IDLE state
# ===================================================================

class TestIdle:
    def test_no_face_stays_idle(self) -> None:
        em = _make_em()
        for _ in range(10):
            result = em.update(_obs(face=False))
            assert result is None
        assert em.state == "IDLE"

    def test_single_face_moves_to_confirming(self) -> None:
        em = _make_em()
        em.update(_obs(face=True))
        assert em.state == "CONFIRMING"

    def test_below_k_no_event(self) -> None:
        em = _make_em(confirm_k=3)
        result1 = em.update(_obs(face=True))
        result2 = em.update(_obs(face=True))
        # Only 2 faces in window — below confirm_k=3
        assert result1 is None
        assert result2 is None
        assert em.state == "CONFIRMING"


# ===================================================================
# CONFIRMING → ACTIVE  (K-of-N)
# ===================================================================

class TestConfirmation:
    def test_k_of_n_fires_event(self) -> None:
        em = _make_em(window_n=5, confirm_k=3)
        events = []
        for _ in range(3):
            ev = em.update(_obs(face=True, name="Alice", score=0.85, person_id=1))
            if ev is not None:
                events.append(ev)

        assert len(events) == 1
        assert em.state == "ACTIVE"
        event = events[0]
        assert isinstance(event, Event)
        assert event.status == "authorised"
        assert event.person_name == "Alice"
        assert event.score == 0.85

    def test_mixed_observations_still_confirm(self) -> None:
        em = _make_em(window_n=5, confirm_k=3)
        em.update(_obs(face=True, name="Bob", score=0.6))
        em.update(_obs(face=False))
        em.update(_obs(face=True, name="Bob", score=0.7))
        ev = em.update(_obs(face=True, name="Bob", score=0.65))
        assert ev is not None
        assert em.state == "ACTIVE"

    def test_unknown_face_fires_unauthorised(self) -> None:
        em = _make_em(window_n=5, confirm_k=3)
        events = []
        for _ in range(3):
            ev = em.update(_obs(face=True, name=None, score=0.0))
            if ev is not None:
                events.append(ev)

        assert len(events) == 1
        assert events[0].status == "unauthorised"
        assert events[0].person_name is None

    def test_low_score_fires_unauthorised(self) -> None:
        em = _make_em(window_n=5, confirm_k=3, score_threshold=0.5)
        events = []
        for _ in range(3):
            ev = em.update(_obs(face=True, name="Alice", score=0.3))
            if ev is not None:
                events.append(ev)

        assert len(events) == 1
        assert events[0].status == "unauthorised"

    def test_all_absent_returns_to_idle(self) -> None:
        """If all faces in window disappear while CONFIRMING → back to IDLE."""
        em = _make_em(window_n=3, confirm_k=2)
        em.update(_obs(face=True))
        assert em.state == "CONFIRMING"
        # Push out the face-present observation
        em.update(_obs(face=False))
        em.update(_obs(face=False))
        em.update(_obs(face=False))
        assert em.state == "IDLE"

    def test_event_has_uuid_and_timestamp(self) -> None:
        em = _make_em(window_n=3, confirm_k=2)
        em.update(_obs(face=True, name="X", score=0.9))
        ev = em.update(_obs(face=True, name="X", score=0.9))
        assert ev is not None
        assert len(ev.event_id) == 36  # UUID-4 string
        assert "T" in ev.created_at  # ISO 8601

    def test_event_has_bbox_json(self) -> None:
        em = _make_em(window_n=3, confirm_k=2)
        em.update(_obs(face=True, score=0.5))
        ev = em.update(_obs(face=True, score=0.5))
        assert ev is not None
        assert ev.bbox_json is not None
        assert '"x1"' in ev.bbox_json


# ===================================================================
# ACTIVE state
# ===================================================================

class TestActive:
    def _activate(self, em: EventManager) -> Event:
        """Push the EM into ACTIVE and return the emitted event."""
        events = []
        for _ in range(em._confirm_k):
            ev = em.update(_obs(face=True, name="A", score=0.8))
            if ev is not None:
                events.append(ev)
        assert em.state == "ACTIVE"
        return events[-1]

    def test_face_present_stays_active(self) -> None:
        em = _make_em(confirm_k=3, lost_frames=3)
        self._activate(em)
        for _ in range(10):
            assert em.update(_obs(face=True)) is None
        assert em.state == "ACTIVE"

    def test_no_duplicate_events_while_active(self) -> None:
        em = _make_em(confirm_k=3)
        self._activate(em)
        for _ in range(20):
            ev = em.update(_obs(face=True, name="A", score=0.8))
            assert ev is None  # must NOT re-fire

    def test_lost_frames_triggers_cooldown(self) -> None:
        em = _make_em(confirm_k=3, lost_frames=3)
        self._activate(em)
        em.update(_obs(face=False))
        em.update(_obs(face=False))
        assert em.state == "ACTIVE"
        em.update(_obs(face=False))  # 3rd absent → COOLDOWN
        assert em.state == "COOLDOWN"

    def test_intermittent_absence_resets_counter(self) -> None:
        em = _make_em(confirm_k=3, lost_frames=3)
        self._activate(em)
        em.update(_obs(face=False))
        em.update(_obs(face=False))
        em.update(_obs(face=True))  # resets counter
        em.update(_obs(face=False))
        em.update(_obs(face=False))
        assert em.state == "ACTIVE"  # only 2 consecutive, not 3


# ===================================================================
# COOLDOWN state
# ===================================================================

class TestCooldown:
    def _to_cooldown(self, em: EventManager) -> None:
        """Drive EM through IDLE → CONFIRMING → ACTIVE → COOLDOWN."""
        for _ in range(em._confirm_k):
            em.update(_obs(face=True, name="Z", score=0.9))
        assert em.state == "ACTIVE"
        for _ in range(em._lost_frames):
            em.update(_obs(face=False))
        assert em.state == "COOLDOWN"

    def test_cooldown_suppresses_new_events(self) -> None:
        em = _make_em(confirm_k=3, lost_frames=3, cooldown_seconds=100.0)
        self._to_cooldown(em)
        # Face reappears during cooldown — must not fire
        for _ in range(10):
            ev = em.update(_obs(face=True, name="Z", score=0.9))
            assert ev is None
        assert em.state == "COOLDOWN"

    def test_cooldown_expires_to_idle(self) -> None:
        em = _make_em(confirm_k=3, lost_frames=3, cooldown_seconds=0.5)
        self._to_cooldown(em)

        # Simulate waiting for cooldown to expire
        with patch("app.core.event_manager.time") as mock_time:
            # First call during _to_cooldown set _cooldown_start
            # Now we pretend enough time has passed
            mock_time.monotonic.return_value = time.monotonic() + 1.0
            ev = em.update(_obs(face=False))
            assert ev is None
            assert em.state == "IDLE"

    def test_cooldown_expires_with_face_reconfirms(self) -> None:
        em = _make_em(confirm_k=2, lost_frames=2, cooldown_seconds=0.5)
        self._to_cooldown(em)

        with patch("app.core.event_manager.time") as mock_time:
            mock_time.monotonic.return_value = time.monotonic() + 1.0
            # Cooldown expired + face present → should enter CONFIRMING
            ev = em.update(_obs(face=True, name="Z", score=0.9))
            # Might get None (just moved to CONFIRMING) or Event
            # (if window already has enough from re-process)
            assert em.state in ("CONFIRMING", "ACTIVE")


# ===================================================================
# Best-score tracking
# ===================================================================

class TestBestScoreTracking:
    def test_best_score_is_highest(self) -> None:
        em = _make_em(window_n=5, confirm_k=3)
        em.update(_obs(face=True, name="A", score=0.5, person_id=1))
        em.update(_obs(face=True, name="A", score=0.9, person_id=1))
        ev = em.update(_obs(face=True, name="A", score=0.7, person_id=1))
        assert ev is not None
        assert ev.score == 0.9
        assert ev.person_name == "A"
        assert ev.person_id == 1
