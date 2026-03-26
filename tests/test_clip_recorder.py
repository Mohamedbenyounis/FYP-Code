import traceback
from pathlib import Path
from unittest import mock

import cv2
import numpy as np
import pytest

from app import config
from app.core.models import Event
from app.recording.clip_recorder import ClipRecorder


def test_clip_recorder_ring_buffer_and_job(tmp_path: Path):
    """
    Test the ClipRecorder's ring buffer subsampling, 
    pre-event flushing, and post-event job completion.
    """
    # Force test configuration
    config.CLIP_TARGET_FPS = 10
    config.CLIP_PRE_EVENT_SECONDS = 1.0
    config.CLIP_POST_EVENT_SECONDS = 1.0
    config.CLIP_FILE_EXTENSION = ".mp4"
    config.CLIP_CODEC = "mp4v"
    
    recorder = ClipRecorder(tmp_path)
    
    # Mock frame (100x100 BGR)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    
    # Mock time.monotonic to precisely control the FPS logic
    # We patch it directly at its usage point in the clip_recorder module
    with mock.patch("app.recording.clip_recorder.time.monotonic") as mock_time:
        current_time = [0.0]
        mock_time.side_effect = lambda: current_time[0]
        
        # Step 1: Pre-buffer fill
        # Interval is 1.0 / 10 = 0.1sec. 
        # We simulate 20 frames spaced exactly by 0.1s
        for _ in range(20):
            current_time[0] += 0.11 # Slightly more than 0.1 to avoid float issues
            recorder.feed_frame(frame)
            
        # Target max frames is 1.0 sec * 10 FPS = 10 frames
        # The collections.deque should gracefully truncate older frames.
        assert len(recorder.buffer) == 10
        
        # Step 2: Trigger Event
        event = Event(
            event_id="test-event-123",
            created_at="2026-03-31T20:00:00Z",
            status="unauthorised"
        )
        
        # event hook returns None immediately
        assert recorder.on_event(event, frame) is None
        
        assert "test-event-123" in recorder.active_jobs
        job = recorder.active_jobs["test-event-123"]
        
        # Post duration is 1.0 sec * 10 FPS = 10 frames
        assert job.frames_remaining == 10
        
        # Step 3: Fast-forward post-event processing (9 frames)
        for _ in range(9):
            current_time[0] += 0.11
            completed = recorder.feed_frame(frame)
            assert len(completed) == 0 # Still not finished
            
        # Step 4: Final frame finishes the clip
        current_time[0] += 0.11
        completed = recorder.feed_frame(frame)
        assert len(completed) == 1
        
        ev_id, path = completed[0]
        assert ev_id == "test-event-123"
        assert path.exists()


def test_clip_recorder_writer_failure_and_path(tmp_path: Path):
    """
    Test that the path is formatted as YYYY-MM-DD
    and that a broken cv2.VideoWriter doesn't register an active job.
    """
    config.CLIP_TARGET_FPS = 10
    config.CLIP_FILE_EXTENSION = ".mp4"
    config.CLIP_CODEC = "mp4v"
    
    recorder = ClipRecorder(tmp_path)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    event = Event(
        event_id="bad-writer-uuid",
        created_at="2026-03-31T20:00:00Z",
        status="unauthorised"
    )
    
    # Mock cv2.VideoWriter.isOpened to return False
    with mock.patch("app.recording.clip_recorder.cv2.VideoWriter.isOpened", return_value=False):
        recorder.on_event(event, frame)
        
    # Job should not have been stored because OpenCV rejected the Writer
    assert "bad-writer-uuid" not in recorder.active_jobs
    
    # Check that YYYY-MM-DD was generated securely
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    date_dir = tmp_path / today
    assert date_dir.exists()
