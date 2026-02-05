"""
Core data models used across the application.
"""

from dataclasses import dataclass
from typing import Optional
import numpy as np


@dataclass
class BoundingBox:
    """Axis-aligned bounding box for a detected face."""
    x1: int
    y1: int
    x2: int
    y2: int


@dataclass
class Detection:
    """A single face detection result."""
    bbox: BoundingBox
    confidence: float
    keypoints: Optional[np.ndarray] = None


@dataclass
class RecognitionResult:
    """Result of face recognition comparison."""
    name: Optional[str]
    score: float
    is_match: bool


@dataclass
class FrameResult:
    """Aggregated result for a single frame."""
    frame_number: int
    detection: Optional[Detection] = None
    recognition: Optional[RecognitionResult] = None


@dataclass
class EnrolledPerson:
    """A person enrolled in the system."""
    person_id: int
    name: str
    embedding: np.ndarray
