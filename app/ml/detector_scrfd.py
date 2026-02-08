"""
SCRFD face detector backed by ONNX Runtime.

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


class ModelNotFoundError(Exception):
    """The requested ONNX model file does not exist on disk."""


class SCRFDDetector:
    """
    SCRFD face detector.

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
        self._log.info("SCRFD model loaded  (outputs: %s)", self._output_names)

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Run detection on a BGR frame.

        Returns a list of :class:`Detection` objects whose confidence
        exceeds ``self.conf_threshold``.
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
        """Interpret raw ONNX outputs into ``Detection`` objects.

        SCRFD output layout varies by model export.  This implementation
        handles the common single-tensor ``(1, N, 5+)`` format.  Adjust
        here (and only here) if you switch to a different export.
        """
        dets: list[Detection] = []

        if not outputs:
            return dets

        try:
            # Single-tensor format: (1, N, 5+)  x1 y1 x2 y2 score …
            if len(outputs) == 1 and outputs[0].ndim == 3:
                raw = outputs[0][0]  # drop batch dim
                for row in raw:
                    if len(row) < 5:
                        continue
                    score = float(row[4])
                    if score < self.conf_threshold:
                        continue
                    x1 = int(max(0, min(row[0] * sx, frame_w - 1)))
                    y1 = int(max(0, min(row[1] * sy, frame_h - 1)))
                    x2 = int(max(0, min(row[2] * sx, frame_w)))
                    y2 = int(max(0, min(row[3] * sy, frame_h)))
                    if x2 > x1 and y2 > y1:
                        dets.append(
                            Detection(
                                bbox=BoundingBox(x1, y1, x2, y2),
                                confidence=score,
                            )
                        )
        except Exception as exc:  # noqa: BLE001
            self._log.warning("SCRFD output parsing error: %s", exc)

        return dets


# ------------------------------------------------------------------
# MVP helper
# ------------------------------------------------------------------

def select_largest_face(
    detections: List[Detection],
) -> Optional[Detection]:
    """Return the detection with the biggest bounding-box area, or ``None``."""
    if not detections:
        return None
    return max(detections, key=lambda d: d.bbox.area)
