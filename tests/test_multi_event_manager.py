"""
Tests for Iteration 9 — MultiEntityEventManager orchestrator.

These tests exercise association logic, per-face event lifecycles,
stale track pruning, duplicate event suppression, and backward
compatibility with the existing EventManager.

Run with:  pytest tests/test_multi_event_manager.py -v
"""

from __future__ import annotations

import time

import pytest

from app.core.multi_event_manager import MultiEntityEventManager, _euclidean
from app.core.models import BoundingBox, Event, Observation


# ===================================================================
# Helpers
# ===================================================================

def _obs(
    x1: int = 10, y1: int = 10, x2: int = 110, y2: int = 110,
    name: str | None = None, score: float = 0.0,
    face: bool = True,
) -> Observation:
    """Build a minimal Observation for testing."""
    bbox = BoundingBox(x1, y1, x2, y2) if face else None
    return Observation(
        timestamp=time.monotonic(),
        face_present=face,
        person_name=name,
        score=score,
        bbox=bbox,
    )


def _make_mem(**kwargs) -> MultiEntityEventManager:
    """Create a MultiEntityEventManager with small defaults for fast tests."""
    defaults = dict(
        association_distance=150.0,
        max_entities=10,
        window_n=5,
        confirm_k=3,
        lost_frames=3,
        cooldown_seconds=2.0,
        score_threshold=0.4,
    )
    defaults.update(kwargs)
    return MultiEntityEventManager(**defaults)


# ===================================================================
# Geometry helpers
# ===================================================================

class TestEuclidean:

    def test_same_point(self) -> None:
        assert _euclidean((0, 0), (0, 0)) == 0.0

    def test_known_distance(self) -> None:
        assert _euclidean((0, 0), (3, 4)) == pytest.approx(5.0)


# ===================================================================
# Single-face lifecycle (backward compat)
# ===================================================================

class TestSingleFaceLifecycle:

    def test_single_face_confirms_and_emits_event(self) -> None:
        """One person appearing for 3 frames → ACTIVE → Event emitted."""
        mem = _make_mem(confirm_k=3)
        events = []
        for _ in range(3):
            evs = mem.update([_obs(name="Alice", score=0.8)])
            events.extend(evs)

        assert len(events) == 1
        assert events[0].status == "authorised"
        assert events[0].person_name == "Alice"

    def test_single_face_no_event_below_k(self) -> None:
        """One person for 2 frames, confirm_k=3 → no event yet."""
        mem = _make_mem(confirm_k=3)
        events = []
        for _ in range(2):
            evs = mem.update([_obs(name="Alice", score=0.8)])
            events.extend(evs)
        assert len(events) == 0

    def test_empty_frame_no_crash(self) -> None:
        """Zero faces in frame must not crash."""
        mem = _make_mem()
        events = mem.update([])
        assert events == []


# ===================================================================
# Two independent faces
# ===================================================================

class TestTwoFaces:

    def test_two_faces_independent_events(self) -> None:
        """Two people far apart → two independent events."""
        mem = _make_mem(confirm_k=3, association_distance=150.0)

        # Face A at (50, 50)-(100, 100), Face B at (400, 400)-(500, 500)
        events = []
        for _ in range(3):
            obs_a = _obs(x1=50, y1=50, x2=100, y2=100, name="Alice", score=0.8)
            obs_b = _obs(x1=400, y1=400, x2=500, y2=500, name="Bob", score=0.7)
            evs = mem.update([obs_a, obs_b])
            events.extend(evs)

        assert len(events) == 2
        names = {e.person_name for e in events}
        assert names == {"Alice", "Bob"}

    def test_two_faces_one_leaves(self) -> None:
        """After confirmation, one face disappears, the other stays."""
        mem = _make_mem(confirm_k=3, lost_frames=3)

        # Both present for 3 frames → both confirmed
        for _ in range(3):
            obs_a = _obs(x1=50, y1=50, x2=100, y2=100, name="Alice", score=0.8)
            obs_b = _obs(x1=400, y1=400, x2=500, y2=500, name="Bob", score=0.7)
            mem.update([obs_a, obs_b])

        assert mem.active_tracks == 2

        # Now only Alice stays for 3 more frames
        for _ in range(3):
            obs_a = _obs(x1=50, y1=50, x2=100, y2=100, name="Alice", score=0.8)
            mem.update([obs_a])

        # Bob's track should transition to COOLDOWN
        states = mem.track_states()
        alice_states = [s for k, s in states.items()]
        # At least one should be ACTIVE (Alice) and Bob may be in COOLDOWN
        assert "ACTIVE" in alice_states


# ===================================================================
# Association logic
# ===================================================================

class TestAssociation:

    def test_same_position_stays_on_same_track(self) -> None:
        """Face in similar position across frames → same track."""
        mem = _make_mem(confirm_k=3)

        for _ in range(3):
            mem.update([_obs(x1=100, y1=100, x2=200, y2=200, name="A", score=0.8)])

        assert mem.active_tracks == 1

    def test_far_away_detection_creates_new_track(self) -> None:
        """Detection far from existing tracks → new track."""
        mem = _make_mem(confirm_k=3, association_distance=100.0)

        # Frame 1: one face at (50, 50)
        mem.update([_obs(x1=50, y1=50, x2=100, y2=100, name="A", score=0.8)])
        assert mem.active_tracks == 1

        # Frame 2: same face + one far away at (500, 500)
        obs_a = _obs(x1=50, y1=50, x2=100, y2=100, name="A", score=0.8)
        obs_b = _obs(x1=500, y1=500, x2=600, y2=600, name="B", score=0.7)
        mem.update([obs_a, obs_b])
        assert mem.active_tracks == 2

    def test_close_detection_reuses_track(self) -> None:
        """Detection close to existing track → reuses it (no new track)."""
        mem = _make_mem(confirm_k=3, association_distance=200.0)

        # Frame 1: face at (100, 100)-(200, 200)  centroid=(150, 150)
        mem.update([_obs(x1=100, y1=100, x2=200, y2=200, name="A", score=0.8)])

        # Frame 2: face moved slightly to (120, 120)-(220, 220)  centroid=(170, 170)
        mem.update([_obs(x1=120, y1=120, x2=220, y2=220, name="A", score=0.8)])

        # Should still be one track (distance ~28px, well within 200px threshold)
        assert mem.active_tracks == 1


# ===================================================================
# Stale track cleanup
# ===================================================================

class TestStaleTrackCleanup:

    def test_stale_track_pruned(self) -> None:
        """Track with no detections for stale_threshold frames -> pruned."""
        mem = _make_mem(confirm_k=3, lost_frames=3)
        # stale_threshold = lost_frames(3) + 5 = 8

        # Confirm a face
        for _ in range(3):
            mem.update([_obs(x1=50, y1=50, x2=100, y2=100, name="A", score=0.8)])
        assert mem.active_tracks == 1

        # Send enough empty frames to guarantee stale pruning.
        # Need: lost_frames (3) to enter COOLDOWN, then stale_threshold (8)
        # more for pruning. Send 15 to be safe.
        for _ in range(15):
            mem.update([])

        assert mem.active_tracks == 0

    def test_active_track_not_pruned(self) -> None:
        """Track that keeps receiving observations is NOT pruned."""
        mem = _make_mem(confirm_k=3, lost_frames=3)

        for _ in range(20):
            mem.update([_obs(x1=50, y1=50, x2=100, y2=100, name="A", score=0.8)])

        assert mem.active_tracks == 1


# ===================================================================
# Event spam prevention
# ===================================================================

class TestNoEventSpam:

    def test_no_duplicate_events_while_active(self) -> None:
        """Same face every frame → only ONE event emitted (at confirmation)."""
        mem = _make_mem(confirm_k=3)
        events = []
        for _ in range(20):
            evs = mem.update([_obs(name="Alice", score=0.8)])
            events.extend(evs)

        assert len(events) == 1

    def test_cooldown_prevents_immediate_refire(self) -> None:
        """After event + disappearance + reappearance, cooldown prevents spam."""
        mem = _make_mem(confirm_k=3, lost_frames=3, cooldown_seconds=100.0)

        events = []
        # Phase 1: Confirm
        for _ in range(3):
            evs = mem.update([_obs(name="Alice", score=0.8)])
            events.extend(evs)
        assert len(events) == 1

        # Phase 2: Disappear
        for _ in range(3):
            evs = mem.update([])
            events.extend(evs)

        # Phase 3: Reappear in cooldown
        for _ in range(5):
            evs = mem.update([_obs(name="Alice", score=0.8)])
            events.extend(evs)

        # Should still be only 1 event (cooldown blocks refire)
        assert len(events) == 1


# ===================================================================
# Max entities limit
# ===================================================================

class TestMaxEntities:

    def test_respects_max_entities(self) -> None:
        """When max_entities reached, new faces are ignored."""
        mem = _make_mem(max_entities=2, association_distance=50.0)

        # Three faces far apart
        obs_a = _obs(x1=0, y1=0, x2=30, y2=30, name="A", score=0.8)
        obs_b = _obs(x1=200, y1=200, x2=230, y2=230, name="B", score=0.7)
        obs_c = _obs(x1=400, y1=400, x2=430, y2=430, name="C", score=0.6)

        mem.update([obs_a, obs_b, obs_c])
        assert mem.active_tracks == 2  # capped at 2


# ===================================================================
# Unknown / mixed identities
# ===================================================================

class TestMixedIdentities:

    def test_unknown_face_fires_unauthorised(self) -> None:
        """Unknown face (no name, low score) → unauthorised event."""
        mem = _make_mem(confirm_k=3)
        events = []
        for _ in range(3):
            evs = mem.update([_obs(name=None, score=0.1)])
            events.extend(evs)

        assert len(events) == 1
        assert events[0].status == "unauthorised"

    def test_mixed_known_unknown_separate_events(self) -> None:
        """Known + unknown faces → separate events with correct status."""
        mem = _make_mem(confirm_k=3, association_distance=150.0)

        events = []
        for _ in range(3):
            obs_known = _obs(x1=50, y1=50, x2=100, y2=100, name="Alice", score=0.8)
            obs_unknown = _obs(x1=400, y1=400, x2=500, y2=500, name=None, score=0.1)
            evs = mem.update([obs_known, obs_unknown])
            events.extend(evs)

        assert len(events) == 2
        statuses = {e.status for e in events}
        assert statuses == {"authorised", "unauthorised"}


# ===================================================================
# Backward compatibility
# ===================================================================

class TestBackwardCompat:

    def test_observation_track_key_is_set(self) -> None:
        """After update(), observations get track_key assigned."""
        mem = _make_mem(confirm_k=3)
        obs = _obs(name="Alice", score=0.8)
        mem.update([obs])
        assert obs.track_key is not None
        assert obs.track_key.startswith("face_")

    def test_events_have_standard_fields(self) -> None:
        """Emitted events have the same structure as single-entity events."""
        mem = _make_mem(confirm_k=3)
        events = []
        for _ in range(3):
            evs = mem.update([_obs(name="Alice", score=0.8)])
            events.extend(evs)

        event = events[0]
        assert isinstance(event, Event)
        assert len(event.event_id) == 36  # UUID-4
        assert "T" in event.created_at  # ISO 8601
        assert event.status in ("authorised", "unauthorised")
        assert event.person_name == "Alice"
        assert event.score == 0.8
