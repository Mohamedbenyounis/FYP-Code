"""
SCRFD face detector backed by ONNX Runtime.

Supports the **det_500m** multi-stride anchor-based output format
(9 heads: 3 strides × {scores, bboxes, keypoints}).

This module is an **internal** detail of ``app/ml``.  External code
(main, services, etc.) should interact through ``ml/pipeline.py`` only.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import numpy as np

from app import config
from app.core.models import BoundingBox, Detection
from app.services.logging_service import get_logger

# Anchor / stride constants for SCRFD det_500m
_FEAT_STRIDES = (8, 16, 32)
_NUM_ANCHORS = 2  # anchors per feature-map cell


class ModelNotFoundError(Exception):
    """The requested ONNX model file does not exist on disk."""


# ------------------------------------------------------------------
# NMS  (pure numpy, IoU-greedy)
# ------------------------------------------------------------------

def _nms(
    boxes: np.ndarray,
    scores: np.ndarray,
    iou_threshold: float,
) -> np.ndarray:
    """
    Non-Maximum Suppression.

    Parameters
    ----------
    boxes : (N, 4) float32   x1 y1 x2 y2
    scores : (N,) float32    confidence
    iou_threshold : float

    Returns
    -------
    np.ndarray  — indices to keep, sorted by descending score.
    """
    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)

    order = scores.argsort()[::-1]
    keep: list[int] = []

    while order.size > 0:
        i = order[0]
        keep.append(int(i))
        if order.size == 1:
            break

        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])

        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)

        remaining = np.where(iou <= iou_threshold)[0]
        order = order[remaining + 1]

    return np.array(keep, dtype=np.intp)


class SCRFDDetector:
    """
    SCRFD face detector (det_500m).

    Loads the ONNX model **once** at construction time.
    Call :py:meth:`detect` per frame.
    """

    def __init__(
        self,
        model_path: Optional[Path] = None,
        conf_threshold: Optional[float] = None,
        input_size: tuple[int, int] = (640, 640),
    ) -> None:
        self._log = get_logger()
        self.model_path = model_path or config.SCRFD_MODEL_PATH
        self.conf_threshold = conf_threshold or config.DETECTION_CONF_THRESH
        self.input_size = input_size
        self._session = None
        self._input_name: str = ""
        self._output_names: list[str] = []
        self._load_model()

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _load_model(self) -> None:
        import onnxruntime as ort

        if not self.model_path.exists():
            raise ModelNotFoundError(
                f"SCRFD model not found: {self.model_path}\n"
                "Place the .onnx file in models/ (see docs/SETUP.md)."
            )

        self._log.info("Loading SCRFD model from %s", self.model_path)
        self._session = ort.InferenceSession(
            str(self.model_path),
            providers=config.ONNX_PROVIDERS,
        )
        self._input_name = self._session.get_inputs()[0].name
        self._output_names = [o.name for o in self._session.get_outputs()]
        self._log.info("SCRFD model loaded  (outputs: %d heads)", len(self._output_names))

    # ------------------------------------------------------------------
    # Anchor grid  (cached per input_size)
    # ------------------------------------------------------------------

    @staticmethod
    def _make_anchor_centers(
        input_h: int, input_w: int, stride: int,
    ) -> np.ndarray:
        """
        Build ``(fh*fw*NUM_ANCHORS, 2)`` anchor centres in pixel coordinates.

        Column order: ``[cx, cy]``.
        """
        fh = input_h // stride
        fw = input_w // stride
        # mgrid[row, col] — note [::-1] swaps to (x, y) order
        grid = np.stack(np.mgrid[:fh, :fw][::-1], axis=-1).astype(np.float32)
        centers = (grid * stride).reshape(-1, 2)
        if _NUM_ANCHORS > 1:
            centers = np.tile(centers, (_NUM_ANCHORS, 1))
            # Re-interleave so that the first fh*fw rows are anchor-0
            # and the next fh*fw rows are anchor-1, matching SCRFD order.
            centers = np.stack(
                [centers[:len(centers) // _NUM_ANCHORS],
                 centers[len(centers) // _NUM_ANCHORS:]],
                axis=1,
            ).reshape(-1, 2)
        return centers

    # ------------------------------------------------------------------
    # Output grouping
    # ------------------------------------------------------------------

    @staticmethod
    def _group_outputs(
        outputs: list[np.ndarray],
    ) -> list[tuple[np.ndarray, np.ndarray, np.ndarray]]:
        """
        Group 9 raw ONNX outputs into ``(scores, bboxes, kps)`` per stride.

        Identification is by shape: ``(N, 1)`` = scores,
        ``(N, 4)`` = bboxes, ``(N, 10)`` = keypoints.
        Strides are sorted largest-anchor-count first (stride 8, 16, 32).
        """
        buckets: dict[int, dict[int, np.ndarray]] = {}
        for tensor in outputs:
            n, c = tensor.shape
            buckets.setdefault(n, {})[c] = tensor

        result: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []
        for n in sorted(buckets.keys(), reverse=True):
            grp = buckets[n]
            result.append((grp[1], grp[4], grp[10]))
        return result

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Run detection on a BGR frame.

        Returns a list of :class:`Detection` objects whose confidence
        exceeds ``self.conf_threshold``, after NMS.
        """
        from app.ml.preprocess import prepare_frame_for_detection

        if self._session is None:
            return []

        h, w = frame.shape[:2]
        input_tensor, sx, sy = prepare_frame_for_detection(frame, self.input_size)

        outputs = self._session.run(self._output_names, {self._input_name: input_tensor})
        return self._parse_outputs(outputs, sx, sy, w, h)

    def _parse_outputs(
        self,
        outputs: list[np.ndarray],
        sx: float,
        sy: float,
        frame_w: int,
        frame_h: int,
    ) -> List[Detection]:
        """
        Decode the 9-head SCRFD det_500m output.

        1. Per stride: generate anchor centres → decode bboxes & keypoints.
        2. Concatenate all strides.
        3. Threshold on confidence.
        4. NMS.
        5. Scale back to original frame coordinates.
        """
        if not outputs or len(outputs) != 9:
            return []

        try:
            stride_groups = self._group_outputs(outputs)
        except (KeyError, ValueError):
            self._log.warning("SCRFD: unexpected output shapes — skipping frame")
            return []

        all_scores: list[np.ndarray] = []
        all_bboxes: list[np.ndarray] = []
        all_kps: list[np.ndarray] = []

        input_h, input_w = self.input_size[1], self.input_size[0]

        for idx, (scores_raw, bbox_raw, kps_raw) in enumerate(stride_groups):
            stride = _FEAT_STRIDES[idx]
            centers = self._make_anchor_centers(input_h, input_w, stride)

            # Scores are already post-sigmoid in the det_500m export
            scores_1d = scores_raw[:, 0]

            # Decode bounding boxes: distance offsets × stride + anchor centre
            dist = bbox_raw * stride
            x1 = centers[:, 0] - dist[:, 0]
            y1 = centers[:, 1] - dist[:, 1]
            x2 = centers[:, 0] + dist[:, 2]
            y2 = centers[:, 1] + dist[:, 3]
            bboxes = np.stack([x1, y1, x2, y2], axis=-1)

            # Decode keypoints: offset × stride + anchor centre
            kps_scaled = kps_raw * stride
            kps_decoded = np.empty_like(kps_scaled)
            for k in range(5):
                kps_decoded[:, 2 * k] = centers[:, 0] + kps_scaled[:, 2 * k]
                kps_decoded[:, 2 * k + 1] = centers[:, 1] + kps_scaled[:, 2 * k + 1]

            all_scores.append(scores_1d)
            all_bboxes.append(bboxes)
            all_kps.append(kps_decoded)

        scores = np.concatenate(all_scores)
        bboxes = np.concatenate(all_bboxes)
        kps = np.concatenate(all_kps)

        # Confidence threshold ------------------------------------------------
        mask = scores >= self.conf_threshold
        scores = scores[mask]
        bboxes = bboxes[mask]
        kps = kps[mask]

        if scores.size == 0:
            return []

        # NMS ------------------------------------------------------------------
        keep = _nms(bboxes, scores, config.NMS_IOU_THRESH)

        # Build Detection objects, scaling to original frame coords -----------
        dets: list[Detection] = []
        for i in keep:
            bx1 = int(max(0, min(bboxes[i, 0] * sx, frame_w - 1)))
            by1 = int(max(0, min(bboxes[i, 1] * sy, frame_h - 1)))
            bx2 = int(max(0, min(bboxes[i, 2] * sx, frame_w)))
            by2 = int(max(0, min(bboxes[i, 3] * sy, frame_h)))

            if bx2 <= bx1 or by2 <= by1:
                continue

            keypoints = np.empty((5, 2), dtype=np.float32)
            for k in range(5):
                keypoints[k, 0] = kps[i, 2 * k] * sx
                keypoints[k, 1] = kps[i, 2 * k + 1] * sy

            dets.append(
                Detection(
                    bbox=BoundingBox(bx1, by1, bx2, by2),
                    confidence=float(scores[i]),
                    keypoints=keypoints,
                )
            )

        return dets


# ------------------------------------------------------------------
# Selection helpers
# ------------------------------------------------------------------

def select_largest_face(
    detections: List[Detection],
) -> Optional[Detection]:
    """Return the detection with the biggest bounding-box area, or ``None``."""
    if not detections:
        return None
    return max(detections, key=lambda d: d.bbox.area)


def select_highest_score(
    detections: List[Detection],
) -> Optional[Detection]:
    """Return the detection with the highest confidence score, or ``None``."""
    if not detections:
        return None
    return max(detections, key=lambda d: d.confidence)
