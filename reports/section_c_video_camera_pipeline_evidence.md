# Section C - Video and Camera Pipeline

This is source material for writing the report, not the final polished section.

Evidence source set used for this pack:
- [app/camera/base.py](../app/camera/base.py)
- [app/camera/webcam.py](../app/camera/webcam.py)
- [app/camera/rtsp.py](../app/camera/rtsp.py)
- [app/main.py](../app/main.py)
- [app/config.py](../app/config.py)
- [app/web/routes.py](../app/web/routes.py)
- [tests/test_camera_rtsp.py](../tests/test_camera_rtsp.py)
- [tests/test_camera_webcam.py](../tests/test_camera_webcam.py)
- [tests/test_hardware_resilience.py](../tests/test_hardware_resilience.py)
- [tests/test_main_loop.py](../tests/test_main_loop.py)
- [tests/test_dashboard.py](../tests/test_dashboard.py)
- [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)
- [docs/SETUP.md](../docs/SETUP.md)
- [docs/BUILD_LOG.md](../docs/BUILD_LOG.md)
- [docs/VALIDATION_REPORT.md](../docs/VALIDATION_REPORT.md)
- [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)
- [reports/live_stream_optimization_report.md](live_stream_optimization_report.md)
- [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md)
- [webcam_test_log.txt](../webcam_test_log.txt)
- [rtsp_test_log.txt](../rtsp_test_log.txt)

Evidence reliability rule used:
- Current code is ground truth for current behavior.
- Historical behavior and failed attempts are taken from versioned reports/log documents where old code paths are no longer active.
- If a statement is interpretive rather than directly measured, it is explicitly marked as inference.

---

## C1. RTSP Integration, Camera Abstraction, and End-to-End Wiring

### Technical evidence summary

Architecture and camera abstraction:
- A strict camera interface exists in [app/camera/base.py](../app/camera/base.py) with mandatory read/release/is_opened/reconnect/frame properties.
- Local and RTSP sources both implement this interface in [app/camera/webcam.py](../app/camera/webcam.py) and [app/camera/rtsp.py](../app/camera/rtsp.py).
- Runtime camera selection happens in [app/main.py](../app/main.py) via SV_CAMERA_TYPE and SV_RTSP_URL.

Configuration and operational entry:
- Camera-related env vars are centralized in [app/config.py](../app/config.py): SV_CAMERA_TYPE, SV_CAMERA_INDEX, SV_RTSP_URL.
- Pi-side stream setup commands and host-side env setup are documented in [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md).

Validation evidence:
- Unit tests cover RTSP open/read/reconnect and conservative buffer behavior in [tests/test_camera_rtsp.py](../tests/test_camera_rtsp.py).
- Hardware resilience tests cover repeated failures and reconnect behavior in [tests/test_hardware_resilience.py](../tests/test_hardware_resilience.py).

### 1. What existed before

- Default system camera mode is webcam (SV_CAMERA_TYPE default webcam in [app/config.py](../app/config.py)).
- Build history explicitly states webcam-first behavior before bonus RTSP integration in [docs/BUILD_LOG.md](../docs/BUILD_LOG.md).

### 2. What changed

- Added RTSP adapter with explicit FFmpeg backend usage and reconnect support in [app/camera/rtsp.py](../app/camera/rtsp.py).
- Extended camera interface contract to include reconnect in [app/camera/base.py](../app/camera/base.py).
- Main runtime now branches camera source by config and fails fast if RTSP URL is missing in [app/main.py](../app/main.py).
- Added setup and troubleshooting procedures for Raspberry Pi streaming in [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md).

### 3. Why it changed

- To decouple sensing location (Pi camera) from processing location (host machine), enabling practical deployment topology instead of laptop-attached cameras only.

### 4. What files matter most

- [app/camera/base.py](../app/camera/base.py)
- [app/camera/rtsp.py](../app/camera/rtsp.py)
- [app/main.py](../app/main.py)
- [app/config.py](../app/config.py)
- [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)
- [tests/test_camera_rtsp.py](../tests/test_camera_rtsp.py)

### 5. Useful code snippets

Snippet C1-1 from [app/main.py](../app/main.py)

~~~python
camera_type = config.CAMERA_TYPE.strip().lower()
log.info("Camera source: %s", camera_type)

if camera_type == "rtsp":
    if not config.RTSP_URL:
        log.error(
            "CAMERA_TYPE is 'rtsp' but SV_RTSP_URL is empty - "
            "set SV_RTSP_URL to the stream address and retry."
        )
        conn.close()
        return 1
    camera = RTSPCamera(config.RTSP_URL)
else:
    camera = WebcamCamera(device_index=config.CAMERA_INDEX)
~~~

Snippet C1-2 from [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)

~~~bash
# Start MediaMTX
./mediamtx &

# Stream Pi camera into RTSP endpoint
rpicam-vid -t 0 --width 640 --height 480 --framerate 15 --codec h264 \
  --inline -o - | ffmpeg -i - -c copy -f rtsp rtsp://localhost:8554/cam
~~~

Snippet C1-3 from [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)

~~~powershell
$env:SV_CAMERA_TYPE = "rtsp"
$env:SV_RTSP_URL = "rtsp://192.168.1.50:8554/cam"
python -m app.main
~~~

### 6. How to describe this in report language

- The camera subsystem was refactored behind a strict adapter interface so the core pipeline consumes frames identically regardless of local webcam or remote RTSP source.
- RTSP integration was implemented as an infrastructure extension, not a rewrite of ML/event logic: source switching is configuration-driven and runtime-safe.

### 7. Limitations and honest weaknesses

- SecureVision does not include its own RTSP server; Pi-side stream infrastructure is an external prerequisite.
- Current integration is single-stream oriented; no multi-camera scheduler is implemented.
- If RTSP source is selected without a valid URL, startup exits by design.

---

## C2. Empirical Evaluation: RTSP vs Webcam (Throughput, Read Cost, and Pipeline Impact)

### Technical evidence summary

Published comparison data:
- [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md) reports 60s runs at fixed 640x480 for both modes.
- Reported metrics include camera FPS, MJPEG stream FPS, frame read time, host pipeline latency, max latency, internal drops, and ML FPS.

Raw runtime evidence:
- RTSP run sample in [rtsp_test_log.txt](../rtsp_test_log.txt): line 92 shows DIAG FAST cam=19.9 fps then stabilizing around 15 fps; lines 345/422/500 remain near 15 fps with enc around 7.4-7.6 fps.
- Webcam run sample in [webcam_test_log.txt](../webcam_test_log.txt): lines 222/363/491 show cam near 30 fps, enc near 15 fps.

Host-vs-browser boundary:
- [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md) explicitly excludes browser-end user latency from core-engine benchmark.
- [docs/SETUP.md](../docs/SETUP.md) documents process split where app.main handles camera/ML and app.web_run handles dashboard/UI.

### 1. What existed before

- No structured quantitative webcam-vs-RTSP comparison was present before RTSP integration and diagnostics.

### 2. What changed

- Added explicit benchmark-style diagnostics and published comparison report.
- Added DIAG FAST/DIAG SLOW logs to observe camera ingest FPS and ML throughput under both sources.

### 3. Why it changed

- To verify whether deployment flexibility from RTSP was worth throughput and latency penalties relative to local webcam.

### 4. What files matter most

- [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)
- [rtsp_test_log.txt](../rtsp_test_log.txt)
- [webcam_test_log.txt](../webcam_test_log.txt)
- [docs/SETUP.md](../docs/SETUP.md)

### 5. Useful evidence snippets

Snippet C2-1 from [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)

~~~text
Avg Camera FPS: webcam 30.0 fps vs RTSP 15.0 fps
Avg Frame Read Time: webcam 27.4 ms vs RTSP 52.0 ms
Avg Pipeline Latency: webcam 53.4 ms vs RTSP 59.1 ms
Max Pipeline Latency: webcam 141.0 ms vs RTSP 266.0 ms
ML FPS: webcam 10.0 fps vs RTSP 5.0 fps
~~~

Snippet C2-2 from [rtsp_test_log.txt](../rtsp_test_log.txt) and [webcam_test_log.txt](../webcam_test_log.txt)

~~~text
rtsp_test_log.txt:92  [DIAG FAST] cam=19.9 fps (avg=41.6ms max=109.0ms) | enc=9.9 fps (avg=8 KB) | shm_w=50 skip=0 q_drop=4 | ml=0.0 fps
rtsp_test_log.txt:345 [DIAG FAST] cam=15.3 fps (avg=61.2ms max=141.0ms) | enc=7.5 fps (avg=13 KB) | shm_w=38 skip=0 q_drop=0 | ml=0.0 fps
webcam_test_log.txt:222 [DIAG FAST] cam=29.9 fps (avg=30.9ms max=94.0ms) | enc=15.0 fps (avg=17 KB) | shm_w=75 skip=0 q_drop=3 | ml=0.0 fps
webcam_test_log.txt:491 [DIAG FAST] cam=30.2 fps (avg=31.6ms max=63.0ms) | enc=15.2 fps (avg=19 KB) | shm_w=76 skip=0 q_drop=0 | ml=0.0 fps
~~~

Snippet C2-3 from [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)

~~~text
Stream (MJPEG) FPS and end-to-end user latency were excluded from this dataset,
as they are handled by the asynchronous dashboard web process (app.web_run).
~~~

### 6. How to describe this in report language

- RTSP delivered deployment decoupling at a measurable ingest cost: roughly half camera ingest rate and about double frame read blocking time versus local webcam under the same 640x480 test condition.
- Host-side post-ingest pipeline remained relatively efficient, but user-observed lag still depends strongly on network/decode stages outside host-only timestamps.

### 7. Limitations and honest weaknesses

- Evaluation was LAN-only and single-hardware; no WAN/cellular stress profile.
- Benchmark window was 60s and not a long-duration statistical campaign.
- Browser glass-to-glass latency was intentionally out of scope in the core comparison dataset.

---

## C3. FFmpeg Buffering Constraints and Why Latency Persists

### Technical evidence summary

Implemented mitigations:
- [app/camera/rtsp.py](../app/camera/rtsp.py) sets OPENCV_FFMPEG_CAPTURE_OPTIONS before opening VideoCapture.
- It explicitly requests cv2.CAP_FFMPEG backend and attempts CAP_PROP_BUFFERSIZE=1.

Constraint documentation:
- [app/camera/rtsp.py](../app/camera/rtsp.py) and [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md) both state these are hints, not guaranteed behavior.
- [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md) documents 0.3-1.5s typical LAN latency and notes that sub-100ms requires replacing VideoCapture backend (for example raw GStreamer path).

Test-backed conservative behavior:
- [tests/test_camera_rtsp.py](../tests/test_camera_rtsp.py) verifies CAP_PROP_BUFFERSIZE set attempt and non-crashing behavior when rejected.

### 1. What existed before

- Webcam path had no network demux/decode buffer chain and therefore no RTSP-specific FFmpeg tuning surface.

### 2. What changed

- RTSP path added explicit low-latency capture options and conservative buffering hints.

### 3. Why it changed

- To reduce buffered stale frames and improve freshness under network ingestion without replacing the capture stack.

### 4. What files matter most

- [app/camera/rtsp.py](../app/camera/rtsp.py)
- [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)
- [tests/test_camera_rtsp.py](../tests/test_camera_rtsp.py)

### 5. Useful code snippets

Snippet C3-1 from [app/camera/rtsp.py](../app/camera/rtsp.py)

~~~python
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
    "rtsp_transport;tcp|analyzeduration;0|probesize;32|"
    "fflags;nobuffer|flags;low_delay|framedrop;1"
)

self._cap = cv2.VideoCapture(self._url, cv2.CAP_FFMPEG)
result = self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
~~~

Snippet C3-2 from [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)

~~~text
CAP_PROP_BUFFERSIZE is only supported by certain OpenCV+FFmpeg build combinations.
If backend ignores it, setting is skipped.
To achieve sub-100ms latency, replace cv2.VideoCapture with lower-level pipeline.
~~~

Snippet C3-3 from [tests/test_camera_rtsp.py](../tests/test_camera_rtsp.py)

~~~python
mock_cap.set.return_value = False  # Backend rejects the hint
cam = RTSPCamera("rtsp://test")
self.assertTrue(cam.is_opened())
~~~

### 6. How to describe this in report language

- The project applies all practical low-latency controls available through OpenCV+FFmpeg, but architectural buffering in demux/decode and network transport still imposes residual delay that cannot be fully removed in this stack.
- Buffer hint rejection is treated as non-fatal by design, improving portability across different OpenCV builds.

### 7. Limitations and honest weaknesses

- Buffer controls are best-effort and backend-dependent.
- Mid-stream RTSP failures can still block read calls for timeout windows, reducing real-time responsiveness.
- True ultra-low-latency ingest is deferred to future backend replacement scope.

---

## C4. Low-Latency Optimization Attempts: What Worked and What Failed

### Technical evidence summary

Documented failed attempt:
- [reports/live_stream_optimization_report.md](live_stream_optimization_report.md) states that replacing disk handoff with shared memory stopped file-lock crashes but did not fix lag by itself.

Documented successful architecture pivot:
- Same report plus current [app/main.py](../app/main.py) show producer-consumer split with bounded queue and independent slow ML thread.

Additional RTSP-side tuning attempts:
- [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md) and [app/camera/rtsp.py](../app/camera/rtsp.py) show FFmpeg low-delay flags and CAP_PROP_BUFFERSIZE hint.
- [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md) reports an aggressive profile with reduced cooldown and reduced deadzone; it increased responsiveness but increased oscillation risk.

### 1. What existed before

- Historical design relied on tighter coupling between frame publication timing and heavy processing, creating starvation effects in practical runs.

### 2. What changed

- Fast camera/publish loop and slow ML/event loop were separated.
- Queue was bounded to size 1 to drop stale work instead of accumulating delay.
- Shared memory publication became sequence-based and timestamped for freshness diagnostics.

### 3. Why it changed

- The bottleneck was not only transport medium, but scheduling and blocking behavior in the frame-critical path.

### 4. What files matter most

- [reports/live_stream_optimization_report.md](live_stream_optimization_report.md)
- [app/main.py](../app/main.py)
- [app/web/routes.py](../app/web/routes.py)
- [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)
- [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md)

### 5. Useful code snippets

Snippet C4-1 from [app/main.py](../app/main.py)

~~~python
frame_queue: queue.Queue = queue.Queue(maxsize=1)

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
        servo_controller,
        log,
    ),
    daemon=True,
    name="sv-processing",
)
processing_thread.start()
~~~

Snippet C4-2 from [reports/live_stream_optimization_report.md](live_stream_optimization_report.md)

~~~text
The crashes stopped, but the lag persisted (~1 FPS).
Removing SSD write eliminated file-lock crashes, but not framerate issue.
Root cause was synchronous thread starvation.
~~~

Snippet C4-3 from [app/web/routes.py](../app/web/routes.py)

~~~python
latency = (time.monotonic() - cap_ts) * 1000.0
if latency > 0:
    total_latency += latency
    if latency > max_latency:
        max_latency = latency
~~~

### 6. How to describe this in report language

- The optimization journey shows a key engineering lesson: medium-level optimization (disk to RAM) reduced failure modes, but only scheduler-level redesign (thread decoupling plus bounded queues) addressed sustained freshness.
- Latency diagnostics were embedded directly in the serving path to verify that improvements reflected actual frame freshness rather than just process-level throughput.

### 7. Limitations and honest weaknesses

- Some optimization history is report-based because interim code states are no longer in active files.
- Aggressive tuning profiles can improve response but may reduce control stability (reported oscillation risk in servo extension).
- Flask/browser rendering remains a separate layer with its own bottlenecks beyond ingest-thread optimization.

---

## C5. Resolution/FPS Trade-offs, Cadence Controls, and Their Surveillance Impact

### Technical evidence summary

Documented operating point:
- [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md) recommends 640x480 at 15 fps for latency and compatibility balance.
- It explicitly states higher resolutions (720p/1080p) increase latency and network load.

Runtime cadence controls:
- [app/config.py](../app/config.py): SV_PROCESS_EVERY_N_FRAMES default 3 and SV_LIVE_VIEW_EVERY_N_FRAMES default 2.
- [app/main.py](../app/main.py): ML queue feed is decimated by PROCESS_EVERY_N_FRAMES; live publish is decimated by LIVE_VIEW_EVERY_N_FRAMES.

Observed effect in logs and report:
- [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md) explains stream FPS approximately halves due to LIVE_VIEW_EVERY_N_FRAMES=2 and ML throughput aligns with 1/3 cadence at PROCESS_EVERY_N_FRAMES=3.
- Raw logs in [webcam_test_log.txt](../webcam_test_log.txt) and [rtsp_test_log.txt](../rtsp_test_log.txt) show this ratio in practice (about 30->15 and about 15->7.5).

Known weakness from cadence decimation:
- [docs/VALIDATION_REPORT.md](../docs/VALIDATION_REPORT.md) states PROCESS_EVERY_N_FRAMES creates blind spots for face movement between processed frames.

### 1. What existed before

- Earlier iterations had less explicit articulation of cadence-vs-latency trade-offs; current config makes this tunable and explicit.

### 2. What changed

- Added explicit frame-skipping controls for both ML and live-view publish cadence.
- Standardized deployment recommendation for RTSP resolution/fps baseline.

### 3. Why it changed

- To keep total system responsive under CPU and network constraints while preserving acceptable detection capability for surveillance use.

### 4. What files matter most

- [app/config.py](../app/config.py)
- [app/main.py](../app/main.py)
- [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)
- [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)
- [docs/VALIDATION_REPORT.md](../docs/VALIDATION_REPORT.md)
- [webcam_test_log.txt](../webcam_test_log.txt)
- [rtsp_test_log.txt](../rtsp_test_log.txt)

### 5. Useful code snippets

Snippet C5-1 from [app/config.py](../app/config.py)

~~~python
PROCESS_EVERY_N_FRAMES: int = _env_int("SV_PROCESS_EVERY_N_FRAMES", 3)
LIVE_VIEW_EVERY_N_FRAMES: int = _env_int("SV_LIVE_VIEW_EVERY_N_FRAMES", 2)
~~~

Snippet C5-2 from [app/main.py](../app/main.py)

~~~python
if frame_counter % config.PROCESS_EVERY_N_FRAMES == 0:
    try:
        frame_queue.put_nowait(frame.copy())
    except queue.Full:
        fast_diag.tick_queue_drop()

if config.LIVE_VIEW_ENABLED and live_shm is not None:
    if frame_counter % config.LIVE_VIEW_EVERY_N_FRAMES == 0:
        success, buffer = cv2.imencode(
            '.jpg', display_frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), 65]
        )
~~~

Snippet C5-3 from [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)

~~~text
Recommended: 640x480, 15 fps, H.264, TCP transport.
Higher resolutions increase latency and network load.
~~~

### 6. How to describe this in report language

- The system intentionally trades temporal granularity for stability: ML and browser publication are decimated to cap compute/network load and prevent backlog growth.
- 640x480 at 15 fps is the chosen deployment compromise because it keeps RTSP ingest feasible while still supporting face detection requirements.

### 7. Limitations and honest weaknesses

- Frame decimation introduces genuine blind spots for short-lived or rapid movements.
- RTSP mode compounds these blind spots with network/decode delay, which may reduce operator-perceived immediacy.
- Configuration values are global; no adaptive runtime controller currently tunes cadence based on observed load.

---

## Cross-cutting note: Host ingest/ML vs browser preview path

This distinction should be explicit in the final write-up:
- Host ingest and ML occur in app.main using camera adapters, queue decimation, and event pipeline.
- Browser preview is served through app.web_run/app.web routes using shared memory reads and MJPEG response generation.
- Therefore, any host-only metric (camera read ms, DIAG FAST/DIAG SLOW) is not equivalent to end-user glass-to-glass latency in browser playback.

Primary evidence:
- [docs/SETUP.md](../docs/SETUP.md)
- [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)
- [app/web/routes.py](../app/web/routes.py)
- [tests/test_dashboard.py](../tests/test_dashboard.py)
