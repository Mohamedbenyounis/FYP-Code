"""
Tests for ML-layer pure-logic helpers  (ML Integration).

These tests exercise selection helpers, similarity functions, template
generation, alignment output shapes, NMS, and the pipeline decision rule
**without** loading real ONNX models.

Run with:  pytest tests/test_ml_logic.py -v
"""

from __future__ import annotations

import numpy as np
import pytest
from unittest.mock import Mock

from app.core.models import BoundingBox, Detection, RecognitionResult, FrameResult


# ===================================================================
# Fixtures
# ===================================================================

def _det(x1: int, y1: int, x2: int, y2: int, conf: float,
         kps: np.ndarray | None = None) -> Detection:
    """Shortcut to build a Detection."""
    return Detection(
        bbox=BoundingBox(x1, y1, x2, y2),
        confidence=conf,
        keypoints=kps,
    )


def _random_kps() -> np.ndarray:
    """5-point keypoints within a 640×640 frame."""
    return np.array([
        [200, 180], [280, 180], [240, 220], [210, 260], [270, 260]
    ], dtype=np.float32)


# ===================================================================
# select_highest_score
# ===================================================================

class TestSelectHighestScore:

    def test_returns_highest_confidence(self) -> None:
        from app.ml.detector_scrfd import select_highest_score
        dets = [_det(0, 0, 50, 50, 0.6), _det(0, 0, 50, 50, 0.9),
                _det(0, 0, 50, 50, 0.3)]
        assert select_highest_score(dets).confidence == pytest.approx(0.9)

    def test_empty_returns_none(self) -> None:
        from app.ml.detector_scrfd import select_highest_score
        assert select_highest_score([]) is None

    def test_single_detection(self) -> None:
        from app.ml.detector_scrfd import select_highest_score
        d = _det(10, 10, 100, 100, 0.42)
        assert select_highest_score([d]) is d


# ===================================================================
# select_largest_face  (regression — behaviour unchanged)
# ===================================================================

class TestSelectLargestFace:

    def test_returns_largest_area(self) -> None:
        from app.ml.detector_scrfd import select_largest_face
        small = _det(0, 0, 10, 10, 0.9)   # area 100
        big = _det(0, 0, 100, 100, 0.5)    # area 10000
        assert select_largest_face([small, big]) is big

    def test_empty_returns_none(self) -> None:
        from app.ml.detector_scrfd import select_largest_face
        assert select_largest_face([]) is None


# ===================================================================
# cosine_similarity
# ===================================================================

class TestCosineSimilarity:

    def test_identical_vectors(self) -> None:
        from app.ml.preprocess import cosine_similarity
        a = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        assert cosine_similarity(a, a) == pytest.approx(1.0, abs=1e-6)

    def test_orthogonal_vectors(self) -> None:
        from app.ml.preprocess import cosine_similarity
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([0.0, 1.0], dtype=np.float32)
        assert cosine_similarity(a, b) == pytest.approx(0.0, abs=1e-6)

    def test_opposite_vectors(self) -> None:
        from app.ml.preprocess import cosine_similarity
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([-1.0, 0.0], dtype=np.float32)
        assert cosine_similarity(a, b) == pytest.approx(-1.0, abs=1e-6)

    def test_zero_vector_returns_zero(self) -> None:
        from app.ml.preprocess import cosine_similarity
        a = np.zeros(3, dtype=np.float32)
        b = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        assert cosine_similarity(a, b) == 0.0


# ===================================================================
# make_template
# ===================================================================

class TestMakeTemplate:

    def test_single_embedding_returns_normalised(self) -> None:
        from app.ml.preprocess import make_template
        emb = np.random.randn(512).astype(np.float32)
        t = make_template([emb])
        assert t.shape == (512,)
        assert np.linalg.norm(t) == pytest.approx(1.0, abs=1e-5)

    def test_multiple_embeddings(self) -> None:
        from app.ml.preprocess import make_template
        embs = [np.random.randn(512).astype(np.float32) for _ in range(5)]
        t = make_template(embs)
        assert t.shape == (512,)
        assert np.linalg.norm(t) == pytest.approx(1.0, abs=1e-5)

    def test_empty_raises(self) -> None:
        from app.ml.preprocess import make_template
        with pytest.raises(ValueError, match="zero"):
            make_template([])

    def test_dtype_is_float32(self) -> None:
        from app.ml.preprocess import make_template
        emb = np.random.randn(512).astype(np.float64)
        t = make_template([emb])
        assert t.dtype == np.float32


# ===================================================================
# align_face_5point — shape check (no ONNX needed)
# ===================================================================

class TestAlignFace5Point:

    def test_output_shape(self) -> None:
        from app.ml.preprocess import align_face_5point
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        kps = _random_kps()
        aligned = align_face_5point(frame, kps)
        assert aligned is not None
        assert aligned.shape == (112, 112, 3)

    def test_custom_output_size(self) -> None:
        from app.ml.preprocess import align_face_5point
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        kps = _random_kps()
        aligned = align_face_5point(frame, kps, output_size=224)
        assert aligned is not None
        assert aligned.shape == (224, 224, 3)

    def test_returns_none_for_bad_keypoints(self) -> None:
        from app.ml.preprocess import align_face_5point
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        assert align_face_5point(frame, None) is None
        assert align_face_5point(frame, np.zeros((3, 2))) is None

    def test_returns_bgr_dtype(self) -> None:
        from app.ml.preprocess import align_face_5point
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        aligned = align_face_5point(frame, _random_kps())
        assert aligned.dtype == np.uint8


# ===================================================================
# align_face_2point — fallback shape check
# ===================================================================

class TestAlignFace2Point:

    def test_output_shape(self) -> None:
        from app.ml.preprocess import align_face_2point
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        bbox = BoundingBox(100, 100, 300, 300)
        aligned = align_face_2point(frame, bbox)
        assert aligned.shape == (112, 112, 3)


# ===================================================================
# NMS
# ===================================================================

class TestNMS:

    def test_removes_overlapping(self) -> None:
        from app.ml.detector_scrfd import _nms
        boxes = np.array([
            [0, 0, 100, 100],
            [5, 5, 105, 105],  # high IoU with first
            [200, 200, 300, 300],  # no overlap
        ], dtype=np.float32)
        scores = np.array([0.9, 0.8, 0.7], dtype=np.float32)
        keep = _nms(boxes, scores, iou_threshold=0.5)
        assert len(keep) == 2
        assert 0 in keep  # highest score kept
        assert 2 in keep  # non-overlapping kept

    def test_all_kept_when_no_overlap(self) -> None:
        from app.ml.detector_scrfd import _nms
        boxes = np.array([
            [0, 0, 10, 10],
            [100, 100, 110, 110],
            [200, 200, 210, 210],
        ], dtype=np.float32)
        scores = np.array([0.5, 0.6, 0.7], dtype=np.float32)
        keep = _nms(boxes, scores, iou_threshold=0.4)
        assert len(keep) == 3

    def test_single_box(self) -> None:
        from app.ml.detector_scrfd import _nms
        boxes = np.array([[10, 10, 50, 50]], dtype=np.float32)
        scores = np.array([0.9], dtype=np.float32)
        keep = _nms(boxes, scores, iou_threshold=0.4)
        assert list(keep) == [0]

    def test_identical_boxes_keeps_one(self) -> None:
        from app.ml.detector_scrfd import _nms
        boxes = np.array([
            [0, 0, 100, 100],
            [0, 0, 100, 100],
            [0, 0, 100, 100],
        ], dtype=np.float32)
        scores = np.array([0.5, 0.9, 0.3], dtype=np.float32)
        keep = _nms(boxes, scores, iou_threshold=0.5)
        assert len(keep) == 1
        assert keep[0] == 1  # highest score


# ===================================================================
# prepare_frame_for_detection — preprocessing contract
# ===================================================================

class TestPrepareFrameForDetection:

    def test_output_shape_and_dtype(self) -> None:
        from app.ml.preprocess import prepare_frame_for_detection
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        tensor, sx, sy = prepare_frame_for_detection(frame)
        assert tensor.shape == (1, 3, 640, 640)
        assert tensor.dtype == np.float32

    def test_no_normalisation(self) -> None:
        """Values must be normalised to approx [-1, 1] via (x-127.5)/128."""
        from app.ml.preprocess import prepare_frame_for_detection
        frame = np.full((480, 640, 3), 200, dtype=np.uint8)
        tensor, _, _ = prepare_frame_for_detection(frame)
        # (200 - 127.5) / 128.0 ≈ 0.566
        assert tensor.max() < 1.0
        assert tensor.min() >= -1.0

    def test_scales_match_original_frame(self) -> None:
        from app.ml.preprocess import prepare_frame_for_detection
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        _, sx, sy = prepare_frame_for_detection(frame, (640, 640))
        assert sx == pytest.approx(1280 / 640)
        assert sy == pytest.approx(720 / 640)


# ===================================================================
# Adaptive lighting assessment + enhancement
# ===================================================================

class TestAdaptiveLightingHelpers:

    def test_assess_backlighting_triggers_for_bright_bg_dark_center(self) -> None:
        from app.ml.preprocess import assess_backlighting

        frame = np.full((120, 120, 3), 220, dtype=np.uint8)
        frame[30:90, 30:90] = 60

        assessment = assess_backlighting(frame)
        assert assessment.global_mean > assessment.center_mean
        assert assessment.backlit_score > 0
        assert assessment.should_enhance is True

    def test_assess_backlighting_false_for_even_lighting(self) -> None:
        from app.ml.preprocess import assess_backlighting

        frame = np.full((120, 120, 3), 128, dtype=np.uint8)
        assessment = assess_backlighting(frame)
        assert abs(assessment.global_mean - assessment.center_mean) < 1.0
        assert assessment.should_enhance is False

    def test_clahe_preserves_shape_and_dtype(self) -> None:
        from app.ml.preprocess import apply_clahe_for_detection

        frame = np.random.randint(0, 255, (240, 320, 3), dtype=np.uint8)
        enhanced = apply_clahe_for_detection(frame)
        assert enhanced.shape == frame.shape
        assert enhanced.dtype == frame.dtype

    def test_gamma_preserves_shape_and_dtype(self) -> None:
        from app.ml.preprocess import apply_gamma_for_detection

        frame = np.random.randint(0, 255, (240, 320, 3), dtype=np.uint8)
        enhanced = apply_gamma_for_detection(frame)
        assert enhanced.shape == frame.shape
        assert enhanced.dtype == frame.dtype


class _DummyDetector:
    def __init__(self, detections: list[Detection]) -> None:
        self.detections = detections
        self.received_frame = None

    def detect(self, frame: np.ndarray) -> list[Detection]:
        self.received_frame = frame
        return self.detections


class TestPipelineDetectionFrameSelection:

    def test_pipeline_uses_enhanced_frame_when_backlit(self, monkeypatch) -> None:
        from app.ml.pipeline import FacePipeline
        from app.ml.preprocess import LightingAssessment

        raw = np.zeros((100, 100, 3), dtype=np.uint8)
        enhanced = np.full((100, 100, 3), 255, dtype=np.uint8)
        detector = _DummyDetector([])

        pipe = FacePipeline.__new__(FacePipeline)
        pipe._log = Mock()
        pipe._detector = detector
        pipe._recogniser = None
        pipe._enrolled = []
        pipe._enrolled_provider = None
        pipe.ml_enabled = True

        monkeypatch.setattr(
            "app.ml.pipeline.select_detection_frame",
            lambda frame: (
                enhanced,
                LightingAssessment(200.0, 90.0, 110.0, True),
            ),
        )

        pipe.process_frame(raw)
        assert detector.received_frame is enhanced

    def test_pipeline_uses_raw_frame_when_not_backlit(self, monkeypatch) -> None:
        from app.ml.pipeline import FacePipeline
        from app.ml.preprocess import LightingAssessment

        raw = np.zeros((100, 100, 3), dtype=np.uint8)
        detector = _DummyDetector([])

        pipe = FacePipeline.__new__(FacePipeline)
        pipe._log = Mock()
        pipe._detector = detector
        pipe._recogniser = None
        pipe._enrolled = []
        pipe._enrolled_provider = None
        pipe.ml_enabled = True

        monkeypatch.setattr(
            "app.ml.pipeline.select_detection_frame",
            lambda frame: (
                frame,
                LightingAssessment(125.0, 122.0, 3.0, False),
            ),
        )

        pipe.process_frame(raw)
        assert detector.received_frame is raw


# ===================================================================
# Decision rule  (authorised / unknown — via FrameResult)
# ===================================================================

class TestDecisionRule:
    """
    Verify the corrected decision rule:
      authorised iff primary_detection exists AND is_match AND score >= threshold
      unknown    iff no primary OR no recognition OR score < threshold
    """

    def test_authorised(self) -> None:
        """Primary + match + score above threshold → authorised."""
        result = FrameResult(
            detections=[_det(0, 0, 100, 100, 0.8)],
            primary_detection=_det(0, 0, 100, 100, 0.8),
            recognition=RecognitionResult(name="Alice", score=0.6, is_match=True),
            ml_enabled=True,
            detection_enabled=True,
            recognition_enabled=True,
        )
        assert result.primary_detection is not None
        assert result.recognition.is_match is True
        assert result.recognition.score >= 0.25

    def test_unknown_no_match(self) -> None:
        """Primary exists but score below threshold → unknown."""
        result = FrameResult(
            detections=[_det(0, 0, 100, 100, 0.8)],
            primary_detection=_det(0, 0, 100, 100, 0.8),
            recognition=RecognitionResult(name=None, score=0.1, is_match=False),
            ml_enabled=True,
            detection_enabled=True,
            recognition_enabled=True,
        )
        assert result.primary_detection is not None
        assert result.recognition.is_match is False

    def test_unknown_no_primary(self) -> None:
        """No primary detection → unknown regardless of recognition."""
        result = FrameResult(
            detections=[],
            primary_detection=None,
            ml_enabled=True,
            detection_enabled=True,
            recognition_enabled=True,
        )
        assert result.primary_detection is None

    def test_unknown_no_recognition(self) -> None:
        """Primary exists but no recognition result → unknown."""
        result = FrameResult(
            detections=[_det(0, 0, 100, 100, 0.8)],
            primary_detection=_det(0, 0, 100, 100, 0.8),
            recognition=None,
            ml_enabled=True,
            detection_enabled=True,
            recognition_enabled=True,
        )
        assert result.recognition is None

    def test_multiple_detections_primary_authorised(self) -> None:
        """Multiple detections — primary (largest) recognised → authorised."""
        dets = [_det(0, 0, 50, 50, 0.9), _det(0, 0, 200, 200, 0.7)]
        primary = max(dets, key=lambda d: d.bbox.area)
        result = FrameResult(
            detections=dets,
            primary_detection=primary,
            recognition=RecognitionResult(name="Bob", score=0.5, is_match=True),
            ml_enabled=True,
            detection_enabled=True,
            recognition_enabled=True,
        )
        assert len(result.detections) == 2
        assert result.primary_detection is primary
        assert result.recognition.is_match is True
