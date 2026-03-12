"""Recording abstractions used by evidence capture modules."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import numpy as np

from app.core.models import Event


class Recorder(ABC):
    """Abstract recorder interface for event-triggered media capture."""

    @abstractmethod
    def on_event(self, event: Event, frame: np.ndarray) -> Optional[Path]:
        """Capture evidence for an event and return the saved file path."""
        raise NotImplementedError
