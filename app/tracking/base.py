"""
Abstract base class for object trackers.
Stub for Iteration 6.
"""

from abc import ABC, abstractmethod
from typing import Optional, Tuple
import numpy as np

from app.core.models import BoundingBox


class Tracker(ABC):
    """Abstract base class for object trackers."""

    @abstractmethod
    def init(self, frame: np.ndarray, bbox: BoundingBox) -> bool:
        """Initialize tracker with frame and bounding box."""
        pass

    @abstractmethod
    def update(self, frame: np.ndarray) -> Tuple[bool, Optional[BoundingBox]]:
        """Update tracker and return new bounding box."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset tracker state."""
        pass
