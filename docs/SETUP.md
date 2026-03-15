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
| SCRFD-500M | `det_500m.onnx` | Face detection | [InsightFace buffalo_s](https://github.com/deepinsight/insightface) |
| MobileFaceNet (w600k) | `w600k_mbf.onnx` | Face recognition | [InsightFace buffalo_s](https://github.com/deepinsight/insightface) |

Place them in the **`models/`** directory:

```
FYP-Code/
  models/
    det_500m.onnx
    w600k_mbf.onnx
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

## 5b. Run Dashboard (Iteration 5)

Run the dashboard in a separate terminal/process:

```bash
python -m app.web_run
```

Default URL:

```text
http://127.0.0.1:5000
```

Bootstrap admin is created only when both env vars are provided:

```text
SV_BOOTSTRAP_ADMIN_USERNAME
SV_BOOTSTRAP_ADMIN_PASSWORD
```

Example (PowerShell):

```powershell
$env:SV_BOOTSTRAP_ADMIN_USERNAME = "admin"
$env:SV_BOOTSTRAP_ADMIN_PASSWORD = "change-this-now"
python -m app.web_run
```

If these variables are not set and `admin_users` is empty, login will remain
disabled until you create the first admin.

The dashboard and pipeline are intentionally separate:
- `app.main` handles camera + ML + event writing.
- `app.web_run` handles local browser UI + admin actions.

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
| `SV_CAMERA_INDEX` | `0` | Webcam device index |
| `SV_ML_ENABLED_AUTO` | `true` | Auto-load models if present |
| `SV_DETECTION_CONF_THRESH` | `0.45` | Min detection confidence |
| `SV_RECOGNITION_SIM_THRESH` | `0.25` | Min cosine similarity for match |
| `SV_NMS_IOU_THRESH` | `0.4` | IoU threshold for NMS |
| `SV_MAX_GALLERY_EMBEDDINGS` | `5` | Max raw embeddings stored per person |
| `SV_PROCESS_EVERY_N_FRAMES` | `3` | Run ML every N-th frame |
| `SV_DETECTION_ADAPTIVE_PREPROCESS_ENABLED` | `true` | Enable adaptive detection-only preprocessing gate |
| `SV_DETECTION_PREPROCESS_MODE` | `clahe` | Enhancement mode: `none`, `clahe`, or `gamma` |
| `SV_BRIGHT_GLOBAL_THRESHOLD` | `165.0` | Global grayscale brightness threshold |
| `SV_DARK_CENTER_THRESHOLD` | `115.0` | Center-region grayscale darkness threshold |
| `SV_BACKLIT_SCORE_THRESHOLD` | `35.0` | Trigger when `(global_mean - center_mean)` exceeds this |
| `SV_CLAHE_CLIP_LIMIT` | `2.0` | CLAHE clip limit |
| `SV_CLAHE_TILE_GRID_SIZE` | `8` | CLAHE tile grid size (square) |
| `SV_GAMMA_VALUE` | `1.35` | Gamma value for `gamma` mode |
| `SV_LOG_LEVEL` | `INFO` | Logging level |
| `SV_SHOW_PREVIEW` | `true` | Show live camera window |
| `SV_PREVIEW_WINDOW_NAME` | `SecureVision` | Preview window title |
| `SV_EVENT_CONFIRM_WINDOW_N` | `5` | Event manager rolling window size |
| `SV_EVENT_CONFIRM_MIN_K` | `3` | Min faces in window to confirm |
| `SV_EVENT_LOST_FRAMES` | `5` | Consecutive no-face frames to end event |
| `SV_EVENT_COOLDOWN_SECONDS` | `10.0` | Cooldown seconds after event closes |
| `SV_EVENT_SCORE_THRESHOLD` | `0.4` | Min score for "authorised" status |
| `SV_DRAW_BBOX_ON_SNAPSHOT` | `true` | Draw event bounding box + label on snapshot |
| `SV_SNAPSHOT_JPEG_QUALITY` | `90` | JPEG quality (1-100) for snapshot files |
| `SV_SNAPSHOT_SUBDIR_BY_DATE` | `true` | Save snapshots under `YYYY-MM-DD` subdirectory |
| `SV_SAVE_RAW_SNAPSHOT` | `false` | Save unannotated frame even if bbox exists |
| `SV_DASHBOARD_HOST` | `127.0.0.1` | Flask dashboard bind host |
| `SV_DASHBOARD_PORT` | `5000` | Flask dashboard bind port |
| `SV_FLASK_SECRET_KEY` | `securevision-dev-secret` | Session secret key |
| `SV_BOOTSTRAP_ADMIN_USERNAME` | *(unset)* | Initial admin username (first bootstrap only) |
| `SV_BOOTSTRAP_ADMIN_PASSWORD` | *(unset)* | Initial admin password (first bootstrap only) |

## Inspect Events  (Iteration 3)

Events are stored in the `events` table.  Query them directly with SQLite:

```bash
sqlite3 data/db/securevision.sqlite \
  "SELECT id, status, person_name, score, created_at FROM events ORDER BY created_at DESC LIMIT 10;"
```

Each row represents a confirmed face presence — the `EventManager` uses a
K-of-N rolling window to avoid false triggers from single-frame noise.

## Snapshot Evidence  (Iteration 4)

When a new event is emitted, SecureVision saves one JPEG snapshot and links
it to the same event row via `events.snapshot_path`.

Default output path pattern:

```
data/snapshots/YYYY-MM-DD/<event_id>.jpg
```

To inspect recent linked snapshots:

```bash
sqlite3 data/db/securevision.sqlite \
  "SELECT id, status, snapshot_path, created_at FROM events ORDER BY created_at DESC LIMIT 10;"
```

Dashboard snapshot display uses `/events/<event_id>/snapshot`, which validates
the DB path and serves files only from `data/snapshots/` to prevent traversal
and arbitrary file reads.

## Troubleshooting

**Camera won't open**
- Check the webcam is connected and not in use.
- Try `set SV_CAMERA_INDEX=1` for a different device.

**ML-disabled mode**
- Verify `.onnx` files exist in `models/`.
- Check the log for "model not found" messages.

**Low FPS**
- Increase `SV_PROCESS_EVERY_N_FRAMES` (e.g. 5).

## Headless Mode

To run without a GUI window (e.g. background service, CI, SSH session):

```bash
set SV_SHOW_PREVIEW=false
python -m app.main
```

The camera and ML pipeline operate normally; results are logged to the
console only.

## Developer Tools (Optional)

```bash
pip install -r requirements-dev.txt

# Check for lint issues
ruff check app/ tests/

# Auto-format code
ruff format app/ tests/
```
