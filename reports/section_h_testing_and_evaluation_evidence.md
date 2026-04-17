# Section H - Testing and Evaluation

This is source material for writing the report, not the final polished section.

Evidence source set used for this pack:
- [app/main.py](../app/main.py)
- [app/web/routes.py](../app/web/routes.py)
- [app/services/logging_service.py](../app/services/logging_service.py)
- [app/camera/rtsp.py](../app/camera/rtsp.py)
- [app/camera/webcam.py](../app/camera/webcam.py)
- [app/config.py](../app/config.py)
- [app/services/servo_service.py](../app/services/servo_service.py)
- [tests/test_main_loop.py](../tests/test_main_loop.py)
- [tests/test_camera_rtsp.py](../tests/test_camera_rtsp.py)
- [tests/test_camera_webcam.py](../tests/test_camera_webcam.py)
- [tests/test_hardware_resilience.py](../tests/test_hardware_resilience.py)
- [tests/test_dashboard.py](../tests/test_dashboard.py)
- [tests/test_servo_logic.py](../tests/test_servo_logic.py)
- [docs/VALIDATION_REPORT.md](../docs/VALIDATION_REPORT.md)
- [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)
- [docs/BUILD_LOG.md](../docs/BUILD_LOG.md)
- [docs/DASHBOARD_UI_LOG.md](../docs/DASHBOARD_UI_LOG.md)
- [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)
- [reports/live_stream_optimization_report.md](live_stream_optimization_report.md)
- [reports/iteration_9_11_evaluation.md](iteration_9_11_evaluation.md)
- [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md)
- [new_rtsp_main.txt](../new_rtsp_main.txt)
- [new_rtsp_mjpeg.txt](../new_rtsp_mjpeg.txt)
- [new_webcam_main.txt](../new_webcam_main.txt)
- [new_webcam_mjpeg.txt](../new_webcam_mjpeg.txt)
- [test_errors_ascii.txt](../test_errors_ascii.txt)

Evidence reliability rule used:
- Current code is ground truth for current behavior.
- Empirical behavior is reconstructed from runtime logs and evaluation reports.
- Historical failures are reconstructed from debug artifacts and build/evaluation logs.
- Any statement not explicit in code/docs/logs is marked as INFERENCE.

---

## H1. System-Wide Performance Benchmarking Framework

### Technical evidence summary

There is integrated runtime instrumentation, but no standalone benchmark harness in the current main branch.

Instrumentation present in code:
- Core engine diagnostics in a reusable helper class: [app/main.py](../app/main.py) lines 84-142.
- Shared-memory stream diagnostics in dashboard generator: [app/web/routes.py](../app/web/routes.py) lines 245-323.
- Shared-memory freshness metadata (sequence + capture timestamp): [app/main.py](../app/main.py) lines 72-77 and [app/main.py](../app/main.py) line 608.

Evidence of no formal benchmark runner:
- Evaluation report explicitly states correctness-focused testing and no full-system benchmark: [reports/iteration_9_11_evaluation.md](iteration_9_11_evaluation.md) line 23.
- Explicit note that app.benchmark_run does not exist on current main: [reports/iteration_9_11_evaluation.md](iteration_9_11_evaluation.md) line 25.
- No runnable source benchmark script is present in the current tree (app.benchmark_run source is absent). Benchmark references appear in documentation and historical bytecode artifacts (for example [app/__pycache__](../app/__pycache__)).

### 1. What existed before

- Historical system appears to rely on ad hoc/manual observation and per-iteration test runs.
- INFERENCE: Early iterations had limited formalized performance telemetry because newer diagnostics are described as temporary/additive instrumentation in current code and optimization report.

### 2. What changed

- Added continuous periodic diagnostics across fast and slow execution paths.
- Added stream-level diagnostic channel with latency and stale-frame counters.
- Added sequence+timestamp metadata in shared memory for measurable freshness/age analysis.

### 3. Why it changed

- To diagnose severe live-stream lag and differentiate camera bottlenecks from web-serving bottlenecks.
- This is explicitly described in optimization report debugging narrative: [reports/live_stream_optimization_report.md](live_stream_optimization_report.md) lines 27, 76-87.

### 4. What files matter most

- [app/main.py](../app/main.py)
- [app/web/routes.py](../app/web/routes.py)
- [app/services/logging_service.py](../app/services/logging_service.py)
- [reports/live_stream_optimization_report.md](live_stream_optimization_report.md)
- [reports/iteration_9_11_evaluation.md](iteration_9_11_evaluation.md)

### 5. Useful snippets

Snippet H1-1 from [app/main.py](../app/main.py)

~~~python
log.info(
    "[DIAG %s] cam=%.1f fps (avg=%.1fms max=%.1fms) | "
    "enc=%.1f fps (avg=%.0f KB) | shm_w=%d skip=%d q_drop=%d | ml=%.1f fps",
    self.label, cam_fps, cam_avg, cam_max,
    enc_fps, avg_kb, self.shm_writes, self.shm_skips, self.queue_drops, ml_fps,
)
~~~

Snippet H1-2 from [app/web/routes.py](../app/web/routes.py)

~~~python
stream_log.info(
    "[DIAG MJPEG] yield=%.1f fps | stale=%d | err=%d | "
    "lat_avg=%.1fms lat_max=%.1fms | last_seq=%d",
    yfps, stale_count, error_count, avg_lat, max_latency, last_seq,
)
~~~

Snippet H1-3 from [reports/iteration_9_11_evaluation.md](iteration_9_11_evaluation.md)

~~~text
This evaluation is based on correctness verification through automated testing —
not on a full-system benchmark with live camera and ML inference.

Note: python -m app.benchmark_run does not exist on current main branch.
~~~

### 6. How to describe this in report language

- The project uses embedded telemetry and log-based profiling rather than a dedicated external benchmark framework.
- Metrics are sampled in production-like runtime loops, which improves realism, but repeatability and automation of benchmark runs are weaker than a formal harness.

### 7. Limitations / honest weaknesses

- No single command/script for reproducible benchmark suites in current branch.
- No machine-readable benchmark artifact schema (for example JSON/CSV baseline comparisons).
- Diagnostics are log-based and periodic, so high-frequency transient spikes can be under-sampled.
- INFERENCE: Benchmark repeatability depends on manual run discipline and environment consistency.

---

## H2. RTSP vs Webcam Empirical Evaluation

### Technical evidence summary

A dedicated empirical report compares local webcam and RTSP ingestion.

What was compared:
- Local webcam mode vs RTSP network stream mode at matched 640x480 resolution.

Metrics used:
- Avg Camera FPS
- Stream FPS (MJPEG)
- Avg Frame Read Time
- Avg/Max Pipeline Latency
- Internal Frame Drops
- ML FPS
Evidence: [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md) lines 32-40.

How comparison was run:
- 60-second runs, stable lighting, PROCESS_EVERY_N_FRAMES=3: [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md) lines 21-23, 30.
- DIAG FAST/DIAG SLOW used as measurement source: [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md) lines 14-15.

### 1. What existed before

- Baseline system started as webcam-first local ingestion: [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md) line 5.

### 2. What changed

- RTSP mode added and then measured against webcam mode under controlled settings.
- Run logs were captured for both modes:
  - RTSP diagnostics: [new_rtsp_main.txt](../new_rtsp_main.txt) lines 24-31, 405-406.
  - RTSP MJPEG diagnostics: [new_rtsp_mjpeg.txt](../new_rtsp_mjpeg.txt) lines 23-35.
  - Webcam diagnostics: [new_webcam_main.txt](../new_webcam_main.txt) lines 206, 410-411, 623, 627.

### 3. Why it changed

- To quantify deployment trade-offs between physically decoupled RTSP architecture and local webcam responsiveness.

### 4. What files matter most

- [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)
- [app/main.py](../app/main.py)
- [app/web/routes.py](../app/web/routes.py)
- [new_rtsp_main.txt](../new_rtsp_main.txt)
- [new_rtsp_mjpeg.txt](../new_rtsp_mjpeg.txt)
- [new_webcam_main.txt](../new_webcam_main.txt)

### 5. Useful snippets

Snippet H2-1 from [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)

~~~text
| Avg Camera FPS      | 30.0 fps | 15.0 fps |
| Avg Frame Read Time | 27.4 ms  | 52.0 ms  |
| Max Pipeline Latency| 141.0 ms | 266.0 ms |
| ML FPS              | 10.0 fps | 5.0 fps  |
~~~

Snippet H2-2 from [new_rtsp_main.txt](../new_rtsp_main.txt)

~~~text
[DIAG FAST] cam=15.0 fps (avg=52.0ms max=79.0ms) ...
[DIAG SLOW] ... ml=5.1 fps
~~~

Snippet H2-3 from [new_webcam_main.txt](../new_webcam_main.txt)

~~~text
[DIAG FAST] cam=28.9 fps (avg=27.4ms max=79.0ms) ...
[DIAG SLOW] ... ml=8.1 fps
~~~

### 6. How to describe this in report language

- The RTSP-vs-webcam evaluation is an empirical, runtime-log-driven comparison that isolates transport/decode overhead by controlling resolution and duration.
- Results show RTSP deployment feasibility with measurable responsiveness penalties.

### 7. Limitations / honest weaknesses

- Core report explicitly excludes full glass-to-glass browser latency from dataset: [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md) line 24 and line 64.
- WAN/cellular behavior was not benchmarked; conclusions are LAN-scoped: [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md) line 65.
- Webcam MJPEG comparison log is incomplete in the available artifact (startup-only [new_webcam_mjpeg.txt](../new_webcam_mjpeg.txt)); no DIAG MJPEG samples are present there.

---

## H3. Latency Measurement Methodology (Timestamp / Visual)

### Technical evidence summary

Timestamp-based method in code:
- Main process writes capture timing metadata into shared memory:
  - sequence number and capture timestamp fields: [app/main.py](../app/main.py) lines 74-75.
  - timestamp write uses monotonic clock: [app/main.py](../app/main.py) line 608.
- Web stream computes frame age at yield time:
  - reads seq and timestamp: [app/web/routes.py](../app/web/routes.py) lines 281, 287.
  - computes latency in ms: [app/web/routes.py](../app/web/routes.py) line 288.
  - reports lat_avg and lat_max: [app/web/routes.py](../app/web/routes.py) lines 312-313.

Visual/observational method in reports:
- RTSP evaluation distinguishes instrumented pipeline latency vs observed perceived delay (~0.5-1.5s): [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md) lines 51-54.
- It explicitly states host timestamps do not capture in-flight network buffering delay: [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md) line 54.

### 1. What existed before

- Historical near-live route used file polling approach documented in UI log (latest_frame.jpg + 800ms browser polling): [docs/DASHBOARD_UI_LOG.md](../docs/DASHBOARD_UI_LOG.md) lines 16, 19.

### 2. What changed

- Measurement moved from coarse polling-era behavior to explicit sequence+timestamp shared-memory telemetry for MJPEG stream diagnostics.
- This is reflected in current code and optimization report.

### 3. Why it changed

- To objectively distinguish stale reads, camera update health, and stream delivery latency during live-stream debugging.

### 4. What files matter most

- [app/main.py](../app/main.py)
- [app/web/routes.py](../app/web/routes.py)
- [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)
- [reports/live_stream_optimization_report.md](live_stream_optimization_report.md)
- [docs/DASHBOARD_UI_LOG.md](../docs/DASHBOARD_UI_LOG.md)
- [new_rtsp_mjpeg.txt](../new_rtsp_mjpeg.txt)

### 5. Useful snippets

Snippet H3-1 from [app/main.py](../app/main.py)

~~~python
# Bytes 5-8: sequence number
# Bytes 9-16: capture timestamp
live_shm.buf[5:9] = (shm_seq & 0xFFFFFFFF).to_bytes(4, 'little')
live_shm.buf[9:17] = struct.pack('<d', t_read_start)
~~~

Snippet H3-2 from [app/web/routes.py](../app/web/routes.py)

~~~python
seq = int.from_bytes(shm.buf[5:9], 'little')
cap_ts = struct.unpack('<d', shm.buf[9:17])[0]
latency = (time.monotonic() - cap_ts) * 1000.0
~~~

Snippet H3-3 from [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)

~~~text
Pipeline Latency and Network Ingestion Delay are distinct.
Observed network ingestion delay (~0.5s-1.5s) is not captured by host-side timestamps.
~~~

### 6. How to describe this in report language

- The methodology combines process-level timestamp telemetry for frame-age estimation with observational interpretation for external transport delays that remain outside host-only timing windows.

### 7. Limitations / honest weaknesses

- No explicit phone-timer or external synchronized visual protocol is documented; only observational phrasing is present for perceived delay.
- Latency metric uses t_read_start (host read-start) as proxy timestamp, not sensor-exposure timestamp.
- Current code comment drift exists: main.py header comment says 9-byte layout while implementation and routes use 17-byte header with timestamp: [app/main.py](../app/main.py) lines 70, 75, 77 and [app/web/routes.py](../app/web/routes.py) lines 218, 254.
- Optimization report still references 9-byte header in historical narrative: [reports/live_stream_optimization_report.md](live_stream_optimization_report.md) line 78.

---

## H4. Servo System Functional Testing and Validation

### Technical evidence summary

Automated servo logic tests exist at unit level:
- dead zone suppression: [tests/test_servo_logic.py](../tests/test_servo_logic.py) line 15
- pan direction selection: [tests/test_servo_logic.py](../tests/test_servo_logic.py) line 28
- cooldown enforcement: [tests/test_servo_logic.py](../tests/test_servo_logic.py) line 41
- anti-oscillation block: [tests/test_servo_logic.py](../tests/test_servo_logic.py) line 56
- extreme override: [tests/test_servo_logic.py](../tests/test_servo_logic.py) line 77
- timeout and HTTP error handling: [tests/test_servo_logic.py](../tests/test_servo_logic.py) lines 97, 106

Technical report adds manual/field validation narrative:
- claims 100% logic coverage and all tests passing: [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md) line 178
- lists field issues/fixes: [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md) lines 181, 185-187

### 1. What existed before

- INFERENCE: Initial servo validation likely relied on field debugging first, followed by targeted unit tests as control policy stabilized.

### 2. What changed

- Explicit unit tests now cover major control rules and network error paths.
- Field fixes were documented for direction mapping, input validation, and bbox access errors.

### 3. Why it changed

- To prove stability-focused control behavior under delayed feedback and avoid regressions in suppression logic.

### 4. What files matter most

- [tests/test_servo_logic.py](../tests/test_servo_logic.py)
- [app/services/servo_service.py](../app/services/servo_service.py)
- [scripts/pi_servo_service.py](../scripts/pi_servo_service.py)
- [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md)

### 5. Useful snippets

Snippet H4-1 from [tests/test_servo_logic.py](../tests/test_servo_logic.py)

~~~python
def test_anti_oscillation_block(controller):
    ...
    moved = controller.compute_and_send(face_right, 640, 480)
    assert moved is False

def test_anti_oscillation_override_extreme(controller):
    ...
    moved = controller.compute_and_send(face_extreme_right, 640, 480)
    assert moved is True
~~~

Snippet H4-2 from [tests/test_servo_logic.py](../tests/test_servo_logic.py)

~~~python
mock_get.assert_called_once_with(
    "http://1.2.3.4:5000/move", params={"axis": "pan", "dir": "left"}, timeout=1.0
)
~~~

Snippet H4-3 from [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md)

~~~text
Observed issues and applied fixes:
- Vertical movement inverted -> corrected direction mapping
- Invalid axis/dir -> improved Pi input validation
- Attribute access error -> fixed bbox property reference
~~~

### 6. How to describe this in report language

- Servo validation combines deterministic unit tests for control rules with field debugging feedback for hardware-direction and integration edge cases.
- Success criteria are behavioral, not purely numeric: suppression where expected, movement when correction is needed, and graceful degradation on network faults.

### 7. Limitations / honest weaknesses

- Unit tests are request-mocked and do not execute real pigpio hardware paths.
- No hardware-in-loop automated test harness is present for end-to-end latency + servo motion confirmation.
- Documentation/test consistency risk:
  - Report claims all tests pass.
  - Current test fixture uses plain BBox namedtuple while controller code dereferences face_bbox.bbox in runtime path: [tests/test_servo_logic.py](../tests/test_servo_logic.py) line 8 and [app/services/servo_service.py](../app/services/servo_service.py) line 61.
  - INFERENCE: This may indicate test drift unless an adapter layer existed in an earlier state.

---

## H5. Failure Case Analysis and Debugging

### Technical evidence summary

Primary failure/debug episodes evidenced in repository artifacts:

1) Live stream severe lag and file-lock crashes
- Symptom: dashboard stream around 1 FPS: [reports/live_stream_optimization_report.md](live_stream_optimization_report.md) line 7.
- Symptom: WinError 5 PermissionError from file overwrite contention: [reports/live_stream_optimization_report.md](live_stream_optimization_report.md) line 15.
- Debug path: moved from disk handoff to shared memory, then identified deeper synchronous starvation and refactored to two-thread architecture: [reports/live_stream_optimization_report.md](live_stream_optimization_report.md) lines 18, 27, 44.

2) RTSP/network fragility and reconnect handling
- Failure symptom documented and expected recovery path: [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md) lines 131-132, 179.
- Runtime loop behavior on read failure is explicit: [app/main.py](../app/main.py) lines 525-527.
- RTSP reconnect API has bounded retry policy: [app/camera/rtsp.py](../app/camera/rtsp.py) lines 154-155.

3) Codec/VideoWriter initialization errors during runs
- Repeated libopenh264 and VideoWriter initialization errors in both RTSP and webcam logs:
  - [new_rtsp_main.txt](../new_rtsp_main.txt) lines 55, 57, 216, 218
  - [new_webcam_main.txt](../new_webcam_main.txt) lines 45-46, 215-216, 641-643

4) Historical API/regression mismatches in archived test error artifact
- device_id parameter mismatch: [test_errors_ascii.txt](../test_errors_ascii.txt) lines 6, 10.
- add_alert severity argument mismatch: [test_errors_ascii.txt](../test_errors_ascii.txt) line 14.
- old config symbol imports mismatch (EMAIL_HOST): [test_errors_ascii.txt](../test_errors_ascii.txt) line 32.
- FK failure in dashboard test run: [test_errors_ascii.txt](../test_errors_ascii.txt) line 52.
- Current code indicates API shifted to device_index, add_alert(event_id, alert_type, message), and EMAIL_SMTP_* names:
  - [app/camera/webcam.py](../app/camera/webcam.py) line 20
  - [app/db/repo.py](../app/db/repo.py) line 630
  - [app/config.py](../app/config.py) lines 246-249

5) Remaining documented known limitations
- Identity swap/crossing limitations and no visual tracking:
  - [docs/VALIDATION_REPORT.md](../docs/VALIDATION_REPORT.md) lines 172, 186, 260
  - [reports/iteration_9_11_evaluation.md](iteration_9_11_evaluation.md) lines 101, 124-125

### 1. What existed before

- Monolithic processing flow and file-based frame sharing were used historically (documented in optimization report and UI log).
- RTSP robustness and stream diagnostics were less explicit before reconnect and sequence/timestamp instrumentation updates.

### 2. What changed

- Introduced shared memory transport and then two-thread producer-consumer split to isolate fast camera/display path from slow ML/I/O path.
- Added periodic triad diagnostics (FAST/SLOW/MJPEG) and sequence-based stale detection.
- Added reconnect behaviors and troubleshooting guidance for RTSP failures.
- Updated tests/config APIs from older names/signatures (as evidenced by archived failure artifact vs current code).

### 3. Why it changed

- To remove critical usability failures (lag, crashes) and provide enough observability to localize bottlenecks.
- To harden system against network/camera interruptions and reduce recurrence of regressions.

### 4. What files matter most

- [reports/live_stream_optimization_report.md](live_stream_optimization_report.md)
- [app/main.py](../app/main.py)
- [app/web/routes.py](../app/web/routes.py)
- [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)
- [new_rtsp_main.txt](../new_rtsp_main.txt)
- [new_webcam_main.txt](../new_webcam_main.txt)
- [test_errors_ascii.txt](../test_errors_ascii.txt)
- [docs/VALIDATION_REPORT.md](../docs/VALIDATION_REPORT.md)

### 5. Useful snippets

Snippet H5-1 from [reports/live_stream_optimization_report.md](live_stream_optimization_report.md)

~~~text
Symptom: dashboard live stream dropped to ~1 FPS.
Root cause evolved from disk I/O suspicion to synchronous pipeline starvation.
Fix: two-thread producer-consumer architecture.
~~~

Snippet H5-2 from [app/main.py](../app/main.py)

~~~python
if not ok or frame is None:
    log.warning("Frame read failed - attempting reconnect")
    if not camera.reconnect():
        log.error("Reconnect failed - exiting")
        break
~~~

Snippet H5-3 from [test_errors_ascii.txt](../test_errors_ascii.txt)

~~~text
TypeError: WebcamCamera.__init__() got an unexpected keyword argument 'device_id'
TypeError: SQLiteAlertRepository.add_alert() got an unexpected keyword argument 'severity'
ImportError: cannot import name 'EMAIL_HOST' from app.config
sqlite3.IntegrityError: FOREIGN KEY constraint failed
~~~

### 6. How to describe this in report language

- Failure analysis in SecureVision was evidence-led: runtime telemetry narrowed the bottleneck class, then architectural changes were validated against improved operating diagnostics.
- Debugging was iterative: initial hypotheses were partially correct (file locking) but insufficient, and deeper scheduling/flow constraints were ultimately addressed.

### 7. Limitations / honest weaknesses

- Some failure artifacts are historical snapshots and not guaranteed to reflect current head behavior without rerunning the exact test matrix.
- Repeated VideoWriter codec errors remain visible in run logs and should be treated as unresolved environment/codec dependency risk unless explicitly remediated.
- Known tracking/association limitations remain open by design, not fixed in current evaluation scope.

---

## Automation vs Manual vs Instrumentation vs Empirical (explicit split)

Automated tests:
- [tests/test_camera_rtsp.py](../tests/test_camera_rtsp.py)
- [tests/test_camera_webcam.py](../tests/test_camera_webcam.py)
- [tests/test_hardware_resilience.py](../tests/test_hardware_resilience.py)
- [tests/test_main_loop.py](../tests/test_main_loop.py)
- [tests/test_dashboard.py](../tests/test_dashboard.py)
- [tests/test_servo_logic.py](../tests/test_servo_logic.py)

Manual validation:
- [docs/VALIDATION_REPORT.md](../docs/VALIDATION_REPORT.md) section Manual Test Plan (line 100 onward)
- [reports/SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md](SERVO_TRACKING_SYSTEM_TECHNICAL_REPORT.md) field-testing section (lines 181-187)

Instrumentation/diagnostics:
- [app/main.py](../app/main.py) DIAG FAST/SLOW
- [app/web/routes.py](../app/web/routes.py) DIAG MJPEG with sequence and latency
- Runtime log artifacts in [new_rtsp_main.txt](../new_rtsp_main.txt), [new_rtsp_mjpeg.txt](../new_rtsp_mjpeg.txt), [new_webcam_main.txt](../new_webcam_main.txt)

Empirical evaluation artifacts:
- [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)
- [reports/live_stream_optimization_report.md](live_stream_optimization_report.md)
- [reports/iteration_9_11_evaluation.md](iteration_9_11_evaluation.md)
