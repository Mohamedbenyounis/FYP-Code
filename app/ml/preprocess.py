"""
Preprocessing utilities for ML models.
"""

from typing import Tuple
import numpy as np

from app.core.models import BoundingBox


def safe_crop_face(frame: np.ndarray, bbox: BoundingBox, padding_ratio: float = 0.2) -> np.ndarray:
    """Safely crop a face region from frame with padding."""
    # TODO: Implement
    return np.array([])


def resize_face(face: np.ndarray, target_size: Tuple[int, int] = (112, 112)) -> np.ndarray:
    """Resize face crop to target size for recognition model."""
    # TODO: Implement
    return np.array([])


def normalize_for_arcface(face: np.ndarray) -> np.ndarray:
    """Normalize face image for ArcFace model input."""
    # TODO: Implement
    return np.array([])


def prepare_frame_for_detection(frame: np.ndarray, input_size: Tuple[int, int] = (640, 640)) -> Tuple[np.ndarray, float, float]:
    """Prepare frame for SCRFD detection model."""
    # TODO: Implement
    return np.array([]), 1.0, 1.0
