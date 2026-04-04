"""
Abstract base class for camera sources.

Every concrete camera class must implement all five methods defined here.
``main.py`` relies on ``reconnect()`` for automatic recovery when frame
reads fail, so it is part of the mandatory interface — not optional.
"""

from abc import ABC, abstractmethod
from typing import Optional
import numpy as np


class CameraSource(ABC):
    """Abstract base class for camera input sources.

    Concrete subclasses must implement:
    - ``read()``       — return the next frame
    - ``release()``    — free hardware / network resources
    - ``is_opened()``  — readiness check
    - ``reconnect()``  — recover from failures (called by main loop)
    - ``frame_width``  — current capture width  (property)
    - ``frame_height`` — current capture height  (property)
    """

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

    @abstractmethod
    def reconnect(
        self, max_attempts: int = 3, delay_seconds: float = 1.0
    ) -> bool:
        """Attempt to recover the camera connection after a failure.

        Args:
            max_attempts: Maximum number of retry cycles before giving up.
            delay_seconds: Pause between each retry attempt.

        Returns:
            True if the camera is successfully reopened, False otherwise.
        """
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
