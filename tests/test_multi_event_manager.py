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


# ===================================================================
# Edge Cases and Validation (Iteration 9)
# ===================================================================

class TestEdgeCases:

    def test_ghost_face_filtered(self) -> None:
        """Transient false positive (1 frame) should not emit an event and should be pruned."""
        mem = _make_mem(confirm_k=3, lost_frames=3)
        # 1 frame appearance
        events = mem.update([_obs(x1=10, y1=10, x2=50, y2=50, name=None, score=0.0)])
        assert len(events) == 0
        assert mem.active_tracks == 1
        
        # Then empty frames
        for _ in range(15):
            mem.update([])
            
        # Ghost track should be gone
        assert mem.active_tracks == 0

    def test_crossing_identities_swap_gracefully(self) -> None:
        """When two faces cross paths, identities swap but lifecycle survives without crashing."""
        mem = _make_mem(confirm_k=3, association_distance=150.0)
        
        # Frame 1: Face A at (100) and Face B at (400)
        mem.update([
            _obs(100, 100, 150, 150, "A", 0.9), 
            _obs(400, 400, 450, 450, "B", 0.8)
        ])
        
        # Frame 2: Move closer
        mem.update([
            _obs(200, 200, 250, 250, "A", 0.9), 
            _obs(300, 300, 350, 350, "B", 0.8)
        ])
        
        # Frame 3: Crossover (they swap positions relative to each other)
        events = mem.update([
            _obs(350, 350, 400, 400, "A", 0.9), 
            _obs(150, 150, 200, 200, "B", 0.8)
        ])
        
        # The system must not crash. Because 3 frames elapsed, two events fire.
        # Note: Depending on the swap distance vs association distance,
        # the tracks might swap identities, but the orchestrator must survive.
        assert len(events) == 2
        assert mem.active_tracks == 2


# ===================================================================
# Track key on emitted events  (Iteration 11b)
# ===================================================================

class TestTrackKeyOnEvents:
    """Verify that events emitted by MultiEntityEventManager carry correct track_keys."""

    def test_single_face_event_has_track_key(self) -> None:
        """A confirmed single face should emit an event with a non-None track_key."""
        mem = _make_mem(confirm_k=3)
        events = []
        for _ in range(3):
            evs = mem.update([_obs(name="Alice", score=0.8)])
            events.extend(evs)

        assert len(events) == 1
        assert events[0].track_key is not None
        assert events[0].track_key.startswith("face_")

    def test_two_faces_get_different_track_keys(self) -> None:
        """Two independently confirmed faces should have different track_keys."""
        mem = _make_mem(confirm_k=3, association_distance=150.0)
        events = []
        for _ in range(3):
            obs_a = _obs(x1=50, y1=50, x2=100, y2=100, name="Alice", score=0.8)
            obs_b = _obs(x1=400, y1=400, x2=500, y2=500, name=None, score=0.1)
            evs = mem.update([obs_a, obs_b])
            events.extend(evs)

        assert len(events) == 2
        track_keys = {e.track_key for e in events}
        assert len(track_keys) == 2  # different keys
        assert all(k.startswith("face_") for k in track_keys)

    def test_unknown_event_has_stable_track_key(self) -> None:
        """Unknown face event should carry a track_key usable for alert suppression."""
        mem = _make_mem(confirm_k=3)
        events = []
        for _ in range(3):
            evs = mem.update([_obs(name=None, score=0.1)])
            events.extend(evs)

        assert len(events) == 1
        assert events[0].status == "unauthorised"
        assert events[0].track_key is not None
        # This track_key is what AlertService would use as
        # "unknown_track:<track_key>" for suppression


# ===================================================================
# EVALUATION TESTS — Multiple Unknown Entities
# ===================================================================

class TestMultipleUnknowns:
    """Two unknowns at the same time must produce independent events."""

    def test_two_unknowns_produce_two_events(self) -> None:
        """Two unknown faces far apart → two separate unauthorised events."""
        mem = _make_mem(confirm_k=3, association_distance=150.0)
        events = []
        for _ in range(3):
            obs_a = _obs(x1=50, y1=50, x2=100, y2=100, name=None, score=0.1)
            obs_b = _obs(x1=400, y1=400, x2=500, y2=500, name=None, score=0.15)
            evs = mem.update([obs_a, obs_b])
            events.extend(evs)

        assert len(events) == 2
        assert all(e.status == "unauthorised" for e in events)

    def test_two_unknowns_have_distinct_track_keys(self) -> None:
        """Two unknowns must get different track_keys so AlertService can discriminate."""
        mem = _make_mem(confirm_k=3, association_distance=150.0)
        events = []
        for _ in range(3):
            obs_a = _obs(x1=50, y1=50, x2=100, y2=100, name=None, score=0.1)
            obs_b = _obs(x1=400, y1=400, x2=500, y2=500, name=None, score=0.15)
            evs = mem.update([obs_a, obs_b])
            events.extend(evs)

        track_keys = {e.track_key for e in events}
        assert len(track_keys) == 2, "Two unknowns must have distinct track_keys"
        assert None not in track_keys, "Unknown events must have non-None track_keys"

    def test_two_unknowns_do_not_suppress_each_other(self) -> None:
        """First unknown's confirmation must not block the second unknown's event."""
        mem = _make_mem(confirm_k=3, association_distance=150.0)

        # Feed both unknowns for exactly confirm_k frames
        events_per_frame = []
        for _ in range(3):
            obs_a = _obs(x1=50, y1=50, x2=100, y2=100, name=None, score=0.1)
            obs_b = _obs(x1=400, y1=400, x2=500, y2=500, name=None, score=0.15)
            evs = mem.update([obs_a, obs_b])
            events_per_frame.append(len(evs))

        total = sum(events_per_frame)
        assert total == 2, f"Expected 2 total events (one per unknown), got {total}"


# ===================================================================
# EVALUATION TESTS — Known + Unknown Interaction
# ===================================================================

class TestKnownUnknownInteraction:
    """Known person must NOT interfere with unknown alert lifecycle."""

    def test_known_person_does_not_block_unknown_event(self) -> None:
        """Known + unknown co-existing → independent events with correct statuses."""
        mem = _make_mem(confirm_k=3, association_distance=150.0)
        events = []
        for _ in range(3):
            obs_known = _obs(x1=50, y1=50, x2=100, y2=100, name="Alice", score=0.8)
            obs_unknown = _obs(x1=400, y1=400, x2=500, y2=500, name=None, score=0.1)
            evs = mem.update([obs_known, obs_unknown])
            events.extend(evs)

        auth_events = [e for e in events if e.status == "authorised"]
        unauth_events = [e for e in events if e.status == "unauthorised"]
        assert len(auth_events) == 1, "Known person should produce 1 authorised event"
        assert len(unauth_events) == 1, "Unknown person should produce 1 unauthorised event"

    def test_known_event_track_key_differs_from_unknown(self) -> None:
        """Known and unknown events must have different track_keys."""
        mem = _make_mem(confirm_k=3, association_distance=150.0)
        events = []
        for _ in range(3):
            obs_known = _obs(x1=50, y1=50, x2=100, y2=100, name="Alice", score=0.8)
            obs_unknown = _obs(x1=400, y1=400, x2=500, y2=500, name=None, score=0.1)
            evs = mem.update([obs_known, obs_unknown])
            events.extend(evs)

        track_keys = [e.track_key for e in events]
        assert len(set(track_keys)) == 2, "Known and unknown must have different track_keys"

    def test_known_removal_does_not_affect_unknown_tracking(self) -> None:
        """When known person leaves, the unknown track continues independently."""
        mem = _make_mem(confirm_k=3, lost_frames=3, association_distance=150.0)

        # Both present for 3 frames → both confirmed
        for _ in range(3):
            obs_known = _obs(x1=50, y1=50, x2=100, y2=100, name="Alice", score=0.8)
            obs_unknown = _obs(x1=400, y1=400, x2=500, y2=500, name=None, score=0.1)
            mem.update([obs_known, obs_unknown])

        assert mem.active_tracks == 2

        # Only unknown stays for 5 more frames
        for _ in range(5):
            obs_unknown = _obs(x1=400, y1=400, x2=500, y2=500, name=None, score=0.1)
            mem.update([obs_unknown])

        # Unknown track should still be ACTIVE
        states = mem.track_states()
        active_count = sum(1 for s in states.values() if s == "ACTIVE")
        assert active_count >= 1, "Unknown track should remain ACTIVE after known leaves"


# ===================================================================
# EVALUATION TESTS — Track Continuity
# ===================================================================

class TestTrackContinuity:
    """Same face moving slightly must maintain the same track_key across frames."""

    def test_slight_movement_preserves_track_key(self) -> None:
        """Face drifting 20px per frame → same track_key throughout."""
        mem = _make_mem(confirm_k=3, association_distance=200.0)

        observed_track_keys = set()
        for i in range(6):
            x1 = 100 + i * 20
            y1 = 100 + i * 15
            obs = _obs(x1=x1, y1=y1, x2=x1 + 100, y2=y1 + 100, name="A", score=0.8)
            mem.update([obs])
            if obs.track_key is not None:
                observed_track_keys.add(obs.track_key)

        assert len(observed_track_keys) == 1, (
            f"Expected 1 track_key for gradual movement, got {observed_track_keys}"
        )
        assert mem.active_tracks == 1

    def test_track_key_consistent_across_observations(self) -> None:
        """Observations fed to the same track must all get the same track_key."""
        mem = _make_mem(confirm_k=3, association_distance=200.0)

        keys = []
        for i in range(5):
            obs = _obs(x1=100, y1=100, x2=200, y2=200, name="A", score=0.8)
            mem.update([obs])
            keys.append(obs.track_key)

        # All should be the same non-None key
        assert all(k == keys[0] for k in keys), f"Track keys not consistent: {keys}"
        assert keys[0] is not None


# ===================================================================
# EVALUATION TESTS — Crossing Scenario (Detailed)
# ===================================================================

class TestCrossingScenarioDetailed:
    """
    Two faces swap positions.

    DOCUMENTED LIMITATION: with centroid-only association, identity swap
    IS EXPECTED when faces cross within association distance.  The test
    validates that the system does not crash and events still emit.
    """

    def test_crossing_does_not_crash(self) -> None:
        """System must not crash when two faces cross paths."""
        mem = _make_mem(confirm_k=3, association_distance=300.0)

        positions = [
            # Frame 1: A left, B right
            [(100, 100, 150, 150), (400, 400, 450, 450)],
            # Frame 2: moving toward each other
            [(200, 200, 250, 250), (300, 300, 350, 350)],
            # Frame 3: crossed
            [(350, 350, 400, 400), (150, 150, 200, 200)],
            # Frame 4: further apart on opposite sides
            [(400, 400, 450, 450), (100, 100, 150, 150)],
        ]

        all_events = []
        for frame_positions in positions:
            obs_list = [
                _obs(x1=p[0], y1=p[1], x2=p[2], y2=p[3], name=None, score=0.1)
                for p in frame_positions
            ]
            evs = mem.update(obs_list)
            all_events.extend(evs)

        # System survived — that's the primary assertion
        assert mem.active_tracks == 2, "Both tracks should survive crossing"

    def test_crossing_still_emits_events(self) -> None:
        """Events must still be emitted even if identities swap during crossing."""
        mem = _make_mem(confirm_k=3, association_distance=300.0)

        all_events = []
        # 5 frames to ensure confirm_k=3 is met
        for i in range(5):
            # Faces moving linearly, will cross around frame 3
            a_x = 100 + i * 80
            b_x = 500 - i * 80
            obs_a = _obs(x1=a_x, y1=100, x2=a_x + 50, y2=150, name=None, score=0.1)
            obs_b = _obs(x1=b_x, y1=100, x2=b_x + 50, y2=150, name=None, score=0.15)
            evs = mem.update([obs_a, obs_b])
            all_events.extend(evs)

        # At least some events should have been emitted
        assert len(all_events) >= 1, "Events should still fire despite crossing"

    def test_crossing_identity_swap_is_known_limitation(self) -> None:
        """
        KNOWN LIMITATION: After crossing within association distance,
        the track_keys assigned to observations may swap between the
        two physical entities.  This test documents the behaviour.
        """
        mem = _make_mem(confirm_k=1, association_distance=300.0)

        # Frame 1: Face A at left (centroid ~125), Face B at right (centroid ~425)
        obs_a1 = _obs(x1=100, y1=100, x2=150, y2=150, name="A", score=0.9)
        obs_b1 = _obs(x1=400, y1=100, x2=450, y2=150, name="B", score=0.8)
        mem.update([obs_a1, obs_b1])

        key_left = obs_a1.track_key
        key_right = obs_b1.track_key
        assert key_left != key_right

        # Frame 2: Faces have swapped sides
        obs_a2 = _obs(x1=400, y1=100, x2=450, y2=150, name="A", score=0.9)
        obs_b2 = _obs(x1=100, y1=100, x2=150, y2=150, name="B", score=0.8)
        mem.update([obs_a2, obs_b2])

        # With centroid association and these positions within 300px,
        # each detection gets matched to the nearest existing track centroid.
        # The key assigned may or may not match the original face's identity.
        # We just assert the system is stable.
        assert mem.active_tracks == 2


# ===================================================================
# EVALUATION TESTS — Long Duration / No Event Spam
# ===================================================================

class TestLongDurationNoSpam:
    """Same person present for many frames → only ONE event ever."""

    def test_50_frames_single_event(self) -> None:
        """50 consecutive frames of the same face → exactly 1 event."""
        mem = _make_mem(confirm_k=3)
        events = []
        for _ in range(50):
            evs = mem.update([_obs(name="Alice", score=0.8)])
            events.extend(evs)

        assert len(events) == 1, f"Expected 1 event over 50 frames, got {len(events)}"
        assert events[0].person_name == "Alice"

    def test_100_frames_two_faces_two_events(self) -> None:
        """100 frames with 2 faces → exactly 2 events and no spam."""
        mem = _make_mem(confirm_k=3, association_distance=150.0)
        events = []
        for _ in range(100):
            obs_a = _obs(x1=50, y1=50, x2=100, y2=100, name="Alice", score=0.8)
            obs_b = _obs(x1=400, y1=400, x2=500, y2=500, name="Bob", score=0.7)
            evs = mem.update([obs_a, obs_b])
            events.extend(evs)

        assert len(events) == 2, f"Expected exactly 2 events over 100 frames, got {len(events)}"


# ===================================================================
# EVALUATION TESTS — Leave / Return Before Cooldown
# ===================================================================

class TestLeaveReturnBeforeCooldown:
    """Entity leaves and returns within cooldown → NO new event."""

    def test_same_position_return_before_cooldown_no_new_event(self) -> None:
        """
        Sequence: confirm → leave (enter COOLDOWN) → return in same position
        → blocked by per-face EventManager cooldown.
        """
        mem = _make_mem(
            confirm_k=3, lost_frames=3, cooldown_seconds=100.0,
            association_distance=200.0,
        )

        events = []
        # Phase 1: Confirm (3 frames)
        for _ in range(3):
            evs = mem.update([_obs(x1=100, y1=100, x2=200, y2=200, name=None, score=0.1)])
            events.extend(evs)
        assert len(events) == 1

        # Phase 2: Leave (3 frames absent → COOLDOWN)
        for _ in range(3):
            evs = mem.update([])
            events.extend(evs)

        # Phase 3: Return to same location before cooldown expires
        # The track may still exist or be recreated depending on stale threshold.
        # But EventManager cooldown of 100s won't have expired.
        for _ in range(5):
            evs = mem.update([_obs(x1=100, y1=100, x2=200, y2=200, name=None, score=0.1)])
            events.extend(evs)

        # Should still be 1 event total — cooldown blocked the re-fire
        assert len(events) == 1, (
            f"Expected 1 event (cooldown should block re-fire), got {len(events)}"
        )


# ===================================================================
# EVALUATION TESTS — Leave / Return After Cooldown
# ===================================================================

class TestLeaveReturnAfterCooldown:
    """Entity leaves, cooldown expires, returns → NEW event fires."""

    def test_return_after_cooldown_fires_new_event(self) -> None:
        """
        Sequence: confirm → leave → cooldown expires → return → new event.

        Uses a very short cooldown (0.01s) and time.sleep to ensure expiry.
        The stale threshold will prune the old track, so return creates a
        fresh track with a new EventManager.
        """
        import time as t

        mem = _make_mem(
            confirm_k=3, lost_frames=3, cooldown_seconds=0.01,
            association_distance=200.0,
        )

        events = []
        # Phase 1: Confirm
        for _ in range(3):
            evs = mem.update([_obs(x1=100, y1=100, x2=200, y2=200, name=None, score=0.1)])
            events.extend(evs)
        assert len(events) == 1

        # Phase 2: Leave (enough frames to enter COOLDOWN + prune stale)
        for _ in range(15):
            evs = mem.update([])
            events.extend(evs)

        # Let cooldown expire
        t.sleep(0.02)

        assert mem.active_tracks == 0, "Stale track should have been pruned"

        # Phase 3: Return — creates new track, new EventManager
        for _ in range(3):
            evs = mem.update([_obs(x1=100, y1=100, x2=200, y2=200, name=None, score=0.1)])
            events.extend(evs)

        assert len(events) == 2, (
            f"Expected 2 events (original + post-cooldown return), got {len(events)}"
        )
