# SecureVision Build Log

## 2026-02-13 — Iteration 1: Core ML Pipeline (Complete)

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

## 2026-01-25 — Boilerplate Setup

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
