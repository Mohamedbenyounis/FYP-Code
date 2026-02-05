"""
Alert service stub for Iteration 8.
"""

from typing import Protocol
from app.core.models import FrameResult


class AlertHandler(Protocol):
    """Protocol for alert handlers."""

    def send_alert(self, message: str, frame_result: FrameResult) -> None:
        """Send an alert notification."""
        ...


class AlertService:
    """Stub alert service for Iteration 8."""

    def __init__(self) -> None:
        self._handlers: list[AlertHandler] = []

    def register_handler(self, handler: AlertHandler) -> None:
        """Register an alert handler."""
        self._handlers.append(handler)

    def trigger_alert(self, message: str, frame_result: FrameResult) -> None:
        """Trigger alert to all registered handlers."""
        # TODO: Implement in Iteration 8
        pass
