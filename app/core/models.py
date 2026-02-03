"""
Core data models used across the application.
All models are plain dataclasses — no framework dependency.
"""

from __future__ import annotations

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
    """

    detections: List[Detection] = field(default_factory=list)
    primary_detection: Optional[Detection] = None
    recognition: Optional[RecognitionResult] = None
    ml_enabled: bool = False
    message: str = ""


# ---------------------------------------------------------------------------
# Enrolled person (gallery entry)
# ---------------------------------------------------------------------------

@dataclass
class EnrolledPerson:
    """
    A person enrolled in the system.
    Iteration 1: loaded from .npy file.
    Iteration 2+: loaded from database.
    """

    person_id: int
    name: str
    embedding: np.ndarray
