"""Snapshot recorder for Iteration 4 event evidence capture."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from app import config
from app.core.models import Event
from app.recording.base import Recorder
from app.services.logging_service import get_logger


class SnapshotRecorder(Recorder):
    """Saves one JPEG snapshot when an event is emitted."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self._log = get_logger()

    def _build_output_path(self, event: Event) -> Path:
        base = self.output_dir
        if config.SNAPSHOT_SUBDIR_BY_DATE:
            day = datetime.now().strftime("%Y-%m-%d")
            base = base / day
        base.mkdir(parents=True, exist_ok=True)
        return base / f"{event.event_id}.jpg"

    @staticmethod
    def _draw_bbox_overlay(image: np.ndarray, event: Event) -> np.ndarray:
        if not event.bbox_json:
            return image

        try:
            bbox = json.loads(event.bbox_json)
            x1 = int(bbox.get("x1", 0))
            y1 = int(bbox.get("y1", 0))
            x2 = int(bbox.get("x2", 0))
            y2 = int(bbox.get("y2", 0))
        except (ValueError, TypeError):
            return image

        if x2 <= x1 or y2 <= y1:
            return image

        cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)
        label = event.person_name if event.person_name else "unknown"
        cv2.putText(
            image,
            label,
            (x1, max(20, y1 - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2,
        )
        return image

    def on_event(self, event: Event, frame: np.ndarray) -> Optional[Path]:
        """Save a snapshot for the given event and return saved path."""
        if frame is None or frame.size == 0:
            self._log.warning("Snapshot skipped for event %s: empty frame", event.event_id)
            return None

        output_path = self._build_output_path(event)
        image = frame.copy()

        if config.DRAW_BBOX_ON_SNAPSHOT and not config.SAVE_RAW_SNAPSHOT:
            image = self._draw_bbox_overlay(image, event)

        quality = max(1, min(100, int(config.SNAPSHOT_JPEG_QUALITY)))
        ok = cv2.imwrite(str(output_path), image, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            self._log.error("Failed to write snapshot for event %s", event.event_id)
            return None

        self._log.info("Snapshot saved for event %s: %s", event.event_id, output_path)
        return output_path
