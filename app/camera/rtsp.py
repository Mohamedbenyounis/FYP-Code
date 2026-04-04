"""
RTSP camera source using OpenCV VideoCapture.

Connects to a remote RTSP stream (e.g. from a Raspberry Pi running
mediamtx / v4l2rtspserver / rpicam-vid → RTSP relay) and provides
frames through the same ``CameraSource`` interface used by the webcam.

Latency notes
-------------
OpenCV uses FFmpeg (or GStreamer) under the hood. RTSP streams are
decoded through a demuxer → decoder chain that maintains an internal
buffer. While we attempt to reduce buffering via ``CAP_PROP_BUFFERSIZE``
and ``OPENCV_FFMPEG_CAPTURE_OPTIONS``, these are **hints** that not all
OpenCV backends honour.

Typical end‑to‑end latency over a local LAN: 0.3–1.5 seconds.
This is inherent to the RTSP/TCP/H.264 decode pipeline and cannot
be fully eliminated without replacing the entire capture backend
(e.g. using raw GStreamer pipelines), which is out of scope.
"""

from __future__ import annotations

import os
import time
from typing import Optional

import cv2
import numpy as np

from app.camera.base import CameraSource
from app.services.logging_service import get_logger


class RTSPCamera(CameraSource):
    """RTSP network stream input source via ``cv2.VideoCapture``.

    Parameters
    ----------
    url:
        Full RTSP URL, e.g. ``rtsp://192.168.1.50:8554/cam``.
        If credentials are required: ``rtsp://user:pass@host:port/path``.
    """

    def __init__(self, url: str) -> None:
        self._url = url
        self._cap: Optional[cv2.VideoCapture] = None
        self._log = get_logger()

        # Apply FFmpeg‑level low‑latency options via environment variable.
        # This is set *before* VideoCapture is created so FFmpeg picks it up.
        # ``fflags=nobuffer``  — do not buffer input
        # ``flags=low_delay``  — hint to the decoder to prefer low delay
        # ``framedrop=1``      — allow dropping frames to keep up
        #
        # NOTE: These are best‑effort.  If OpenCV was compiled with a
        # different backend (GStreamer, MSMF) these have no effect.
        os.environ.setdefault(
            "OPENCV_FFMPEG_CAPTURE_OPTIONS",
            "fflags;nobuffer|flags;low_delay|framedrop;1",
        )

        self._open()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _open(self) -> bool:
        """Open (or reopen) the RTSP stream.

        Applies conservative buffer‑reduction settings.
        Returns True if the stream is successfully opened.
        """
        self._log.info("Opening RTSP stream: %s", self._url)

        # Use FFMPEG backend explicitly for RTSP — it has the most
        # reliable RTSP/TCP support across platforms.
        self._cap = cv2.VideoCapture(self._url, cv2.CAP_FFMPEG)

        # --- Buffer‑reduction hints (conservative) ---
        # CAP_PROP_BUFFERSIZE is supported by some backends (FFMPEG ≥4.x
        # builds of OpenCV). If the backend ignores it, no harm is done —
        # the call simply returns False, which we log at DEBUG level.
        if self._cap is not None:
            result = self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self._log.debug(
                "Set CAP_PROP_BUFFERSIZE=1 → accepted=%s", result
            )

        if self._cap is not None and self._cap.isOpened():
            self._log.info(
                "RTSP stream opened: url=%s  resolution=%dx%d",
                self._url,
                self.frame_width,
                self.frame_height,
            )
            return True

        self._log.error("Failed to open RTSP stream: %s", self._url)
        return False

    # ------------------------------------------------------------------
    # CameraSource interface
    # ------------------------------------------------------------------

    def read(self) -> tuple[bool, Optional[np.ndarray]]:
        """Read the next frame from the RTSP stream.

        If the internal ``VideoCapture`` is not open, returns
        ``(False, None)`` immediately — the caller is expected to
        invoke ``reconnect()`` in that case.
        """
        if self._cap is None or not self._cap.isOpened():
            return False, None
        ret, frame = self._cap.read()
        if not ret:
            return False, None
        return True, frame

    def release(self) -> None:
        """Release the VideoCapture and free network resources."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            self._log.info("RTSP stream released: %s", self._url)

    def is_opened(self) -> bool:
        """Return True if the underlying VideoCapture is connected."""
        return self._cap is not None and self._cap.isOpened()

    @property
    def frame_width(self) -> int:
        if self._cap is None:
            return 0
        return int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))

    @property
    def frame_height(self) -> int:
        if self._cap is None:
            return 0
        return int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # ------------------------------------------------------------------
    # Reconnect helper
    # ------------------------------------------------------------------

    def reconnect(
        self, max_attempts: int = 5, delay_seconds: float = 2.0
    ) -> bool:
        """Attempt to re‑establish the RTSP stream after a failure.

        RTSP streams are more fragile than local webcams — network
        blips, Wi‑Fi handoffs, and Pi reboots can all cause drops.
        We therefore default to slightly more generous retry parameters
        than the webcam class (5 attempts, 2 s delay) while still
        accepting the same signature for interface compatibility.

        Args:
            max_attempts: Maximum retries before giving up.
            delay_seconds: Pause between retries (seconds).

        Returns:
            True if reconnection succeeded.
        """
        self._log.warning(
            "Attempting RTSP reconnect to %s …", self._url
        )
        self.release()
        for attempt in range(1, max_attempts + 1):
            self._log.info(
                "RTSP reconnect attempt %d/%d", attempt, max_attempts
            )
            if self._open():
                self._log.info("RTSP reconnect succeeded on attempt %d", attempt)
                return True
            time.sleep(delay_seconds)
        self._log.error(
            "RTSP reconnect failed after %d attempts: %s",
            max_attempts,
            self._url,
        )
        return False
