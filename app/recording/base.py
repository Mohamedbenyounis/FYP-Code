"""
Abstract base class for recorders.
Stub for Iteration 4.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
import numpy as np


class Recorder(ABC):
    """Abstract base class for media recorders."""

    @abstractmethod
    def save(self, frame: np.ndarray, event_id: Optional[int] = None) -> Optional[Path]:
        """Save media and return path."""
        pass
