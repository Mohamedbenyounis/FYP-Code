"""
SecureVision — main entry point (Iteration 9 — experimental branch).

Captures webcam frames, runs the ML pipeline every N-th frame, feeds
per-face observations into the MultiEntityEventManager, and persists
confirmed events to the SQLite database.
"""

from __future__ import annotations

import sys
import time

import cv2

from app import config
from app.camera.webcam import WebcamCamera
from app.core.multi_event_manager import MultiEntityEventManager
from app.core.models import Observation
from app.db.migrations import init_db
from app.db.repo import (
    SQLiteEventRepository,
    SQLitePersonRepository,
    SQLiteAlertRepository,
    make_enrolled_provider,
)
from app.ml.pipeline import FacePipeline
from app.recording.snapshot_recorder import SnapshotRecorder
from app.recording.clip_recorder import ClipRecorder
from app.services.alert_service import AlertService
from app.services.email_service import EmailService
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
    log.info("SecureVision starting — Iteration 9 (experimental)")
    log.info("=" * 60)

    # Ensure folders ---------------------------------------------------
    _ensure_directories()
    log.info("Data dir : %s", config.DATA_DIR)
    log.info("Models dir: %s", config.MODELS_DIR)

    # Database ---------------------------------------------------------
    conn = init_db(config.DB_PATH)
    repo = SQLitePersonRepository(conn)
    event_repo = SQLiteEventRepository(conn)
    alert_repo = SQLiteAlertRepository(conn)
    snapshot_recorder = SnapshotRecorder(config.SNAPSHOTS_DIR)
    clip_recorder = ClipRecorder(config.CLIPS_DIR)
    
    # Alert Services (Iteration 11)
    email_service = EmailService(
        smtp_host=config.EMAIL_SMTP_HOST,
        smtp_port=config.EMAIL_SMTP_PORT,
        username=config.EMAIL_USERNAME,
        password=config.EMAIL_PASSWORD
    )
    alert_service = AlertService(alert_repo, email_service)
    
    log.info("DB path  : %s", config.DB_PATH)

    # Multi-Entity Event Manager (Iteration 9) -------------------------
    event_manager = MultiEntityEventManager(
        association_distance=config.MULTI_FACE_ASSOCIATION_DISTANCE,
        max_entities=config.MULTI_FACE_MAX_ENTITIES,
        window_n=config.EVENT_CONFIRM_WINDOW_N,
        confirm_k=config.EVENT_CONFIRM_MIN_K,
        lost_frames=config.EVENT_LOST_FRAMES,
        cooldown_seconds=config.EVENT_COOLDOWN_SECONDS,
        score_threshold=config.AUTHORISATION_THRESHOLD,
    )
    log.info(
        "MultiEntityEventManager: assoc_dist=%.0fpx  max_entities=%d",
        config.MULTI_FACE_ASSOCIATION_DISTANCE,
        config.MULTI_FACE_MAX_ENTITIES,
    )
    log.info(
        "  per-face: window=%d  confirm=%d  lost=%d  cooldown=%.1fs",
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

            # --- Ring Buffer / Clip Recording (Iteration 10) --------------
            if config.CLIP_ENABLED:
                completed_clips = clip_recorder.feed_frame(frame)
                for ev_id, clip_path in completed_clips:
                    try:
                        rel_path = clip_path.relative_to(config.BASE_DIR).as_posix()
                    except ValueError:
                        rel_path = clip_path.as_posix()
                        
                    updated = event_repo.update_event_clip(ev_id, rel_path)
                    if updated:
                        log.info("EVENT CLIP linked id=%s path=%s", ev_id[:8], rel_path)
                    else:
                        log.warning("EVENT CLIP link failed id=%s", ev_id[:8])

            # --- ML processing (every N-th frame) -------------------------
            if frame_counter % config.PROCESS_EVERY_N_FRAMES == 0:
                result = pipeline.process_frame(frame)
                last_result = result  # persist for drawing on all frames

                # Structured console output (always active)
                if result.detections:
                    log.info("Detected %d face(s)", len(result.detections))

                if result.primary_detection is not None:
                    det = result.primary_detection
                    log.info(
                        "Primary face  | conf=%.2f | bbox=%s | size=%dx%d",
                        det.confidence,
                        det.bbox.as_tuple(),
                        det.bbox.width,
                        det.bbox.height,
                    )

                # Multi-face recognition summary  (Iteration 8)
                if result.recognitions:
                    known = [
                        r for r in result.recognitions
                        if r is not None and r.is_match
                    ]
                    if known:
                        names = ", ".join(r.name for r in known)
                        log.info("Recognised: %s", names)
                    unknown_count = sum(
                        1 for r in result.recognitions
                        if r is None or not r.is_match
                    )
                    if unknown_count:
                        log.info("Unknown faces: %d", unknown_count)
                elif result.recognition is not None:
                    # Fallback for backward compat (single recognition)
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

                # --- Multi-Face Event Manager (Iteration 9) ---------------
                now = time.monotonic()
                per_face_obs: list[Observation] = []

                for idx, det in enumerate(result.detections):
                    rec = None
                    if idx < len(result.recognitions):
                        rec = result.recognitions[idx]

                    obs = Observation(
                        timestamp=now,
                        face_present=True,
                        person_name=(
                            rec.name
                            if rec is not None and rec.is_match
                            else None
                        ),
                        person_id=None,  # resolved in future iteration
                        score=rec.score if rec is not None else 0.0,
                        bbox=det.bbox,
                    )
                    per_face_obs.append(obs)

                # If no faces detected, still send an empty list so
                # tracked entities get their "absent" observations.
                events = event_manager.update(per_face_obs)

                for event in events:
                    event_repo.add_event(event)

                    # --- Alerts Trigger (Iteration 11) ---
                    if config.ALERTS_ENABLED and event.status == "unauthorised":
                        alert_service.trigger_unauthorised_alert(event)

                    snapshot_path = snapshot_recorder.on_event(event, frame)
                    if snapshot_path is not None:
                        try:
                            rel_path = snapshot_path.relative_to(config.BASE_DIR).as_posix()
                        except ValueError:
                            rel_path = snapshot_path.as_posix()

                        updated = event_repo.update_event_snapshot(
                            event.event_id,
                            rel_path,
                        )
                        if updated:
                            log.info(
                                "EVENT SNAPSHOT linked id=%s path=%s",
                                event.event_id[:8],
                                rel_path,
                            )
                        else:
                            log.warning(
                                "EVENT SNAPSHOT link failed id=%s",
                                event.event_id[:8],
                            )
                        log.warning(
                            "EVENT SNAPSHOT save failed id=%s",
                            event.event_id[:8],
                        )

                    if config.CLIP_ENABLED:
                        clip_recorder.on_event(event, frame)

                    log.info(
                        "EVENT  id=%s  status=%s  person=%s  score=%.3f",
                        event.event_id[:8],
                        event.status,
                        event.person_name or "unknown",
                        event.score or 0.0,
                    )

                if event_manager.active_tracks > 0:
                    log.debug(
                        "Active tracks: %d  states: %s",
                        event_manager.active_tracks,
                        event_manager.track_states(),
                    )

            # --- Preview window (guarded by SHOW_PREVIEW) -----------------
            if config.SHOW_PREVIEW:
                display_frame = frame.copy()

                # Overlay all detection bboxes using latest ML result
                if last_result is not None:
                    for idx, det in enumerate(last_result.detections):
                        b = det.bbox
                        is_primary = (
                            last_result.primary_detection is not None
                            and det is last_result.primary_detection
                        )

                        # Look up per-face recognition (Iteration 8)
                        rec = None
                        if idx < len(last_result.recognitions):
                            rec = last_result.recognitions[idx]

                        # Colour: primary green, known yellow, unknown grey
                        if is_primary:
                            colour = (0, 255, 0)
                            thickness = 2
                        elif rec is not None and rec.is_match:
                            colour = (0, 255, 255)  # yellow — known
                            thickness = 2
                        else:
                            colour = (180, 180, 180)  # grey — unknown
                            thickness = 1

                        cv2.rectangle(
                            display_frame,
                            (b.x1, b.y1),
                            (b.x2, b.y2),
                            colour,
                            thickness,
                        )

                        # Label: show identity if recognised, else confidence
                        if rec is not None and rec.is_match:
                            label = f"{rec.name} ({rec.score:.2f})"
                        elif rec is not None:
                            label = f"Unknown ({rec.score:.2f})"
                        else:
                            label = f"conf={det.confidence:.2f}"

                        cv2.putText(
                            display_frame,
                            label,
                            (b.x1, b.y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6 if is_primary else 0.5,
                            colour,
                            2 if is_primary else 1,
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
