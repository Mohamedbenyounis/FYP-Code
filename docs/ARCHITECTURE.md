# SecureVision Architecture

## Overview

SecureVision is a **local-first** smart CCTV system built for a TU Dublin FYP.
It performs real-time face detection and recognition on a USB webcam feed,
with a clean modular design that supports iterative feature additions without
refactoring existing layers.

## Design Principles

1. **Pluggable ML Adapter** — `app/ml/pipeline.py` exposes ONE stable method
   (`process_frame(frame) → FrameResult`).  All consumers use this.  Changing
   the detector (SCRFD → YOLO) or recogniser (ArcFace → AdaFace) only requires
   edits inside `app/ml/`.  No other module is affected.
2. **Graceful Degradation** — If ONNX model files are missing the pipeline
   returns `FrameResult(ml_enabled=False)` with a human-readable message.
3. **Configuration-Driven** — Every constant lives in `app/config.py` with
   environment-variable overrides (`SV_*`).
4. **Repository Pattern** — All DB access is isolated in `app/db/repo.py`.
   No SQL appears in `main.py` or `app/ml/`.  The pipeline receives an
   `enrolled_provider` callable — it never knows about SQLite.
5. **Clean Interfaces / Stubs** — Every future module (tracking, recording,
   web, alerts) has an ABC or stub today so Iteration 3+ can land without
   restructuring imports or contracts.

## Iteration 2 Data Flow

```
  ┌──────────┐
  │  SQLite   │  db/migrations.py → init_db()
  │  DB       │  db/repo.py       → SQLitePersonRepository
  └────┬─────┘
       │ enrolled_provider()  (zero-arg callable)
       ▼
  ┌──────────────┐
  │ FacePipeline  │  ml/pipeline.py  ← STABLE PUBLIC API
  │  .process_frame(frame) → FrameResult
  │              │
  │  ┌──────────┤
  │  │ SCRFD    │  ml/detector_scrfd.py   (internal)
  │  │ Detector │  ml/preprocess.py       (internal)
  │  ├──────────┤
  │  │ ArcFace  │  ml/recogniser_arcface.py (internal)
  │  │ Recog.   │
  │  └──────────┤
  └──────┬───────┘
         │ FrameResult
         ▼
  ┌──────────┐          ┌──────────────┐
  │ main.py   │          │ enroll.py     │  CLI enrollment
  │ (camera   │          │ (image →      │
  │  display) │          │  DB entry)    │
  └──────────┘          └──────────────┘
```

### Enrollment Flow

```
  photo.jpg
       │
       ▼
  SCRFDDetector.detect()     → must find exactly 1 face
       │
       ▼
  ArcFaceRecogniser.embed()  → 512-d unit vector
       │
       ▼
  SQLitePersonRepository.add_person(name, embedding)
       │
       ▼
  Stored as BLOB (np.float32.tobytes) + metadata
```

### Dependency Injection (no SQL in ml/)

```
  main.py
    ├── init_db(config.DB_PATH)              → sqlite3.Connection
    ├── SQLitePersonRepository(conn)         → repo
    ├── make_enrolled_provider(repo)         → Callable[[], List[EnrolledPerson]]
    └── FacePipeline(enrolled_provider=...)  → pipeline uses the callable
```

## FrameResult Contract

```python
@dataclass
class FrameResult:
    detections: list[Detection]          # all detected faces
    primary_detection: Detection | None  # largest bbox (MVP rule)
    recognition: RecognitionResult | None
    ml_enabled: bool
    message: str                         # human-readable summary
```

## Why This Avoids Future Refactors

| Iteration | What Changes | What Stays the Same |
|-----------|-------------|---------------------|
| 2 – SQLite | `db/repo.py`, `db/migrations.py`, `enroll.py` | pipeline API, camera |
| 3 – Events | new `services/event_manager.py` consumes `FrameResult` | pipeline, main |
| 4 – Snapshots | `recording/snapshot_recorder.py` | pipeline, camera |
| 5 – Dashboard | `web/` reads DB via `repo.py` | pipeline (separate process) |
| 6 – Tracking | `tracking/` wraps pipeline | pipeline API unchanged |
| 7 – RTSP | `camera/rtsp.py` implements same ABC | pipeline, main |
| 8 – Alerts | `services/alert_service.py` subscribes to events | everything else |

## Module Map

```
app/
├── config.py               # All configuration + env overrides
├── main.py                 # Entry point (uses FacePipeline only)
├── enroll.py               # CLI enrollment  (Iteration 2)
├── core/models.py          # Shared dataclasses
├── camera/
│   ├── base.py             # CameraSource ABC
│   ├── webcam.py           # USB webcam (Iteration 1)
│   └── rtsp.py             # RTSP stub (Iteration 7)
├── ml/
│   ├── pipeline.py         # ★ Stable adapter (public API)
│   ├── detector_scrfd.py   # SCRFD ONNX (internal)
│   ├── recogniser_arcface.py # ArcFace ONNX (internal)
│   └── preprocess.py       # Crop / resize / normalise (internal)
├── db/
│   ├── schema.sql          # DDL for persons + events
│   ├── migrations.py       # init_db(), WAL + FK pragmas
│   └── repo.py             # SQLitePersonRepository + provider factory
├── tracking/               # Stub — Iteration 6
├── recording/              # Stub — Iteration 4
├── services/
│   ├── logging_service.py  # Centralised logger
│   ├── alert_service.py    # Stub — Iteration 8
│   └── email_service.py    # Stub — Iteration 8
└── web/                    # Stub — Iteration 5
```
