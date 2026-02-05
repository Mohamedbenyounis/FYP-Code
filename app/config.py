"""
Centralised configuration with environment variable overrides.
"""

import os
from pathlib import Path


# =============================================================================
# PATHS
# =============================================================================

BASE_DIR: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = Path(os.getenv("SV_DATA_DIR", str(BASE_DIR / "data")))
DB_DIR: Path = DATA_DIR / "db"
SNAPSHOTS_DIR: Path = DATA_DIR / "snapshots"
CLIPS_DIR: Path = DATA_DIR / "clips"
MODELS_DIR: Path = Path(os.getenv("SV_MODELS_DIR", str(BASE_DIR / "models")))

SCRFD_MODEL_PATH: Path = Path(os.getenv("SV_SCRFD_MODEL", str(MODELS_DIR / "scrfd_10g_bnkps.onnx")))
ARCFACE_MODEL_PATH: Path = Path(os.getenv("SV_ARCFACE_MODEL", str(MODELS_DIR / "arcface_r100.onnx")))
ENROLLED_EMBEDDING_PATH: Path = Path(os.getenv("SV_ENROLLED_EMBEDDING", str(DATA_DIR / "enrolled_embedding.npy")))
ENROLLED_NAME: str = os.getenv("SV_ENROLLED_NAME", "KnownPerson")

# =============================================================================
# FEATURE FLAGS
# =============================================================================

ML_ENABLED_AUTO: bool = os.getenv("SV_ML_ENABLED_AUTO", "true").lower() == "true"
CAMERA_TYPE: str = os.getenv("SV_CAMERA_TYPE", "webcam")
WEBCAM_INDEX: int = int(os.getenv("SV_WEBCAM_INDEX", "0"))
RTSP_URL: str = os.getenv("SV_RTSP_URL", "")

# =============================================================================
# ML THRESHOLDS
# =============================================================================

DETECTION_CONF_THRESH: float = float(os.getenv("SV_DETECTION_CONF_THRESH", "0.5"))
RECOGNITION_SIM_THRESH: float = float(os.getenv("SV_RECOGNITION_SIM_THRESH", "0.4"))

# =============================================================================
# PERFORMANCE
# =============================================================================

PROCESS_EVERY_N_FRAMES: int = int(os.getenv("SV_PROCESS_EVERY_N_FRAMES", "3"))
ONNX_PROVIDERS: list[str] = ["CPUExecutionProvider"]
LOG_LEVEL: str = os.getenv("SV_LOG_LEVEL", "INFO")
