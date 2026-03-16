"""
Core data models used across the application.
All models are plain dataclasses — no framework dependency.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional, List

import numpy as np


# ---------------------------------------------------------------------------
# Bounding box
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BoundingBox:
    """Axis-aligned bounding box (pixel coordinates)."""

    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def center(self) -> tuple[int, int]:
        return ((self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2)

    def as_tuple(self) -> tuple[int, int, int, int]:
        """Return (x1, y1, x2, y2)."""
        return (self.x1, self.y1, self.x2, self.y2)

    def to_json(self) -> str:
        """Serialise to a JSON string for DB storage."""
        return json.dumps(
            {"x1": self.x1, "y1": self.y1, "x2": self.x2, "y2": self.y2}
        )

    @classmethod
    def from_json(cls, s: str) -> BoundingBox:
        """Reconstruct from a JSON string."""
        d = json.loads(s)
        return cls(x1=d["x1"], y1=d["y1"], x2=d["x2"], y2=d["y2"])


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

@dataclass
class Detection:
    """A single face detection result from SCRFD (or any detector)."""

    bbox: BoundingBox
    confidence: float
    keypoints: Optional[np.ndarray] = None  # (5, 2) landmarks, optional


# ---------------------------------------------------------------------------
# Recognition
# ---------------------------------------------------------------------------

@dataclass
class RecognitionResult:
    """Result of comparing an embedding to the enrolled gallery."""

    name: Optional[str]   # None ⇒ unknown
    score: float           # cosine similarity
    is_match: bool = False


# ---------------------------------------------------------------------------
# Frame‑level aggregate (the contract between pipeline and main)
# ---------------------------------------------------------------------------

@dataclass
class FrameResult:
    """
    Aggregated ML output for one frame.

    This is the **stable public contract** between ``ml/pipeline.py`` and
    every consumer (main loop, event manager, dashboard …).
    If you change the ML backend, only the *producer* changes — not consumers.

    Iteration 7 added multi-face detection (``detections`` list).
    Iteration 8 adds multi-face recognition (``recognitions`` list,
    aligned 1:1 with ``detections``).

    Backward compatibility
    ----------------------
    ``primary_detection`` / ``primary_recognition`` / ``recognition``
    continue to expose single-face results for EventManager and
    existing consumers that have not yet migrated to multi-face.
    """

    detections: List[Detection] = field(default_factory=list)
    recognitions: List[Optional[RecognitionResult]] = field(default_factory=list)
    primary_detection: Optional[Detection] = None
    ml_enabled: bool = False
    detection_enabled: bool = False
    recognition_enabled: bool = False
    message: str = ""

    @property
    def detection_count(self) -> int:
        """Number of detections in this frame."""
        return len(self.detections)

    @property
    def primary_recognition(self) -> Optional[RecognitionResult]:
        """Recognition result for the primary (largest) face, or None."""
        if self.primary_detection is None:
            return None
        try:
            idx = self.detections.index(self.primary_detection)
            if idx < len(self.recognitions):
                return self.recognitions[idx]
        except ValueError:
            pass
        return None

    @property
    def recognition(self) -> Optional[RecognitionResult]:
        """Backward-compatible alias for ``primary_recognition``."""
        return self.primary_recognition


# ---------------------------------------------------------------------------
# Enrolled person (gallery entry)
# ---------------------------------------------------------------------------

@dataclass
class EnrolledPerson:
    """
    A person enrolled in the system.
    Loaded from the SQLite database via ``db/repo.py``.
    """

    person_id: int
    name: str
    embedding: np.ndarray


# ---------------------------------------------------------------------------
# Observation — raw per-frame input to the EventManager  (Iteration 3)
# ---------------------------------------------------------------------------

@dataclass
class Observation:
    """
    A single processed-frame observation fed into the EventManager.

    Built by ``main.py`` from a ``FrameResult``.  The event manager
    accumulates observations to decide when to emit an ``Event``.
    """

    timestamp: float                          # time.monotonic() seconds
    face_present: bool                        # True if primary_detection exists
    person_name: Optional[str] = None         # recognised name (None ⇒ unknown)
    person_id: Optional[int] = None           # DB id, if recognised
    score: float = 0.0                        # cosine similarity
    bbox: Optional[BoundingBox] = None        # primary face bbox


# ---------------------------------------------------------------------------
# Event — confirmed presence event written to the DB  (Iteration 3)
# ---------------------------------------------------------------------------

@dataclass
class Event:
    """
    A confirmed presence event emitted by the EventManager and persisted
    to the ``events`` table via ``db/repo.py``.

    Fields
    ------
    event_id : str
        UUID-4 string (generated at emission time).
    created_at : str
        UTC ISO 8601 timestamp.
    status : str
        ``"authorised"`` or ``"unauthorised"``.
    person_name : str | None
        Display name if recognised, else None.
    person_id : int | None
        DB person id if recognised, else None.
    score : float | None
        Best cosine similarity during the confirmed observation window.
    bbox_json : str | None
        JSON-serialised bounding box at confirmation time.
    snapshot_path : str | None
        Reserved for Iteration 4 (always None for now).
    clip_path : str | None
        Reserved for Iteration 4 (always None for now).
    """

    event_id: str
    created_at: str
    status: str
    person_name: Optional[str] = None
    person_id: Optional[int] = None
    score: Optional[float] = None
    bbox_json: Optional[str] = None
    snapshot_path: Optional[str] = None
    clip_path: Optional[str] = None
