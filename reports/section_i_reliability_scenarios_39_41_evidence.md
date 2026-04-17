# Section I - Reliability Scenarios 39-41 Evidence Pack

This is source-grounded material for Section I only (not polished final report prose).

Evidence source set used:
- [app/main.py](../app/main.py)
- [app/recording/clip_recorder.py](../app/recording/clip_recorder.py)
- [app/camera/base.py](../app/camera/base.py)
- [app/camera/rtsp.py](../app/camera/rtsp.py)
- [app/camera/webcam.py](../app/camera/webcam.py)
- [app/config.py](../app/config.py)
- [tests/test_clip_recorder.py](../tests/test_clip_recorder.py)
- [tests/test_camera_rtsp.py](../tests/test_camera_rtsp.py)
- [tests/test_camera_webcam.py](../tests/test_camera_webcam.py)
- [tests/test_hardware_resilience.py](../tests/test_hardware_resilience.py)
- [tests/test_main_loop.py](../tests/test_main_loop.py)
- [docs/BUILD_LOG.md](../docs/BUILD_LOG.md)
- [docs/CLIP_RECORDING_LOG.md](../docs/CLIP_RECORDING_LOG.md)
- [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)
- [docs/VALIDATION_REPORT.md](../docs/VALIDATION_REPORT.md)
- [new_rtsp_main.txt](../new_rtsp_main.txt)
- [new_webcam_main.txt](../new_webcam_main.txt)

Evidence handling rule used:
- Current code is treated as ground truth for current behavior.
- Runtime log statements are used only when explicitly present in preserved logs.
- Anything not explicitly shown in code/docs/logs is labeled as INFERENCE.

---

## I1. Scenario 39 - Thread Safety in ClipRecorder

### Technical evidence summary

- `ClipRecorder` maintains mutable shared state: `self.buffer` and `self.active_jobs` in [app/recording/clip_recorder.py](../app/recording/clip_recorder.py) lines 53-54.
- The same object is mutated by three methods:
  - `update_track_states()` in [app/recording/clip_recorder.py](../app/recording/clip_recorder.py) line 63.
  - `feed_frame()` in [app/recording/clip_recorder.py](../app/recording/clip_recorder.py) line 77.
  - `on_event()` in [app/recording/clip_recorder.py](../app/recording/clip_recorder.py) line 116.
- In `main.py`, accesses to these methods are serialized with a shared `clip_lock`:
  - lock creation: [app/main.py](../app/main.py) line 398.
  - slow-thread path: [app/main.py](../app/main.py) lines 314-315 and 349-350.
  - fast-thread path: [app/main.py](../app/main.py) lines 536-537.
- No internal mutex exists inside `ClipRecorder` itself (no `threading.Lock` in [app/recording/clip_recorder.py](../app/recording/clip_recorder.py)).

### 1. What existed before

- Earlier clip design was fixed post-event duration, not lifecycle-aware tracking: [docs/CLIP_RECORDING_LOG.md](../docs/CLIP_RECORDING_LOG.md) lines 25-28.
- INFERENCE: Before lifecycle-aware update calls were added, contention risk between fast and slow threads was lower because fewer code paths mutated clip state.

### 2. What changed

- Lifecycle-aware recording introduced `update_track_states()` transitions (`active` -> `tail`) and dynamic duration control in [app/recording/clip_recorder.py](../app/recording/clip_recorder.py) lines 63-75 and 99-106.
- `main.py` now uses explicit critical sections around all recorder state mutations via `clip_lock`:
  - [app/main.py](../app/main.py) lines 314-315, 349-350, 536-537.

### 3. Why it changed

- Dynamic clip lifecycle required both threads to coordinate recorder state safely:
  - fast loop continuously writes frames (`feed_frame`).
  - slow loop updates track states and starts jobs (`update_track_states`, `on_event`).
- Without locking, concurrent mutation of `active_jobs` and `buffer` could cause dropped jobs or dictionary mutation races.
- INFERENCE: The chosen design is external lock orchestration in `main.py` instead of internal locking in `ClipRecorder` to keep recorder class logic simple and avoid nested lock ownership confusion.

### 4. What files matter most

- [app/main.py](../app/main.py)
- [app/recording/clip_recorder.py](../app/recording/clip_recorder.py)
- [tests/test_clip_recorder.py](../tests/test_clip_recorder.py)
- [docs/CLIP_RECORDING_LOG.md](../docs/CLIP_RECORDING_LOG.md)
- [docs/VALIDATION_REPORT.md](../docs/VALIDATION_REPORT.md)

### 5. Useful snippets

Snippet I1-1 from [app/main.py](../app/main.py)

~~~python
# slow thread path
if config.CLIP_ENABLED:
    with clip_lock:
        clip_recorder.update_track_states(event_manager.track_states())

# slow thread event trigger
if config.CLIP_ENABLED:
    with clip_lock:
        clip_recorder.on_event(event, frame)

# fast thread path
if config.CLIP_ENABLED:
    with clip_lock:
        completed_clips = clip_recorder.feed_frame(frame)
~~~

Snippet I1-2 from [app/recording/clip_recorder.py](../app/recording/clip_recorder.py)

~~~python
self.buffer: collections.deque = collections.deque(maxlen=self.max_buffer_len)
self.active_jobs: dict[str, ClipJob] = {}

self.buffer.append(saved_frame)
for job_id, job in list(self.active_jobs.items()):
    ...
    if time_to_close:
        job.writer.release()
        completed.append((job.event_id, job.path))
        del self.active_jobs[job_id]

...
self.active_jobs[event.event_id] = job
~~~

Snippet I1-3 from [tests/test_clip_recorder.py](../tests/test_clip_recorder.py)

~~~python
# Functional lifecycle checks (single-threaded)
recorder.update_track_states({"face_1": "ACTIVE"})
for _ in range(15):
    completed = recorder.feed_frame(frame)
    assert len(completed) == 0

recorder.update_track_states({"face_2": "ACTIVE"})  # face_1 missing
assert recorder.active_jobs["dynamic-test"].mode == "tail"
~~~

### 6. How to describe this in report language

- Thread safety is currently enforced at orchestration level (`main.py`) using one shared lock around all mutable `ClipRecorder` operations.
- Recorder internals are intentionally stateful and mutable; safety depends on callers respecting lock discipline.
- Test evidence confirms lifecycle correctness, but not true concurrent race stress.

### 7. Limitations / honest weaknesses

- No dedicated race-condition test that runs `feed_frame` and `on_event` concurrently with randomized scheduling.
- Locking is external; any future caller that bypasses `clip_lock` can reintroduce race bugs.
- Synchronous writer I/O remains in the fast path (see Scenario 41), so lock duration includes disk work.

---

## I2. Scenario 40 - Network Failure and Reconnection Handling

### Technical evidence summary

- `CameraSource` contract makes `reconnect()` mandatory: [app/camera/base.py](../app/camera/base.py) lines 42-55.
- Fast loop recovery branch in `main.py`:
  - read failure -> warn -> `camera.reconnect()` -> exit if reconnect fails: [app/main.py](../app/main.py) lines 525-527.
- RTSP reconnect policy is more aggressive than webcam:
  - RTSP defaults: `max_attempts=5`, `delay_seconds=2.0` in [app/camera/rtsp.py](../app/camera/rtsp.py) line 155.
  - Webcam defaults: `max_attempts=3`, `delay_seconds=1.0` in [app/camera/webcam.py](../app/camera/webcam.py) line 82.
- RTSP low-latency configuration is best-effort (backend may ignore):
  - [app/camera/rtsp.py](../app/camera/rtsp.py) lines 12-13, 64, 92-94.
  - [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md) lines 147, 150, 181.

### 1. What existed before

- RTSP integration iteration log states reconnect behavior was introduced as part of camera abstraction upgrade:
  - [docs/BUILD_LOG.md](../docs/BUILD_LOG.md) lines 45-47.
- INFERENCE: Prior webcam-only flow had less explicit network recovery surface because network stream failure mode did not exist.

### 2. What changed

- Introduced camera-interface-level reconnect method and wired it into main loop failure handling.
- Added source-specific retry policies (RTSP vs webcam).
- Added dedicated reconnect tests and resilience tests:
  - [tests/test_camera_rtsp.py](../tests/test_camera_rtsp.py) lines 139-198.
  - [tests/test_hardware_resilience.py](../tests/test_hardware_resilience.py) lines 48-77, 162-173.

### 3. Why it changed

- RTSP streams are vulnerable to network jitter, process restarts, and mid-stream drops.
- System needed automatic retry instead of immediate process exit on a single read failure.
- Documentation explicitly describes this expected behavior and failure response:
  - [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md) lines 131-132, 162, 179.

### 4. What files matter most

- [app/main.py](../app/main.py)
- [app/camera/base.py](../app/camera/base.py)
- [app/camera/rtsp.py](../app/camera/rtsp.py)
- [app/camera/webcam.py](../app/camera/webcam.py)
- [tests/test_camera_rtsp.py](../tests/test_camera_rtsp.py)
- [tests/test_hardware_resilience.py](../tests/test_hardware_resilience.py)
- [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)

### 5. Useful snippets

Snippet I2-1 from [app/main.py](../app/main.py)

~~~python
if not ok or frame is None:
    log.warning("Frame read failed — attempting reconnect")
    if not camera.reconnect():
        log.error("Reconnect failed — exiting")
        break
    continue
~~~

Snippet I2-2 from [app/camera/rtsp.py](../app/camera/rtsp.py)

~~~python
def reconnect(self, max_attempts: int = 5, delay_seconds: float = 2.0) -> bool:
    self._log.warning("Attempting RTSP reconnect to %s …", self._url)
    self.release()
    for attempt in range(1, max_attempts + 1):
        self._log.info("RTSP reconnect attempt %d/%d", attempt, max_attempts)
        if self._open():
            self._log.info("RTSP reconnect succeeded on attempt %d", attempt)
            return True
        time.sleep(delay_seconds)
    self._log.error("RTSP reconnect failed after %d attempts: %s", max_attempts, self._url)
    return False
~~~

Snippet I2-3 from [tests/test_camera_rtsp.py](../tests/test_camera_rtsp.py)

~~~python
result = cam.reconnect(max_attempts=5, delay_seconds=0.01)
self.assertTrue(result)
self.assertEqual(mock_sleep.call_count, 2)  # succeeded on third attempt

result = cam.reconnect(max_attempts=3, delay_seconds=0.01)
self.assertFalse(result)
self.assertEqual(mock_sleep.call_count, 3)  # exhausted attempts
~~~

### 6. How to describe this in report language

- Recovery is centralized at the camera abstraction boundary, then consumed uniformly by the fast loop.
- RTSP and webcam share a common API but use different retry defaults reflecting different failure profiles.
- The design favors clean termination after bounded retries rather than endless reconnect loops.

### 7. Limitations / honest weaknesses

- No preserved runtime `.txt` log in this repo currently shows explicit reconnect-attempt lines from a live disconnect episode; most hard evidence is code + unit tests + integration documentation.
- `main.py` reconnect branch itself is not directly integration-tested with a mocked camera in `tests/test_main_loop.py`.
- `cv2.VideoCapture.read()` may block during network timeout (documented in [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md) line 167), so recovery latency is backend-dependent.
- Retry policy is fixed-count/fixed-delay; no exponential backoff or adaptive strategy.

---

## I3. Scenario 41 - Codec and FFmpeg Errors (including OpenH264)

### Technical evidence summary

- Clip writer path is OpenCV/FFmpeg-backed and codec-config driven:
  - codec selection: [app/config.py](../app/config.py) line 165 (`avc1` default).
  - writer creation and open gate: [app/recording/clip_recorder.py](../app/recording/clip_recorder.py) lines 124-128.
- Build log explicitly records stabilization change:
  - `writer.isOpened()` guard to avoid corrupt/orphan records after permission/codec failure: [docs/BUILD_LOG.md](../docs/BUILD_LOG.md) line 117.
- Runtime logs show repeated OpenH264/FFmpeg writer initialization failures:
  - [new_rtsp_main.txt](../new_rtsp_main.txt) lines 51-57, 215-218, 485-487.
  - [new_webcam_main.txt](../new_webcam_main.txt) lines 41-46, 215-216, 641-643.
- Regression test exists for writer-open failure path:
  - [tests/test_clip_recorder.py](../tests/test_clip_recorder.py) lines 97-102.

### 1. What existed before

- Iteration 10 stabilization notes imply earlier behavior could produce bad clip artifacts/DB inconsistencies when writer initialization failed:
  - [docs/BUILD_LOG.md](../docs/BUILD_LOG.md) line 117.

### 2. What changed

- Added explicit `writer.isOpened()` guard and early return in `on_event()` so failed writers do not register active jobs.
- Set default clip codec to `avc1` for wider compatibility in dashboard playback:
  - [docs/BUILD_LOG.md](../docs/BUILD_LOG.md) line 23.
  - [app/config.py](../app/config.py) line 165.
- Added unit test that mocks `VideoWriter.isOpened=False` and asserts job not stored:
  - [tests/test_clip_recorder.py](../tests/test_clip_recorder.py) lines 97-102.

### 3. Why it changed

- Observed runtime failures from missing/mismatched OpenH264 libraries and FFmpeg writer init failures needed containment.
- Goal was fail-safe behavior: skip broken clip write path without corrupting recorder state or linking non-existent clips.

### 4. What files matter most

- [app/recording/clip_recorder.py](../app/recording/clip_recorder.py)
- [app/config.py](../app/config.py)
- [tests/test_clip_recorder.py](../tests/test_clip_recorder.py)
- [docs/BUILD_LOG.md](../docs/BUILD_LOG.md)
- [new_rtsp_main.txt](../new_rtsp_main.txt)
- [new_webcam_main.txt](../new_webcam_main.txt)

### 5. Useful snippets

Snippet I3-1 from [app/recording/clip_recorder.py](../app/recording/clip_recorder.py)

~~~python
fourcc = cv2.VideoWriter_fourcc(*config.CLIP_CODEC)
writer = cv2.VideoWriter(str(out_path), fourcc, self.target_fps, (w, h))

if not writer.isOpened():
    self._log.error("VideoWriter failed to open for event %s path %s", event.event_id, out_path)
    return None
~~~

Snippet I3-2 from [tests/test_clip_recorder.py](../tests/test_clip_recorder.py)

~~~python
with mock.patch("app.recording.clip_recorder.cv2.VideoWriter.isOpened", return_value=False):
    recorder.on_event(event, frame)

assert "bad-writer-uuid" not in recorder.active_jobs
~~~

Snippet I3-3 from [new_rtsp_main.txt](../new_rtsp_main.txt) (runtime log)

~~~text
51: Failed to load OpenH264 library: openh264-1.8.0-win64.dll
54: [libopenh264 @ ...] Incorrect library version loaded
55: [ERROR:0@29.022] ... Could not open codec libopenh264, error: Unspecified error (-22)
57: [ERROR:0@29.022] ... VIDEOIO/FFMPEG: Failed to initialize VideoWriter
~~~

### 6. How to describe this in report language

- Codec/FFmpeg failure handling is defensive rather than corrective: the system detects writer-open failure and aborts clip job creation safely.
- Operational evidence confirms repeated external codec dependency failures (OpenH264 mismatch) can still occur even with safe guards.
- Reliability gain is containment of failure impact, not elimination of codec dependency risk.

### 7. Limitations / honest weaknesses

- No automatic codec fallback strategy (for example trying `mp4v` after `avc1` failure).
- No startup self-test to pre-validate FFmpeg codec availability before first event.
- Repeated runtime errors can still spam logs during high event rates (seen in both RTSP and webcam runs).
- INFERENCE: Because failure is handled at event-trigger time, operator only discovers codec problems when events occur, not proactively at boot.

---

## Cross-scenario note (39-41)

- Strongest evidence quality is for Scenario 41 (runtime logs + code guard + test).
- Scenario 40 is strong in code/test design evidence, weaker in preserved live reconnect transcript evidence.
- Scenario 39 has clear locking design evidence, but dedicated concurrency stress testing is still a gap.