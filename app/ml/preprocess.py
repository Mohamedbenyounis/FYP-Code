"""
Preprocessing utilities for the ML pipeline.

All image manipulation (crop, resize, normalise, align) lives here so
that swapping the model only requires changes inside ``app/ml/``.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import cv2
import numpy as np

from app.core.models import BoundingBox


# ------------------------------------------------------------------
# ArcFace 112×112 reference landmarks  (5-point, from InsightFace)
# ------------------------------------------------------------------

ARCFACE_REF_LANDMARKS = np.array(
    [
        [38.2946, 51.6963],   # left eye
        [73.5318, 51.5014],   # right eye
        [56.0252, 71.7366],   # nose tip
        [41.5493, 92.3655],   # left mouth corner
        [70.7299, 92.2041],   # right mouth corner
    ],
    dtype=np.float32,
)


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
# 5-point face alignment  (runtime — uses detected keypoints)
# ------------------------------------------------------------------

def align_face_5point(
    frame: np.ndarray,
    keypoints: np.ndarray,
    output_size: int = 112,
) -> Optional[np.ndarray]:
    """
    Align a face to the ArcFace canonical pose via a similarity transform.

    Parameters
    ----------
    frame : np.ndarray
        Full BGR image ``(H, W, 3)``.
    keypoints : np.ndarray
        Detected 5-point landmarks ``(5, 2)`` in pixel coordinates of
        *frame* — ``[[x,y], ...]`` for left-eye, right-eye, nose,
        left-mouth, right-mouth.
    output_size : int
        Side length of the output square crop (default 112 for ArcFace).

    Returns
    -------
    np.ndarray | None
        Aligned BGR face crop ``(output_size, output_size, 3)``, or
        ``None`` if the transform estimation fails.
    """
    if keypoints is None or keypoints.shape != (5, 2):
        return None

    src = keypoints.astype(np.float32)
    dst = ARCFACE_REF_LANDMARKS.copy()

    # Scale reference if output_size differs from 112
    if output_size != 112:
        dst = dst * (output_size / 112.0)

    M, _ = cv2.estimateAffinePartial2D(src, dst)
    if M is None:
        return None

    return cv2.warpAffine(
        frame, M, (output_size, output_size), borderValue=(0, 0, 0)
    )


# ------------------------------------------------------------------
# 2-point face alignment  (GT / fallback — estimates eyes from bbox)
# ------------------------------------------------------------------

def align_face_2point(
    frame: np.ndarray,
    bbox: BoundingBox,
    output_size: int = 112,
) -> np.ndarray:
    """
    Align a face using eye positions estimated from the bounding box.

    This is a coarse fallback for when 5-point keypoints are unavailable.
    Eye centres are heuristically placed at 35 % from the top and
    ±17.5 % horizontally from the bbox centre.

    Returns
    -------
    np.ndarray
        Aligned BGR face crop ``(output_size, output_size, 3)``.
    """
    cx = (bbox.x1 + bbox.x2) / 2.0
    cy = bbox.y1 + bbox.height * 0.35
    half_eye = bbox.width * 0.175

    src = np.array(
        [[cx - half_eye, cy], [cx + half_eye, cy]],
        dtype=np.float32,
    )
    dst = ARCFACE_REF_LANDMARKS[:2].copy()  # left-eye, right-eye refs
    if output_size != 112:
        dst = dst * (output_size / 112.0)

    M, _ = cv2.estimateAffinePartial2D(src, dst)
    if M is None:
        # Ultimate fallback: simple crop + resize
        return resize_face(safe_crop_face(frame, bbox), (output_size, output_size))

    return cv2.warpAffine(
        frame, M, (output_size, output_size), borderValue=(0, 0, 0)
    )


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

    * BGR → RGB  (``swapRB`` to match InsightFace training convention)
    * Scale to ``[-1, 1]``  via ``(x − 127.5) / 127.5``
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
    Resize and format a frame for SCRFD (det_500m).

    The det_500m model expects **RGB float32** normalised with
    ``(x − 127.5) / 128.0`` in CHW layout with a batch dimension.
    This matches the InsightFace SCRFD training convention.

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
    blob = (rgb.astype(np.float32) - 127.5) / 128.0   # normalise
    chw = blob.transpose(2, 0, 1)                      # HWC → CHW
    return np.expand_dims(chw, axis=0), scale_x, scale_y


# ------------------------------------------------------------------
# Embedding / template helpers
# ------------------------------------------------------------------

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two 1-D vectors (safe against zero-norm)."""
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def make_template(embeddings: List[np.ndarray]) -> np.ndarray:
    """
    Compute an L2-normalised mean template from one or more embeddings.

    Raises ``ValueError`` if *embeddings* is empty.
    """
    if not embeddings:
        raise ValueError("Cannot make template from zero embeddings")

    stacked = np.stack(embeddings, axis=0)       # (N, D)
    mean = stacked.mean(axis=0)                  # (D,)
    norm = np.linalg.norm(mean)
    if norm > 0:
        mean = mean / norm
    return mean.astype(np.float32)
