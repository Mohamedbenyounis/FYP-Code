"""
SecureVision — main entry point (Iteration 12c — threaded architecture).

Two-thread design:
  FAST thread (main) — camera capture, overlay drawing, live stream publishing
  SLOW thread (daemon) — ML inference, event management, DB writes, alerts

The fast thread never blocks on ML or I/O. The slow thread processes frames
from a bounded queue and publishes overlay data back via atomic reference swap.
"""

from __future__ import annotations

import queue
import sys
import threading
import time

import cv2
import numpy as np

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


# ---------------------------------------------------------------------------
# Overlay structure shared between threads
# ---------------------------------------------------------------------------
# Each overlay entry is a dict:
#   {"bbox": (x1,y1,x2,y2), "label": str, "colour": (b,g,r), "thickness": int}
# The list is replaced atomically (reference swap). No lock needed for reads
# because Python's GIL guarantees atomic reference assignment.

_latest_overlays: list[dict] = []
_ml_status_text: str = "ML: STARTING"
_ml_status_colour: tuple = (180, 180, 180)

# ---------------------------------------------------------------------------
# Shared Memory Layout (9-byte header)
# ---------------------------------------------------------------------------
# Byte 0:     lock flag (0=ready, 1=writing)
# Bytes 1-4:  JPEG payload size (uint32 LE)
# Bytes 5-8:  sequence number (uint32 LE)
# Bytes 9+:   JPEG payload
SHM_HEADER_SIZE = 9
SHM_TOTAL_SIZE = 2 * 1024 * 1024  # 2 MB


# ---------------------------------------------------------------------------
# Stream Diagnostics (temporary instrumentation)
# ---------------------------------------------------------------------------
class _StreamDiag:
    """Lightweight periodic diagnostics. Prints summary every `interval` seconds."""

    def __init__(self, label: str, interval: float = 5.0):
        self.label = label
        self.interval = interval
        self._reset()

    def _reset(self):
        self._t0 = time.monotonic()
        self.cam_reads = 0
        self.cam_read_total_ms = 0.0
        self.cam_read_max_ms = 0.0
        self.jpeg_encodes = 0
        self.jpeg_total_bytes = 0
        self.shm_writes = 0
        self.shm_skips = 0
        self.ml_frames = 0

    def tick_cam_read(self, elapsed_ms: float):
        self.cam_reads += 1
        self.cam_read_total_ms += elapsed_ms
        if elapsed_ms > self.cam_read_max_ms:
            self.cam_read_max_ms = elapsed_ms

    def tick_jpeg(self, byte_size: int):
        self.jpeg_encodes += 1
        self.jpeg_total_bytes += byte_size

    def tick_shm_write(self):
        self.shm_writes += 1

    def tick_shm_skip(self):
        self.shm_skips += 1

    def tick_ml(self):
        self.ml_frames += 1

    def maybe_log(self, log) -> None:
        elapsed = time.monotonic() - self._t0
        if elapsed < self.interval:
            return
        cam_fps = self.cam_reads / elapsed if elapsed > 0 else 0
        cam_avg = self.cam_read_total_ms / self.cam_reads if self.cam_reads > 0 else 0
        cam_max = self.cam_read_max_ms
        enc_fps = self.jpeg_encodes / elapsed if elapsed > 0 else 0
        avg_kb = (self.jpeg_total_bytes / self.jpeg_encodes / 1024) if self.jpeg_encodes > 0 else 0
        ml_fps = self.ml_frames / elapsed if elapsed > 0 else 0
        log.info(
            "[DIAG %s] cam=%.1f fps (avg=%.1fms max=%.1fms) | "
            "enc=%.1f fps (avg=%.0f KB) | shm_w=%d skip=%d | ml=%.1f fps",
            self.label, cam_fps, cam_avg, cam_max,
            enc_fps, avg_kb, self.shm_writes, self.shm_skips, ml_fps,
        )
        self._reset()


def _processing_loop(
    frame_queue: queue.Queue,
    pipeline: FacePipeline,
    event_manager: MultiEntityEventManager,
    event_repo: SQLiteEventRepository,
    snapshot_recorder: SnapshotRecorder,
    clip_recorder: ClipRecorder,
    clip_lock: threading.Lock,
    alert_service: AlertService,
    log,
) -> None:
    """
    SLOW THREAD — ML inference, event management, DB writes, alerts.

    Reads frames from the bounded queue. Publishes overlay data back to the
    fast thread via atomic reference swap of the global _latest_overlays.
    """
    global _latest_overlays, _ml_status_text, _ml_status_colour

    stats = FrameRateLogger(log_every_n=100)
    slow_diag = _StreamDiag("SLOW", interval=5.0)

    _ml_status_text = "ML: ON" if pipeline.ml_enabled else "ML: DISABLED"
    _ml_status_colour = (0, 255, 0) if pipeline.ml_enabled else (0, 0, 255)

    while True:
        try:
            frame = frame_queue.get(timeout=2.0)
        except queue.Empty:
            continue

        if frame is None:
            # Poison pill — main thread is shutting down
            break

        # --- ML processing ------------------------------------------------
        result = pipeline.process_frame(frame)
        slow_diag.tick_ml()
        slow_diag.maybe_log(log)

        # Build overlay list from ML results
        new_overlays = []
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

        # Multi-face recognition summary
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
            rec = result.recognition
            if rec.is_match:
                log.info("Recognised: %s  score=%.3f", rec.name, rec.score)
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

        # Build overlays for the fast thread to draw
        for idx, det in enumerate(result.detections):
            b = det.bbox
            is_primary = (
                result.primary_detection is not None
                and det is result.primary_detection
            )

            rec = None
            if idx < len(result.recognitions):
                rec = result.recognitions[idx]

            if is_primary:
                colour = (0, 255, 0)
                thickness = 2
            elif rec is not None and rec.is_match:
                colour = (0, 255, 255)
                thickness = 2
            else:
                colour = (180, 180, 180)
                thickness = 1

            if rec is not None and rec.is_match:
                label = f"{rec.name} ({rec.score:.2f})"
            elif rec is not None:
                label = f"Unknown ({rec.score:.2f})"
            else:
                label = f"conf={det.confidence:.2f}"

            font_scale = 0.6 if is_primary else 0.5
            font_thickness = 2 if is_primary else 1

            new_overlays.append({
                "bbox": (b.x1, b.y1, b.x2, b.y2),
                "label": label,
                "colour": colour,
                "thickness": thickness,
                "font_scale": font_scale,
                "font_thickness": font_thickness,
            })

        # Atomic swap — fast thread will pick this up on next iteration
        _latest_overlays = new_overlays

        # --- Multi-Face Event Manager (Iteration 9) -----------------------
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
                person_id=None,
                score=rec.score if rec is not None else 0.0,
                bbox=det.bbox,
            )
            per_face_obs.append(obs)

        events = event_manager.update(per_face_obs)

        # Notify clip recorder of active presences
        if config.CLIP_ENABLED:
            with clip_lock:
                clip_recorder.update_track_states(event_manager.track_states())

        for event in events:
            event_repo.add_event(event)

            # --- Alerts (Iteration 11) ---
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

            # Clip recording trigger (thread-safe)
            if config.CLIP_ENABLED:
                with clip_lock:
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


def main() -> int:
    """Application entry point.  Returns 0 on success, 1 on error."""
    global _ml_status_text, _ml_status_colour

    log = get_logger()
    log.info("=" * 60)
    log.info("SecureVision starting — Iteration 12c (threaded)")
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
    enrolled_provider = make_enrolled_provider(repo)
    snapshot_recorder = SnapshotRecorder(config.SNAPSHOTS_DIR)
    clip_recorder = ClipRecorder(config.CLIPS_DIR)
    clip_lock = threading.Lock()

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

    # Initialize Shared Memory for Live Stream -------------------------
    from multiprocessing import shared_memory
    live_shm = None
    shm_seq = 0  # monotonic sequence counter for published frames
    if config.LIVE_VIEW_ENABLED:
        try:
            live_shm = shared_memory.SharedMemory(
                name="sv_live_frame", create=True, size=SHM_TOTAL_SIZE
            )
            live_shm.buf[0] = 0
            live_shm.buf[1:5] = (0).to_bytes(4, 'little')
            live_shm.buf[5:9] = (0).to_bytes(4, 'little')  # seq=0
        except FileExistsError:
            live_shm = shared_memory.SharedMemory(name="sv_live_frame")

    # Frame queue: maxsize=1 ensures stale frames are dropped ----------
    frame_queue: queue.Queue = queue.Queue(maxsize=1)

    # Start the slow processing thread ---------------------------------
    processing_thread = threading.Thread(
        target=_processing_loop,
        args=(
            frame_queue,
            pipeline,
            event_manager,
            event_repo,
            snapshot_recorder,
            clip_recorder,
            clip_lock,
            alert_service,
            log,
        ),
        daemon=True,
        name="sv-processing",
    )
    processing_thread.start()
    log.info("Processing thread started (daemon)")

    # FAST LOOP (main thread) — camera + overlay + stream publish -------
    frame_counter = 0
    fast_diag = _StreamDiag("FAST", interval=5.0)
    log.info("Entering fast camera loop (Ctrl+C to stop)")

    try:
        while True:
            t_read_start = time.monotonic()
            ok, frame = camera.read()
            t_read_ms = (time.monotonic() - t_read_start) * 1000.0

            if not ok or frame is None:
                log.warning("Frame read failed — attempting reconnect")
                if not camera.reconnect():
                    log.error("Reconnect failed — exiting")
                    break
                continue

            frame_counter += 1
            fast_diag.tick_cam_read(t_read_ms)

            # --- Feed clip recorder ring buffer (needs every frame) ----
            if config.CLIP_ENABLED:
                with clip_lock:
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

            # --- Push frame to slow thread (drop if full) -------------
            if frame_counter % config.PROCESS_EVERY_N_FRAMES == 0:
                try:
                    frame_queue.put_nowait(frame.copy())
                except queue.Full:
                    pass  # Drop stale frame — slow thread is busy

            # --- Draw overlays and publish to dashboard ----------------
            if config.SHOW_PREVIEW or config.LIVE_VIEW_ENABLED:
                display_frame = frame.copy()

                # Read latest overlays (atomic reference read, no lock)
                overlays = _latest_overlays
                for ov in overlays:
                    x1, y1, x2, y2 = ov["bbox"]
                    cv2.rectangle(
                        display_frame,
                        (x1, y1), (x2, y2),
                        ov["colour"],
                        ov["thickness"],
                    )
                    cv2.putText(
                        display_frame,
                        ov["label"],
                        (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        ov["font_scale"],
                        ov["colour"],
                        ov["font_thickness"],
                    )

                # Status bar
                cv2.putText(
                    display_frame,
                    _ml_status_text,
                    (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    _ml_status_colour,
                    2,
                )

                # Publish to shared memory for dashboard MJPEG stream
                if config.LIVE_VIEW_ENABLED and live_shm is not None:
                    if frame_counter % config.LIVE_VIEW_EVERY_N_FRAMES == 0:
                        success, buffer = cv2.imencode(
                            '.jpg', display_frame,
                            [int(cv2.IMWRITE_JPEG_QUALITY), 65]
                        )
                        if success:
                            payload = buffer.tobytes()
                            size = len(payload)
                            fast_diag.tick_jpeg(size)
                            if size < SHM_TOTAL_SIZE - SHM_HEADER_SIZE:
                                shm_seq += 1
                                live_shm.buf[0] = 1  # writing flag
                                live_shm.buf[1:5] = size.to_bytes(4, 'little')
                                live_shm.buf[5:9] = (shm_seq & 0xFFFFFFFF).to_bytes(4, 'little')
                                live_shm.buf[SHM_HEADER_SIZE:SHM_HEADER_SIZE+size] = payload
                                live_shm.buf[0] = 0  # done
                                fast_diag.tick_shm_write()
                            else:
                                fast_diag.tick_shm_skip()
                                log.warning(
                                    "Live frame exceeds 2MB shared memory buffer. Skipping."
                                )

                fast_diag.maybe_log(log)

                # Show native desktop preview window if enabled
                if config.SHOW_PREVIEW:
                    cv2.imshow(config.PREVIEW_WINDOW_NAME, display_frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        log.info("'q' pressed — shutting down")
                        break

    except KeyboardInterrupt:
        log.info("Keyboard interrupt — shutting down")
    finally:
        # Signal slow thread to exit
        try:
            frame_queue.put_nowait(None)  # poison pill
        except queue.Full:
            pass
        processing_thread.join(timeout=3.0)

        if live_shm is not None:
            live_shm.close()
            try:
                live_shm.unlink()
            except Exception:
                pass
        camera.release()
        conn.close()
        if config.SHOW_PREVIEW:
            cv2.destroyAllWindows()
        log.info("SecureVision stopped")

    return 0


if __name__ == "__main__":
    sys.exit(main())
