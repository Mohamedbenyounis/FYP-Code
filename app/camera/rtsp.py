"""
RTSP camera source stub for Iteration 7.
"""

from typing import Optional
import numpy as np

from app.camera.base import CameraSource


class RTSPCamera(CameraSource):
    """RTSP stream input source. Stub for future implementation."""

    def __init__(self, url: str):
        """Initialize RTSP stream."""
        self.url = url
        # TODO: Implement in Iteration 7

    def read(self) -> tuple[bool, Optional[np.ndarray]]:
        """Read frame from RTSP stream."""
        return False, None

    def release(self) -> None:
        """Release RTSP resources."""
        pass

    def is_opened(self) -> bool:
        """Check if RTSP stream is opened."""
        return False

    @property
    def frame_width(self) -> int:
        """Get frame width."""
        return 0

    @property
    def frame_height(self) -> int:
        """Get frame height."""
        return 0
