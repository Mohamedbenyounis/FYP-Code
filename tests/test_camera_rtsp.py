"""
Unit tests for the RTSP camera source and config-based camera selection.

All tests mock ``cv2.VideoCapture`` so they run without a live RTSP server.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np

from app.camera.rtsp import RTSPCamera


# =========================================================================
# RTSPCamera unit tests
# =========================================================================


class TestRTSPCameraInit(unittest.TestCase):
    """Verify RTSPCamera opens a VideoCapture on construction."""

    @patch("app.camera.rtsp.cv2.VideoCapture")
    def test_init_opens_capture(self, mock_vc_cls):
        """Constructor should call VideoCapture(url, CAP_FFMPEG)."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value = 640  # frame_width / frame_height
        mock_vc_cls.return_value = mock_cap

        cam = RTSPCamera("rtsp://192.168.1.50:8554/cam")

        mock_vc_cls.assert_called_once()
        # First positional arg should be the URL
        args, kwargs = mock_vc_cls.call_args
        self.assertEqual(args[0], "rtsp://192.168.1.50:8554/cam")
        self.assertTrue(cam.is_opened())

    @patch("app.camera.rtsp.cv2.VideoCapture")
    def test_init_fails_gracefully(self, mock_vc_cls):
        """If VideoCapture fails to open, is_opened() returns False."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_vc_cls.return_value = mock_cap

        cam = RTSPCamera("rtsp://bad-url")

        self.assertFalse(cam.is_opened())


class TestRTSPCameraRead(unittest.TestCase):
    """Verify frame reading behaviour."""

    def _make_camera(self, mock_vc_cls):
        """Helper: create an RTSPCamera with a mocked capture."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value = 640
        mock_vc_cls.return_value = mock_cap
        cam = RTSPCamera("rtsp://test")
        return cam, mock_cap

    @patch("app.camera.rtsp.cv2.VideoCapture")
    def test_read_success(self, mock_vc_cls):
        """Successful read() returns (True, frame)."""
        cam, mock_cap = self._make_camera(mock_vc_cls)

        fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cap.read.return_value = (True, fake_frame)

        ok, frame = cam.read()

        self.assertTrue(ok)
        self.assertIsNotNone(frame)
        np.testing.assert_array_equal(frame, fake_frame)

    @patch("app.camera.rtsp.cv2.VideoCapture")
    def test_read_failure(self, mock_vc_cls):
        """Failed read() returns (False, None)."""
        cam, mock_cap = self._make_camera(mock_vc_cls)
        mock_cap.read.return_value = (False, None)

        ok, frame = cam.read()

        self.assertFalse(ok)
        self.assertIsNone(frame)

    @patch("app.camera.rtsp.cv2.VideoCapture")
    def test_read_when_not_opened(self, mock_vc_cls):
        """read() returns (False, None) if capture is not opened."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_vc_cls.return_value = mock_cap

        cam = RTSPCamera("rtsp://dead")
        ok, frame = cam.read()

        self.assertFalse(ok)
        self.assertIsNone(frame)


class TestRTSPCameraRelease(unittest.TestCase):
    """Verify resource cleanup."""

    @patch("app.camera.rtsp.cv2.VideoCapture")
    def test_release_calls_cap_release(self, mock_vc_cls):
        """release() should call the underlying capture's release."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value = 640
        mock_vc_cls.return_value = mock_cap

        cam = RTSPCamera("rtsp://test")
        cam.release()

        mock_cap.release.assert_called_once()
        self.assertFalse(cam.is_opened())

    @patch("app.camera.rtsp.cv2.VideoCapture")
    def test_release_idempotent(self, mock_vc_cls):
        """Calling release() twice should not raise."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value = 640
        mock_vc_cls.return_value = mock_cap

        cam = RTSPCamera("rtsp://test")
        cam.release()
        cam.release()  # Second call — should not raise


class TestRTSPCameraReconnect(unittest.TestCase):
    """Verify reconnect retry logic."""

    @patch("app.camera.rtsp.time.sleep")  # Skip real sleeps
    @patch("app.camera.rtsp.cv2.VideoCapture")
    def test_reconnect_succeeds_first_try(self, mock_vc_cls, mock_sleep):
        """reconnect() succeeds on the first retry attempt."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value = 640
        # Return a new working capture on each call
        mock_vc_cls.return_value = mock_cap

        cam = RTSPCamera("rtsp://test")
        result = cam.reconnect(max_attempts=3, delay_seconds=0.01)

        self.assertTrue(result)

    @patch("app.camera.rtsp.time.sleep")
    @patch("app.camera.rtsp.cv2.VideoCapture")
    def test_reconnect_fails_all_attempts(self, mock_vc_cls, mock_sleep):
        """reconnect() returns False after exhausting all attempts."""
        # Initial open succeeds
        mock_cap_ok = MagicMock()
        mock_cap_ok.isOpened.return_value = True
        mock_cap_ok.get.return_value = 640

        # Subsequent opens fail
        mock_cap_bad = MagicMock()
        mock_cap_bad.isOpened.return_value = False

        mock_vc_cls.side_effect = [mock_cap_ok, mock_cap_bad, mock_cap_bad, mock_cap_bad]

        cam = RTSPCamera("rtsp://flaky")
        result = cam.reconnect(max_attempts=3, delay_seconds=0.01)

        self.assertFalse(result)
        # Should have slept between each failed attempt
        self.assertEqual(mock_sleep.call_count, 3)

    @patch("app.camera.rtsp.time.sleep")
    @patch("app.camera.rtsp.cv2.VideoCapture")
    def test_reconnect_succeeds_on_third_try(self, mock_vc_cls, mock_sleep):
        """reconnect() succeeds on attempt 3 of 5."""
        mock_cap_ok = MagicMock()
        mock_cap_ok.isOpened.return_value = True
        mock_cap_ok.get.return_value = 640

        mock_cap_bad = MagicMock()
        mock_cap_bad.isOpened.return_value = False

        # init=OK, attempt1=fail, attempt2=fail, attempt3=OK
        mock_vc_cls.side_effect = [
            mock_cap_ok,   # __init__
            mock_cap_bad,  # reconnect attempt 1
            mock_cap_bad,  # reconnect attempt 2
            mock_cap_ok,   # reconnect attempt 3
        ]

        cam = RTSPCamera("rtsp://flaky")
        result = cam.reconnect(max_attempts=5, delay_seconds=0.01)

        self.assertTrue(result)
        # Slept after attempt 1 and 2 (not after the successful attempt 3)
        self.assertEqual(mock_sleep.call_count, 2)


class TestRTSPCameraProperties(unittest.TestCase):
    """Verify frame dimension properties."""

    @patch("app.camera.rtsp.cv2.VideoCapture")
    def test_frame_dimensions(self, mock_vc_cls):
        """frame_width and frame_height delegate to VideoCapture.get()."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True

        # cv2.CAP_PROP_FRAME_WIDTH = 3, CAP_PROP_FRAME_HEIGHT = 4
        def side_effect(prop):
            if prop == 3:   # CAP_PROP_FRAME_WIDTH
                return 1280.0
            elif prop == 4:  # CAP_PROP_FRAME_HEIGHT
                return 720.0
            return 0.0

        mock_cap.get.side_effect = side_effect
        mock_vc_cls.return_value = mock_cap

        cam = RTSPCamera("rtsp://test")

        self.assertEqual(cam.frame_width, 1280)
        self.assertEqual(cam.frame_height, 720)

    @patch("app.camera.rtsp.cv2.VideoCapture")
    def test_frame_dimensions_when_released(self, mock_vc_cls):
        """Dimensions return 0 after release."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value = 640
        mock_vc_cls.return_value = mock_cap

        cam = RTSPCamera("rtsp://test")
        cam.release()

        self.assertEqual(cam.frame_width, 0)
        self.assertEqual(cam.frame_height, 0)


# =========================================================================
# Camera factory logic (config-based selection in main.py)
# =========================================================================


class TestCameraSelection(unittest.TestCase):
    """Verify that main.py's camera selection uses config correctly.

    These tests don't run the full main loop — they just verify the
    selection logic by checking the import paths and config values.
    """

    def test_config_defaults_to_webcam(self):
        """Default CAMERA_TYPE should be 'webcam'."""
        from app import config
        self.assertEqual(config.CAMERA_TYPE.strip().lower(), "webcam")

    def test_rtsp_url_default_is_empty(self):
        """Default RTSP_URL should be empty (no accidental connections)."""
        from app import config
        self.assertEqual(config.RTSP_URL, "")

    def test_rtsp_camera_implements_interface(self):
        """RTSPCamera should be a subclass of CameraSource."""
        from app.camera.base import CameraSource
        self.assertTrue(issubclass(RTSPCamera, CameraSource))

    def test_webcam_camera_implements_interface(self):
        """WebcamCamera should be a subclass of CameraSource."""
        from app.camera.base import CameraSource
        from app.camera.webcam import WebcamCamera
        self.assertTrue(issubclass(WebcamCamera, CameraSource))


# =========================================================================
# Buffer-setting acceptance test
# =========================================================================


class TestRTSPBufferSetting(unittest.TestCase):
    """Verify that buffer-reduction settings are applied conservatively."""

    @patch("app.camera.rtsp.cv2.VideoCapture")
    def test_buffer_size_set_attempted(self, mock_vc_cls):
        """RTSPCamera should attempt to set CAP_PROP_BUFFERSIZE=1."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value = 640
        mock_cap.set.return_value = True  # Backend accepts the hint
        mock_vc_cls.return_value = mock_cap

        cam = RTSPCamera("rtsp://test")

        # Verify .set() was called with CAP_PROP_BUFFERSIZE (=38) and value 1
        import cv2
        mock_cap.set.assert_any_call(cv2.CAP_PROP_BUFFERSIZE, 1)

    @patch("app.camera.rtsp.cv2.VideoCapture")
    def test_buffer_size_rejection_does_not_crash(self, mock_vc_cls):
        """If backend rejects CAP_PROP_BUFFERSIZE, camera still opens."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value = 640
        mock_cap.set.return_value = False  # Backend rejects the hint

        mock_vc_cls.return_value = mock_cap

        cam = RTSPCamera("rtsp://test")

        # Camera should still be open despite the rejected setting
        self.assertTrue(cam.is_opened())


if __name__ == "__main__":
    unittest.main()
