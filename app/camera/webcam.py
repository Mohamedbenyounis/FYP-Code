"""
Webcam camera source using OpenCV.
"""

from typing import Optional
import numpy as np

from app.camera.base import CameraSource


class WebcamCamera(CameraSource):
    """Webcam input source using cv2.VideoCapture."""

    def __init__(self, device_index: int = 0):
        """Initialize webcam capture."""
        self.device_index = device_index
        # TODO: Implement

    def read(self) -> tuple[bool, Optional[np.ndarray]]:
        """Read the next frame from webcam."""
        # TODO: Implement
        return False, None

    def release(self) -> None:
        """Release webcam resources."""
        # TODO: Implement
        pass

    def is_opened(self) -> bool:
        """Check if webcam is opened."""
        # TODO: Implement
        return False

    @property
    def frame_width(self) -> int:
        """Get frame width."""
        return 0

    @property
    def frame_height(self) -> int:
        """Get frame height."""
        return 0
