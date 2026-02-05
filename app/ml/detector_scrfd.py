"""
SCRFD face detector using ONNX Runtime.
"""

from pathlib import Path
from typing import List, Optional
import numpy as np

from app.core.models import Detection


class ModelNotFoundError(Exception):
    """Raised when ONNX model file is not found."""
    pass


class SCRFDDetector:
    """SCRFD face detector."""

    def __init__(self, model_path: Optional[Path] = None, conf_threshold: Optional[float] = None):
        """Initialize SCRFD detector."""
        # TODO: Implement
        pass

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """Detect faces in frame."""
        # TODO: Implement
        return []


def select_largest_face(detections: List[Detection]) -> Optional[Detection]:
    """Select the largest face from detections (MVP single-face rule)."""
    # TODO: Implement
    return None
