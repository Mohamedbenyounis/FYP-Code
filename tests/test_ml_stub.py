"""
Tests for Iteration 1 — ML-disabled mode and utility functions.

Run with:  pytest tests/ -v
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from app.core.models import BoundingBox, Detection, EnrolledPerson
from app.ml.detector_scrfd import ModelNotFoundError, SCRFDDetector, select_largest_face
from app.ml.recogniser_arcface import ArcFaceRecogniser, load_enrolled_embedding


# ===================================================================
# ModelNotFoundError
# ===================================================================

class TestModelNotFound:
    """ML modules must raise ModelNotFoundError when files are absent."""

    def test_detector_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ModelNotFoundError, match="not found"):
            SCRFDDetector(model_path=tmp_path / "nope.onnx")

    def test_recogniser_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ModelNotFoundError, match="not found"):
            ArcFaceRecogniser(model_path=tmp_path / "nope.onnx")


# ===================================================================
# FacePipeline — ML disabled mode
# ===================================================================

class TestPipelineMLDisabled:
    """When models are missing the pipeline must degrade gracefully."""

    def test_ml_enabled_is_false(self, tmp_path: Path) -> None:
        """Pipeline constructed with missing models → ml_enabled=False."""
        with (
            patch("app.config.SCRFD_MODEL_PATH", tmp_path / "no.onnx"),
            patch("app.config.ARCFACE_MODEL_PATH", tmp_path / "no.onnx"),
        ):
            from app.ml.pipeline import FacePipeline
            pipe = FacePipeline()
            assert pipe.ml_enabled is False

    def test_process_frame_returns_disabled_message(self, tmp_path: Path) -> None:
        """process_frame must return a FrameResult with an explanatory message."""
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        with (
            patch("app.config.SCRFD_MODEL_PATH", tmp_path / "no.onnx"),
            patch("app.config.ARCFACE_MODEL_PATH", tmp_path / "no.onnx"),
        ):
            from app.ml.pipeline import FacePipeline
            pipe = FacePipeline()
            result = pipe.process_frame(dummy_frame)

            assert result.ml_enabled is False
            assert "disabled" in result.message.lower()
            assert result.detections == []
            assert result.primary_detection is None
            assert result.recognition is None


# ===================================================================
# select_largest_face
# ===================================================================

class TestSelectLargestFace:
    def test_empty_list(self) -> None:
        assert select_largest_face([]) is None

    def test_single(self) -> None:
        d = Detection(bbox=BoundingBox(0, 0, 100, 100), confidence=0.9)
        assert select_largest_face([d]) is d

    def test_picks_largest(self) -> None:
        small = Detection(bbox=BoundingBox(0, 0, 50, 50), confidence=0.95)
        large = Detection(bbox=BoundingBox(0, 0, 200, 200), confidence=0.7)
        assert select_largest_face([small, large]) is large


# ===================================================================
# BoundingBox
# ===================================================================

class TestBoundingBox:
    def test_properties(self) -> None:
        b = BoundingBox(10, 20, 110, 120)
        assert b.width == 100
        assert b.height == 100
        assert b.area == 10000
        assert b.center == (60, 70)
        assert b.as_tuple() == (10, 20, 110, 120)


# ===================================================================
# load_enrolled_embedding
# ===================================================================

class TestLoadEnrolledEmbedding:
    def test_missing_file(self, tmp_path: Path) -> None:
        assert load_enrolled_embedding(tmp_path / "nope.npy", "X") is None

    def test_valid_embedding(self, tmp_path: Path) -> None:
        emb = np.random.randn(512).astype(np.float32)
        emb /= np.linalg.norm(emb)
        p = tmp_path / "test.npy"
        np.save(str(p), emb)

        person = load_enrolled_embedding(p, "Alice")
        assert person is not None
        assert person.name == "Alice"
        assert person.embedding.shape == (512,)
        assert abs(np.linalg.norm(person.embedding) - 1.0) < 0.01

    def test_wrong_shape(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.npy"
        np.save(str(p), np.zeros(256))
        assert load_enrolled_embedding(p, "Bad") is None
