# SecureVision Build Log

## 2026-03 — Iteration 5: Local Flask Dashboard MVP (In Progress)

### Purpose
Add a local-first browser dashboard without redesigning the camera/ML/event
pipeline.

### What Changed So Far
- Added `admin_users` table explicitly in `app/db/schema.sql`.
- Added idempotent admin bootstrap in `app/db/migrations.py`.
- Removed hardcoded default dashboard credentials; bootstrap admin now
  requires `SV_BOOTSTRAP_ADMIN_USERNAME` and `SV_BOOTSTRAP_ADMIN_PASSWORD`.
- Normalized snapshot paths to POSIX form on write (`app/main.py`) and added
  separator-normalized resolving in dashboard route (`app/web/routes.py`) to
  avoid Windows path separator issues.
- Added dashboard-focused repository methods in `app/db/repo.py`:
  `count_persons`, `list_person_summaries`, `get_event_by_id`, `count_events`,
  and `AdminRepository`.
- Added dashboard config in `app/config.py`:
  `SV_DASHBOARD_HOST`, `SV_DASHBOARD_PORT`, `SV_FLASK_SECRET_KEY`.
- Added shared enrollment orchestration in
  `app/services/enrollment_service.py` for Flask + CLI reuse.
- Implemented Flask dashboard core:
  `app/web/app_factory.py`, `app/web/auth.py`, `app/web/routes.py`.
- Added templates and CSS in `app/web/templates/` and `app/web/static/style.css`.
- Added dashboard entry point in `app/web_run.py`.
- Added `tests/test_dashboard.py` covering auth, events, event detail,
  persons page, and snapshot path restrictions.
- Clarified two-threshold semantics without DB schema changes:
  recognition match threshold and separate authorisation threshold.
- Added explicit config names `RECOGNITION_MATCH_THRESHOLD` and
  `AUTHORISATION_THRESHOLD` with backward-compatible aliases.
- Updated dashboard presentation to derive display-only match state from
  existing event fields (`status`, `person_name`, `score`) and show explicit
  low-confidence explanation for named but unauthorised events.
- Added tests for threshold edge cases and non-misleading template rendering.

### Scope Guardrails Kept
- No clips added.
- No ML pipeline redesign.
- No SQL in Flask routes.
- Snapshot serving restricted to snapshots directory only.
- Persons page uses safe metadata only (no raw embedding blobs).

## 2026-03 — Iteration 4: Event Snapshot Evidence (Complete)

### Purpose
Add event-triggered snapshot evidence capture and link saved image paths to
the existing SQLite `events` rows. This iteration intentionally excludes
clip recording/ring buffer logic.

### What Changed
- **recording/base.py** — Replaced placeholder `save()` API with a minimal
  event-oriented `Recorder.on_event(event, frame)` interface.
- **recording/snapshot_recorder.py** — Implemented JPEG snapshot capture:
  creates output directories, supports date subfolders, optional bbox+label
  overlay, configurable quality, and robust failure handling.
- **db/repo.py** — Added `SQLiteEventRepository.update_event_snapshot()` to
  link saved snapshot file path after event insert.
- **main.py** — Wired orchestration flow:
  1) persist event,
  2) save snapshot,
  3) update event row with `snapshot_path`,
  4) emit clear logs for success/failure.
- **config.py** — Added snapshot config flags:
  `SV_DRAW_BBOX_ON_SNAPSHOT`, `SV_SNAPSHOT_JPEG_QUALITY`,
  `SV_SNAPSHOT_SUBDIR_BY_DATE`, `SV_SAVE_RAW_SNAPSHOT`.
- **tests/test_snapshot_recorder.py** — New focused tests for file save,
  directory creation, bbox overlay tolerance, and empty-frame handling.
- **tests/test_db_repo.py** — Added test for event snapshot-path update.
- **docs/ARCHITECTURE.md / docs/SETUP.md** — Documented Iteration 4 evidence
  flow and configuration.

### Validation
```
Iteration 4 tests added for recorder + DB path update.
```

## 2026-03 — Adaptive Detection-Only Lighting Compensation (Complete)

### Purpose
Improve face detection stability in strong backlighting/high-contrast scenes
without broad architecture changes and without default double detection passes.

### File-by-file Progress

- **app/config.py**
  Added adaptive preprocessing feature flags and thresholds with `SV_*`
  environment overrides:
  `DETECTION_ADAPTIVE_PREPROCESS_ENABLED`, `DETECTION_PREPROCESS_MODE`,
  `BRIGHT_GLOBAL_THRESHOLD`, `DARK_CENTER_THRESHOLD`,
  `BACKLIT_SCORE_THRESHOLD`, `CLAHE_CLIP_LIMIT`,
  `CLAHE_TILE_GRID_SIZE`, `GAMMA_VALUE`.

- **app/ml/preprocess.py**
  Added isolated lighting and enhancement utilities:
  `LightingAssessment`, `assess_backlighting`,
  `apply_clahe_for_detection`, `apply_gamma_for_detection`,
  `apply_detection_enhancement`, `select_detection_frame`.
  This keeps adaptive logic local to ML preprocessing.

- **app/ml/pipeline.py**
  Added orchestration hook before detector call:
  pipeline selects raw/enhanced frame for detection only via
  `select_detection_frame(frame)`. Recognition/alignment path continues to use
  the original frame.

- **tests/test_ml_logic.py**
  Added pure-logic tests for:
  1) lighting assessment decisions on synthetic frames,
  2) CLAHE/gamma shape and dtype preservation,
  3) pipeline routing to enhanced/raw detection input.

- **docs/ML_INTEGRATION_LOG.md**
  Documented adaptive detection-only path, rationale, and known heuristic
  limitations.

- **docs/SETUP.md**
  Updated model filenames and expanded env var reference with adaptive
  preprocessing controls and current defaults.

### Validation

```
tests/test_ml_logic.py: 36 passed
```

## 2026-03 — Iteration 3: Level 2 Event Manager (Complete)

### Purpose
Implement event logging to SQLite — a state machine that confirms face
presence via a K-of-N rolling window, emits `Event` objects, and persists
them to the `events` table.  No dashboard, no snapshots, no clips, no
tracking, no RTSP.

### Architecture Decisions
- **EventManager is pure logic** — lives in `core/event_manager.py`, receives
  `Observation` objects, returns `Optional[Event]`.  No I/O, no SQL.
- **Single-target MVP** — one person tracked at a time.  Multi-target
  tracking deferred to Iteration 6.
- **State machine**: IDLE → CONFIRMING → ACTIVE → COOLDOWN → IDLE.
- **K-of-N confirmation** — prevents single-frame noise from firing events.
- **Cooldown** — prevents rapid re-fire after an event closes.
- **UUID-4 event IDs** — future-proof for distributed systems / dashboard.
- **SQL stays in `db/repo.py`** — `SQLiteEventRepository.add_event()` and
  `list_events()` encapsulate all event SQL.

### What Changed
- **core/models.py** — Added `Observation` and `Event` dataclasses.  Added
  `BoundingBox.to_json()` / `from_json()` for DB serialisation.
- **core/event_manager.py** — **NEW** Level 2 state machine with 4 states,
  rolling window, best-score tracking, cooldown timer.
- **config.py** — Added `EVENT_CONFIRM_WINDOW_N` (5), `EVENT_CONFIRM_MIN_K`
  (3), `EVENT_LOST_FRAMES` (5), `EVENT_COOLDOWN_SECONDS` (10.0),
  `EVENT_SCORE_THRESHOLD` (0.4).  All with `SV_*` env overrides.
- **db/schema.sql** — Redesigned `events` table: TEXT PK (UUID), `status`,
  `person_name`, `score`, `bbox_json`, `snapshot_path`, `clip_path`.
  Added `idx_events_status` index.
- **db/repo.py** — Added `SQLiteEventRepository` with `add_event(Event)` and
  `list_events(limit, status)`.  Imported `Event` model.
- **main.py** — Wired `EventManager` + `SQLiteEventRepository`.  Builds
  `Observation` from `FrameResult` on each processed frame.  Logs events.
  Updated banner to "Iteration 3".
- **tests/test_event_manager.py** — **NEW** 18 tests: IDLE, CONFIRMING,
  ACTIVE, COOLDOWN, best-score tracking, UUID/timestamp validation.
- **tests/test_db_repo.py** — Added 6 event repository tests: add/list,
  limit, ordering, status filter, nullable fields.
- **docs/ARCHITECTURE.md** — Added Iteration 3 data flow diagram,
  EventManager section, updated module map and iteration table.
- **docs/SETUP.md** — Added 5 event config vars, "Inspect Events" section.

### Files Touched
```
app/core/models.py             (MODIFIED)
app/core/event_manager.py      (NEW)
app/config.py                  (MODIFIED)
app/db/schema.sql              (MODIFIED)
app/db/repo.py                 (MODIFIED)
app/main.py                    (MODIFIED)
tests/test_event_manager.py    (NEW)
tests/test_db_repo.py          (MODIFIED)
docs/ARCHITECTURE.md           (MODIFIED)
docs/SETUP.md                  (MODIFIED)
docs/BUILD_LOG.md              (MODIFIED)
```

### Test Results
```
55 passed in 2.35s  (31 existing + 18 event manager + 6 event DB)
```

### Next Steps
- **Iteration 4**: Snapshot + clip recording on event emission

---

## 2026-03 — Iteration 2: Refinement Pass (Complete)

### Purpose
Remove .npy legacy, add headless preview support, improve ML status
reporting, harden enrollment script, and sync documentation.
No new features.  No behaviour changes to the webcam pipeline or DB layer.

### What Changed
- **config.py** — Removed `ENROLLED_DIR`, `ENROLLED_EMBEDDING_PATH`,
  `ENROLLED_NAME`.  Added `SHOW_PREVIEW` and `PREVIEW_WINDOW_NAME`.
- **core/models.py** — Added `detection_enabled` and `recognition_enabled`
  fields to `FrameResult` (backward-compatible defaults).
- **ml/pipeline.py** — Exposed `detection_enabled` / `recognition_enabled`
  properties.  All `FrameResult` returns now populate the new fields.
  Updated `__init__` logging to reflect per-model status.
- **ml/recogniser_arcface.py** — Removed legacy `load_enrolled_embedding()`.
- **main.py** — Guarded cv2 preview behind `SHOW_PREVIEW`.  Removed unused
  `time` import and stale `config.ENROLLED_DIR` reference.
- **enroll.py** — Removed unused `sqlite3` and `select_largest_face` imports.
  Wrapped DB connection in `try/finally` for guaranteed close.
- **tests/test_ml_stub.py** — Removed `TestLoadEnrolledEmbedding` (3 tests).
  Added assertions for `detection_enabled` / `recognition_enabled`.
  Removed unused `EnrolledPerson` import.  Test count: 34 → 31.
- **db/repo.py** — Hardened `_row_to_person()` with `dim > 0` guard, dtype
  allowlist, and logging warnings.  Added threading/lifecycle docstring.
- **docs/ARCHITECTURE.md** — Updated `FrameResult` contract with new fields.
  Added "Headless Mode", "Early events Table", and "SQLite Threading Note".
- **docs/SETUP.md** — Added `SV_SHOW_PREVIEW` / `SV_PREVIEW_WINDOW_NAME`
  to config table.  Added headless mode and developer tools sections.
- **.gitignore** — Removed `data/enrolled/*.npy` pattern.
- **data/enrolled/.gitkeep** — Updated comment.
- **requirements-dev.txt** — **NEW** optional dev dependency (ruff).

### Files Touched
```
app/config.py                  (MODIFIED)
app/core/models.py             (MODIFIED)
app/ml/pipeline.py             (MODIFIED)
app/ml/recogniser_arcface.py   (MODIFIED)
app/main.py                    (MODIFIED)
app/enroll.py                  (MODIFIED)
app/db/repo.py                 (MODIFIED)
tests/test_ml_stub.py          (MODIFIED)
docs/ARCHITECTURE.md           (MODIFIED)
docs/SETUP.md                  (MODIFIED)
docs/BUILD_LOG.md              (MODIFIED)
.gitignore                     (MODIFIED)
data/enrolled/.gitkeep         (MODIFIED)
requirements-dev.txt           (NEW)
```

### Next Steps
- **Iteration 3**: Event logging — persist recognition events to `events` table

---

## 2026-02 — Iteration 2: SQLite Persistence + Enrollment (Complete)

### What Changed
- **db/schema.sql** — Redesigned `persons` table: added `embedding_dim`,
  `dtype`, ISO 8601 `created_at`, dropped `updated_at`.
- **db/migrations.py** — `init_db()` creates parent dirs, applies schema,
  sets `PRAGMA journal_mode=WAL` and `foreign_keys=ON`.
- **db/repo.py** — `InMemoryPersonRepository` upgraded with full CRUD.
  `SQLitePersonRepository` fully implemented: `get_all`, `get_by_id`,
  `get_by_name`, `add_person`, `update_embedding`, `delete_person`.
  `make_enrolled_provider()` factory for pipeline injection.
- **config.py** — Added `DB_PATH` setting (`data/db/securevision.sqlite`).
- **ml/pipeline.py** — Replaced hardcoded `.npy` loader with injectable
  `enrolled_provider` callable.  New `reload_enrolled()` method for live
  gallery refresh.  **No SQL in ml/.**
- **enroll.py** — **NEW** CLI enrollment tool with argparse.  Loads image,
  detects single face (rejects 0 or >1), embeds via ArcFace, stores in DB.
  Supports re-enrollment (updates embedding for existing name).
- **main.py** — Wired up DB init → repo → enrolled_provider → pipeline.
  DB connection closed in finally block.  **No SQL in main.py.**
- **tests/test_db_repo.py** — **NEW** 25+ tests: init_db pragmas, CRUD for
  both InMemory and SQLite repos, embedding round-trip, provider factory.

### Architecture Rule Enforced
```
SQL lives ONLY in:  db/repo.py  +  db/migrations.py
Pipeline gets data via:  enrolled_provider() callable
main.py orchestrates via:  init_db → repo → make_enrolled_provider → FacePipeline
```

### Files Touched
```
app/db/schema.sql          (MODIFIED)
app/db/migrations.py       (MODIFIED)
app/db/repo.py             (MODIFIED)
app/config.py              (MODIFIED)
app/ml/pipeline.py         (MODIFIED)
app/main.py                (MODIFIED)
app/enroll.py              (NEW)
tests/test_db_repo.py      (NEW)
docs/BUILD_LOG.md          (MODIFIED)
docs/ARCHITECTURE.md       (MODIFIED)
docs/SETUP.md              (MODIFIED)
```

### Next Steps
- **Iteration 3**: Event logging — persist recognition events to `events` table

---

## 2026-02 — Iteration 1: Core ML Pipeline (Complete)

### What Changed
- **config.py** — Added `ENROLLED_DIR`, `CAMERA_INDEX`, helper functions
  `_env`, `_env_bool`, `_env_int`, `_env_float` for safe env parsing.
- **core/models.py** — `BoundingBox` now frozen with `width`, `height`,
  `area`, `center`, `as_tuple()`.  `FrameResult` redesigned with
  `detections`, `primary_detection`, `recognition`, `ml_enabled`, `message`.
- **camera/webcam.py** — Full implementation with `cv2.VideoCapture`,
  `reconnect()` with retry loop.
- **ml/preprocess.py** — `safe_crop_face`, `resize_face`,
  `normalize_for_arcface`, `prepare_frame_for_detection` fully implemented.
- **ml/detector_scrfd.py** — ONNX loading, `detect()`, output parsing,
  `select_largest_face()` implemented.
- **ml/recogniser_arcface.py** — ONNX loading, `embed()`, `compare()`,
  `load_enrolled_embedding()` implemented.
- **ml/pipeline.py** — **NEW** stable adapter wrapping detector + recogniser.
  Single `process_frame(frame) → FrameResult` API.  ML-disabled fallback.
- **main.py** — Full entry point: folder creation, camera init, pipeline
  init, N-th frame loop, structured console output, Ctrl+C exit.
- **tests/test_ml_stub.py** — Tests for ML-disabled mode, BoundingBox,
  select_largest_face, load_enrolled_embedding.
- **.gitignore** — Added `data/enrolled/*.npy` pattern.
- **data/enrolled/.gitkeep** — Created enrolled directory.
- **docs/** — ARCHITECTURE.md, SETUP.md, BUILD_LOG.md updated.

### Files Touched
```
app/config.py
app/core/models.py
app/camera/webcam.py
app/ml/preprocess.py
app/ml/detector_scrfd.py
app/ml/recogniser_arcface.py
app/ml/pipeline.py              (NEW)
app/main.py
tests/test_ml_stub.py
data/enrolled/.gitkeep          (NEW)
.gitignore
docs/ARCHITECTURE.md
docs/SETUP.md
docs/BUILD_LOG.md
```

### Next Steps
- **Iteration 2**: SQLite persistence + enrollment via `db/repo.py`

---

## 2026-01 — Boilerplate Setup

### What Changed
- Created complete project directory structure with all stub files.
- No iteration functionality implemented.

### Files Created
- All module `__init__.py` files
- `app/config.py`, `app/main.py`
- `app/core/models.py`
- `app/camera/base.py`, `webcam.py`, `rtsp.py`
- `app/ml/detector_scrfd.py`, `recogniser_arcface.py`, `preprocess.py`
- `app/db/schema.sql`, `repo.py`, `migrations.py`
- `app/tracking/base.py`, `tracking_manager.py`
- `app/recording/base.py`, `snapshot_recorder.py`, `clip_recorder.py`
- `app/services/logging_service.py`, `alert_service.py`, `email_service.py`
- `app/web/app_factory.py`, `routes.py`, `auth.py`
- `tests/test_ml_stub.py`
- `docs/BUILD_LOG.md`, `ARCHITECTURE.md`, `SETUP.md`
- `requirements.txt`, `.gitignore`

### Next Steps
- Implement Iteration 1: Core ML pipeline on webcam
