# Section K - Meta / Project Value

This is source material for writing the report, not the final polished section.

Evidence source set used for this pack:
- [app/config.py](../app/config.py)
- [app/main.py](../app/main.py)
- [app/camera/base.py](../app/camera/base.py)
- [app/camera/webcam.py](../app/camera/webcam.py)
- [app/camera/rtsp.py](../app/camera/rtsp.py)
- [app/web/app_factory.py](../app/web/app_factory.py)
- [app/web/auth.py](../app/web/auth.py)
- [app/web/routes.py](../app/web/routes.py)
- [app/web/templates/base.html](../app/web/templates/base.html)
- [app/web/templates/dashboard.html](../app/web/templates/dashboard.html)
- [app/web/templates/event.html](../app/web/templates/event.html)
- [app/web/templates/enroll.html](../app/web/templates/enroll.html)
- [app/services/alert_service.py](../app/services/alert_service.py)
- [app/services/email_service.py](../app/services/email_service.py)
- [app/services/servo_service.py](../app/services/servo_service.py)
- [scripts/pi_servo_service.py](../scripts/pi_servo_service.py)
- [app/recording/clip_recorder.py](../app/recording/clip_recorder.py)
- [app/recording/snapshot_recorder.py](../app/recording/snapshot_recorder.py)
- [app/core/event_manager.py](../app/core/event_manager.py)
- [app/core/multi_event_manager.py](../app/core/multi_event_manager.py)
- [app/services/enrollment_service.py](../app/services/enrollment_service.py)
- [app/ml/pipeline.py](../app/ml/pipeline.py)
- [app/db/schema.sql](../app/db/schema.sql)
- [app/db/migrations.py](../app/db/migrations.py)
- [app/db/repo.py](../app/db/repo.py)
- [app/web_run.py](../app/web_run.py)
- [docs/BUILD_LOG.md](../docs/BUILD_LOG.md)
- [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)
- [docs/SETUP.md](../docs/SETUP.md)
- [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)
- [docs/VALIDATION_REPORT.md](../docs/VALIDATION_REPORT.md)
- [docs/MULTI_FACE_EVENT_HANDLING_LOG.md](../docs/MULTI_FACE_EVENT_HANDLING_LOG.md)
- [docs/TRACKING_INTEGRATION_LOG.md](../docs/TRACKING_INTEGRATION_LOG.md)
- [docs/CLIP_RECORDING_LOG.md](../docs/CLIP_RECORDING_LOG.md)
- [docs/ENROLLMENT_UI_LOG.md](../docs/ENROLLMENT_UI_LOG.md)
- [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)
- [reports/live_stream_optimization_report.md](live_stream_optimization_report.md)
- [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md)
- [tests/test_rbac.py](../tests/test_rbac.py)
- [tests/test_auth.py](../tests/test_auth.py)
- [tests/test_dashboard.py](../tests/test_dashboard.py)
- [tests/test_servo_logic.py](../tests/test_servo_logic.py)

Evidence reliability rule used:
- Current code is ground truth for current behavior.
- Historical behavior is reconstructed from iteration logs and evaluation reports.
- Anything implied but not explicitly stated in code/docs is tagged INFERENCE.
- If evidence is absent in repo, it is stated as not found.

---

## K1. System Scalability and Limitations Analysis

### 1. What exists in the current system

- Single-node runtime with one selected camera source at a time (`webcam` or one `rtsp` URL) in [app/main.py](../app/main.py#L435).
- Two-thread architecture:
  - FAST loop for camera read, overlay, shared-memory publish.
  - SLOW loop for ML inference, event handling, DB writes, alerts, clip triggers.
  Evidence in [app/main.py](../app/main.py).
- Explicit bounded queue for freshness (`queue.Queue(maxsize=1)`), dropping stale frames under load in [app/main.py](../app/main.py#L490) and [app/main.py](../app/main.py#L552).
- Multi-face eventing exists but bounded by `SV_MULTI_FACE_MAX_ENTITIES` (default 10) in [app/config.py](../app/config.py#L232) and enforced in [app/core/multi_event_manager.py](../app/core/multi_event_manager.py#L147).
- Event confirmation and cooldown are fixed-rule state-machine thresholds (`N`, `K`, lost frames, cooldown) in [app/config.py](../app/config.py#L185) and [app/core/event_manager.py](../app/core/event_manager.py#L65).
- Dashboard live stream is shared-memory latest-frame semantics (not frame-history stream queue), with one shared block `sv_live_frame` in [app/main.py](../app/main.py#L487) and [app/web/routes.py](../app/web/routes.py#L246).
- SQLite is the storage backend with WAL and one process-owned connection per process path in [app/db/migrations.py](../app/db/migrations.py#L76) and [app/db/migrations.py](../app/db/migrations.py#L79).

### 2. What design decision created this situation

- Local-first, single-host architecture prioritized implementation reliability and observability over distributed scale.
- Design intentionally chooses freshness over completeness by dropping queued frames (`maxsize=1`, non-blocking put).
- Nearest-centroid association was chosen as lightweight multi-entity orchestration instead of appearance-based tracking.
- SQLite chosen for simple local persistence and easy deployment.
- Dashboard transport is latest-frame shared memory, not event streaming or broker-backed fanout.

### 3. Why it matters

- This design scales well for prototype/small deployment workloads, but not for multi-camera enterprise workloads.
- The major bottlenecks become:
  - Camera ingest and decode (especially RTSP).
  - CPU-bound ML inference throughput in the slow thread.
  - Synchronous I/O paths (clip write, DB updates) under event bursts.
  - Single-process coordination constraints around shared objects.
- Empirical evidence shows ingest and ML throughput roughly halved in RTSP mode versus webcam mode in [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md#L34).

### 4. What files matter most

- [app/main.py](../app/main.py)
- [app/config.py](../app/config.py)
- [app/core/multi_event_manager.py](../app/core/multi_event_manager.py)
- [app/core/event_manager.py](../app/core/event_manager.py)
- [app/camera/rtsp.py](../app/camera/rtsp.py)
- [app/db/migrations.py](../app/db/migrations.py)
- [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)
- [reports/live_stream_optimization_report.md](live_stream_optimization_report.md)
- [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)
- [docs/VALIDATION_REPORT.md](../docs/VALIDATION_REPORT.md)

### 5. 1-3 short useful snippets

Snippet K1-1 from [app/main.py](../app/main.py)

~~~python
frame_queue: queue.Queue = queue.Queue(maxsize=1)

if frame_counter % config.PROCESS_EVERY_N_FRAMES == 0:
    try:
        frame_queue.put_nowait(frame.copy())
    except queue.Full:
        fast_diag.tick_queue_drop()
~~~

Snippet K1-2 from [app/core/multi_event_manager.py](../app/core/multi_event_manager.py)

~~~python
if len(self._tracks) >= self._max_entities:
    self._log.debug(
        "Max entities (%d) reached - ignoring new face",
        self._max_entities,
    )
    break
~~~

Snippet K1-3 from [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)

~~~text
Avg Camera FPS: webcam 30.0 fps vs RTSP 15.0 fps
Avg Frame Read Time: webcam 27.4 ms vs RTSP 52.0 ms
Max Pipeline Latency: webcam 141.0 ms vs RTSP 266.0 ms
ML FPS: webcam 10.0 fps vs RTSP 5.0 fps
~~~

### 6. How I could describe this in report language

- SecureVision scales to a single-host, low-concurrency deployment by using a bounded producer-consumer architecture that favors frame freshness over full-frame retention.
- The current design is intentionally conservative: one selected camera stream, single-node persistence, and capped multi-entity tracking, which is suitable for a final-year prototype but not for high-density multi-site deployments.
- Measured RTSP ingest overhead confirms that networked deployment flexibility is achieved at a significant throughput cost.

### 7. Limitations and honest weaknesses

- Single camera source selection in runtime; no native multi-camera orchestration in [app/main.py](../app/main.py#L435).
- RTSP docs explicitly list multi-camera as out of scope in [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md#L214).
- Centroid-only track association can swap identities on crossing in [app/core/multi_event_manager.py](../app/core/multi_event_manager.py#L19) and [docs/VALIDATION_REPORT.md](../docs/VALIDATION_REPORT.md#L172).
- INFERENCE: Queue `maxsize=1` keeps stream responsive but sacrifices temporal continuity for downstream analytics.
- No dedicated benchmark harness currently present on main branch, noted in evaluation artifacts.
- INFERENCE: For larger deployments, needed changes include multi-stream scheduler, per-camera worker isolation, external message bus, and database upgrade beyond single SQLite file.

---

## K2. Security Considerations

### 1. What exists in the current system

- Dashboard auth and RBAC exist:
  - password hash verification via `check_password_hash` in [app/web/routes.py](../app/web/routes.py#L133).
  - role gate via `role_required` and explicit 403 in [app/web/auth.py](../app/web/auth.py#L35).
  - tests for auth/RBAC in [tests/test_auth.py](../tests/test_auth.py) and [tests/test_rbac.py](../tests/test_rbac.py).
- Session cookie hardening is partial:
  - HTTPOnly and SameSite=Lax set in [app/web/app_factory.py](../app/web/app_factory.py#L24).
  - no `SESSION_COOKIE_SECURE` found in repo (not found via code search).
- Secret and bootstrap behavior:
  - default Flask secret is development-like value in [app/config.py](../app/config.py#L218).
  - warning emitted if default secret is used in [app/web/app_factory.py](../app/web/app_factory.py#L37).
  - bootstrap admin requires env vars in [app/db/migrations.py](../app/db/migrations.py#L197).
- Path traversal defenses for media evidence routes:
  - snapshot and clip resolution constrained to approved roots in [app/web/routes.py](../app/web/routes.py#L49) and [app/web/routes.py](../app/web/routes.py#L73).
  - tested against traversal payloads in [tests/test_dashboard.py](../tests/test_dashboard.py#L158) and [tests/test_dashboard.py](../tests/test_dashboard.py#L257).
- Transport/security assumptions in docs:
  - RTSP unencrypted by default and LAN trust assumptions in [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md#L202).
  - production suggestion is RTSPS or VPN in [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md#L204).
- Servo control surface:
  - host sends unauthenticated HTTP GET commands in [app/services/servo_service.py](../app/services/servo_service.py#L16) and [app/services/servo_service.py](../app/services/servo_service.py#L159).
  - Pi endpoint listens on 0.0.0.0 and accepts query params in [scripts/pi_servo_service.py](../scripts/pi_servo_service.py#L53) and [scripts/pi_servo_service.py](../scripts/pi_servo_service.py#L100).
- Email alert channel uses STARTTLS if offered by server in [app/services/email_service.py](../app/services/email_service.py#L61).

### 2. What design decision created this situation

- Project is designed for trusted local/LAN deployment first, not Internet-exposed zero-trust deployment.
- Security controls focus on practical baseline protections for prototype usage (session auth, RBAC, path sandboxing, hashed passwords).
- Control-plane simplicity was prioritized for servo and RTSP integration (plain endpoints, minimal auth complexity).

### 3. Why it matters

- If deployed outside trusted LAN assumptions, attack surface expands significantly:
  - RTSP sniffing/tampering risk if plaintext stream is reachable.
  - Servo command endpoint abuse if reachable without auth.
  - CSRF and session transport concerns for browser actions.
  - Credential management and brute-force hardening gaps.
- The system can be reasonably safe for localhost/lab but needs explicit hardening for production.

### 4. What files matter most

- [app/web/app_factory.py](../app/web/app_factory.py)
- [app/web/auth.py](../app/web/auth.py)
- [app/web/routes.py](../app/web/routes.py)
- [app/config.py](../app/config.py)
- [app/db/migrations.py](../app/db/migrations.py)
- [app/services/servo_service.py](../app/services/servo_service.py)
- [scripts/pi_servo_service.py](../scripts/pi_servo_service.py)
- [app/services/email_service.py](../app/services/email_service.py)
- [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)
- [tests/test_rbac.py](../tests/test_rbac.py)
- [tests/test_dashboard.py](../tests/test_dashboard.py)

### 5. 1-3 short useful snippets

Snippet K2-1 from [app/web/app_factory.py](../app/web/app_factory.py)

~~~python
app.config["SECRET_KEY"] = config.FLASK_SECRET_KEY
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

if config.FLASK_SECRET_KEY == "securevision-dev-secret":
    log.warning("SECURITY: SV_FLASK_SECRET_KEY not set; using dev secret")
~~~

Snippet K2-2 from [app/services/servo_service.py](../app/services/servo_service.py) and [scripts/pi_servo_service.py](../scripts/pi_servo_service.py)

~~~python
self.base_url = f"http://{self.pi_ip}:{self.pi_port}"
resp = requests.get(url, params=params, timeout=1.0)

@app.route('/move', methods=['GET'])
def move_servo():
    axis = request.args.get('axis', '').lower()
~~~

Snippet K2-3 from [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)

~~~text
RTSP streams are unencrypted by default. On a trusted home/lab LAN, this is acceptable.
For production deployments, consider RTSP-over-TLS (RTSPS) or VPN tunnels.
~~~

### 6. How I could describe this in report language

- SecureVision implements baseline application-layer controls (session auth, RBAC, hashed passwords, media path sandboxing), but network-layer assumptions remain LAN-centric.
- The current security posture is prototype-appropriate for controlled environments and explicitly documents that production deployment requires transport encryption and endpoint hardening.

### 7. Limitations and honest weaknesses

- No CSRF token framework found in routes/templates; state-changing POST actions exist (not found: Flask-WTF or CSRF middleware in requirements/code).
- No `SESSION_COOKIE_SECURE` found, so HTTPS-only cookie enforcement is not configured in-app.
- No explicit login rate-limiting/account lockout found.
- Servo control endpoint is unauthenticated HTTP GET and network-reachable on Pi (`0.0.0.0`).
- RTSP stream is plaintext by default unless external RTSPS/VPN is added.
- INFERENCE: If dashboard host is changed from localhost to broader network without reverse-proxy hardening, risk profile increases substantially.

---

## K3. Ethical Considerations of Face Recognition

### 1. What exists in the current system

- System performs biometric identification and stores both identity template data and evidential media:
  - face embeddings in `persons` and `person_embeddings` in [app/db/schema.sql](../app/db/schema.sql#L10) and [app/db/schema.sql](../app/db/schema.sql#L19).
  - event metadata with person labels/status in [app/db/schema.sql](../app/db/schema.sql#L35).
  - snapshot and clip references in [app/db/schema.sql](../app/db/schema.sql#L42).
- Event classification is threshold-based (`authorised` vs `unauthorised`) in [app/core/event_manager.py](../app/core/event_manager.py#L176) with thresholds configured in [app/config.py](../app/config.py#L110) and [app/config.py](../app/config.py#L197).
- Enrollment quality gate requires minimum valid captures in [app/services/enrollment_service.py](../app/services/enrollment_service.py#L41) and [app/services/enrollment_service.py](../app/services/enrollment_service.py#L93).
- K-of-N event confirmation reduces one-frame false triggers in [app/core/event_manager.py](../app/core/event_manager.py#L164).
- Known identification integrity limitations are documented:
  - crossing identity swaps and ghost slot effects in [docs/VALIDATION_REPORT.md](../docs/VALIDATION_REPORT.md#L172) and [docs/MULTI_FACE_EVENT_HANDLING_LOG.md](../docs/MULTI_FACE_EVENT_HANDLING_LOG.md#L23).
- UI surfaces identity + media evidence directly in [app/web/templates/event.html](../app/web/templates/event.html#L31) and [app/web/templates/event.html](../app/web/templates/event.html#L47).

### 2. What design decision created this situation

- Chosen design emphasizes security event traceability: each detection outcome can be linked to stored artifacts (name, score, snapshot, clip).
- Local-first storage avoids cloud dependency but centralizes sensitive biometric and surveillance evidence on local disk.
- Lightweight association and static thresholds were chosen for manageable complexity in a final-year prototype.

### 3. Why it matters

- Ethical impact is direct because the system is not just detecting faces, it is assigning identities and storing persistent evidence.
- False positives/negatives and identity swaps can produce real-world consequences:
  - wrongful unauthorised labeling,
  - missed unauthorised individuals,
  - misattributed event history in crossing scenarios.
- Privacy exposure exists because biometric templates and incident media are retained in a local database/filesystem with no built-in retention lifecycle.

### 4. What files matter most

- [app/db/schema.sql](../app/db/schema.sql)
- [app/services/enrollment_service.py](../app/services/enrollment_service.py)
- [app/core/event_manager.py](../app/core/event_manager.py)
- [app/core/multi_event_manager.py](../app/core/multi_event_manager.py)
- [app/config.py](../app/config.py)
- [docs/VALIDATION_REPORT.md](../docs/VALIDATION_REPORT.md)
- [docs/MULTI_FACE_EVENT_HANDLING_LOG.md](../docs/MULTI_FACE_EVENT_HANDLING_LOG.md)
- [app/web/templates/event.html](../app/web/templates/event.html)
- [docs/ENROLLMENT_UI_LOG.md](../docs/ENROLLMENT_UI_LOG.md)

### 5. 1-3 short useful snippets

Snippet K3-1 from [app/db/schema.sql](../app/db/schema.sql)

~~~sql
CREATE TABLE IF NOT EXISTS persons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    embedding BLOB NOT NULL,
    embedding_dim INTEGER NOT NULL,
    dtype TEXT NOT NULL DEFAULT 'float32'
);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    person_name TEXT,
    score REAL,
    snapshot_path TEXT,
    clip_path TEXT
);
~~~

Snippet K3-2 from [app/services/enrollment_service.py](../app/services/enrollment_service.py)

~~~python
if len(valid_embeddings) < min_captures:
    err_msg = (
        f"Only {len(valid_embeddings)}/{len(images)} valid captures obtained. "
        f"{min_captures} required. Needs clear, single front-facing portraits."
    )
    return EnrollmentResult(success=False, message=err_msg)
~~~

Snippet K3-3 from [docs/VALIDATION_REPORT.md](../docs/VALIDATION_REPORT.md)

~~~text
KNOWN LIMITATION: identities may swap after crossing because centroid-only
association cannot distinguish visual identity when faces are close together.
~~~

### 6. How I could describe this in report language

- SecureVision includes practical safeguards against noisy classification (multi-capture enrollment, K-of-N confirmation), but it still carries ethical risk due to persistent biometric storage and known identity continuity limitations.
- The system is technically transparent about these limits, which is important for responsible reporting: it does not claim perfect identity fidelity under crossing/motion stress.

### 7. Limitations and honest weaknesses

- No explicit consent workflow, privacy notice, or data-subject rights mechanism found in repo (not found in code/docs).
- No explicit retention/deletion schedule for events/snapshots/clips found; storage appears append-oriented by default.
- No fairness/bias evaluation protocol found (no demographic performance study artifacts in repo).
- Thresholds are global static values; no context-aware calibration pipeline found.
- INFERENCE: Any logged-in operator can review person names and evidence media, which may exceed least-privilege expectations for sensitive surveillance contexts.
- INFERENCE: If identity swap occurs in crossing scenes, downstream accountability narratives in reports may be wrong unless manually verified.

---

## K4. Sustainability and Efficiency Considerations

### 1. What exists in the current system

- Efficiency knobs are explicitly configurable:
  - `SV_PROCESS_EVERY_N_FRAMES` default 3 in [app/config.py](../app/config.py#L148).
  - `SV_LIVE_VIEW_EVERY_N_FRAMES` default 2 in [app/config.py](../app/config.py#L173).
  - clip fps/duration caps (`SV_CLIP_TARGET_FPS`, `SV_CLIP_MAX_DURATION_SECONDS`) in [app/config.py](../app/config.py#L164).
  - gallery cap (`SV_MAX_GALLERY_EMBEDDINGS`) in [app/config.py](../app/config.py#L117).
- FAST/SLOW split improves responsiveness by isolating heavy work in background thread in [app/main.py](../app/main.py).
- JPEG stream quality is tuned down (`IMWRITE_JPEG_QUALITY` 65) and oversized payloads are dropped at 2 MB shared-memory limit in [app/main.py](../app/main.py#L596) and [app/main.py](../app/main.py#L615).
- Ring-buffer clip design bounds temporal context and uses max-duration safety in [app/recording/clip_recorder.py](../app/recording/clip_recorder.py#L43) and [app/recording/clip_recorder.py](../app/recording/clip_recorder.py#L99).
- RTSP deployment recommendations intentionally lower stream load (640x480, 15fps, H.264 over TCP) in [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md#L63).
- Empirical trade-off data exists: RTSP mode incurs higher ingest/read latency and lower FPS in [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md#L34).

### 2. What design decision created this situation

- Project chooses host-side inference (laptop/host) with Pi as edge sensor/stream source, rather than full edge inference.
- Design accepts controlled frame dropping and subsampling to keep perceived responsiveness and avoid backlog growth.
- Clip evidence strategy prioritizes incident context over strict storage minimization (pre/post buffer and possible overlap).

### 3. Why it matters

- CPU efficiency: frame skipping and thread decoupling reduce CPU pressure and improve UX stability.
- Bandwidth efficiency: lower resolution/fps and JPEG quality reduce network and browser delivery cost.
- Storage efficiency: clip caps and embedding caps prevent unbounded growth in some dimensions.
- Sustainability perspective: these controls reduce wasted compute cycles and data volume, but incomplete lifecycle management still risks long-term storage bloat.

### 4. What files matter most

- [app/config.py](../app/config.py)
- [app/main.py](../app/main.py)
- [app/recording/clip_recorder.py](../app/recording/clip_recorder.py)
- [app/db/repo.py](../app/db/repo.py)
- [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)
- [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)
- [reports/live_stream_optimization_report.md](live_stream_optimization_report.md)
- [docs/CLIP_RECORDING_LOG.md](../docs/CLIP_RECORDING_LOG.md)

### 5. 1-3 short useful snippets

Snippet K4-1 from [app/config.py](../app/config.py)

~~~python
PROCESS_EVERY_N_FRAMES: int = _env_int("SV_PROCESS_EVERY_N_FRAMES", 3)
LIVE_VIEW_EVERY_N_FRAMES: int = _env_int("SV_LIVE_VIEW_EVERY_N_FRAMES", 2)
CLIP_TARGET_FPS: int = _env_int("SV_CLIP_TARGET_FPS", 15)
CLIP_MAX_DURATION_SECONDS: float = _env_float("SV_CLIP_MAX_DURATION_SECONDS", 60.0)
MAX_GALLERY_EMBEDDINGS: int = _env_int("SV_MAX_GALLERY_EMBEDDINGS", 5)
~~~

Snippet K4-2 from [app/main.py](../app/main.py)

~~~python
frame_queue: queue.Queue = queue.Queue(maxsize=1)

success, buffer = cv2.imencode(
    '.jpg', display_frame,
    [int(cv2.IMWRITE_JPEG_QUALITY), 65]
)

if size < SHM_TOTAL_SIZE - SHM_HEADER_SIZE:
    ...
else:
    log.warning("Live frame exceeds 2MB shared memory buffer. Skipping.")
~~~

Snippet K4-3 from [docs/CLIP_RECORDING_LOG.md](../docs/CLIP_RECORDING_LOG.md)

~~~text
Clip writing happens synchronously through continuous main loop execution.
It is NOT truly asynchronous.
Overlapping clips might duplicate disk space.
~~~

### 6. How I could describe this in report language

- SecureVision uses pragmatic efficiency controls (frame decimation, bounded queues, compressed live-view payloads, clip duration caps) to keep a constrained prototype responsive under mixed CPU and I/O load.
- The architecture reflects an explicit trade-off: responsiveness and deployment realism are prioritized over full-frame fidelity and maximal evidence completeness.

### 7. Limitations and honest weaknesses

- No direct power/energy measurement (wattage, kWh, carbon) found in repo artifacts.
- Synchronous clip writing remains a known I/O bottleneck path in docs.
- Overlapping clips can duplicate storage and there is no explicit retention policy found.
- RTSP mode adds substantial ingest overhead; efficiency gains from edge sensing are partly offset by decode and transport costs.
- INFERENCE: For sustainability at scale, future work should include retention policies, async clip writer, hardware-accelerated decode/inference, and adaptive quality control under load.

---

## Cross-cutting "not found" notes (to avoid hallucination)

- No CSRF token implementation found in current Flask routes/templates.
- No explicit TLS termination config for dashboard app found in app code.
- No `SESSION_COOKIE_SECURE` config found.
- No explicit rate limiting/account lockout implementation found.
- No formal bias/fairness benchmark report found.
- No explicit data retention/deletion policy module for snapshots/clips/events found.
- No built-in RTSP server provisioning automation found in app runtime (docs require external Pi setup).
