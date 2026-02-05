"""
Centralised logging service.
"""

import logging
import sys
from typing import Optional

from app import config


_logger_instance: Optional[logging.Logger] = None


def get_logger(name: str = "securevision") -> logging.Logger:
    """Get or create the application logger."""
    global _logger_instance

    if _logger_instance is not None:
        return _logger_instance

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    _logger_instance = logger
    return logger


class FrameRateLogger:
    """Helper to log frame processing stats without spamming."""

    def __init__(self, log_every_n: int = 100):
        self.log_every_n = log_every_n
        self.frame_count = 0
        self.detection_count = 0
        self.recognition_count = 0
        self.logger = get_logger()

    def log_frame(self, detected: bool = False, recognised: bool = False) -> None:
        """Record frame stats and log periodically."""
        self.frame_count += 1
        if detected:
            self.detection_count += 1
        if recognised:
            self.recognition_count += 1

        if self.frame_count % self.log_every_n == 0:
            self.logger.info(
                f"Processed {self.frame_count} frames | "
                f"Detections: {self.detection_count} | "
                f"Recognitions: {self.recognition_count}"
            )

    def reset(self) -> None:
        """Reset counters."""
        self.frame_count = 0
        self.detection_count = 0
        self.recognition_count = 0
