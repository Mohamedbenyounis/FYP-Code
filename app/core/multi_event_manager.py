"""
Multi-Entity Event Manager — orchestrates per-face EventManager instances.

Iteration 9 (experimental).

This module wraps the proven single-entity ``EventManager`` to support
independent event lifecycles for every detected face.  It does NOT
modify the ``EventManager`` itself.

Face association strategy
-------------------------
**Nearest-centroid (simple heuristic)**:  Each tracked entity stores
its last known bbox centroid.  New detections are matched to the closest
existing track within ``config.MULTI_FACE_ASSOCIATION_DISTANCE`` pixels.
Unmatched detections become new tracks.

.. warning::

    Centroid-only association is **weak without real visual tracking**
    (CSRT / KCF).  Two people crossing paths will swap identities.
    This is a known, documented limitation.  Future integration with
    Iteration 6 tracking would solve this properly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from app import config
from app.core.event_manager import EventManager
from app.core.models import BoundingBox, Event, Observation
from app.services.logging_service import get_logger


@dataclass
class _TrackedEntity:
    """Internal bookkeeping for one tracked face."""

    track_key: str
    event_manager: EventManager
    last_centroid: Tuple[int, int]   # (cx, cy) from most recent observation
    frames_since_seen: int = 0      # incremented when no detection matches


class MultiEntityEventManager:
    """
    Orchestrator that manages one ``EventManager`` per tracked face.

    Usage
    -----
    Call ``update(observations)`` once per processed frame, passing one
    ``Observation`` per detected face.  The orchestrator:

    1. Associates observations to existing tracks (nearest centroid).
    2. Creates new tracks for unmatched detections.
    3. Sends "absent" observations to tracks with no matching detection.
    4. Collects and returns all newly emitted ``Event`` objects.
    5. Prunes stale tracks that haven't been seen for too long.

    Parameters
    ----------
    association_distance : float
        Max pixel distance to associate a detection centroid with a track.
    max_entities : int
        Hard cap on concurrent tracked entities.
    event_manager_kwargs : dict
        Keyword arguments forwarded to each per-face ``EventManager``.
    """

    def __init__(
        self,
        association_distance: float | None = None,
        max_entities: int | None = None,
        **event_manager_kwargs,
    ) -> None:
        self._log = get_logger()
        self._association_distance = (
            association_distance
            if association_distance is not None
            else config.MULTI_FACE_ASSOCIATION_DISTANCE
        )
        self._max_entities = (
            max_entities
            if max_entities is not None
            else config.MULTI_FACE_MAX_ENTITIES
        )
        self._em_kwargs = event_manager_kwargs
        self._tracks: Dict[str, _TrackedEntity] = {}
        self._next_id: int = 0

        # How many frames a track can go unseen before it's pruned.
        # Uses the same lost_frames setting as the per-face EventManager,
        # plus a small buffer so the EM can transition to COOLDOWN first.
        self._stale_threshold: int = (
            event_manager_kwargs.get("lost_frames", config.EVENT_LOST_FRAMES) + 5
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def active_tracks(self) -> int:
        """Number of currently tracked entities."""
        return len(self._tracks)

    def track_states(self) -> Dict[str, str]:
        """Return a snapshot of track_key → EventManager state."""
        return {k: t.event_manager.state for k, t in self._tracks.items()}

    def update(self, observations: List[Observation]) -> List[Event]:
        """
        Process one frame's worth of observations.

        Parameters
        ----------
        observations : list[Observation]
            One per detected face, each with ``bbox`` and optionally
            ``track_key`` (ignored — association is done internally).

        Returns
        -------
        list[Event]
            Zero or more events emitted by the per-face EventManagers.
        """
        events: List[Event] = []

        # --- 1. Associate observations to existing tracks ----------------
        matched, unmatched_obs = self._associate(observations)

        # --- 2. Feed matched observations to their EventManagers ---------
        for track_key, obs in matched:
            track = self._tracks[track_key]
            track.last_centroid = _bbox_centroid(obs.bbox)
            track.frames_since_seen = 0
            # Tag the observation with its track key
            obs.track_key = track_key
            event = track.event_manager.update(obs)
            if event is not None:
                events.append(event)

        # --- 3. Create new tracks for unmatched observations -------------
        created_this_frame: set[str] = set()
        for obs in unmatched_obs:
            if len(self._tracks) >= self._max_entities:
                self._log.debug(
                    "Max entities (%d) reached — ignoring new face",
                    self._max_entities,
                )
                break
            track_key = self._make_track_key()
            em = EventManager(**self._em_kwargs)
            centroid = _bbox_centroid(obs.bbox)
            self._tracks[track_key] = _TrackedEntity(
                track_key=track_key,
                event_manager=em,
                last_centroid=centroid,
            )
            obs.track_key = track_key
            event = em.update(obs)
            if event is not None:
                events.append(event)
            created_this_frame.add(track_key)
            self._log.debug("New track %s at centroid %s", track_key, centroid)

        # --- 4. Send "absent" to unmatched tracks ------------------------
        matched_keys = {tk for tk, _ in matched}
        for track_key, track in list(self._tracks.items()):
            if track_key not in matched_keys and track_key not in created_this_frame:
                track.frames_since_seen += 1
                absent_obs = Observation(
                    timestamp=observations[0].timestamp if observations else 0.0,
                    face_present=False,
                    track_key=track_key,
                )
                event = track.event_manager.update(absent_obs)
                if event is not None:
                    events.append(event)

        # --- 5. Prune stale tracks ---------------------------------------
        self._prune_stale()

        return events

    # ------------------------------------------------------------------
    # Association logic (nearest centroid)
    # ------------------------------------------------------------------

    def _associate(
        self, observations: List[Observation],
    ) -> Tuple[List[Tuple[str, Observation]], List[Observation]]:
        """
        Greedy nearest-centroid matching.

        Returns
        -------
        matched : list[(track_key, observation)]
            Observations matched to existing tracks.
        unmatched : list[Observation]
            Observations that didn't match any existing track.
        """
        if not self._tracks or not observations:
            return [], list(observations)

        # Compute centroids for incoming observations
        obs_centroids = []
        for obs in observations:
            if obs.bbox is not None:
                obs_centroids.append(_bbox_centroid(obs.bbox))
            else:
                obs_centroids.append(None)

        # Track keys and their centroids
        track_entries = list(self._tracks.items())

        # Greedy assignment: for each track, find closest unmatched observation
        used_obs: set[int] = set()
        matched: List[Tuple[str, Observation]] = []

        for track_key, track in track_entries:
            best_idx: int | None = None
            best_dist: float = float("inf")

            for i, obs_c in enumerate(obs_centroids):
                if i in used_obs or obs_c is None:
                    continue
                dist = _euclidean(track.last_centroid, obs_c)
                if dist < best_dist:
                    best_dist = dist
                    best_idx = i

            if best_idx is not None and best_dist <= self._association_distance:
                used_obs.add(best_idx)
                matched.append((track_key, observations[best_idx]))

        # Unmatched observations
        unmatched = [
            obs for i, obs in enumerate(observations)
            if i not in used_obs and obs.bbox is not None
        ]
        return matched, unmatched

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_track_key(self) -> str:
        key = f"face_{self._next_id}"
        self._next_id += 1
        return key

    def _prune_stale(self) -> None:
        """Remove tracks that haven't been seen for too long."""
        stale = [
            k for k, t in self._tracks.items()
            if t.frames_since_seen >= self._stale_threshold
        ]
        for k in stale:
            self._log.debug("Pruning stale track %s", k)
            del self._tracks[k]


# ======================================================================
# Pure geometry helpers
# ======================================================================

def _bbox_centroid(bbox: BoundingBox | None) -> Tuple[int, int]:
    """Return (cx, cy) for a bounding box, or (0, 0) if None."""
    if bbox is None:
        return (0, 0)
    return bbox.center


def _euclidean(a: Tuple[int, int], b: Tuple[int, int]) -> float:
    """Euclidean distance between two 2D points."""
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)
