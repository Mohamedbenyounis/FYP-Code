"""
Level 2 Event Manager — presence confirmation state machine.

States
------
IDLE        → no face activity
CONFIRMING  → face detected, waiting for K-of-N confirmation
ACTIVE      → confirmed presence (event emitted on entry)
COOLDOWN    → post-event suppression window

The manager is a **pure logic** component.  It does not touch the
database or filesystem — ``main.py`` is responsible for persisting the
``Event`` objects it returns.

Iteration 3 scope: one person at a time (single-target).
"""

from __future__ import annotations

import time
import uuid
from collections import deque
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Optional

from app.core.models import Event, Observation


class _State(Enum):
    IDLE = auto()
    CONFIRMING = auto()
    ACTIVE = auto()
    COOLDOWN = auto()


class EventManager:
    """
    Stateful per-frame observer that emits ``Event`` objects when a face
    presence is confirmed via a K-of-N rolling window.

    Parameters
    ----------
    window_n : int
        Rolling window size (number of recent observations kept).
    confirm_k : int
        Minimum face-present observations in the window to confirm.
    lost_frames : int
        Consecutive no-face frames to end an active event.
    cooldown_seconds : float
        Seconds to suppress new events after one closes.
    score_threshold : float
        Authorisation threshold. A recognised identity below this score
        remains unauthorised.
    """

    def __init__(
        self,
        window_n: int = 5,
        confirm_k: int = 3,
        lost_frames: int = 5,
        cooldown_seconds: float = 10.0,
        score_threshold: float = 0.4,
    ) -> None:
        self._window_n = window_n
        self._confirm_k = confirm_k
        self._lost_frames = lost_frames
        self._cooldown_seconds = cooldown_seconds
        self._score_threshold = score_threshold

        self._state: _State = _State.IDLE
        self._window: deque[Observation] = deque(maxlen=window_n)

        # ACTIVE state bookkeeping
        self._consecutive_absent: int = 0
        self._best_score: float = 0.0
        self._best_name: Optional[str] = None
        self._best_person_id: Optional[int] = None
        self._best_bbox_json: Optional[str] = None

        # COOLDOWN timer
        self._cooldown_start: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> str:
        """Current state name (for logging / testing)."""
        return self._state.name

    def update(self, obs: Observation) -> Optional[Event]:
        """
        Feed one observation and optionally receive an ``Event``.

        Returns
        -------
        Event | None
            An ``Event`` object if the state machine just transitioned
            into ACTIVE (i.e. presence confirmed).  None otherwise.
        """
        self._window.append(obs)

        if self._state == _State.IDLE:
            return self._handle_idle(obs)
        if self._state == _State.CONFIRMING:
            return self._handle_confirming(obs)
        if self._state == _State.ACTIVE:
            return self._handle_active(obs)
        if self._state == _State.COOLDOWN:
            return self._handle_cooldown(obs)
        return None  # pragma: no cover

    # ------------------------------------------------------------------
    # State handlers
    # ------------------------------------------------------------------

    def _handle_idle(self, obs: Observation) -> Optional[Event]:
        if obs.face_present:
            self._state = _State.CONFIRMING
            self._reset_active_bookkeeping()
            self._track_best(obs)
            return self._check_confirmation()
        return None

    def _handle_confirming(self, obs: Observation) -> Optional[Event]:
        if obs.face_present:
            self._track_best(obs)
        faces_in_window = sum(1 for o in self._window if o.face_present)
        if faces_in_window == 0:
            self._state = _State.IDLE
            return None
        return self._check_confirmation()

    def _handle_active(self, obs: Observation) -> Optional[Event]:
        if obs.face_present:
            self._consecutive_absent = 0
            self._track_best(obs)
        else:
            self._consecutive_absent += 1
            if self._consecutive_absent >= self._lost_frames:
                self._state = _State.COOLDOWN
                self._cooldown_start = time.monotonic()
        return None

    def _handle_cooldown(self, obs: Observation) -> Optional[Event]:
        elapsed = time.monotonic() - self._cooldown_start
        if elapsed >= self._cooldown_seconds:
            self._state = _State.IDLE
            self._window.clear()
            # Re-process this observation in IDLE state
            return self._handle_idle(obs)
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _check_confirmation(self) -> Optional[Event]:
        """If K-of-N reached, emit an Event and transition to ACTIVE."""
        faces = sum(1 for o in self._window if o.face_present)
        if faces >= self._confirm_k:
            event = self._emit_event()
            self._state = _State.ACTIVE
            self._consecutive_absent = 0
            return event
        return None

    def _emit_event(self) -> Event:
        """Build an Event from the current best observation.

        ``person_name`` may be present while status is unauthorised when the
        match passes recognition but not authorisation confidence.
        """
        status = (
            "authorised"
            if (
                self._best_name is not None
                and self._best_score >= self._score_threshold
            )
            else "unauthorised"
        )
        return Event(
            event_id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc).isoformat(),
            status=status,
            person_name=self._best_name,
            person_id=self._best_person_id,
            score=self._best_score if self._best_score > 0 else None,
            bbox_json=self._best_bbox_json,
            snapshot_path=None,
            clip_path=None,
        )

    def _track_best(self, obs: Observation) -> None:
        """Keep the highest-scoring observation details."""
        if obs.score > self._best_score:
            self._best_score = obs.score
            self._best_name = obs.person_name
            self._best_person_id = obs.person_id
            if obs.bbox is not None:
                self._best_bbox_json = obs.bbox.to_json()

    def _reset_active_bookkeeping(self) -> None:
        self._consecutive_absent = 0
        self._best_score = 0.0
        self._best_name = None
        self._best_person_id = None
        self._best_bbox_json = None
