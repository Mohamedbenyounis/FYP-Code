"""
ArcFace face recognition using ONNX Runtime.
"""

from pathlib import Path
from typing import List, Optional
import numpy as np

from app.core.models import EnrolledPerson, RecognitionResult


class ArcFaceRecogniser:
    """ArcFace face recognition model."""

    def __init__(self, model_path: Optional[Path] = None, similarity_threshold: Optional[float] = None):
        """Initialize ArcFace recogniser."""
        # TODO: Implement
        pass

    def embed(self, face_crop: np.ndarray) -> np.ndarray:
        """Generate embedding for a face crop."""
        # TODO: Implement
        return np.array([])

    def compare(self, embedding: np.ndarray, enrolled_persons: List[EnrolledPerson]) -> RecognitionResult:
        """Compare embedding against enrolled persons."""
        # TODO: Implement
        return RecognitionResult(name=None, score=0.0, is_match=False)


def load_enrolled_embedding(path: Path, name: str) -> Optional[EnrolledPerson]:
    """Load a single enrolled embedding from .npy file."""
    # TODO: Implement
    return None
