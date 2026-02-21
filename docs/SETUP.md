# SecureVision — Setup Guide

## Prerequisites

- **Python 3.11+**
- **Webcam** (USB or built-in)
- ~200 MB disk for ONNX models

## 1. Clone & Create Virtual Environment

```bash
git clone <repository-url>
cd FYP-Code

python -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate
```

## 2. Install Dependencies

```bash
pip install -r requirements.txt
```

## 3. Obtain ONNX Models

SecureVision does **not** auto-download models.  You must place them manually.

| Model | Filename | Purpose | Source |
|-------|----------|---------|--------|
| SCRFD-10G | `scrfd_10g_bnkps.onnx` | Face detection | [InsightFace SCRFD](https://github.com/deepinsight/insightface/tree/master/detection/scrfd) |
| ArcFace-R100 | `arcface_r100.onnx` | Face recognition | [InsightFace ArcFace](https://github.com/deepinsight/insightface/tree/master/recognition/arcface) |

Place them in the **`models/`** directory:

```
FYP-Code/
  models/
    scrfd_10g_bnkps.onnx
    arcface_r100.onnx
```

> **Tip:** If your model files have different names, set the paths via
> environment variables `SV_SCRFD_MODEL` / `SV_ARCFACE_MODEL`.

If models are **not** present the application runs in ML-disabled mode —
it still captures frames and logs that ML is disabled.

## 4. Enroll Identities

Use the CLI enrollment tool to register faces into the database.  Each photo
must contain **exactly one face** — the tool rejects 0 or multiple.

```bash
python -m app.enroll --name "Alice" --image ./photos/alice.jpg
python -m app.enroll --name "Bob"   --image ./photos/bob.png
```

Re-running with the same `--name` updates the existing embedding (no duplicates).

The database is stored at `data/db/securevision.sqlite` by default (override
with `SV_DB_PATH`).  Enrolled identities **persist across restarts**.

If no identities are enrolled, all detected faces are labelled "Unknown".

## 5. Run

```bash
python -m app.main
```

Press **Ctrl+C** to stop.

## 6. Run Tests

```bash
pytest tests/ -v
```

## Configuration Reference

All settings live in `app/config.py` and can be overridden via env vars:

| Variable | Default | Description |
|----------|---------|-------------|
| `SV_DATA_DIR` | `./data` | Root data directory |
| `SV_MODELS_DIR` | `./models` | ONNX model directory |
| `SV_DB_PATH` | `data/db/securevision.sqlite` | SQLite database path |
| `SV_ENROLLED_DIR` | `./data/enrolled` | Enrolled embeddings dir (legacy) |
| `SV_CAMERA_INDEX` | `0` | Webcam device index |
| `SV_ML_ENABLED_AUTO` | `true` | Auto-load models if present |
| `SV_DETECTION_CONF_THRESH` | `0.5` | Min detection confidence |
| `SV_RECOGNITION_SIM_THRESH` | `0.4` | Min cosine similarity for match |
| `SV_PROCESS_EVERY_N_FRAMES` | `3` | Run ML every N-th frame |
| `SV_LOG_LEVEL` | `INFO` | Logging level |

## Troubleshooting

**Camera won't open**
- Check the webcam is connected and not in use.
- Try `set SV_CAMERA_INDEX=1` for a different device.

**ML-disabled mode**
- Verify `.onnx` files exist in `models/`.
- Check the log for "model not found" messages.

**Low FPS**
- Increase `SV_PROCESS_EVERY_N_FRAMES` (e.g. 5).
