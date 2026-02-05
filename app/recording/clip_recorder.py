"""
Clip recorder for ring-buffer video capture.
Stub for Iteration 7.
"""

from pathlib import Path
from typing import Optional
import numpy as np

from app.recording.base import Recorder


class ClipRecorder(Recorder):
    """Records video clips with pre/post event buffering."""

    def __init__(self, output_dir: Path, pre_seconds: float = 5.0, post_seconds: float = 5.0) -> None:
        self.output_dir = output_dir
        self.pre_seconds = pre_seconds
        self.post_seconds = post_seconds
        # TODO: Implement in Iteration 7

    def save(self, frame: np.ndarray, event_id: Optional[int] = None) -> Optional[Path]:
        """Save a video clip."""
        # TODO: Implement in Iteration 7
        return None

    def feed_frame(self, frame: np.ndarray) -> None:
        """Feed a frame to the ring buffer."""
        # TODO: Implement in Iteration 7
        pass
