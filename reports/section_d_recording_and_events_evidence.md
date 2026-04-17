# Section D - Recording and Events

This is source material for writing the report, not the final polished section.

Evidence source set used for this pack:
- [app/recording/clip_recorder.py](../app/recording/clip_recorder.py)
- [app/recording/base.py](../app/recording/base.py)
- [app/main.py](../app/main.py)
- [app/config.py](../app/config.py)
- [app/core/models.py](../app/core/models.py)
- [app/core/event_manager.py](../app/core/event_manager.py)
- [app/core/multi_event_manager.py](../app/core/multi_event_manager.py)
- [app/db/schema.sql](../app/db/schema.sql)
- [app/db/migrations.py](../app/db/migrations.py)
- [app/db/repo.py](../app/db/repo.py)
- [app/web/routes.py](../app/web/routes.py)
- [app/web/templates/event.html](../app/web/templates/event.html)
- [tests/test_clip_recorder.py](../tests/test_clip_recorder.py)
- [tests/test_main_loop.py](../tests/test_main_loop.py)
- [tests/test_dashboard.py](../tests/test_dashboard.py)
- [tests/test_db_repo.py](../tests/test_db_repo.py)
- [tests/test_event_manager.py](../tests/test_event_manager.py)
- [tests/test_multi_event_manager.py](../tests/test_multi_event_manager.py)
- [docs/CLIP_RECORDING_LOG.md](../docs/CLIP_RECORDING_LOG.md)
- [docs/TRACKING_INTEGRATION_LOG.md](../docs/TRACKING_INTEGRATION_LOG.md)
- [docs/BUILD_LOG.md](../docs/BUILD_LOG.md)
- [docs/VALIDATION_REPORT.md](../docs/VALIDATION_REPORT.md)
- [docs/DASHBOARD_UI_LOG.md](../docs/DASHBOARD_UI_LOG.md)
- [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)
- [reports/iteration_9_11_evaluation.md](iteration_9_11_evaluation.md)

Evidence reliability rule used:
- Current code is ground truth for current behavior.
- Historical behavior is reconstructed from build/log docs and older evaluation reports.
- Any statement that is not directly explicit in code/docs is marked as INFERENCE.

---

## D1. Scenario 16: Clip Recording System Design (Ring Buffer)

### Technical evidence summary

Current architecture is a hybrid two-thread design:
- Slow processing thread emits events and triggers clip jobs: [app/main.py](../app/main.py) lines 310, 315, 350.
- Fast camera loop feeds every camera frame into recorder buffering/writing and links completed clips into DB: [app/main.py](../app/main.py) lines 535-545.

Recorder internals:
- Ring buffer capacity is computed as `target_fps * pre_sec`: [app/recording/clip_recorder.py](../app/recording/clip_recorder.py) lines 49, 53.
- Post tail frames are computed as `target_fps * post_sec`: [app/recording/clip_recorder.py](../app/recording/clip_recorder.py) line 50.
- Hard ceiling is `target_fps * max_duration`: [app/recording/clip_recorder.py](../app/recording/clip_recorder.py) lines 51, 99.
- Output path is date-partitioned `YYYY-MM-DD/<event_id>.<ext>`: [app/recording/clip_recorder.py](../app/recording/clip_recorder.py) lines 56, 58, 61.

Persistence and playback:
- Event rows carry `clip_path` and `track_key`: [app/db/schema.sql](../app/db/schema.sql) lines 43-44.
- Clip path update API is explicit (`update_event_clip`): [app/db/repo.py](../app/db/repo.py) lines 471-475.
- Dashboard serves clips only through constrained path resolution under `CLIPS_DIR`: [app/web/routes.py](../app/web/routes.py) lines 73, 95, 388-400.

### 1. What existed before

Before clip implementation:
- Iteration 4 explicitly excluded clip logic: [docs/BUILD_LOG.md](../docs/BUILD_LOG.md) lines 170, 175.
- Build log also states "No clips added" in dashboard MVP stage: [docs/BUILD_LOG.md](../docs/BUILD_LOG.md) line 164.
- Schema had reserved media columns (`snapshot_path`, `clip_path`) prior to active clip wiring: [app/db/schema.sql](../app/db/schema.sql) line 43 and [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) lines 222-223.

### 2. What changed

Iteration 10 + stabilisation introduced active clip recording:
- Ring buffer pre/post recording model documented: [docs/CLIP_RECORDING_LOG.md](../docs/CLIP_RECORDING_LOG.md) lines 3, 9-13.
- Stabilisation added date output path and `writer.isOpened()` guard: [docs/BUILD_LOG.md](../docs/BUILD_LOG.md) lines 111, 117.
- Concrete writer-open failure behavior is unit-tested: [tests/test_clip_recorder.py](../tests/test_clip_recorder.py) lines 80, 98, 102.

Runtime integration now includes:
- Trigger job on event emission: [app/main.py](../app/main.py) line 350.
- Continuously feed frame buffer and finalize jobs in fast loop: [app/main.py](../app/main.py) line 537.
- Link finalized clip path into event row: [app/main.py](../app/main.py) lines 543, 545.

### 3. Why it changed

Primary motivation was evidential context:
- Preserve pre-event frames and post-event continuation around a detected security event.
- Persist clip location into event records so incident review can use one event detail page with both snapshot and video.

Direct evidence:
- Pre-buffer flush in `on_event`: [app/recording/clip_recorder.py](../app/recording/clip_recorder.py) lines 132-134.
- Event detail computes `clip_available` based on persisted DB path: [app/web/routes.py](../app/web/routes.py) line 359.
- Event page embeds secure event clip route in HTML5 player: [app/web/templates/event.html](../app/web/templates/event.html) lines 60-62.

### 4. What files matter most

- [app/recording/clip_recorder.py](../app/recording/clip_recorder.py)
- [app/main.py](../app/main.py)
- [app/db/repo.py](../app/db/repo.py)
- [app/db/schema.sql](../app/db/schema.sql)
- [app/web/routes.py](../app/web/routes.py)
- [tests/test_clip_recorder.py](../tests/test_clip_recorder.py)
- [docs/CLIP_RECORDING_LOG.md](../docs/CLIP_RECORDING_LOG.md)
- [docs/BUILD_LOG.md](../docs/BUILD_LOG.md)

### 5. Useful code snippets

Snippet D1-1 from [app/recording/clip_recorder.py](../app/recording/clip_recorder.py)

~~~python
self.target_fps = config.CLIP_TARGET_FPS
self.pre_sec = config.CLIP_PRE_EVENT_SECONDS
self.post_sec = config.CLIP_POST_EVENT_SECONDS
self.max_duration = config.CLIP_MAX_DURATION_SECONDS

self.max_buffer_len = int(self.target_fps * self.pre_sec)
self.post_frames = int(self.target_fps * self.post_sec)
self.max_total_frames = int(self.target_fps * self.max_duration)

self.buffer: collections.deque = collections.deque(maxlen=self.max_buffer_len)
~~~

Snippet D1-2 from [app/recording/clip_recorder.py](../app/recording/clip_recorder.py)

~~~python
frames_flushed = 0
for b_frame in list(self.buffer):
    writer.write(b_frame)
    frames_flushed += 1
~~~

Snippet D1-3 from [app/main.py](../app/main.py)

~~~python
if config.CLIP_ENABLED:
    with clip_lock:
        completed_clips = clip_recorder.feed_frame(frame)
for ev_id, clip_path in completed_clips:
    rel_path = clip_path.relative_to(config.BASE_DIR).as_posix()
    updated = event_repo.update_event_clip(ev_id, rel_path)
~~~

Snippet D1-4 from [tests/test_clip_recorder.py](../tests/test_clip_recorder.py)

~~~python
# Target max frames is 1.0 sec * 10 FPS = 10 frames
assert len(recorder.buffer) == 10
~~~

### 6. How to describe this in report language

- The clip subsystem is an event-linked recorder that continuously maintains a bounded temporal ring buffer, then materializes a per-event video artifact by flushing buffered pre-history and appending post-trigger frames under explicit FPS and duration controls.
- Design choice: recorder writes are centralized and deterministic, with explicit DB linking only after file completion, reducing orphan metadata risk.

### 7. Limitations and honest weaknesses

- Clip writes are synchronous/blocking (`VideoWriter.write`) on the recording path; this is acknowledged in docs: [docs/CLIP_RECORDING_LOG.md](../docs/CLIP_RECORDING_LOG.md) line 16 and [docs/VALIDATION_REPORT.md](../docs/VALIDATION_REPORT.md) lines 206, 216.
- Overlapping events can duplicate storage by design: [docs/CLIP_RECORDING_LOG.md](../docs/CLIP_RECORDING_LOG.md) line 17.
- INFERENCE: if process stops before a job reaches close condition, clip file may exist but `events.clip_path` stays null because DB link happens only after `feed_frame()` returns completion tuple: [app/main.py](../app/main.py) lines 537-543 and [app/db/repo.py](../app/db/repo.py) lines 471-475.
- Configuration docs lag: `docs/SETUP.md` currently exposes CLAHE clip limit but no `SV_CLIP_*` recorder knobs (repository text search found no `SV_CLIP_*` entries).

---

## D2. Scenario 17: Fixed-Length Clip Limitation Analysis

### Technical evidence summary

The fixed-length behavior is historically documented and still present as legacy fallback logic.

Historical fixed model evidence:
- Iteration 10 is explicitly "Pre/Post Event Video Clip Recording": [docs/CLIP_RECORDING_LOG.md](../docs/CLIP_RECORDING_LOG.md) line 3.
- Iteration 9-11 evaluation reports clip correctness around pre-buffer/post-buffer countdown, not lifecycle-duration coupling: [reports/iteration_9_11_evaluation.md](iteration_9_11_evaluation.md) lines 72, 76-79, 137.
- Validation report clip test table lists only the original five tests: [docs/VALIDATION_REPORT.md](../docs/VALIDATION_REPORT.md) lines 82, 86, 89.

Current code retains a fixed fallback mode:
- If event has no track key, clip starts immediately in tail mode (`frames_remaining = post_frames`): [app/recording/clip_recorder.py](../app/recording/clip_recorder.py) lines 137-138, 144.
- Tail mode decrements by one per saved frame until completion: [app/recording/clip_recorder.py](../app/recording/clip_recorder.py) lines 103-106.

### 1. What existed before

Static pre/post duration dominated completion:
- With fixed mode, total clip duration approximates `pre_sec + post_sec`.
- Current defaults are `pre=2.0s`, `post=3.0s`, giving approximately 5 seconds when fallback path is used: [app/config.py](../app/config.py) lines 161-162.

The redesign log explicitly calls this out:
- "static, artificially limited 5-second video output clips": [docs/CLIP_RECORDING_LOG.md](../docs/CLIP_RECORDING_LOG.md) line 22.

### 2. What changed

The limitation was identified as operationally insufficient:
- Subject dwell time beyond fixed window was not represented in event evidence.
- Timeline relation to actual presence lifecycle was weak when clips closed only by fixed post countdown.

Concrete fixed-length mechanics still visible:
- Fixed post frame budget in tests (`initial_remaining == 5` when post=0.5, fps=10): [tests/test_clip_recorder.py](../tests/test_clip_recorder.py) lines 150, 184.
- Fixed completion countdown behavior validated in old lifecycle tests: [tests/test_clip_recorder.py](../tests/test_clip_recorder.py) lines 150, 200-201.

### 3. Why it changed

The redesign pressure came from mismatch between event semantics and evidence duration:
- Event lifecycle (ACTIVE, COOLDOWN) existed in event manager state machine: [app/core/event_manager.py](../app/core/event_manager.py) lines 30-34, 144.
- Clip closure was still post-frame budget based in fixed mode, which can truncate long presences.

The project log names this as the explicit flaw later addressed:
- [docs/CLIP_RECORDING_LOG.md](../docs/CLIP_RECORDING_LOG.md) line 22.

### 4. What files matter most

- [app/recording/clip_recorder.py](../app/recording/clip_recorder.py)
- [app/config.py](../app/config.py)
- [tests/test_clip_recorder.py](../tests/test_clip_recorder.py)
- [docs/CLIP_RECORDING_LOG.md](../docs/CLIP_RECORDING_LOG.md)
- [reports/iteration_9_11_evaluation.md](iteration_9_11_evaluation.md)
- [docs/VALIDATION_REPORT.md](../docs/VALIDATION_REPORT.md)

### 5. Useful evidence snippets

Snippet D2-1 from [app/recording/clip_recorder.py](../app/recording/clip_recorder.py)

~~~python
# If no track_key exists in the event, fallback to legacy trailing immediately.
mode = "active" if event.track_key else "tail"

job = ClipJob(
    ...
    frames_remaining=self.post_frames if mode == "tail" else 0,
)
~~~

Snippet D2-2 from [app/recording/clip_recorder.py](../app/recording/clip_recorder.py)

~~~python
elif job.mode == "tail":
    job.frames_remaining -= 1
    if job.frames_remaining <= 0:
        time_to_close = True
~~~

Snippet D2-3 from [docs/CLIP_RECORDING_LOG.md](../docs/CLIP_RECORDING_LOG.md)

~~~text
Implemented and active. Resolves the flaw of static, artificially limited
5-second video output clips.
~~~

Snippet D2-4 from [tests/test_clip_recorder.py](../tests/test_clip_recorder.py)

~~~python
initial_remaining = job.frames_remaining
assert initial_remaining == 5, f"Post-frames should be 5, got {initial_remaining}"
~~~

### 6. How to describe this in report language

- The original pre/post implementation guaranteed deterministic bounded clips, but this boundedness was also the core evidential weakness: clip length was dominated by configured windows rather than real entity dwell time.
- The static window was acceptable for MVP capture but insufficient for sustained unauthorized presence scenarios.

### 7. Limitations and honest weaknesses

- Legacy fixed-tail behavior still exists as compatibility path when `event.track_key` is missing: [app/recording/clip_recorder.py](../app/recording/clip_recorder.py) lines 137-138.
- Documentation set is partially stale: architecture and model docs still describe clip fields as reserved/always none in places: [app/core/models.py](../app/core/models.py) lines 211, 213 and [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) lines 223, 289.
- Validation documentation lags current test suite evolution (still lists only old five clip tests): [docs/VALIDATION_REPORT.md](../docs/VALIDATION_REPORT.md) lines 82-90.

---

## D3. Scenario 18: Dynamic Event-Based Clip Recording Redesign

### Technical evidence summary

The redesign binds clip lifetime to tracked entity lifecycle:
- `track_key` is propagated from per-face observations into emitted events: [app/core/multi_event_manager.py](../app/core/multi_event_manager.py) lines 139, 161 and [app/core/event_manager.py](../app/core/event_manager.py) lines 195, 202.
- Main loop sends current track states to recorder: [app/main.py](../app/main.py) line 315.
- Recorder keeps jobs in `active` mode while state is ACTIVE, then transitions to `tail`: [app/recording/clip_recorder.py](../app/recording/clip_recorder.py) lines 63, 71-73.
- Safety cap prevents unbounded recording: [app/recording/clip_recorder.py](../app/recording/clip_recorder.py) lines 51, 99.

Redesign is documented as Iteration 12c:
- [docs/CLIP_RECORDING_LOG.md](../docs/CLIP_RECORDING_LOG.md) lines 19, 25, 28, 29.

### 1. What existed before

Before Iteration 12c:
- Clip behavior centered on fixed pre/post windows (Scenario 17 evidence).
- Iteration 10 reports validate this pre/post model but do not include lifecycle-aware duration assertions: [reports/iteration_9_11_evaluation.md](iteration_9_11_evaluation.md) lines 72-79.

### 2. What changed

Core redesign changes:
1. Track lifecycle binding
- Event model carries `track_key`: [app/core/models.py](../app/core/models.py) lines 229-230.
- Event manager emits events with captured track key: [app/core/event_manager.py](../app/core/event_manager.py) lines 195, 202.
- DB schema/repo persist key with clip metadata: [app/db/schema.sql](../app/db/schema.sql) lines 43-44 and [app/db/repo.py](../app/db/repo.py) lines 387, 398, 456-457.

2. Active-to-tail transition
- Active jobs are moved to tail when state is not ACTIVE: [app/recording/clip_recorder.py](../app/recording/clip_recorder.py) lines 71-73.
- State source comes from `MultiEntityEventManager.track_states()`: [app/core/multi_event_manager.py](../app/core/multi_event_manager.py) line 109.

3. Hard cap protection
- Recorder forces closure when `frames_written >= max_total_frames`: [app/recording/clip_recorder.py](../app/recording/clip_recorder.py) line 99.

4. Runtime + web integration
- Event-triggered job start: [app/main.py](../app/main.py) line 350.
- Continuous fast-loop write and DB clip linking on completion: [app/main.py](../app/main.py) lines 537, 543.
- Secure dashboard retrieval route and HTML5 embed: [app/web/routes.py](../app/web/routes.py) lines 73, 388-400 and [app/web/templates/event.html](../app/web/templates/event.html) lines 60-62.

### 3. Why it changed

Directly stated reason:
- Resolve static 5-second truncation and represent true event duration: [docs/CLIP_RECORDING_LOG.md](../docs/CLIP_RECORDING_LOG.md) lines 22, 25.

Enabling prerequisite:
- Track-key propagation had to be fixed first (Iteration 11b), because clip binding requires a stable entity key crossing Observation -> Event -> persistence pipeline: [docs/TRACKING_INTEGRATION_LOG.md](../docs/TRACKING_INTEGRATION_LOG.md) lines 19, 23, 36, 65.

### 4. What files matter most

- [app/recording/clip_recorder.py](../app/recording/clip_recorder.py)
- [app/main.py](../app/main.py)
- [app/core/event_manager.py](../app/core/event_manager.py)
- [app/core/multi_event_manager.py](../app/core/multi_event_manager.py)
- [app/core/models.py](../app/core/models.py)
- [app/db/schema.sql](../app/db/schema.sql)
- [app/db/repo.py](../app/db/repo.py)
- [tests/test_clip_recorder.py](../tests/test_clip_recorder.py)
- [tests/test_event_manager.py](../tests/test_event_manager.py)
- [docs/CLIP_RECORDING_LOG.md](../docs/CLIP_RECORDING_LOG.md)
- [docs/TRACKING_INTEGRATION_LOG.md](../docs/TRACKING_INTEGRATION_LOG.md)

### 5. Useful code and test snippets

Snippet D3-1 from [app/recording/clip_recorder.py](../app/recording/clip_recorder.py)

~~~python
def update_track_states(self, states: dict[str, str]) -> None:
    for job in list(self.active_jobs.values()):
        if job.mode == "active" and job.track_key is not None:
            current_state = states.get(job.track_key)
            if current_state != "ACTIVE":
                job.mode = "tail"
                job.frames_remaining = self.post_frames
~~~

Snippet D3-2 from [app/main.py](../app/main.py)

~~~python
# slow loop side
events = event_manager.update(per_face_obs)
with clip_lock:
    clip_recorder.update_track_states(event_manager.track_states())
for event in events:
    with clip_lock:
        clip_recorder.on_event(event, frame)

# fast loop side
with clip_lock:
    completed_clips = clip_recorder.feed_frame(frame)
for ev_id, clip_path in completed_clips:
    updated = event_repo.update_event_clip(ev_id, rel_path)
~~~

Snippet D3-3 from [tests/test_clip_recorder.py](../tests/test_clip_recorder.py)

~~~python
def test_clip_dynamic_lifecycle_recording(...):
    recorder.update_track_states({"face_1": "ACTIVE"})
    ...
    assert recorder.active_jobs["dynamic-test"].mode == "active"

    recorder.update_track_states({"face_2": "ACTIVE"})  # face_1 missing
    assert recorder.active_jobs["dynamic-test"].mode == "tail"
~~~

Snippet D3-4 from [tests/test_clip_recorder.py](../tests/test_clip_recorder.py)

~~~python
def test_clip_max_duration_safety_cutoff(...):
    config.CLIP_MAX_DURATION_SECONDS = 3.0  # 30 frames MAX
    ...
    if i < 30:
        assert len(completed) == 0
    elif i == 30:
        assert len(completed) == 1
~~~

### 6. How to describe this in report language

- The redesign converts clip recording from trigger-window bounded capture to lifecycle-aware evidence capture: clip jobs remain open while entity state remains ACTIVE, then transition to deterministic post-tail closure, with global duration ceiling enforcing resource safety.
- This ties evidence duration to observed behavior without removing backward compatibility for non-tracked event paths.

### 7. Limitations and honest weaknesses

- INFERENCE: End-of-event transition latency is quantized by slow-loop cadence (`PROCESS_EVERY_N_FRAMES`) because state updates come from processed frames, not every captured frame: [app/config.py](../app/config.py) line 148 and [app/main.py](../app/main.py) lines 315, 550.
- INFERENCE: Hard max duration includes pre-buffer frames because `frames_written` starts at flushed pre-buffer count and shares the same cap counter: [app/recording/clip_recorder.py](../app/recording/clip_recorder.py) lines 99, 132-133, 147.
- Identity swap under centroid association can misattribute lifecycle-bound clips in crossing scenarios: [tests/test_multi_event_manager.py](../tests/test_multi_event_manager.py) lines 601, 655-658 and [docs/VALIDATION_REPORT.md](../docs/VALIDATION_REPORT.md) line 229.
- Track keys are session-scoped (`face_0`, `face_1`, ...) and not globally unique across restarts: [app/core/multi_event_manager.py](../app/core/multi_event_manager.py) line 249 and [docs/VALIDATION_REPORT.md](../docs/VALIDATION_REPORT.md) lines 229, 234.
- Synchronous writer overhead remains an acknowledged bottleneck: [docs/VALIDATION_REPORT.md](../docs/VALIDATION_REPORT.md) lines 206, 216.
- Test coverage gap for final DB clip-link path:
  - No direct `update_event_clip` assertion in test suite text search.
  - Main-loop tests disable clip path (`CLIP_ENABLED = False`) and use mocked recorder/repo: [tests/test_main_loop.py](../tests/test_main_loop.py) lines 74, 78, 120.
  - DB repo tests include snapshot path update test but no parallel clip update test: [tests/test_db_repo.py](../tests/test_db_repo.py) lines 355, 360.
- Codec parity gap between production and recorder tests:
  - Production default is `avc1`: [app/config.py](../app/config.py) line 165.
  - Most clip tests force `mp4v`: [tests/test_clip_recorder.py](../tests/test_clip_recorder.py) lines 24, 87, 125, 159, 214.
  - Browser-compat route rationale assumes `avc1`: [docs/DASHBOARD_UI_LOG.md](../docs/DASHBOARD_UI_LOG.md) lines 24, 26.
