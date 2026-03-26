"""
Clip recorder for ring-buffer video capture.
Iteration 10: Event Clip Recording.
"""

import collections
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from app import config
from app.core.models import Event
from app.recording.base import Recorder
from app.services.logging_service import get_logger

@dataclass
class ClipJob:
    """Internal state for an active recording job."""
    event_id: str
    writer: cv2.VideoWriter
    frames_remaining: int
    path: Path

class ClipRecorder(Recorder):
    """Records video clips with pre/post event buffering using a ring buffer."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._log = get_logger()

        self.target_fps = config.CLIP_TARGET_FPS
        self.pre_sec = config.CLIP_PRE_EVENT_SECONDS
        self.post_sec = config.CLIP_POST_EVENT_SECONDS
        
        self.frame_interval = 1.0 / self.target_fps if self.target_fps > 0 else 0.0
        self.last_frame_time = 0.0
        
        # Max frames to keep for the pre-event buffer
        self.max_buffer_len = int(self.target_fps * self.pre_sec)
        self.buffer: collections.deque = collections.deque(maxlen=self.max_buffer_len)
        
        self.active_jobs: dict[str, ClipJob] = {}

    def _build_output_path(self, event: Event) -> Path:
        """Create date-based subdirectory structure for clips."""
        day = datetime.now().strftime("%Y-%m-%d")
        base = self.output_dir / day
        base.mkdir(parents=True, exist_ok=True)
        return base / f"{event.event_id}{config.CLIP_FILE_EXTENSION}"

    def feed_frame(self, frame: np.ndarray) -> list[tuple[str, Path]]:
        """
        Feed a frame to the ring buffer and active recording jobs.
        Returns a list of completed (event_id, clip_path) recording jobs.
        """
        now = time.monotonic()
        
        # Enforce target FPS for the recording
        if now - self.last_frame_time < self.frame_interval:
            return []
            
        self.last_frame_time = now
        saved_frame = frame.copy()
        
        self.buffer.append(saved_frame)
        
        completed = []
        # Update jobs
        for job_id, job in list(self.active_jobs.items()):
            job.writer.write(saved_frame)
            job.frames_remaining -= 1
            
            if job.frames_remaining <= 0:
                job.writer.release()
                completed.append((job.event_id, job.path))
                del self.active_jobs[job_id]
                self._log.debug("Completed clip job for event %s", job_id[:8])
                
        return completed

    def on_event(self, event: Event, frame: np.ndarray) -> Optional[Path]:
        """
        Start an active recording job for the emitted event.
        Always returns None immediately, as clip finishes synchronously in chunks
        during subsequent main loop iterations over time.
        """
        out_path = self._build_output_path(event)
        h, w = frame.shape[:2]
        
        # Codec requires a sequence of 4 characters
        fourcc = cv2.VideoWriter_fourcc(*config.CLIP_CODEC)
        writer = cv2.VideoWriter(str(out_path), fourcc, self.target_fps, (w, h))
        
        if not writer.isOpened():
            self._log.error("VideoWriter failed to open for event %s path %s", event.event_id, out_path)
            # Cancel job safely without returning a corrupted path later
            return None
        
        # 1. Flush the current ring buffer into the writer
        for b_frame in list(self.buffer):
            writer.write(b_frame)
            
        # 2. Setup the job to gather post-event frames
        post_frames = int(self.target_fps * self.post_sec)
        
        job = ClipJob(
            event_id=event.event_id,
            writer=writer,
            frames_remaining=post_frames,
            path=out_path
        )
        self.active_jobs[event.event_id] = job
        
        self._log.debug("Started clip job for event %s (pre=%d frames, post=%d frames)", 
                        event.event_id[:8], len(self.buffer), post_frames)
        
        # We don't return the path here because the clip is not finished yet
        return None
