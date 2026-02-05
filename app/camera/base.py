"""
Abstract base class for camera sources.
"""

from abc import ABC, abstractmethod
from typing import Optional
import numpy as np


class CameraSource(ABC):
    """Abstract base class for camera input sources."""

    @abstractmethod
    def read(self) -> tuple[bool, Optional[np.ndarray]]:
        """Read the next frame from the camera."""
        pass

    @abstractmethod
    def release(self) -> None:
        """Release camera resources."""
        pass

    @abstractmethod
    def is_opened(self) -> bool:
        """Check if camera is currently opened and ready."""
        pass

    @property
    @abstractmethod
    def frame_width(self) -> int:
        """Get frame width in pixels."""
        pass

    @property
    @abstractmethod
    def frame_height(self) -> int:
        """Get frame height in pixels."""
        pass
