"""
Centralised configuration with environment variable overrides.
All paths, thresholds, and feature flags live here.
No hard-coded constants elsewhere in the codebase.
"""

import os
from pathlib import Path


def _env(key: str, default: str) -> str:
    """Read an environment variable or return *default*."""
    return os.getenv(key, default)


def _env_bool(key: str, default: bool) -> bool:
    """Parse a boolean environment variable."""
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("true", "1", "yes", "on")


def _env_int(key: str, default: int) -> int:
    """Parse an int environment variable."""
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    """Parse a float environment variable."""
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        return default


# =============================================================================
# DIRECTORY PATHS
# =============================================================================

BASE_DIR: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = Path(_env("SV_DATA_DIR", str(BASE_DIR / "data")))
DB_DIR: Path = DATA_DIR / "db"
SNAPSHOTS_DIR: Path = DATA_DIR / "snapshots"
CLIPS_DIR: Path = DATA_DIR / "clips"
MODELS_DIR: Path = Path(_env("SV_MODELS_DIR", str(BASE_DIR / "models")))

# =============================================================================
# DATABASE  (Iteration 2+)
# =============================================================================

DB_PATH: Path = Path(_env("SV_DB_PATH", str(DB_DIR / "securevision.sqlite")))

# =============================================================================
# MODEL FILE PATHS
# =============================================================================

SCRFD_MODEL_PATH: Path = Path(
    _env("SV_SCRFD_MODEL", str(MODELS_DIR / "scrfd_10g_bnkps.onnx"))
)
ARCFACE_MODEL_PATH: Path = Path(
    _env("SV_ARCFACE_MODEL", str(MODELS_DIR / "arcface_r100.onnx"))
)

# =============================================================================
# FEATURE FLAGS
# =============================================================================

ML_ENABLED_AUTO: bool = _env_bool("SV_ML_ENABLED_AUTO", True)
CAMERA_TYPE: str = _env("SV_CAMERA_TYPE", "webcam")
CAMERA_INDEX: int = _env_int("SV_CAMERA_INDEX", 0)
# Alias kept for backward compat
WEBCAM_INDEX: int = CAMERA_INDEX
RTSP_URL: str = _env("SV_RTSP_URL", "")

# =============================================================================
# PREVIEW WINDOW
# =============================================================================

SHOW_PREVIEW: bool = _env_bool("SV_SHOW_PREVIEW", True)
PREVIEW_WINDOW_NAME: str = _env("SV_PREVIEW_WINDOW_NAME", "SecureVision")

# =============================================================================
# ML THRESHOLDS
# =============================================================================

DETECTION_CONF_THRESH: float = _env_float("SV_DETECTION_CONF_THRESH", 0.5)
RECOGNITION_SIM_THRESH: float = _env_float("SV_RECOGNITION_SIM_THRESH", 0.4)

# =============================================================================
# PERFORMANCE
# =============================================================================

PROCESS_EVERY_N_FRAMES: int = _env_int("SV_PROCESS_EVERY_N_FRAMES", 3)

# =============================================================================
# ONNX RUNTIME
# =============================================================================

ONNX_PROVIDERS: list[str] = ["CPUExecutionProvider"]

# =============================================================================
# LOGGING
# =============================================================================

LOG_LEVEL: str = _env("SV_LOG_LEVEL", "INFO")
