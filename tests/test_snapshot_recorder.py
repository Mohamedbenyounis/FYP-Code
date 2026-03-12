"""Tests for Iteration 4 snapshot recorder."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.models import Event
from app.recording.snapshot_recorder import SnapshotRecorder


def _make_event(event_id: str = "event-123", bbox_json: str | None = None) -> Event:
    return Event(
        event_id=event_id,
        created_at="2026-03-17T10:00:00+00:00",
        status="authorised",
        person_name="Alice",
        person_id=1,
        score=0.8,
        bbox_json=bbox_json,
        snapshot_path=None,
        clip_path=None,
    )


def _frame() -> np.ndarray:
    return np.full((120, 160, 3), 120, dtype=np.uint8)


class TestSnapshotRecorder:
    def test_creates_directory_and_saves_file(self, tmp_path: Path) -> None:
        recorder = SnapshotRecorder(tmp_path / "snaps")
        event = _make_event("ev-save")

        path = recorder.on_event(event, _frame())

        assert path is not None
        assert path.exists()
        assert path.suffix.lower() == ".jpg"

    def test_bbox_overlay_path_does_not_crash(self, tmp_path: Path) -> None:
        recorder = SnapshotRecorder(tmp_path / "snaps")
        event = _make_event(
            "ev-bbox",
            bbox_json='{"x1":20,"y1":25,"x2":90,"y2":95}',
        )

        path = recorder.on_event(event, _frame())

        assert path is not None
        assert path.exists()
        image = cv2.imread(str(path))
        assert image is not None

    def test_invalid_bbox_json_is_tolerated(self, tmp_path: Path) -> None:
        recorder = SnapshotRecorder(tmp_path / "snaps")
        event = _make_event("ev-bad-bbox", bbox_json="not-json")

        path = recorder.on_event(event, _frame())

        assert path is not None
        assert path.exists()

    def test_empty_frame_returns_none(self, tmp_path: Path) -> None:
        recorder = SnapshotRecorder(tmp_path / "snaps")
        event = _make_event("ev-empty")
        empty = np.empty((0, 0, 3), dtype=np.uint8)

        path = recorder.on_event(event, empty)

        assert path is None
