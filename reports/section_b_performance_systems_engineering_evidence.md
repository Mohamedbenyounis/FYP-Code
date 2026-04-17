# Section B — Performance and Systems Engineering

This is source material for writing the report, not the final polished section.

Evidence source set used for this pack:
- [app/main.py](../app/main.py)
- [app/web/routes.py](../app/web/routes.py)
- [app/web/templates/dashboard.html](../app/web/templates/dashboard.html)
- [app/web_run.py](../app/web_run.py)
- [app/config.py](../app/config.py)
- [app/camera/base.py](../app/camera/base.py)
- [app/camera/webcam.py](../app/camera/webcam.py)
- [app/camera/rtsp.py](../app/camera/rtsp.py)
- [app/web/app_factory.py](../app/web/app_factory.py)
- [tests/test_dashboard.py](../tests/test_dashboard.py)
- [tests/test_main_loop.py](../tests/test_main_loop.py)
- [tests/test_camera_rtsp.py](../tests/test_camera_rtsp.py)
- [docs/BUILD_LOG.md](../docs/BUILD_LOG.md)
- [docs/DASHBOARD_UI_LOG.md](../docs/DASHBOARD_UI_LOG.md)
- [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)
- [docs/VALIDATION_REPORT.md](../docs/VALIDATION_REPORT.md)
- [reports/live_stream_optimization_report.md](live_stream_optimization_report.md)
- [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)
- [new_webcam_main.txt](../new_webcam_main.txt)
- [new_rtsp_main.txt](../new_rtsp_main.txt)
- [new_rtsp_mjpeg.txt](../new_rtsp_mjpeg.txt)
- [webcam_test_log.txt](../webcam_test_log.txt)
- [rtsp_test_log.txt](../rtsp_test_log.txt)

Evidence reliability rule used:
- Current code is ground truth for current behavior.
- Historical behavior (disk handoff, earlier pipeline) is taken from docs and report logs because old code paths are no longer present in active files.
- If a claim cannot be verified directly, it is marked as uncertain.

---

## B1. Live Stream Latency Debugging and Root Cause Analysis

### Technical evidence summary

Original symptom (documented):
- Dashboard live stream felt very laggy, reported around 1 FPS, while native OpenCV preview was significantly faster.
- Source artifact: [reports/live_stream_optimization_report.md](live_stream_optimization_report.md).

System behavior during issue period (documented historical state):
- Process A wrote latest_frame.jpg periodically from pipeline process.
- Process B (Flask) polled and streamed frame resource to browser.
- Source artifacts: [docs/BUILD_LOG.md](../docs/BUILD_LOG.md), [docs/DASHBOARD_UI_LOG.md](../docs/DASHBOARD_UI_LOG.md), [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md), [reports/live_stream_optimization_report.md](live_stream_optimization_report.md).

How investigation evolved:
- First suspected disk I/O and file-lock contention.
- Shared memory replaced file transport and eliminated file lock crashes.
- Lag persisted, so disk transport was not the dominant cause.
- Final diagnosis: synchronous frame-loop starvation from heavy per-frame tasks.
- Source artifact: [reports/live_stream_optimization_report.md](live_stream_optimization_report.md).

Observed post-fix evidence from log artifacts:
- Webcam runs show FAST camera around 27-30 FPS, SLOW ML around 5.5-10 FPS.
- RTSP runs show FAST camera around 14.6-15.4 FPS, SLOW ML around 4.6-5.4 FPS.
- Files: [new_webcam_main.txt](../new_webcam_main.txt), [new_rtsp_main.txt](../new_rtsp_main.txt), [webcam_test_log.txt](../webcam_test_log.txt), [rtsp_test_log.txt](../rtsp_test_log.txt).

### 1. What existed before

- Historical design documents describe a disk-file handoff and near-live polling flow.
- Main loop was effectively synchronous before threaded split according to optimization report.
- Exact pre-refactor code version is not present in current app/main.py, so this part is reconstructed from logs/docs.

### 2. What changed

- Runtime changed to a FAST producer loop and SLOW consumer thread model in [app/main.py](../app/main.py).
- Frame transport switched to shared memory buffer named sv_live_frame.
- Web streaming endpoint reads from shared memory and reports MJPEG diagnostics in [app/web/routes.py](../app/web/routes.py).

### 3. Why it changed

- To remove blocking ML, DB, alert, and clip tasks from camera refresh cadence.
- To keep browser stream fresh while preserving existing processing features.

### 4. What files matter most

- [reports/live_stream_optimization_report.md](live_stream_optimization_report.md)
- [app/main.py](../app/main.py)
- [app/web/routes.py](../app/web/routes.py)
- [new_webcam_main.txt](../new_webcam_main.txt)
- [new_rtsp_main.txt](../new_rtsp_main.txt)
- [new_rtsp_mjpeg.txt](../new_rtsp_mjpeg.txt)

### 5. Useful code snippets

Snippet B1-1 from [app/main.py](../app/main.py)

~~~python
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

Snippet B1-2 from [app/main.py](../app/main.py)

~~~python
if frame_counter % config.PROCESS_EVERY_N_FRAMES == 0:
    try:
        frame_queue.put_nowait(frame.copy())
    except queue.Full:
        fast_diag.tick_queue_drop()
~~~

Snippet B1-3 from [app/main.py](../app/main.py)

~~~python
except Exception as e:
    log.error(
        "Error processing frame in background thread: %s\n%s",
        str(e),
        traceback.format_exc(),
    )
    continue
~~~

### 6. How to describe this in report language

- The latency issue was not solved by changing transport medium alone. Shared memory reduced file-lock failure modes, but throughput remained limited until the runtime was restructured around producer-consumer threading.
- The final root cause was loop starvation: camera ingestion waited on computational and I/O-heavy steps that should not have been in the frame-critical path.

### 7. Limitations and honest weaknesses

- Pre-fix source code is not available in current branch for line-by-line comparison; historical diagnosis is document-backed, not code-diff-backed.
- Measured logs are experimental artifacts, not formal benchmark harness output with controlled statistical methodology.

---

## B2. Disk I/O vs Shared Memory Frame Transport Evaluation

### Technical evidence summary

Original transport model (historical):
- docs/build log and dashboard log describe writing latest_frame.jpg and browser polling.
- Files: [docs/BUILD_LOG.md](../docs/BUILD_LOG.md), [docs/DASHBOARD_UI_LOG.md](../docs/DASHBOARD_UI_LOG.md), [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).

Current transport model (code):
- Main process writes encoded JPEG payload into shared memory with metadata header.
- Dashboard endpoints read from shared memory directly.
- Files: [app/main.py](../app/main.py), [app/web/routes.py](../app/web/routes.py).

What improved:
- Removed file overwrite/read contention class from hot path.
- Transport serialization became in-memory byte copy, not file-write/file-read.

What did not improve by itself:
- According to optimization report, lag persisted until threading changes; transport replacement alone was insufficient.

### 1. What existed before

- Historical file-based handoff latest_frame.jpg with cache-busting/polling pattern.
- Not present in active code paths now.

### 2. What changed

- Shared memory layout introduced:
  - lock flag
  - payload size
  - sequence number
  - capture timestamp
  - JPEG bytes
- live/frame and live/stream route logic now map to shared memory reads.

### 3. Why it changed

- Avoid disk I/O and Windows file lock conflicts.
- Reduce transport overhead and enable cross-process zero-file handoff.

### 4. What files matter most

- [app/main.py](../app/main.py)
- [app/web/routes.py](../app/web/routes.py)
- [docs/DASHBOARD_UI_LOG.md](../docs/DASHBOARD_UI_LOG.md)
- [docs/BUILD_LOG.md](../docs/BUILD_LOG.md)
- [reports/live_stream_optimization_report.md](live_stream_optimization_report.md)
- [tests/test_dashboard.py](../tests/test_dashboard.py)

### 5. Useful code snippets

Snippet B2-1 from [app/main.py](../app/main.py)

~~~python
SHM_HEADER_SIZE = 17
SHM_TOTAL_SIZE = 2 * 1024 * 1024

live_shm = shared_memory.SharedMemory(
    name="sv_live_frame", create=True, size=SHM_TOTAL_SIZE
)
live_shm.buf[0] = 0
live_shm.buf[1:5] = (0).to_bytes(4, 'little')
live_shm.buf[5:9] = (0).to_bytes(4, 'little')
live_shm.buf[9:17] = (0).to_bytes(8, 'little')
~~~

Snippet B2-2 from [app/main.py](../app/main.py)

~~~python
if size < SHM_TOTAL_SIZE - SHM_HEADER_SIZE:
    live_shm.buf[0] = 1
    live_shm.buf[1:5] = size.to_bytes(4, 'little')
    live_shm.buf[5:9] = (shm_seq & 0xFFFFFFFF).to_bytes(4, 'little')
    live_shm.buf[9:17] = struct.pack('<d', t_read_start)
    live_shm.buf[SHM_HEADER_SIZE:SHM_HEADER_SIZE+size] = payload
    live_shm.buf[0] = 0
~~~

Snippet B2-3 from [app/web/routes.py](../app/web/routes.py)

~~~python
try:
    shm = shared_memory.SharedMemory(name="sv_live_frame")
except FileNotFoundError:
    abort(503, "Camera pipeline not running")

if shm.buf[0] == 0:
    size = int.from_bytes(shm.buf[1:5], 'little')
    frame_data = bytes(shm.buf[SHM_HEADER:SHM_HEADER+size])
~~~

### 6. How to describe this in report language

- The transport layer evolved from filesystem polling to shared-memory byte transport. This removed a class of file-contention faults and reduced handoff overhead, but it did not fully solve latency until scheduling architecture was also refactored.

### 7. Limitations and honest weaknesses

- Shared memory size is fixed at 2 MB; oversized JPEG payloads are skipped.
- Transport is local-host only and process-coupled; not suitable for multi-host distribution.
- No ring buffer history in shared memory: latest-frame semantics only.
- Comment drift exists: header comment text says 9-byte header while implementation actually uses 17 bytes.

---

## B3. Producer-Consumer Multithreading Refactor

### Technical evidence summary

Original behavior (historical diagnosis):
- Frame loop had heavy tasks in the same cadence path.
- Tasks included ML inference, DB writes, clip recording, alert dispatch, and frame publishing.
- Source: [reports/live_stream_optimization_report.md](live_stream_optimization_report.md).

Refactor design (current code):
- FAST thread in main loop handles camera read, drawing overlays, and stream publish.
- SLOW daemon thread handles process_frame plus event/DB/alerts/recording side effects.
- Queue maxsize=1 with non-blocking put_nowait enforces freshness.

Measured impact from log artifacts:
- Webcam: FAST camera around 27-30 FPS with ENCODE around 13-15 FPS, SLOW ML around 5.5-10 FPS.
- RTSP: FAST camera around 14.6-15.4 FPS with ENCODE around 7.3-7.6 FPS, SLOW ML around 4.6-5.4 FPS.
- Files: [new_webcam_main.txt](../new_webcam_main.txt), [new_rtsp_main.txt](../new_rtsp_main.txt), [webcam_test_log.txt](../webcam_test_log.txt), [rtsp_test_log.txt](../rtsp_test_log.txt).

### 1. What existed before

- Single-loop behavior documented historically, with heavy path operations contributing to camera starvation.

### 2. What changed

- Added _processing_loop background worker.
- Added bounded frame queue with drop-on-full behavior.
- Added overlay handoff by atomic reference swap.
- Added clip_lock for shared clip recorder access from both loop contexts.

### 3. Why it changed

- Isolate frame-critical responsibilities from expensive compute and I/O.
- Maintain responsive live stream while preserving eventing/recording/alerts.

### 4. What files matter most

- [app/main.py](../app/main.py)
- [tests/test_main_loop.py](../tests/test_main_loop.py)
- [reports/live_stream_optimization_report.md](live_stream_optimization_report.md)
- [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)

### 5. Useful code snippets

Snippet B3-1 from [app/main.py](../app/main.py)

~~~python
frame_queue: queue.Queue = queue.Queue(maxsize=1)

processing_thread = threading.Thread(
    target=_processing_loop,
    args=(..., clip_lock, alert_service, servo_controller, log),
    daemon=True,
    name="sv-processing",
)
~~~

Snippet B3-2 from [app/main.py](../app/main.py)

~~~python
# fast thread
if frame_counter % config.PROCESS_EVERY_N_FRAMES == 0:
    try:
        frame_queue.put_nowait(frame.copy())
    except queue.Full:
        fast_diag.tick_queue_drop()
~~~

Snippet B3-3 from [app/main.py](../app/main.py)

~~~python
# slow thread
frame = frame_queue.get(timeout=2.0)
result = pipeline.process_frame(frame)
events = event_manager.update(per_face_obs)
for event in events:
    event_repo.add_event(event)
~~~

### 6. How to describe this in report language

- A producer-consumer split was used to decouple acquisition-rate concerns from inference and persistence workloads.
- The design intentionally allows dropping stale frames in favor of preserving user-visible responsiveness and reducing feedback lag.

### 7. Limitations and honest weaknesses

- Shared SQLite connection is accessed in a multi-threaded runtime; while configured with check_same_thread disabled, this still has contention risk under heavier concurrency.
- Python threading and GIL limit CPU-bound parallelism; refactor improves scheduling isolation more than true parallel compute throughput.
- queue maxsize=1 can hide bursts by dropping intermediate context.
- Existing test coverage verifies queue-full behavior and live/frame endpoint, but does not deeply load-test multi-client streaming under stress.

---

## B4. MJPEG Streaming Bottleneck Analysis

### Technical evidence summary

Browser/dashboard stream path (current):
- Dashboard template uses img source bound to /live/stream.
- Route live_stream in Flask opens shared memory and yields multipart JPEG chunks.
- Generator loops every ~40 ms and emits only when sequence number changes.
- Files: [app/web/templates/dashboard.html](../app/web/templates/dashboard.html), [app/web/routes.py](../app/web/routes.py).

What was tested and observed:
- MJPEG diagnostics in [new_rtsp_mjpeg.txt](../new_rtsp_mjpeg.txt) show yield around 6.6-7.8 FPS, stale counts around 65-86, zero errors.
- Simultaneous FAST diagnostics in RTSP logs show encode around 7.3-7.6 FPS.
- This close match suggests the stream yield rate is often upstream-limited by producer update rate, not only by Flask generator overhead.

Where bottleneck appears to be:
- In RTSP runs, update cadence from producer is roughly half camera FPS due to LIVE_VIEW_EVERY_N_FRAMES=2, and camera itself is around 15 FPS.
- MJPEG stream tracks this and sits around 7 FPS.
- Therefore, dominant bottleneck in those captures is production cadence plus RTSP ingest/decode cost, not hard MJPEG transport failure.

What remains limited even after fixes:
- Flask dev server and per-client generator model are not optimized for large concurrent audiences.
- sleep(0.04) poll loop and Python-level byte handling add overhead.
- No adaptive pacing based on producer cadence.

### 1. What existed before

- Historical docs reference JS polling over latest_frame.jpg for near-live UI.
- Current code has moved to multipart MJPEG stream endpoint plus one-shot frame endpoint.

### 2. What changed

- Added /live/stream generator reading shared memory and yielding multipart MJPEG.
- Added DIAG MJPEG logging for yield/stale/error/latency metrics.

### 3. Why it changed

- To avoid repeated browser fetch loops and enable continuous stream delivery semantics.
- To instrument stream freshness and detect whether producer or consumer side is limiting.

### 4. What files matter most

- [app/web/routes.py](../app/web/routes.py)
- [app/web/templates/dashboard.html](../app/web/templates/dashboard.html)
- [new_rtsp_mjpeg.txt](../new_rtsp_mjpeg.txt)
- [new_rtsp_main.txt](../new_rtsp_main.txt)
- [reports/live_stream_optimization_report.md](live_stream_optimization_report.md)

### 5. Useful code snippets

Snippet B4-1 from [app/web/templates/dashboard.html](../app/web/templates/dashboard.html)

~~~html
<div class="video-container">
  <img src="{{ url_for('web.live_stream') }}" alt="Live camera feed">
</div>
~~~

Snippet B4-2 from [app/web/routes.py](../app/web/routes.py)

~~~python
if shm.buf[0] == 0:
    size = int.from_bytes(shm.buf[1:5], 'little')
    seq = int.from_bytes(shm.buf[5:9], 'little')
    if seq != last_seq:
        last_seq = seq
        frame_data = bytes(shm.buf[SHM_HEADER:SHM_HEADER+size])
        yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
~~~

Snippet B4-3 from [app/web/routes.py](../app/web/routes.py)

~~~python
if now - diag_t0 >= DIAG_INTERVAL:
    stream_log.info(
        "[DIAG MJPEG] yield=%.1f fps | stale=%d | err=%d | "
        "lat_avg=%.1fms lat_max=%.1fms | last_seq=%d",
        yfps, stale_count, error_count, avg_lat, max_latency, last_seq,
    )

time.sleep(0.04)
~~~

### 6. How to describe this in report language

- The MJPEG path was instrumented to distinguish transport bottlenecks from producer starvation.
- In captured RTSP runs, yield throughput closely followed producer publish cadence, indicating that the stream endpoint itself was not the sole limiting component.

### 7. Limitations and honest weaknesses

- No dedicated tests for /live/stream route behavior under concurrent clients.
- Flask development server warning indicates non-production serving stack.
- MJPEG is bandwidth-heavy and not as efficient as codecs with inter-frame compression for network delivery.
- Some docs still describe earlier latest_frame.jpg polling model, creating architectural documentation drift.

---

## B5. End-to-End Streaming Diagnostics and Instrumentation

### Technical evidence summary

Diagnostics added in main runtime:
- _StreamDiag class tracks camera read timing, encode frequency, write skips, queue drops, and ML rate.
- Labels FAST and SLOW provide split-path visibility.
- File: [app/main.py](../app/main.py).

Diagnostics added in MJPEG route:
- live_stream generator tracks yield FPS, stale polls, exceptions, sequence progression, and latency based on shared-memory timestamp.
- File: [app/web/routes.py](../app/web/routes.py).

Shared memory header semantics used for diagnostics:
- Byte 0 lock flag.
- Bytes 1-4 payload size.
- Bytes 5-8 sequence number.
- Bytes 9-16 capture timestamp.
- Bytes 17+ payload.
- Files: [app/main.py](../app/main.py), [app/web/routes.py](../app/web/routes.py).

Observed diagnostic patterns (sample artifacts):
- RTSP FAST around 15 FPS, ENCODE around 7.4 FPS, SLOW ML around 5 FPS.
- MJPEG yield around 7.0-7.8 FPS with stale counts around 70-85 per interval and lat_avg around 78-95 ms.
- Files: [new_rtsp_main.txt](../new_rtsp_main.txt), [new_rtsp_mjpeg.txt](../new_rtsp_mjpeg.txt), [rtsp_test_log.txt](../rtsp_test_log.txt).

### 1. What existed before

- Earlier dashboard iteration logs focused on near-live frame polling behavior and did not show this full split diagnostic suite.

### 2. What changed

- Added structured periodic DIAG FAST and DIAG SLOW reporting.
- Added DIAG MJPEG reporting with sequence-aware freshness and latency metrics.
- Added capture timestamp in shared-memory header specifically for end-to-end age estimation.

### 3. Why it changed

- Needed objective observability to avoid guessing about whether producer, consumer, transport, or rendering was limiting.
- Enabled root-cause discrimination between stale source and slow stream consumer.

### 4. What files matter most

- [app/main.py](../app/main.py)
- [app/web/routes.py](../app/web/routes.py)
- [new_webcam_main.txt](../new_webcam_main.txt)
- [new_rtsp_main.txt](../new_rtsp_main.txt)
- [new_rtsp_mjpeg.txt](../new_rtsp_mjpeg.txt)
- [webcam_test_log.txt](../webcam_test_log.txt)
- [rtsp_test_log.txt](../rtsp_test_log.txt)
- [reports/live_stream_optimization_report.md](live_stream_optimization_report.md)

### 5. Useful code snippets

Snippet B5-1 from [app/main.py](../app/main.py)

~~~python
log.info(
    "[DIAG %s] cam=%.1f fps (avg=%.1fms max=%.1fms) | "
    "enc=%.1f fps (avg=%.0f KB) | shm_w=%d skip=%d q_drop=%d | ml=%.1f fps",
    self.label, cam_fps, cam_avg, cam_max,
    enc_fps, avg_kb, self.shm_writes, self.shm_skips, self.queue_drops, ml_fps,
)
~~~

Snippet B5-2 from [app/main.py](../app/main.py)

~~~python
live_shm.buf[5:9] = (shm_seq & 0xFFFFFFFF).to_bytes(4, 'little')
live_shm.buf[9:17] = struct.pack('<d', t_read_start)
~~~

Snippet B5-3 from [app/web/routes.py](../app/web/routes.py)

~~~python
cap_ts = struct.unpack('<d', shm.buf[9:17])[0]
latency = (time.monotonic() - cap_ts) * 1000.0
if latency > 0:
    total_latency += latency
~~~

### 6. How to describe this in report language

- Instrumentation was elevated from ad hoc prints to a repeatable metric vocabulary across producer, consumer, and stream delivery paths.
- Sequence-number and timestamp headers allowed objective freshness and delay analysis rather than visual estimates.

### 7. Limitations and honest weaknesses

- Diagnostics are periodic summaries, not persisted time-series telemetry.
- No automatic threshold-based alerting on DIAG anomalies.
- Logs can be noisy and currently require manual interpretation.
- Some naming/comments have minor drift (for example header-size comment mismatch), increasing risk of misunderstanding.

---

## B6. Frame Freshness vs Throughput Trade-off

### Technical evidence summary

Freshness-first design choices in current code:
- Queue maxsize=1 for slow pipeline input.
- Non-blocking enqueue with drop on queue full.
- ML executes every PROCESS_EVERY_N_FRAMES.
- Stream publish executes every LIVE_VIEW_EVERY_N_FRAMES.
- MJPEG generator only yields when sequence changes and tracks stale poll counts.

Why this favors freshness over completeness:
- Prevents backlog accumulation where UI would display old frames.
- Keeps operator view near-present even when inference cannot keep pace with camera source.

Observed behavior confirming the trade-off:
- q_drop non-zero appears in webcam and RTSP logs, proving intentional discard under pressure.
- MJPEG stale counts high while errors remain zero, indicating consumer polls often but intentionally waits for newer producer frames.
- Files: [new_webcam_main.txt](../new_webcam_main.txt), [new_rtsp_main.txt](../new_rtsp_main.txt), [new_rtsp_mjpeg.txt](../new_rtsp_mjpeg.txt), [webcam_test_log.txt](../webcam_test_log.txt), [rtsp_test_log.txt](../rtsp_test_log.txt).

Validation-side risk evidence:
- docs validation report explicitly calls out blind spots from PROCESS_EVERY_N_FRAMES.
- File: [docs/VALIDATION_REPORT.md](../docs/VALIDATION_REPORT.md).

### 1. What existed before

- Historical flow did not expose this explicit freshness policy as clearly and suffered from perceived lag when heavy work blocked frame progression.

### 2. What changed

- Introduced bounded queue and drop policy.
- Added configurable decimation knobs for ML and live streaming rates.
- Added sequence-aware stream delivery and stale metric tracking.

### 3. Why it changed

- Security operator experience prioritizes current scene awareness over preserving every intermediate frame in UI path.
- Prevents stale-data amplification when compute path slows down.

### 4. What files matter most

- [app/main.py](../app/main.py)
- [app/config.py](../app/config.py)
- [app/web/routes.py](../app/web/routes.py)
- [docs/VALIDATION_REPORT.md](../docs/VALIDATION_REPORT.md)
- [tests/test_main_loop.py](../tests/test_main_loop.py)
- [new_webcam_main.txt](../new_webcam_main.txt)
- [new_rtsp_main.txt](../new_rtsp_main.txt)

### 5. Useful code snippets

Snippet B6-1 from [app/config.py](../app/config.py)

~~~python
PROCESS_EVERY_N_FRAMES: int = _env_int("SV_PROCESS_EVERY_N_FRAMES", 3)
LIVE_VIEW_EVERY_N_FRAMES: int = _env_int("SV_LIVE_VIEW_EVERY_N_FRAMES", 2)
~~~

Snippet B6-2 from [app/main.py](../app/main.py)

~~~python
frame_queue: queue.Queue = queue.Queue(maxsize=1)

if frame_counter % config.PROCESS_EVERY_N_FRAMES == 0:
    try:
        frame_queue.put_nowait(frame.copy())
    except queue.Full:
        fast_diag.tick_queue_drop()
~~~

Snippet B6-3 from [app/web/routes.py](../app/web/routes.py)

~~~python
if seq != last_seq:
    last_seq = seq
    yield (...frame_data...)
else:
    stale_count += 1
~~~

### 6. How to describe this in report language

- The system intentionally trades frame completeness for temporal relevance. It drops stale intermediate frames to keep output close to real time under variable computational load.
- This strategy is explicit in both ingestion and streaming paths and is measurable through queue-drop and stale-poll diagnostics.

### 7. Limitations and honest weaknesses

- Brief events can be missed between sampled frames.
- Lower event recall risk exists under high motion and high load.
- Deterministic forensic replay from live path is not possible because not every frame is retained.
- Requires careful parameter tuning for each deployment context.

---

## Explicit unknowns and non-hallucination notes

- Exact pre-refactor code snapshots for disk-only handoff are not available in current active files; historical behavior is reconstructed from docs and reports.
- Multi-client MJPEG scalability limits were not directly benchmarked in provided artifacts.
- No dedicated automated tests were found for /live/stream generator correctness under concurrent clients; current tests focus on /live/frame and related dashboard routes.
