"""
Webcam camera source using OpenCV VideoCapture.
"""

from __future__ import annotations

import time
from typing import Optional

import cv2
import numpy as np

from app.camera.base import CameraSource
from app.services.logging_service import get_logger


class WebcamCamera(CameraSource):
    """USB / built-in webcam via ``cv2.VideoCapture``."""

    def __init__(self, device_index: int = 0) -> None:
        self._device_index = device_index
        self._cap: Optional[cv2.VideoCapture] = None
        self._log = get_logger()
        self._open()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _open(self) -> bool:
        """Open (or reopen) the capture device."""
        self._cap = cv2.VideoCapture(self._device_index)
        if self._cap.isOpened():
            self._log.info(
                "Webcam opened: device=%s  resolution=%dx%d",
                self._device_index,
                self.frame_width,
                self.frame_height,
            )
            return True
        self._log.error("Failed to open webcam device %s", self._device_index)
        return False

    # ------------------------------------------------------------------
    # CameraSource interface
    # ------------------------------------------------------------------

    def read(self) -> tuple[bool, Optional[np.ndarray]]:
        if self._cap is None or not self._cap.isOpened():
            return False, None
        ret, frame = self._cap.read()
        if not ret:
            return False, None
        return True, frame

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            self._log.info("Webcam released")

    def is_opened(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    @property
    def frame_width(self) -> int:
        if self._cap is None:
            return 0
        return int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))

    @property
    def frame_height(self) -> int:
        if self._cap is None:
            return 0
        return int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # ------------------------------------------------------------------
    # Reconnect helper
    # ------------------------------------------------------------------

    def reconnect(
        self, max_attempts: int = 3, delay_seconds: float = 1.0
    ) -> bool:
        """Try to reopen the camera after a failure."""
        self._log.warning("Attempting webcam reconnect …")
        self.release()
        for attempt in range(1, max_attempts + 1):
            self._log.info("Reconnect attempt %d/%d", attempt, max_attempts)
            if self._open():
                return True
            time.sleep(delay_seconds)
        self._log.error("Webcam reconnect failed after %d attempts", max_attempts)
        return False
