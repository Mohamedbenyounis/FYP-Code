"""
Tracking manager for coordinating ML and tracking.
Stub for Iteration 6.
"""

from typing import Optional
import numpy as np

from app.core.models import BoundingBox, Detection


class TrackingManager:
    """Manages object tracking between ML inference calls."""

    def __init__(self) -> None:
        # TODO: Implement in Iteration 6
        pass

    def update(self, frame: np.ndarray, detection: Optional[Detection] = None) -> Optional[BoundingBox]:
        """Update tracking state."""
        # TODO: Implement in Iteration 6
        if detection:
            return detection.bbox
        return None

    def should_run_ml(self, frame_number: int) -> bool:
        """Decide if ML should run on this frame."""
        # TODO: Implement in Iteration 6
        return True
