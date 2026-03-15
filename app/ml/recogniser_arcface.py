"""
ArcFace face recognition backed by ONNX Runtime.

Internal detail of ``app/ml``.  Consumers call ``ml/pipeline.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import numpy as np

from app import config
from app.core.models import EnrolledPerson, RecognitionResult
from app.ml.detector_scrfd import ModelNotFoundError
from app.services.logging_service import get_logger


class ArcFaceRecogniser:
    """
    ArcFace embedding model (MobileFaceNet / w600k_mbf).

    Loads the ONNX model once.  Provides ``embed`` and ``compare``.
    """

    def __init__(
        self,
        model_path: Optional[Path] = None,
        similarity_threshold: Optional[float] = None,
    ) -> None:
        self._log = get_logger()
        self.model_path = model_path or config.ARCFACE_MODEL_PATH
        self.similarity_threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else config.RECOGNITION_MATCH_THRESHOLD
        )
        self._session = None
        self._input_name: str = ""
        self._output_name: str = ""
        self._load_model()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_model(self) -> None:
        import onnxruntime as ort

        if not self.model_path.exists():
            raise ModelNotFoundError(
                f"ArcFace model not found: {self.model_path}\n"
                "Place the .onnx file in models/ (see docs/SETUP.md)."
            )

        self._log.info("Loading ArcFace model from %s", self.model_path)
        self._session = ort.InferenceSession(
            str(self.model_path),
            providers=config.ONNX_PROVIDERS,
        )
        self._input_name = self._session.get_inputs()[0].name
        self._output_name = self._session.get_outputs()[0].name
        self._log.info("ArcFace model loaded")

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------

    def embed(self, face_crop: np.ndarray) -> np.ndarray:
        """
        Generate a **unit-length** 512-d embedding for *face_crop*.

        ``face_crop`` should be an aligned BGR face image (ideally
        112×112 from :func:`preprocess.align_face_5point`).  Resize
        and ArcFace normalisation are applied internally.
        """
        from app.ml.preprocess import resize_face, normalize_for_arcface

        if self._session is None:
            raise RuntimeError("ArcFace model not loaded")

        tensor = normalize_for_arcface(resize_face(face_crop, (112, 112)))
        raw: np.ndarray = self._session.run(
            [self._output_name], {self._input_name: tensor}
        )[0][0]

        # L2 normalise → cosine similarity becomes a simple dot product
        norm = np.linalg.norm(raw)
        if norm > 0:
            raw = raw / norm
        return raw

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------

    def compare(
        self,
        embedding: np.ndarray,
        enrolled_persons: List[EnrolledPerson],
    ) -> RecognitionResult:
        """
        Compare *embedding* against every enrolled person.

        Returns the best match if above ``self.similarity_threshold``,
        else returns an "unknown" result.
        """
        if not enrolled_persons:
            return RecognitionResult(name=None, score=0.0, is_match=False)

        best_name: Optional[str] = None
        best_score: float = -1.0

        for person in enrolled_persons:
            score = float(np.dot(embedding, person.embedding))
            if score > best_score:
                best_score = score
                best_name = person.name

        is_match = best_score >= self.similarity_threshold
        return RecognitionResult(
            name=best_name if is_match else None,
            score=best_score,
            is_match=is_match,
        )

