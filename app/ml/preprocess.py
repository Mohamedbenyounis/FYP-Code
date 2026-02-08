"""
Preprocessing utilities for the ML pipeline.

All image manipulation (crop, resize, normalise) lives here so that
swapping the model only requires changes inside ``app/ml/``.
"""

from __future__ import annotations

from typing import Tuple

import cv2
import numpy as np

from app.core.models import BoundingBox


# ------------------------------------------------------------------
# Face cropping
# ------------------------------------------------------------------

def safe_crop_face(
    frame: np.ndarray,
    bbox: BoundingBox,
    padding_ratio: float = 0.2,
) -> np.ndarray:
    """
    Crop the face region from *frame* with proportional padding.

    Clamps coordinates to the frame boundary so the result is always valid.

    Args:
        frame: BGR image ``(H, W, 3)``
        bbox: Detected bounding box
        padding_ratio: Extra margin as a fraction of bbox size

    Returns:
        Cropped BGR image (may differ from expected size if bbox is at the edge).
    """
    h, w = frame.shape[:2]
    pad_x = int(bbox.width * padding_ratio)
    pad_y = int(bbox.height * padding_ratio)

    x1 = max(0, bbox.x1 - pad_x)
    y1 = max(0, bbox.y1 - pad_y)
    x2 = min(w, bbox.x2 + pad_x)
    y2 = min(h, bbox.y2 + pad_y)

    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return np.empty((0, 0, 3), dtype=np.uint8)
    return crop.copy()


# ------------------------------------------------------------------
# Resize / normalise for ArcFace
# ------------------------------------------------------------------

def resize_face(
    face: np.ndarray,
    target_size: Tuple[int, int] = (112, 112),
) -> np.ndarray:
    """Resize a face crop to *target_size* ``(W, H)``."""
    return cv2.resize(face, target_size, interpolation=cv2.INTER_LINEAR)


def normalize_for_arcface(face: np.ndarray) -> np.ndarray:
    """
    Prepare a face image for ArcFace inference.

    * BGR → RGB
    * Scale to ``[-1, 1]``
    * ``HWC → CHW``
    * Add batch dimension → ``(1, 3, 112, 112)``
    """
    rgb = cv2.cvtColor(face, cv2.COLOR_BGR2RGB)
    norm = (rgb.astype(np.float32) - 127.5) / 127.5
    chw = norm.transpose(2, 0, 1)
    return np.expand_dims(chw, axis=0)


# ------------------------------------------------------------------
# Resize / normalise for SCRFD detection
# ------------------------------------------------------------------

def prepare_frame_for_detection(
    frame: np.ndarray,
    input_size: Tuple[int, int] = (640, 640),
) -> Tuple[np.ndarray, float, float]:
    """
    Resize and normalise a frame for SCRFD.

    Returns:
        ``(input_tensor, scale_x, scale_y)`` where the scales map
        model-space coordinates back to the original frame.
    """
    h, w = frame.shape[:2]
    input_w, input_h = input_size
    scale_x = w / input_w
    scale_y = h / input_h

    resized = cv2.resize(frame, input_size, interpolation=cv2.INTER_LINEAR)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    norm = rgb.astype(np.float32) / 255.0
    chw = norm.transpose(2, 0, 1)
    return np.expand_dims(chw, axis=0), scale_x, scale_y
