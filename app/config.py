"""
Centralised configuration with environment variable overrides.
All paths, thresholds, and feature flags live here.
No hard-coded constants elsewhere in the codebase.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()


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


def _env_optional(key: str) -> str | None:
    """Read an optional env var; return None when unset/blank."""
    val = os.getenv(key)
    if val is None:
        return None
    stripped = val.strip()
    return stripped if stripped else None


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
    _env("SV_SCRFD_MODEL", str(MODELS_DIR / "det_500m.onnx"))
)
ARCFACE_MODEL_PATH: Path = Path(
    _env("SV_ARCFACE_MODEL", str(MODELS_DIR / "w600k_mbf.onnx"))
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

DETECTION_CONF_THRESH: float = _env_float("SV_DETECTION_CONF_THRESH", 0.45)
RECOGNITION_MATCH_THRESHOLD: float = _env_float(
    "SV_RECOGNITION_MATCH_THRESHOLD",
    _env_float("SV_RECOGNITION_SIM_THRESH", 0.25),
)
# Backward-compatible alias (prefer RECOGNITION_MATCH_THRESHOLD in new code)
RECOGNITION_SIM_THRESH: float = RECOGNITION_MATCH_THRESHOLD
NMS_IOU_THRESH: float = _env_float("SV_NMS_IOU_THRESH", 0.4)
MAX_GALLERY_EMBEDDINGS: int = _env_int("SV_MAX_GALLERY_EMBEDDINGS", 5)

# =============================================================================
# ADAPTIVE DETECTION PREPROCESSING
# =============================================================================

DETECTION_ADAPTIVE_PREPROCESS_ENABLED: bool = _env_bool(
    "SV_DETECTION_ADAPTIVE_PREPROCESS_ENABLED", True
)
DETECTION_PREPROCESS_MODE: str = _env(
    "SV_DETECTION_PREPROCESS_MODE", "clahe"
).strip().lower()

BRIGHT_GLOBAL_THRESHOLD: float = _env_float(
    "SV_BRIGHT_GLOBAL_THRESHOLD", 165.0
)
DARK_CENTER_THRESHOLD: float = _env_float(
    "SV_DARK_CENTER_THRESHOLD", 115.0
)
BACKLIT_SCORE_THRESHOLD: float = _env_float(
    "SV_BACKLIT_SCORE_THRESHOLD", 35.0
)

CLAHE_CLIP_LIMIT: float = _env_float("SV_CLAHE_CLIP_LIMIT", 2.0)
CLAHE_TILE_GRID_SIZE: int = _env_int("SV_CLAHE_TILE_GRID_SIZE", 8)
GAMMA_VALUE: float = _env_float("SV_GAMMA_VALUE", 1.35)

# =============================================================================
# PERFORMANCE
# =============================================================================

PROCESS_EVERY_N_FRAMES: int = _env_int("SV_PROCESS_EVERY_N_FRAMES", 3)

# =============================================================================
# RECORDING (Iteration 4)
# =============================================================================

DRAW_BBOX_ON_SNAPSHOT: bool = _env_bool("SV_DRAW_BBOX_ON_SNAPSHOT", True)
SNAPSHOT_JPEG_QUALITY: int = _env_int("SV_SNAPSHOT_JPEG_QUALITY", 90)
SNAPSHOT_SUBDIR_BY_DATE: bool = _env_bool("SV_SNAPSHOT_SUBDIR_BY_DATE", True)
SAVE_RAW_SNAPSHOT: bool = _env_bool("SV_SAVE_RAW_SNAPSHOT", False)

# Iteration 10: Event Clip Recording
CLIP_ENABLED: bool = _env_bool("SV_CLIP_ENABLED", True)
CLIP_PRE_EVENT_SECONDS: float = _env_float("SV_CLIP_PRE_EVENT_SECONDS", 2.0)
CLIP_POST_EVENT_SECONDS: float = _env_float("SV_CLIP_POST_EVENT_SECONDS", 3.0)
CLIP_MAX_DURATION_SECONDS: float = _env_float("SV_CLIP_MAX_DURATION_SECONDS", 60.0)
CLIP_TARGET_FPS: int = _env_int("SV_CLIP_TARGET_FPS", 15)
CLIP_CODEC: str = _env("SV_CLIP_CODEC", "avc1")
CLIP_FILE_EXTENSION: str = _env("SV_CLIP_FILE_EXTENSION", ".mp4")

# =============================================================================
# LIVE VIEW (Iteration 12)
# =============================================================================

LIVE_VIEW_ENABLED: bool = _env_bool("SV_LIVE_VIEW_ENABLED", True)
LIVE_VIEW_EVERY_N_FRAMES: int = _env_int("SV_LIVE_VIEW_EVERY_N_FRAMES", 2)

# =============================================================================
# ONNX RUNTIME
# =============================================================================

ONNX_PROVIDERS: list[str] = ["CPUExecutionProvider"]

# =============================================================================
# EVENT MANAGER  (Iteration 3)
# =============================================================================

EVENT_CONFIRM_WINDOW_N: int = _env_int("SV_EVENT_CONFIRM_WINDOW_N", 5)
"""Rolling window size — how many recent observations to keep."""

EVENT_CONFIRM_MIN_K: int = _env_int("SV_EVENT_CONFIRM_MIN_K", 3)
"""Min face-present observations inside the window to confirm presence."""

EVENT_LOST_FRAMES: int = _env_int("SV_EVENT_LOST_FRAMES", 5)
"""Consecutive no-face observations before an active event ends."""

EVENT_COOLDOWN_SECONDS: float = _env_float("SV_EVENT_COOLDOWN_SECONDS", 10.0)
"""Seconds to stay in COOLDOWN after an event closes (prevent re-fire)."""

AUTHORISATION_THRESHOLD: float = _env_float(
    "SV_AUTHORISATION_THRESHOLD",
    _env_float("SV_EVENT_SCORE_THRESHOLD", 0.4),
)
"""Min cosine similarity to mark an event as authorised."""

# Backward-compatible alias (prefer AUTHORISATION_THRESHOLD in new code)
EVENT_SCORE_THRESHOLD: float = AUTHORISATION_THRESHOLD

# =============================================================================
# LOGGING
# =============================================================================

LOG_LEVEL: str = _env("SV_LOG_LEVEL", "INFO")

# =============================================================================
# DASHBOARD (Iteration 5)
# =============================================================================

DASHBOARD_HOST: str = _env("SV_DASHBOARD_HOST", "127.0.0.1")
DASHBOARD_PORT: int = _env_int("SV_DASHBOARD_PORT", 5000)
FLASK_SECRET_KEY: str = _env("SV_FLASK_SECRET_KEY", "securevision-dev-secret")
BOOTSTRAP_ADMIN_USERNAME: str | None = _env_optional("SV_BOOTSTRAP_ADMIN_USERNAME")
BOOTSTRAP_ADMIN_PASSWORD: str | None = _env_optional("SV_BOOTSTRAP_ADMIN_PASSWORD")

# =============================================================================
# MULTI-FACE EVENT HANDLING  (Iteration 9 — experimental)
# =============================================================================

MULTI_FACE_ASSOCIATION_DISTANCE: float = _env_float(
    "SV_MULTI_FACE_ASSOCIATION_DISTANCE", 150.0
)
"""Max centroid distance (pixels) to associate a detection with an existing track.
Detections further than this from all existing tracks get a new track key."""

MULTI_FACE_MAX_ENTITIES: int = _env_int(
    "SV_MULTI_FACE_MAX_ENTITIES", 10
)
"""Maximum number of concurrent tracked entities (face EventManagers).
Prevents resource leak from spurious detections."""

# =============================================================================
# ALERTS & NOTIFICATIONS (Iteration 11)
# =============================================================================

ALERTS_ENABLED: bool = _env_bool("SV_ALERTS_ENABLED", True)
ALERT_SUPPRESSION_SECONDS: float = _env_float("SV_ALERT_SUPPRESSION_SECONDS", 300.0) # 5m cooldown

EMAIL_ALERTS_ENABLED: bool = _env_bool("SV_EMAIL_ALERTS_ENABLED", False)
EMAIL_SMTP_HOST: str = _env("SV_EMAIL_SMTP_HOST", "")
EMAIL_SMTP_PORT: int = _env_int("SV_EMAIL_SMTP_PORT", 587)
EMAIL_USERNAME: str = _env("SV_EMAIL_USERNAME", "")
EMAIL_PASSWORD: str = _env("SV_EMAIL_PASSWORD", "")
EMAIL_RECIPIENT: str = _env("SV_EMAIL_RECIPIENT", "")
EMAIL_SENDER: str = _env("SV_EMAIL_SENDER", "securevision@localhost")


# =============================================================================
# SERVO CONTROL (FYP Enhancement)
# =============================================================================

SERVO_ENABLED: bool = _env_bool("SV_SERVO_ENABLED", False)
SERVO_PI_IP: str = _env("SV_SERVO_PI_IP", "172.20.10.5")
SERVO_PI_PORT: int = _env_int("SV_SERVO_PI_PORT", 5000)

SERVO_DEADZONE_RATIO: float = _env_float("SV_SERVO_DEADZONE_RATIO", 0.35)
SERVO_STEP_DEGREES: float = _env_float("SV_SERVO_STEP_DEGREES", 4.0)
SERVO_COOLDOWN_MS: float = _env_float("SV_SERVO_COOLDOWN_MS", 500.0)
SERVO_OPPOSITE_LOCKOUT_MS: float = _env_float("SV_SERVO_OPPOSITE_LOCKOUT_MS", 1200.0)

