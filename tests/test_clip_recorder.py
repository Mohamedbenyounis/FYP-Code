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


# ===================================================================
# EVALUATION TESTS — Pre-buffer validation
# ===================================================================

def test_clip_pre_buffer_correct_frame_count(tmp_path: Path):
    """
    Pre-buffer must contain frames from BEFORE the event trigger.
    With pre_sec=1.0 and target_fps=10, the ring buffer should hold
    exactly 10 frames at its maximum.
    """
    config.CLIP_TARGET_FPS = 10
    config.CLIP_PRE_EVENT_SECONDS = 1.0
    config.CLIP_POST_EVENT_SECONDS = 1.0
    config.CLIP_FILE_EXTENSION = ".mp4"
    config.CLIP_CODEC = "mp4v"

    recorder = ClipRecorder(tmp_path)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    with mock.patch("app.recording.clip_recorder.time.monotonic") as mock_time:
        current_time = [0.0]
        mock_time.side_effect = lambda: current_time[0]

        # Fill more than buffer capacity (feed 15 frames at correct interval)
        for i in range(15):
            current_time[0] += 0.11
            recorder.feed_frame(frame)

        # Buffer should be capped at max_buffer_len = 10
        assert len(recorder.buffer) == 10, (
            f"Pre-buffer should hold exactly 10 frames, got {len(recorder.buffer)}"
        )
        assert recorder.max_buffer_len == 10


# ===================================================================
# EVALUATION TESTS — Post-buffer validation
# ===================================================================

def test_clip_post_buffer_continues_after_event(tmp_path: Path):
    """
    After on_event() is called, subsequent feed_frame() calls must
    write frames to the active job until post-event frames are exhausted.
    """
    config.CLIP_TARGET_FPS = 10
    config.CLIP_PRE_EVENT_SECONDS = 0.5  # 5 pre-frames
    config.CLIP_POST_EVENT_SECONDS = 0.5  # 5 post-frames
    config.CLIP_FILE_EXTENSION = ".mp4"
    config.CLIP_CODEC = "mp4v"

    recorder = ClipRecorder(tmp_path)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    with mock.patch("app.recording.clip_recorder.time.monotonic") as mock_time:
        current_time = [0.0]
        mock_time.side_effect = lambda: current_time[0]

        # Fill pre-buffer
        for _ in range(10):
            current_time[0] += 0.11
            recorder.feed_frame(frame)

        # Trigger event
        event = Event(
            event_id="post-buf-test",
            created_at="2026-04-05T00:00:00Z",
            status="unauthorised"
        )
        recorder.on_event(event, frame)
        assert "post-buf-test" in recorder.active_jobs

        job = recorder.active_jobs["post-buf-test"]
        initial_remaining = job.frames_remaining
        assert initial_remaining == 5, f"Post-frames should be 5, got {initial_remaining}"

        # Feed 3 frames — job should still be active
        for _ in range(3):
            current_time[0] += 0.11
            completed = recorder.feed_frame(frame)
            assert len(completed) == 0

        assert recorder.active_jobs["post-buf-test"].frames_remaining == 2

        # Feed 2 more — job should complete
        for _ in range(2):
            current_time[0] += 0.11
            completed = recorder.feed_frame(frame)

        assert len(completed) == 1
        assert completed[0][0] == "post-buf-test"
        assert "post-buf-test" not in recorder.active_jobs


# ===================================================================
# EVALUATION TESTS — Clip file non-zero size
# ===================================================================

def test_clip_file_nonzero_size(tmp_path: Path):
    """Completed clip file must exist and have non-zero size."""
    config.CLIP_TARGET_FPS = 10
    config.CLIP_PRE_EVENT_SECONDS = 0.5
    config.CLIP_POST_EVENT_SECONDS = 0.5
    config.CLIP_FILE_EXTENSION = ".mp4"
    config.CLIP_CODEC = "mp4v"

    recorder = ClipRecorder(tmp_path)
    # Use a real-ish frame with actual pixel data
    frame = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)

    with mock.patch("app.recording.clip_recorder.time.monotonic") as mock_time:
        current_time = [0.0]
        mock_time.side_effect = lambda: current_time[0]

        # Fill pre-buffer
        for _ in range(10):
            current_time[0] += 0.11
            recorder.feed_frame(frame)

        # Trigger event
        event = Event(
            event_id="size-check-test",
            created_at="2026-04-05T00:00:00Z",
            status="unauthorised"
        )
        recorder.on_event(event, frame)

        # Complete post-buffer — accumulate results across iterations
        all_completed = []
        for _ in range(6):
            current_time[0] += 0.11
            completed = recorder.feed_frame(frame)
            all_completed.extend(completed)

        assert len(all_completed) == 1, f"Expected 1 completed clip, got {len(all_completed)}"
        _, clip_path = all_completed[0]
        assert clip_path.exists(), f"Clip file should exist at {clip_path}"
        assert clip_path.stat().st_size > 0, "Clip file must be non-zero bytes"


# ===================================================================
# EVALUATION TESTS — Lifecycle-Aware and Max Duration (Iteration 12c)
# ===================================================================

def test_clip_dynamic_lifecycle_recording(tmp_path: Path):
    """
    Test that an active track_key keeps a job open indefinitely,
    until update_track_states signals its end, triggering the tail.
    """
    config.CLIP_TARGET_FPS = 10
    config.CLIP_PRE_EVENT_SECONDS = 0.5
    config.CLIP_POST_EVENT_SECONDS = 0.5 # 5 tail frames
    config.CLIP_MAX_DURATION_SECONDS = 10.0 # High max duration

    recorder = ClipRecorder(tmp_path)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    with mock.patch("app.recording.clip_recorder.time.monotonic") as mock_time:
        current_time = [0.0]
        mock_time.side_effect = lambda: current_time[0]

        event = Event(
            event_id="dynamic-test",
            created_at="2026-04-05T00:00:00Z",
            status="unauthorised",
            track_key="face_1"
        )
        recorder.on_event(event, frame)
        assert "dynamic-test" in recorder.active_jobs
        
        # Test that while the track is active, feeding frames doesn't decrement the post-buffer
        recorder.update_track_states({"face_1": "ACTIVE"})
        for _ in range(15): # 1.5 seconds passes (3x normal post-sec limitation!)
            current_time[0] += 0.11
            completed = recorder.feed_frame(frame)
            assert len(completed) == 0  # Should still be recording

        assert recorder.active_jobs["dynamic-test"].mode == "active"
        assert recorder.active_jobs["dynamic-test"].frames_written >= 15

        # Face is lost / event ends.
        recorder.update_track_states({"face_2": "ACTIVE"}) # face_1 missing
        
        assert recorder.active_jobs["dynamic-test"].mode == "tail"
        
        # Tail phase starts, expecting 5 frames
        for _ in range(4):
            current_time[0] += 0.11
            assert len(recorder.feed_frame(frame)) == 0

        current_time[0] += 0.11
        completed = recorder.feed_frame(frame)
        assert len(completed) == 1 # Finishes on exactly the 5th frame


def test_clip_max_duration_safety_cutoff(tmp_path: Path):
    """
    Ensure extremely long presences don't violate the MAXIMUM_DURATION safety.
    """
    config.CLIP_TARGET_FPS = 10
    config.CLIP_PRE_EVENT_SECONDS = 0.0
    config.CLIP_POST_EVENT_SECONDS = 5.0
    config.CLIP_MAX_DURATION_SECONDS = 3.0  # 30 frames MAX

    recorder = ClipRecorder(tmp_path)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    with mock.patch("app.recording.clip_recorder.time.monotonic") as mock_time:
        current_time = [0.0]
        mock_time.side_effect = lambda: current_time[0]

        event = Event(
            event_id="max-cap-test",
            created_at="2026-04-05T00:00:00Z",
            status="unauthorised",
            track_key="cap_face"
        )
        recorder.on_event(event, frame)
        
        # Keep track active infinitely
        recorder.update_track_states({"cap_face": "ACTIVE"})
        
        # Try to feed 35 frames. It should hard-cut at 30 frames.
        for i in range(1, 35):
            current_time[0] += 0.11
            completed = recorder.feed_frame(frame)
            if i < 30:
                assert len(completed) == 0
            elif i == 30:
                assert len(completed) == 1
                assert completed[0][0] == "max-cap-test"
            else:
                assert len(completed) == 0 # already done
                
        assert "max-cap-test" not in recorder.active_jobs

