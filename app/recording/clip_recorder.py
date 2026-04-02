"""
Clip recorder for ring-buffer video capture.
Iteration 12c: Lifecycle-Aware Clip Recording.
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
    track_key: Optional[str]
    writer: cv2.VideoWriter
    frames_remaining: int
    path: Path
    mode: str = "active"  # "active" (recording presence) or "tail" (post-event finish)
    frames_written: int = 0

class ClipRecorder(Recorder):
    """Records video clips dynamically capturing the true duration of an event."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._log = get_logger()

        self.target_fps = config.CLIP_TARGET_FPS
        self.pre_sec = config.CLIP_PRE_EVENT_SECONDS
        self.post_sec = config.CLIP_POST_EVENT_SECONDS
        self.max_duration = config.CLIP_MAX_DURATION_SECONDS
        
        self.frame_interval = 1.0 / self.target_fps if self.target_fps > 0 else 0.0
        self.last_frame_time = 0.0
        
        # Calculate maximum limits
        self.max_buffer_len = int(self.target_fps * self.pre_sec)
        self.post_frames = int(self.target_fps * self.post_sec)
        self.max_total_frames = int(self.target_fps * self.max_duration)
        
        self.buffer: collections.deque = collections.deque(maxlen=self.max_buffer_len)
        self.active_jobs: dict[str, ClipJob] = {}

    def _build_output_path(self, event: Event) -> Path:
        """Create date-based subdirectory structure for clips."""
        day = datetime.now().strftime("%Y-%m-%d")
        base = self.output_dir / day
        base.mkdir(parents=True, exist_ok=True)
        return base / f"{event.event_id}{config.CLIP_FILE_EXTENSION}"

    def update_track_states(self, states: dict[str, str]) -> None:
        """
        Signals the recorder with the current state of tracked faces.
        If a face transitions out of 'ACTIVE', its clip job moves into 'tail' mode.
        """
        for job in list(self.active_jobs.values()):
            if job.mode == "active" and job.track_key is not None:
                current_state = states.get(job.track_key)
                if current_state != "ACTIVE":
                    job.mode = "tail"
                    job.frames_remaining = self.post_frames
                    self._log.debug("Event %s (track %s) ended, starting %d frame tail", 
                                    job.event_id[:8], job.track_key, job.frames_remaining)

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
        for job_id, job in list(self.active_jobs.items()):
            job.writer.write(saved_frame)
            job.frames_written += 1
            
            # Check if we hit the hard ceiling for duration (protect disk)
            time_to_close = False
            if job.frames_written >= self.max_total_frames:
                self._log.warning("Event %s reached max duration limit (%.1fs). Forcing closure.", 
                                  job_id[:8], self.max_duration)
                time_to_close = True
            elif job.mode == "tail":
                job.frames_remaining -= 1
                if job.frames_remaining <= 0:
                    time_to_close = True
                    self._log.debug("Completed clip job for event %s", job_id[:8])
            
            if time_to_close:
                job.writer.release()
                completed.append((job.event_id, job.path))
                del self.active_jobs[job_id]
                
        return completed

    def on_event(self, event: Event, frame: np.ndarray) -> Optional[Path]:
        """
        Start an active recording job for the emitted event.
        """
        out_path = self._build_output_path(event)
        h, w = frame.shape[:2]
        
        # Codec requires a sequence of 4 characters
        fourcc = cv2.VideoWriter_fourcc(*config.CLIP_CODEC)
        writer = cv2.VideoWriter(str(out_path), fourcc, self.target_fps, (w, h))
        
        if not writer.isOpened():
            self._log.error("VideoWriter failed to open for event %s path %s", event.event_id, out_path)
            return None
        
        # 1. Flush the current ring buffer into the writer
        frames_flushed = 0
        for b_frame in list(self.buffer):
            writer.write(b_frame)
            frames_flushed += 1
            
        # 2. Setup the job. If no track_key exists in the event, fallback to legacy trailing immediately.
        mode = "active" if event.track_key else "tail"
        
        job = ClipJob(
            event_id=event.event_id,
            track_key=event.track_key,
            writer=writer,
            frames_remaining=self.post_frames if mode == "tail" else 0,
            path=out_path,
            mode=mode,
            frames_written=frames_flushed
        )
        self.active_jobs[event.event_id] = job
        
        self._log.debug("Started clip job for event %s, track_key=%s, mode=%s", 
                        event.event_id[:8], event.track_key, mode)
        
        return None
