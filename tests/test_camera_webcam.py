from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from app.camera.webcam import WebcamCamera
import numpy as np

@patch("app.camera.webcam.cv2.VideoCapture")
def test_webcam_unopened_safe_handling(mock_vc_cls):
    """If webcam fails to open, ensure no crash and is_opened returns False."""
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = False
    mock_vc_cls.return_value = mock_cap
    
    cam = WebcamCamera(device_index=0)
    
    assert not cam.is_opened()
    
    ok, frame = cam.read()
    assert not ok
    assert frame is None

@patch("app.camera.webcam.cv2.VideoCapture")
def test_webcam_read_failure_safe_handling(mock_vc_cls):
    """If webcam reads fail, handles safely."""
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.read.return_value = (False, None)
    mock_vc_cls.return_value = mock_cap
    
    cam = WebcamCamera(device_index=0)
    assert cam.is_opened()
    
    ok, frame = cam.read()
    assert not ok
    assert frame is None
