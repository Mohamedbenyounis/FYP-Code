"""
Tests for atomic multi-capture enrollment service logic.
"""
from unittest import mock
import numpy as np
import pytest

from app.services.enrollment_service import enroll_from_multiple_images
from app.core.models import Detection, BoundingBox

@pytest.fixture
def mock_clean_detection():
    # Helper to return a mock 1-face detection map
    return [
        Detection(
            bbox=BoundingBox(10, 10, 90, 90),
            confidence=0.99,
            keypoints=np.array([(20,20), (30,20), (25, 30), (20, 40), (30, 40)], dtype=np.float32)
        )
    ]

@mock.patch("app.services.enrollment_service.init_db")
@mock.patch("app.services.enrollment_service.SQLiteEmbeddingRepository")
@mock.patch("app.services.enrollment_service.SQLitePersonRepository")
@mock.patch("app.services.enrollment_service.ArcFaceRecogniser")
@mock.patch("app.services.enrollment_service.SCRFDDetector")
def test_multi_image_successful_enrollment(
    mock_detector_cls, mock_rec_cls, mock_person_repo, mock_emb_repo, mock_db, mock_clean_detection
):
    """Ensure passing 3 valid images successfully calls the repo methods."""
    # Setup mocks
    mock_det_instance = mock_detector_cls.return_value
    mock_det_instance.detect.return_value = mock_clean_detection
    
    mock_rec_instance = mock_rec_cls.return_value
    mock_rec_instance.embed.return_value = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    
    mock_emb_repo_instance = mock_emb_repo.return_value
    mock_emb_repo_instance.get_embeddings.return_value = [np.array([0.1, 0.2, 0.3], dtype=np.float32)]
    
    # Send 3 identical fake numpy arrays
    fake_images = [np.zeros((100, 100, 3), dtype=np.uint8) for _ in range(3)]
    
    result = enroll_from_multiple_images("Target Name", fake_images, min_captures=3)
    
    assert result.success is True, result.message
    assert "Successfully enrolled" in result.message
    # Assert ML ran 3 times
    assert mock_det_instance.detect.call_count == 3
    assert mock_rec_instance.embed.call_count == 3

@mock.patch("app.services.enrollment_service.SCRFDDetector")
def test_multi_image_below_threshold_rejection(
    mock_detector_cls, mock_clean_detection
):
    """Ensure passing images containing NO faces fails the threshold requirement cleanly."""
    mock_det_instance = mock_detector_cls.return_value
    
    # Return 1 good face, then 2 empty lists (no faces on frames 2 & 3)
    mock_det_instance.detect.side_effect = [mock_clean_detection, [], []]
    
    fake_images = [np.zeros((100, 100, 3), dtype=np.uint8) for _ in range(3)]
    
    # We require 3, but only 1 will actually return a face
    result = enroll_from_multiple_images("Bad Submitter", fake_images, min_captures=3)
    
    assert result.success is False
    assert "Only 1/3 valid captures" in result.message
