"""
Hardware resilience & camera failure tests.

Validates:
  - WebcamCamera repeated read failure handling
  - WebcamCamera reconnect logic
  - RTSPCamera mid-stream disconnect + reconnect
  - System does not crash during repeated hardware failures
  - Release idempotency
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, call

import numpy as np

from app.camera.webcam import WebcamCamera
from app.camera.rtsp import RTSPCamera


# ===================================================================
# WebcamCamera — Additional Negative Tests
# ===================================================================

class TestWebcamRepeatedFailure:
    """Test that repeated read() failures are handled safely."""

    @patch("app.camera.webcam.cv2.VideoCapture")
    def test_repeated_read_failure_no_crash(self, mock_vc_cls):
        """10 consecutive read() == False does not crash the camera."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (False, None)
        mock_vc_cls.return_value = mock_cap

        cam = WebcamCamera(device_index=0)
        for _ in range(10):
            ok, frame = cam.read()
            assert not ok
            assert frame is None
        # Still alive
        assert cam.is_opened()

    @patch("app.camera.webcam.time.sleep")
    @patch("app.camera.webcam.cv2.VideoCapture")
    def test_reconnect_success(self, mock_vc_cls, mock_sleep):
        """Webcam reconnect succeeds after device comes back."""
        mock_cap_bad = MagicMock()
        mock_cap_bad.isOpened.return_value = False

        mock_cap_good = MagicMock()
        mock_cap_good.isOpened.return_value = True
        mock_cap_good.get.return_value = 640

        # init=bad, attempt1=bad, attempt2=good
        mock_vc_cls.side_effect = [mock_cap_bad, mock_cap_bad, mock_cap_good]

        cam = WebcamCamera(device_index=0)
        assert not cam.is_opened()

        result = cam.reconnect(max_attempts=3, delay_seconds=0.01)
        assert result is True
        assert cam.is_opened()

    @patch("app.camera.webcam.time.sleep")
    @patch("app.camera.webcam.cv2.VideoCapture")
    def test_reconnect_all_attempts_fail(self, mock_vc_cls, mock_sleep):
        """Webcam reconnect returns False after exhausting all attempts."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_vc_cls.return_value = mock_cap

        cam = WebcamCamera(device_index=0)
        result = cam.reconnect(max_attempts=3, delay_seconds=0.01)
        assert result is False

    @patch("app.camera.webcam.cv2.VideoCapture")
    def test_release_then_read_safe(self, mock_vc_cls):
        """Reading after release returns (False, None) without crash."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_vc_cls.return_value = mock_cap

        cam = WebcamCamera(device_index=0)
        cam.release()
        ok, frame = cam.read()
        assert not ok
        assert frame is None

    @patch("app.camera.webcam.cv2.VideoCapture")
    def test_double_release_safe(self, mock_vc_cls):
        """Calling release() twice doesn't crash."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_vc_cls.return_value = mock_cap

        cam = WebcamCamera(device_index=0)
        cam.release()
        cam.release()  # Should not raise


# ===================================================================
# RTSPCamera — Mid-Stream Disconnect Tests
# ===================================================================

class TestRTSPMidStreamDisconnect:
    """Simulate RTSP stream dropping mid-session."""

    @patch("app.camera.rtsp.cv2.VideoCapture")
    def test_read_ok_then_fail_then_ok(self, mock_vc_cls):
        """Stream works, drops, then is read again — no crash."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value = 640

        fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cap.read.side_effect = [
            (True, fake_frame),
            (True, fake_frame),
            (False, None),  # disconnect!
            (False, None),
            (True, fake_frame),  # recovered
        ]
        mock_vc_cls.return_value = mock_cap

        cam = RTSPCamera("rtsp://test")

        # Read 1-2: OK
        ok, f = cam.read()
        assert ok
        ok, f = cam.read()
        assert ok
        # Read 3-4: Disconnect
        ok, f = cam.read()
        assert not ok
        ok, f = cam.read()
        assert not ok
        # Read 5: Recovery
        ok, f = cam.read()
        assert ok

    @patch("app.camera.rtsp.cv2.VideoCapture")
    def test_repeated_read_failure_stress(self, mock_vc_cls):
        """10 consecutive RTSP read failures are handled gracefully."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value = 640
        mock_cap.read.return_value = (False, None)
        mock_vc_cls.return_value = mock_cap

        cam = RTSPCamera("rtsp://test")
        for i in range(10):
            ok, frame = cam.read()
            assert not ok, f"Read {i} should fail"
        # Camera object still alive
        assert cam.is_opened()

    @patch("app.camera.rtsp.time.sleep")
    @patch("app.camera.rtsp.cv2.VideoCapture")
    def test_reconnect_after_mid_stream_drop(self, mock_vc_cls, mock_sleep):
        """After stream drops, reconnect() re-establishes connection."""
        mock_cap_ok = MagicMock()
        mock_cap_ok.isOpened.return_value = True
        mock_cap_ok.get.return_value = 640

        # init=OK, reconnect attempt 1=OK
        mock_vc_cls.side_effect = [mock_cap_ok, mock_cap_ok]

        cam = RTSPCamera("rtsp://test")
        result = cam.reconnect(max_attempts=1, delay_seconds=0.01)
        assert result is True

    @patch("app.camera.rtsp.cv2.VideoCapture")
    def test_malformed_url_initializes_without_crash(self, mock_vc_cls):
        """Malformed RTSP URL doesn't crash — just fails to open."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_vc_cls.return_value = mock_cap

        cam = RTSPCamera("not-a-valid-rtsp-url")
        assert not cam.is_opened()
