# SecureVision Build Log

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
