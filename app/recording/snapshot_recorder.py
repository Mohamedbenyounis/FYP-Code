"""
Snapshot recorder for capturing evidence images.
Stub for Iteration 4.
"""

from pathlib import Path
from typing import Optional
import numpy as np

from app.recording.base import Recorder


class SnapshotRecorder(Recorder):
    """Records snapshot images of detection/recognition events."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        # TODO: Implement in Iteration 4

    def save(self, frame: np.ndarray, event_id: Optional[int] = None) -> Optional[Path]:
        """Save a snapshot image."""
        # TODO: Implement in Iteration 4
        return None
