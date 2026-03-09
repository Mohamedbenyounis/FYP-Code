"""
SecureVision — main entry point (Iteration 3).

Captures webcam frames, runs the ML pipeline every N-th frame, feeds
observations into the EventManager, and persists confirmed events to
the SQLite database.
"""

from __future__ import annotations

import sys
import time

import cv2

from app import config
from app.camera.webcam import WebcamCamera
from app.core.event_manager import EventManager
from app.core.models import Observation
from app.db.migrations import init_db
from app.db.repo import (
    SQLiteEventRepository,
    SQLitePersonRepository,
    make_enrolled_provider,
)
from app.ml.pipeline import FacePipeline
from app.services.logging_service import FrameRateLogger, get_logger


def _ensure_directories() -> None:
    """Create required data directories if they don't exist."""
    for d in (
        config.DATA_DIR,
        config.DB_DIR,
        config.SNAPSHOTS_DIR,
        config.CLIPS_DIR,
        config.MODELS_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)


def main() -> int:
    """Application entry point.  Returns 0 on success, 1 on error."""
    log = get_logger()
    log.info("=" * 60)
    log.info("SecureVision starting — Iteration 3")
    log.info("=" * 60)

    # Ensure folders ---------------------------------------------------
    _ensure_directories()
    log.info("Data dir : %s", config.DATA_DIR)
    log.info("Models dir: %s", config.MODELS_DIR)

    # Database ---------------------------------------------------------
    conn = init_db(config.DB_PATH)
    repo = SQLitePersonRepository(conn)
    enrolled_provider = make_enrolled_provider(repo)
    event_repo = SQLiteEventRepository(conn)
    log.info("DB path  : %s", config.DB_PATH)

    # Event Manager (Level 2 state machine) ----------------------------
    event_manager = EventManager(
        window_n=config.EVENT_CONFIRM_WINDOW_N,
        confirm_k=config.EVENT_CONFIRM_MIN_K,
        lost_frames=config.EVENT_LOST_FRAMES,
        cooldown_seconds=config.EVENT_COOLDOWN_SECONDS,
        score_threshold=config.EVENT_SCORE_THRESHOLD,
    )
    log.info(
        "EventManager: window=%d  confirm=%d  lost=%d  cooldown=%.1fs",
        config.EVENT_CONFIRM_WINDOW_N,
        config.EVENT_CONFIRM_MIN_K,
        config.EVENT_LOST_FRAMES,
        config.EVENT_COOLDOWN_SECONDS,
    )

    # Camera -----------------------------------------------------------
    camera = WebcamCamera(device_index=config.CAMERA_INDEX)
    if not camera.is_opened():
        log.error("Camera failed to open — exiting")
        conn.close()
        return 1

    # ML pipeline (pluggable adapter) ----------------------------------
    pipeline = FacePipeline(enrolled_provider=enrolled_provider)

    if not pipeline.ml_enabled:
        log.warning("=" * 60)
        log.warning("ML DISABLED — running in passthrough mode")
        log.warning("Place ONNX models in %s to enable ML", config.MODELS_DIR)
        log.warning("=" * 60)

    # Main loop --------------------------------------------------------
    frame_counter = 0
    stats = FrameRateLogger(log_every_n=100)
    log.info("Entering main loop (Ctrl+C to stop)")
    last_result = None  # persist detection across frames for smooth drawing

    try:
        while True:
            ok, frame = camera.read()

            if not ok or frame is None:
                log.warning("Frame read failed — attempting reconnect")
                if not camera.reconnect():
                    log.error("Reconnect failed — exiting")
                    break
                continue

            frame_counter += 1

            # --- ML processing (every N-th frame) -------------------------
            if frame_counter % config.PROCESS_EVERY_N_FRAMES == 0:
                result = pipeline.process_frame(frame)
                last_result = result  # persist for drawing on all frames

                # Structured console output (always active)
                if result.primary_detection is not None:
                    det = result.primary_detection
                    log.info(
                        "Detected face | conf=%.2f | bbox=%s | size=%dx%d",
                        det.confidence,
                        det.bbox.as_tuple(),
                        det.bbox.width,
                        det.bbox.height,
                    )

                if result.recognition is not None:
                    rec = result.recognition
                    if rec.is_match:
                        log.info(
                            "Recognised: %s  score=%.3f",
                            rec.name,
                            rec.score,
                        )
                    else:
                        log.info("Unknown face  score=%.3f", rec.score)

                if result.message and result.primary_detection is None:
                    log.debug("%s", result.message)

                stats.log_frame(
                    detected=result.primary_detection is not None,
                    recognised=(
                        result.recognition is not None
                        and result.recognition.is_match
                    ),
                )

                # --- Event Manager (Iteration 3) -------------------------
                obs = Observation(
                    timestamp=time.monotonic(),
                    face_present=result.primary_detection is not None,
                    person_name=(
                        result.recognition.name
                        if result.recognition is not None
                        and result.recognition.is_match
                        else None
                    ),
                    person_id=None,  # resolved in future iteration
                    score=(
                        result.recognition.score
                        if result.recognition is not None
                        else 0.0
                    ),
                    bbox=(
                        result.primary_detection.bbox
                        if result.primary_detection is not None
                        else None
                    ),
                )

                event = event_manager.update(obs)
                if event is not None:
                    event_repo.add_event(event)
                    log.info(
                        "EVENT  id=%s  status=%s  person=%s  score=%.3f",
                        event.event_id[:8],
                        event.status,
                        event.person_name or "unknown",
                        event.score or 0.0,
                    )

            # --- Preview window (guarded by SHOW_PREVIEW) -----------------
            if config.SHOW_PREVIEW:
                display_frame = frame.copy()

                # Overlay detection bbox using latest ML result
                if (
                    last_result is not None
                    and last_result.primary_detection is not None
                ):
                    b = last_result.primary_detection.bbox
                    cv2.rectangle(
                        display_frame,
                        (b.x1, b.y1),
                        (b.x2, b.y2),
                        (0, 255, 0),
                        2,
                    )

                    label = f"conf={last_result.primary_detection.confidence:.2f}"
                    if last_result.recognition is not None:
                        rec = last_result.recognition
                        if rec.is_match:
                            label = f"{rec.name} ({rec.score:.2f})"
                        else:
                            label = f"Unknown ({rec.score:.2f})"

                    cv2.putText(
                        display_frame,
                        label,
                        (b.x1, b.y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (0, 255, 0),
                        2,
                    )

                # Status bar
                status_text = (
                    "ML: ON" if pipeline.ml_enabled else "ML: DISABLED"
                )
                status_colour = (
                    (0, 255, 0) if pipeline.ml_enabled else (0, 0, 255)
                )
                cv2.putText(
                    display_frame,
                    status_text,
                    (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    status_colour,
                    2,
                )

                cv2.imshow(config.PREVIEW_WINDOW_NAME, display_frame)

                if cv2.waitKey(1) & 0xFF == ord("q"):
                    log.info("'q' pressed — shutting down")
                    break

    except KeyboardInterrupt:
        log.info("Keyboard interrupt — shutting down")
    finally:
        camera.release()
        conn.close()
        if config.SHOW_PREVIEW:
            cv2.destroyAllWindows()
        log.info("SecureVision stopped")

    return 0


if __name__ == "__main__":
    sys.exit(main())
