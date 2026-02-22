"""
FacePipeline — the **single stable interface** between the ML subsystem
and every consumer (main loop, event manager, dashboard, tests …).

External code calls ``pipeline.process_frame(frame)`` and receives a
:class:`FrameResult`.  Swapping model backends (SCRFD → YOLO, ArcFace →
AdaFace, etc.) only requires changes inside ``app/ml/`` — nothing else.

The enrolled gallery is loaded via an injectable *provider* callable.
This keeps SQL out of ``app/ml/``.
"""

from __future__ import annotations

from typing import Callable, List, Optional

import numpy as np

from app import config
from app.core.models import (
    Detection,
    EnrolledPerson,
    FrameResult,
    RecognitionResult,
)
from app.ml.detector_scrfd import ModelNotFoundError, SCRFDDetector, select_largest_face
from app.ml.recogniser_arcface import ArcFaceRecogniser
from app.ml.preprocess import safe_crop_face
from app.services.logging_service import get_logger

# Type alias for the provider — any zero-arg callable returning persons.
EnrolledProvider = Callable[[], List[EnrolledPerson]]


class FacePipeline:
    """
    High-level facade that owns detector + recogniser + enrolled gallery.

    Construction tries to load both ONNX models.  If either model file is
    missing the pipeline degrades gracefully and ``ml_enabled`` is ``False``.

    Parameters
    ----------
    enrolled_provider : EnrolledProvider, optional
        A zero-arg callable that returns the current list of enrolled
        persons.  Called **once** during ``__init__`` and can be refreshed
        later via :meth:`reload_enrolled`.  When ``None`` the pipeline
        runs without recognition (all faces labelled *Unknown*).
    """

    def __init__(
        self,
        enrolled_provider: Optional[EnrolledProvider] = None,
    ) -> None:
        self._log = get_logger()

        # Attempt to load detector ------------------------------------------
        self._detector: Optional[SCRFDDetector] = None
        self._recogniser: Optional[ArcFaceRecogniser] = None
        self._enrolled: List[EnrolledPerson] = []
        self._enrolled_provider = enrolled_provider
        self.ml_enabled: bool = False

        if not config.ML_ENABLED_AUTO:
            self._log.info("ML explicitly disabled via config")
            return

        try:
            self._detector = SCRFDDetector()
        except ModelNotFoundError as exc:
            self._log.warning("Detector unavailable: %s", exc)

        try:
            self._recogniser = ArcFaceRecogniser()
        except ModelNotFoundError as exc:
            self._log.warning("Recogniser unavailable: %s", exc)

        self.ml_enabled = self._detector is not None

        if self.ml_enabled:
            self._log.info(
                "ML pipeline — detection_enabled=%s  recognition_enabled=%s",
                self.detection_enabled,
                self.recognition_enabled,
            )
        else:
            self._log.warning(
                "ML DISABLED — detection_enabled=%s  recognition_enabled=%s",
                self.detection_enabled,
                self.recognition_enabled,
            )

        # Load enrolled gallery via provider ---------------------------------
        if self._recogniser is not None:
            self.reload_enrolled()

    # ------------------------------------------------------------------
    # ML status properties
    # ------------------------------------------------------------------

    @property
    def detection_enabled(self) -> bool:
        """True when the SCRFD detector model is loaded."""
        return self._detector is not None

    @property
    def recognition_enabled(self) -> bool:
        """True when the ArcFace recogniser model is loaded."""
        return self._recogniser is not None

    # ------------------------------------------------------------------
    # Enrolled gallery management
    # ------------------------------------------------------------------

    def reload_enrolled(self) -> None:
        """
        Refresh the enrolled gallery from the provider.

        Safe to call at any time — e.g. after a new enrolment.
        """
        if self._enrolled_provider is None:
            self._enrolled = []
            self._log.info("No enrolled provider — all faces will be Unknown")
            return

        try:
            self._enrolled = self._enrolled_provider()
            self._log.info(
                "Enrolled gallery: %d person(s)", len(self._enrolled)
            )
        except Exception as exc:  # noqa: BLE001
            self._log.error("Failed to load enrolled gallery: %s", exc)
            self._enrolled = []

    # ------------------------------------------------------------------
    # Public stable interface
    # ------------------------------------------------------------------

    def process_frame(self, frame: np.ndarray) -> FrameResult:
        """
        Run the full ML pipeline on a single BGR frame.

        This is the **only method** external code needs to call.

        Returns:
            A :class:`FrameResult` populated with detection and recognition
            data (or a descriptive *message* if ML is disabled).
        """
        if not self.ml_enabled or self._detector is None:
            return FrameResult(
                ml_enabled=False,
                detection_enabled=self.detection_enabled,
                recognition_enabled=self.recognition_enabled,
                message=(
                    f"ML disabled — detection={self.detection_enabled}"
                    f"  recognition={self.recognition_enabled}"
                ),
            )

        # 1. Detect --------------------------------------------------------
        detections = self._detector.detect(frame)

        if not detections:
            return FrameResult(
                detections=[],
                ml_enabled=True,
                detection_enabled=self.detection_enabled,
                recognition_enabled=self.recognition_enabled,
                message="No faces detected",
            )

        # 2. MVP single-face rule ------------------------------------------
        primary = select_largest_face(detections)

        result = FrameResult(
            detections=detections,
            primary_detection=primary,
            ml_enabled=True,
            detection_enabled=self.detection_enabled,
            recognition_enabled=self.recognition_enabled,
        )

        if primary is None:
            result.message = "No primary face selected"
            return result

        # 3. Recognition (optional — needs recogniser + crop) ---------------
        if self._recogniser is not None:
            crop = safe_crop_face(frame, primary.bbox)
            if crop.size == 0:
                result.message = (
                    f"Detected face conf={primary.confidence:.2f} "
                    f"bbox={primary.bbox.as_tuple()} — crop failed"
                )
                return result

            try:
                embedding = self._recogniser.embed(crop)
                recognition = self._recogniser.compare(embedding, self._enrolled)
                result.recognition = recognition

                if recognition.is_match:
                    result.message = (
                        f"Recognised: {recognition.name} "
                        f"score={recognition.score:.3f}"
                    )
                else:
                    result.message = (
                        f"Unknown face score={recognition.score:.3f} "
                        f"(thresh={config.RECOGNITION_SIM_THRESH})"
                    )
            except Exception as exc:  # noqa: BLE001
                self._log.error("Recognition error: %s", exc)
                result.message = f"Detection OK, recognition failed: {exc}"
        else:
            bbox = primary.bbox
            result.message = (
                f"Detected face conf={primary.confidence:.2f} "
                f"bbox={bbox.as_tuple()} — recogniser not loaded"
            )

        return result
