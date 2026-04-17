# Section A — Core Systems and Architecture

This file is a source-material evidence pack for report writing. It is not a polished narrative chapter.

Evidence was extracted from implementation code, tests, and architecture/build logs in this repository, including:
- [app/main.py](../app/main.py)
- [app/config.py](../app/config.py)
- [app/core/models.py](../app/core/models.py)
- [app/core/event_manager.py](../app/core/event_manager.py)
- [app/core/multi_event_manager.py](../app/core/multi_event_manager.py)
- [app/ml/pipeline.py](../app/ml/pipeline.py)
- [app/ml/detector_scrfd.py](../app/ml/detector_scrfd.py)
- [app/ml/recogniser_arcface.py](../app/ml/recogniser_arcface.py)
- [app/ml/preprocess.py](../app/ml/preprocess.py)
- [app/enroll.py](../app/enroll.py)
- [app/services/enrollment_service.py](../app/services/enrollment_service.py)
- [app/db/repo.py](../app/db/repo.py)
- [app/db/schema.sql](../app/db/schema.sql)
- [app/camera/base.py](../app/camera/base.py)
- [app/camera/webcam.py](../app/camera/webcam.py)
- [app/camera/rtsp.py](../app/camera/rtsp.py)
- [app/tracking/base.py](../app/tracking/base.py)
- [app/tracking/tracking_manager.py](../app/tracking/tracking_manager.py)
- [tests/test_ml_stub.py](../tests/test_ml_stub.py)
- [tests/test_ml_logic.py](../tests/test_ml_logic.py)
- [tests/test_enrollment_service.py](../tests/test_enrollment_service.py)
- [tests/test_event_manager.py](../tests/test_event_manager.py)
- [tests/test_multi_event_manager.py](../tests/test_multi_event_manager.py)
- [tests/test_main_loop.py](../tests/test_main_loop.py)
- [tests/test_camera_rtsp.py](../tests/test_camera_rtsp.py)
- [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)
- [docs/BUILD_LOG.md](../docs/BUILD_LOG.md)
- [docs/ML_INTEGRATION_LOG.md](../docs/ML_INTEGRATION_LOG.md)
- [docs/MULTI_FACE_EVENT_HANDLING_LOG.md](../docs/MULTI_FACE_EVENT_HANDLING_LOG.md)
- [docs/TRACKING_INTEGRATION_LOG.md](../docs/TRACKING_INTEGRATION_LOG.md)
- [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)
- [docs/ITERATION_2_REPORT.md](../docs/ITERATION_2_REPORT.md)
- [reports/live_stream_optimization_report.md](live_stream_optimization_report.md)
- [reports/iteration_9_11_evaluation.md](iteration_9_11_evaluation.md)
- [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)

Where repository evidence conflicts with prose docs, code is treated as ground truth.

---

## A1. Initial SecureVision System Design

### Core architecture evidence

System purpose:
- Local-first smart CCTV application that detects and recognises faces from camera frames, classifies outcomes as authorised or unauthorised, and persists security events.

Top-level architecture (implied diagram in words):
- Configuration layer loads all runtime flags and thresholds from environment-backed constants.
- Camera adapter layer abstracts frame source behind a common CameraSource interface.
- ML adapter layer exposes one stable API, process_frame, producing FrameResult.
- Repository layer encapsulates SQL and exposes person/event CRUD methods.
- Orchestration layer wires all components and drives the runtime loop.

Main runtime components:
- [app/config.py](../app/config.py): central configuration and feature flags.
- [app/camera/base.py](../app/camera/base.py), [app/camera/webcam.py](../app/camera/webcam.py), [app/camera/rtsp.py](../app/camera/rtsp.py): camera abstraction plus concrete adapters.
- [app/ml/pipeline.py](../app/ml/pipeline.py): stable ML facade.
- [app/core/models.py](../app/core/models.py): shared dataclass contracts.
- [app/db/migrations.py](../app/db/migrations.py), [app/db/repo.py](../app/db/repo.py): persistence and DB lifecycle.
- [app/main.py](../app/main.py): orchestration entry point.

Data flow (initial baseline and then hardened form):
- Frame source provides BGR frame.
- FacePipeline processes frame and returns FrameResult.
- Main loop uses FrameResult for overlays, event logic, and persistence.
- Enrolment path writes enrolled identities and embeddings to SQLite, then pipeline consumes enrolled provider output.

Initial design choices supported by code/docs:
- Stable ML boundary: one method process_frame used everywhere.
- Config-driven system: thresholds and feature flags in config module with SV_* env overrides.
- SQL isolation: repository pattern keeps SQL out of main and ml modules.
- Graceful degradation: missing ONNX models do not crash application; ML-disabled mode remains operational.

### 1. What existed before

- Per [docs/BUILD_LOG.md](../docs/BUILD_LOG.md), earliest state was boilerplate stubs only.
- Iteration 1 introduced a single-loop webcam + ML pipeline with single-face emphasis.
- Iteration 2 replaced single-file embedding workflow with SQLite-backed enrolled identities and enrollment CLI.

### 2. What changed

- Architecture moved from direct file-based enrolment and simpler flow to repository-driven, dependency-injected design.
- FacePipeline became the stable adapter boundary for downstream modules.
- Datamodel contract in [app/core/models.py](../app/core/models.py) expanded to carry detection, recognition, and status metadata.

### 3. Why it changed

- To avoid tight coupling between ML and storage concerns.
- To support iterative expansion (events, multi-face, tracking, dashboard) without repeatedly breaking the same interfaces.
- To create a maintainable architecture where major subsystem changes are additive, not destructive.

### 4. What files matter most

- [app/main.py](../app/main.py)
- [app/ml/pipeline.py](../app/ml/pipeline.py)
- [app/core/models.py](../app/core/models.py)
- [app/db/repo.py](../app/db/repo.py)
- [app/db/migrations.py](../app/db/migrations.py)
- [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)
- [docs/BUILD_LOG.md](../docs/BUILD_LOG.md)
- [docs/ITERATION_2_REPORT.md](../docs/ITERATION_2_REPORT.md)
- [tests/test_ml_stub.py](../tests/test_ml_stub.py)
- [tests/test_db_repo.py](../tests/test_db_repo.py)

### 5. Useful code snippets (genuinely useful)

Snippet A1-1: startup dependency wiring and pipeline injection from [app/main.py](../app/main.py)

~~~python
conn = init_db(config.DB_PATH)
repo = SQLitePersonRepository(conn)
event_repo = SQLiteEventRepository(conn)
enrolled_provider = make_enrolled_provider(repo)

pipeline = FacePipeline(enrolled_provider=enrolled_provider)
~~~

Snippet A1-2: stable ML interface and graceful fallback from [app/ml/pipeline.py](../app/ml/pipeline.py)

~~~python
def process_frame(self, frame: np.ndarray) -> FrameResult:
    if not self.ml_enabled or self._detector is None:
        return FrameResult(
            ml_enabled=False,
            detection_enabled=self.detection_enabled,
            recognition_enabled=self.recognition_enabled,
            message=(
                f"ML disabled — detection={self.detection_enabled}"
                f"  recognition={self.recognition_enabled}"
            ),
        )
~~~

Snippet A1-3: SQL decoupling by provider callable from [app/db/repo.py](../app/db/repo.py)

~~~python
def make_enrolled_provider(repo: SQLitePersonRepository):
    def _provider():
        return repo.get_all()
    return _provider
~~~

### 6. How I could describe this in report language

- The initial SecureVision design established strict module boundaries early: camera ingestion, ML inference, domain models, and persistence were separated and connected through explicit contracts.
- The most important architectural decision was introducing FacePipeline as a stable adapter and feeding it enrolled identities via dependency injection, allowing storage changes without touching ML internals.
- This made subsequent iterations (eventing, multi-face handling, tracking keys, and dashboard process split) evolutionary rather than a rewrite.

### 7. Limitations and honest weaknesses

- Import-time configuration: settings are materialised in module globals at import time, which complicates dynamic runtime reconfiguration and increases test monkeypatching burden.
- Early design history is partly reconstructed from logs, not full git blame chronology. Exact commit-to-commit rationale is only as complete as docs.
- Single-entity assumptions were embedded in early event logic and had to be wrapped later for multi-entity support.
- Initial system was compute-centric; no explicit architecture for distributed scaling, queue brokers, or horizontally scaled workers.

---

## A2. Real-Time Video Processing Pipeline Implementation

### Core architecture evidence

How the frame loop works now:
- [app/main.py](../app/main.py) runs a two-thread design.
- Fast thread (main): camera read, lightweight overlay draw, shared-memory publish, preview.
- Slow daemon thread: ML inference, event generation, DB writes, alert dispatch, recording triggers.

How frames move through the system:
- Camera read in fast loop.
- Every Nth frame copied to bounded queue for slow processing.
- Slow loop processes queued frame and atomically updates overlay list.
- Fast loop draws latest overlays on fresh frames and publishes live image.

Fast vs slow responsibilities:
- Fast path prioritises frame freshness and UI responsiveness.
- Slow path performs CPU and I/O-heavy operations and is isolated from camera cadence.

Threading, queueing, and pipeline structure:
- queue.Queue with maxsize=1 to prevent backlog growth.
- Frame drops occur intentionally when slow consumer lags.
- Shared data exchange by atomic reference swap for overlays.
- Shared memory block for live-frame handoff to dashboard process.

Why designed this way:
- [reports/live_stream_optimization_report.md](live_stream_optimization_report.md) states previous synchronous loop starved camera refresh and caused severe dashboard lag.
- Decoupling producer and consumer solved low effective FPS while preserving existing ML/event stack.

### 1. What existed before

- Earlier architecture (Iteration 1/2) used a mostly synchronous frame loop where capture, inference, and side effects were tightly sequenced.
- [docs/BUILD_LOG.md](../docs/BUILD_LOG.md) indicates progressive additions (events, snapshots, clips, alerts), which increased per-frame work in one loop.

### 2. What changed

- Runtime was split into FAST and SLOW threads in [app/main.py](../app/main.py).
- Bounded queue and stale-frame dropping introduced for backpressure control.
- Shared memory publish replaced file-only handoff for live dashboard path.

### 3. Why it changed

- To stop blocking operations (ML, DB, clips, network/email) from reducing camera refresh frequency.
- To keep live view responsive even when inference or persistence throughput dips.

### 4. What files matter most

- [app/main.py](../app/main.py)
- [app/camera/base.py](../app/camera/base.py)
- [app/camera/webcam.py](../app/camera/webcam.py)
- [app/camera/rtsp.py](../app/camera/rtsp.py)
- [app/config.py](../app/config.py)
- [reports/live_stream_optimization_report.md](live_stream_optimization_report.md)
- [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md)
- [docs/RTSP_INTEGRATION_LOG.md](../docs/RTSP_INTEGRATION_LOG.md)
- [tests/test_main_loop.py](../tests/test_main_loop.py)
- [tests/test_camera_rtsp.py](../tests/test_camera_rtsp.py)

### 5. Useful code snippets (genuinely useful)

Snippet A2-1: bounded queue and intentional drop policy from [app/main.py](../app/main.py)

~~~python
frame_queue: queue.Queue = queue.Queue(maxsize=1)

if frame_counter % config.PROCESS_EVERY_N_FRAMES == 0:
    try:
        frame_queue.put_nowait(frame.copy())
    except queue.Full:
        fast_diag.tick_queue_drop()
~~~

Snippet A2-2: slow-thread responsibilities from [app/main.py](../app/main.py)

~~~python
result = pipeline.process_frame(frame)

events = event_manager.update(per_face_obs)
for event in events:
    event_repo.add_event(event)
    if config.ALERTS_ENABLED and event.status == "unauthorised":
        alert_service.trigger_unauthorised_alert(event)
~~~

Snippet A2-3: shared-memory live frame publish from [app/main.py](../app/main.py)

~~~python
success, buffer = cv2.imencode('.jpg', display_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
if success:
    payload = buffer.tobytes()
    if size < SHM_TOTAL_SIZE - SHM_HEADER_SIZE:
        live_shm.buf[0] = 1
        live_shm.buf[1:5] = size.to_bytes(4, 'little')
        live_shm.buf[SHM_HEADER_SIZE:SHM_HEADER_SIZE+size] = payload
        live_shm.buf[0] = 0
~~~

### 6. How I could describe this in report language

- The final runtime adopts a producer-consumer model: camera ingestion remains non-blocking while heavy ML and I/O tasks execute in a background worker thread.
- Backpressure is explicit and intentional through a single-slot queue that discards stale frames, prioritising recency over completeness.
- This design accepts controlled data loss to preserve operational responsiveness and avoid unbounded latency growth.

### 7. Limitations and honest weaknesses

- Frame skipping is structural: PROCESS_EVERY_N_FRAMES and queue drop mean some transient events can be missed.
- Shared memory buffer has hard size ceiling; oversized JPEGs are dropped.
- RTSP latency remains materially higher than local webcam due to network and decode buffering, even after architecture improvements.
- Current implementation shares one SQLite connection across multi-threaded operations; this can become a contention/race risk under heavier write concurrency.
- No evidence of a reusable benchmark harness on main branch; evaluation is test-driven and instrumented, not full formal benchmarking.

---

## A3. Face Detection and Recognition Pipeline Integration

### Core architecture evidence

Detector and recogniser components:
- SCRFD detector in [app/ml/detector_scrfd.py](../app/ml/detector_scrfd.py).
- ArcFace recogniser in [app/ml/recogniser_arcface.py](../app/ml/recogniser_arcface.py).
- Orchestration in [app/ml/pipeline.py](../app/ml/pipeline.py).
- Preprocessing and alignment in [app/ml/preprocess.py](../app/ml/preprocess.py).

How detection, embedding, and matching work together:
- Frame is optionally enhanced for detection-only path based on lighting gate.
- SCRFD returns detections and landmarks; largest face remains primary for backward compatibility.
- Recognition runs per detection (multi-face iteration), aligns/crops face, computes embedding, and compares against enrolled template embeddings.
- Results stored in FrameResult with detections and recognitions aligned index-for-index.

How enrolment ties into runtime recognition:
- Enrolment service builds validated embeddings and writes to DB.
- Raw shots go into person_embeddings; template embedding in persons table is recomputed.
- Pipeline consumes enrolled persons via provider callable from repository.

How outputs are represented in models:
- Detection: bbox + confidence + optional keypoints.
- RecognitionResult: name, score, is_match.
- FrameResult: detections list, recognitions list, primary detection, status flags, message.

### 1. What existed before

- Iteration 1 had single-face-oriented detection/recognition flow and file-based enrolment artifacts.
- Per [docs/BUILD_LOG.md](../docs/BUILD_LOG.md) and [docs/ITERATION_2_REPORT.md](../docs/ITERATION_2_REPORT.md), pipeline then moved to provider-fed SQLite identities.

### 2. What changed

- Iteration 7 preserved all detections in FrameResult instead of collapsing to one face.
- Iteration 8 introduced multi-face recognition list aligned to detections.
- Adaptive detection-only lighting compensation was integrated via preprocess selection path.
- Iteration 13 introduced atomic multi-capture enrolment thresholding in enrollment_service.

### 3. Why it changed

- To remove brittle single-face assumptions while preserving backward compatibility for consumers still using primary face semantics.
- To improve recognition quality through template formation from multiple captures.
- To improve detection robustness in backlit scenes without paying full cost of always running multiple detector passes.

### 4. What files matter most

- [app/ml/pipeline.py](../app/ml/pipeline.py)
- [app/ml/detector_scrfd.py](../app/ml/detector_scrfd.py)
- [app/ml/recogniser_arcface.py](../app/ml/recogniser_arcface.py)
- [app/ml/preprocess.py](../app/ml/preprocess.py)
- [app/core/models.py](../app/core/models.py)
- [app/services/enrollment_service.py](../app/services/enrollment_service.py)
- [app/enroll.py](../app/enroll.py)
- [app/db/repo.py](../app/db/repo.py)
- [app/db/schema.sql](../app/db/schema.sql)
- [docs/ML_INTEGRATION_LOG.md](../docs/ML_INTEGRATION_LOG.md)
- [tests/test_ml_logic.py](../tests/test_ml_logic.py)
- [tests/test_ml_stub.py](../tests/test_ml_stub.py)
- [tests/test_enrollment_service.py](../tests/test_enrollment_service.py)

### 5. Useful code snippets (genuinely useful)

Snippet A3-1: detection-only enhancement gate from [app/ml/pipeline.py](../app/ml/pipeline.py)

~~~python
detection_frame, lighting = select_detection_frame(frame)
detections = self._detector.detect(detection_frame)

if not detections:
    return FrameResult(
        detections=[],
        ml_enabled=True,
        detection_enabled=self.detection_enabled,
        recognition_enabled=self.recognition_enabled,
        message=("No faces detected ..."),
    )
~~~

Snippet A3-2: multi-face recognition loop from [app/ml/pipeline.py](../app/ml/pipeline.py)

~~~python
recognitions: list[RecognitionResult | None] = []
if self._recogniser is not None:
    for det in detections:
        rec = self._recognise_one(frame, det)
        recognitions.append(rec)
    result.recognitions = recognitions
~~~

Snippet A3-3: enrolment minimum-capture enforcement and template rebuild from [app/services/enrollment_service.py](../app/services/enrollment_service.py)

~~~python
if len(valid_embeddings) < min_captures:
    return EnrollmentResult(success=False, message=err_msg)

for emb in valid_embeddings:
    emb_repo.add_embedding(person_id, emb)

all_embeddings = emb_repo.get_embeddings(person_id)
template = make_template(all_embeddings)
person_repo.update_embedding(person_id, template)
~~~

### 6. How I could describe this in report language

- SecureVision integrates SCRFD detection and ArcFace recognition behind a single orchestration facade that emits typed frame-level contracts.
- The pipeline evolved from primary-face-centric behavior to full multi-face processing while preserving backward compatibility for legacy consumers.
- Enrolment was upgraded from one-shot storage to quality-gated multi-capture template generation, directly improving runtime identity matching stability.

### 7. Limitations and honest weaknesses

- Recognition cost scales linearly with face count per frame.
- Matching uses direct cosine comparison over enrolled templates, with no indexing acceleration.
- In current main loop, Observation.person_id is left as None, so event records rely on person_name and score rather than stable DB id mapping.
- Lighting heuristic is intentionally simple and can fail on complex illumination conditions.
- Unknown handling includes None recognition slots for crop/embedding failures; this is safe but can reduce confidence in edge cases.
- No anti-spoofing or liveness checks are visible in this pipeline.

---

## A4. Multi-Entity Tracking and Event Management System

### Core architecture evidence

How single-face logic evolved:
- Baseline EventManager in [app/core/event_manager.py](../app/core/event_manager.py) is a single-entity state machine.
- Iteration 9 introduced MultiEntityEventManager wrapper in [app/core/multi_event_manager.py](../app/core/multi_event_manager.py), one EventManager per tracked entity.
- This preserved proven single-target logic and avoided rewriting state machine internals.

How observations, tracks, and events are represented:
- Observation includes timestamp, face_present, identity hints, bbox, and optional track_key.
- Event includes status, person metadata, score, bbox_json, and track_key.
- MultiEntityEventManager holds tracked entities with track key, per-track EventManager, last centroid, and frames_since_seen.

Role of EventManager and MultiEntityEventManager:
- EventManager handles lifecycle transitions and confirmation/cooldown semantics.
- MultiEntityEventManager handles association, track creation, absent updates, stale pruning, and aggregates events list per frame.

How track_key continuity is handled:
- Track keys are generated as face_0, face_1, etc.
- Incoming detections are greedily associated by nearest centroid under threshold.
- track_key is written into Observation and propagated into emitted Event.

How events are emitted and persisted:
- EventManager emits on confirmation transition into ACTIVE.
- Main loop persists events to events table and links snapshot/clip artifacts.

Implied architecture diagram in words:
- FrameResult detections become per-face Observation list.
- MultiEntityEventManager routes each observation to per-track EventManager.
- Returned Event objects are persisted by repository and used for alerts/recording actions.

### 1. What existed before

- Single-target EventManager only, using primary face semantics.
- No per-entity track key propagation in Event model initially.
- tracking package remained stubbed and not functionally integrated.

### 2. What changed

- Added multi-entity orchestration with centroid association and max-entity cap.
- Added track_key propagation from Observation to Event and DB schema.
- Main runtime switched from single observation update to list-based per-face update.

### 3. Why it changed

- To support simultaneous faces with independent confirmation, cooldown, and event emission.
- To fix alert suppression for unknown entities by using stable per-entity keys instead of per-event UUIDs.
- To preserve existing tested EventManager behavior while extending capability.

### 4. What files matter most

- [app/core/event_manager.py](../app/core/event_manager.py)
- [app/core/multi_event_manager.py](../app/core/multi_event_manager.py)
- [app/core/models.py](../app/core/models.py)
- [app/main.py](../app/main.py)
- [app/db/schema.sql](../app/db/schema.sql)
- [app/db/migrations.py](../app/db/migrations.py)
- [app/db/repo.py](../app/db/repo.py)
- [docs/MULTI_FACE_EVENT_HANDLING_LOG.md](../docs/MULTI_FACE_EVENT_HANDLING_LOG.md)
- [docs/TRACKING_INTEGRATION_LOG.md](../docs/TRACKING_INTEGRATION_LOG.md)
- [reports/iteration_9_11_evaluation.md](iteration_9_11_evaluation.md)
- [tests/test_event_manager.py](../tests/test_event_manager.py)
- [tests/test_multi_event_manager.py](../tests/test_multi_event_manager.py)
- [app/tracking/base.py](../app/tracking/base.py)
- [app/tracking/tracking_manager.py](../app/tracking/tracking_manager.py)

### 5. Useful code snippets (genuinely useful)

Snippet A4-1: state-machine event emission with threshold and track key from [app/core/event_manager.py](../app/core/event_manager.py)

~~~python
status = (
    "authorised"
    if (
        self._best_name is not None
        and self._best_score >= self._score_threshold
    )
    else "unauthorised"
)
return Event(
    event_id=str(uuid.uuid4()),
    status=status,
    person_name=self._best_name,
    score=self._best_score if self._best_score > 0 else None,
    track_key=self._track_key,
)
~~~

Snippet A4-2: per-face orchestration and track assignment from [app/core/multi_event_manager.py](../app/core/multi_event_manager.py)

~~~python
matched, unmatched_obs = self._associate(observations)

for track_key, obs in matched:
    track = self._tracks[track_key]
    track.last_centroid = _bbox_centroid(obs.bbox)
    obs.track_key = track_key
    event = track.event_manager.update(obs)

for obs in unmatched_obs:
    track_key = self._make_track_key()
    em = EventManager(**self._em_kwargs)
    obs.track_key = track_key
~~~

Snippet A4-3: runtime persistence and side effects from [app/main.py](../app/main.py)

~~~python
events = event_manager.update(per_face_obs)
for event in events:
    event_repo.add_event(event)
    snapshot_path = snapshot_recorder.on_event(event, frame)
    if config.CLIP_ENABLED:
        with clip_lock:
            clip_recorder.on_event(event, frame)
~~~

### 6. How I could describe this in report language

- Multi-entity support was achieved through a wrapper orchestration pattern, not by rewriting the existing event state machine.
- Each tracked face receives an independent EventManager instance, preserving clean lifecycle semantics while enabling concurrent event timelines.
- track_key propagation closes the loop between geometric association, event identity, persistence, and suppression logic.

### 7. Limitations and honest weaknesses

- Centroid-only association is weak under crossing trajectories and can swap identities.
- Track keys are session-scoped and reset on application restart.
- app/tracking modules are still stubs; no visual tracker (for example CSRT/KCF) is integrated in production path.
- Ghost detections can temporarily consume track slots until stale pruning.
- Event quality depends on recognition score quality and best-score bookkeeping, which can be sensitive to brief false positives.

---

## Cross-cutting evidence notes for report writer

- Use [docs/BUILD_LOG.md](../docs/BUILD_LOG.md) and [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) for iteration chronology, but anchor technical claims in code and tests.
- For performance narrative, treat [reports/live_stream_optimization_report.md](live_stream_optimization_report.md) and [reports/rtsp_vs_webcam_evaluation.md](rtsp_vs_webcam_evaluation.md) as implementation notes, not controlled academic benchmark papers.
- Explicit unknown: this evidence pack did not reconstruct full git commit diffs for every iteration. Historical claims are based on repository docs and current code state.
