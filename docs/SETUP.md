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

## 4. (Optional) Create an Enrolled Embedding

For Iteration 1 you can enroll **one** identity by saving a 512-d numpy
embedding to `data/enrolled/known.npy`:

```python
import numpy as np
# Assume `embedding` is a 512-d float32 vector from ArcFace
np.save("data/enrolled/known.npy", embedding)
```

Set the person's name:

```bash
# Windows
set SV_ENROLLED_NAME=Mohamed

# Linux/macOS
export SV_ENROLLED_NAME=Mohamed
```

If the file is missing, all detected faces will be labelled "Unknown".

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
| `SV_ENROLLED_DIR` | `./data/enrolled` | Enrolled embeddings dir |
| `SV_ENROLLED_EMBEDDING` | `data/enrolled/known.npy` | Enrolled .npy path |
| `SV_ENROLLED_NAME` | `KnownPerson` | Name for enrolled identity |
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
