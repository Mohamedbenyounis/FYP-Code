"""
Alert service for Iteration 11.
Provides suppression logic and links events to alerts.
"""

import threading
import time

from app import config
from app.core.models import Event
from app.db.repo import SQLiteAlertRepository
from app.services.email_service import EmailService
from app.services.logging_service import get_logger


class AlertService:
    """Manages system alerts with spam suppression."""

    def __init__(
        self, 
        repo: SQLiteAlertRepository, 
        email_svc: EmailService
    ) -> None:
        self._log = get_logger()
        self._repo = repo
        self._email_svc = email_svc
        
        self.cooldown_sec = config.ALERT_SUPPRESSION_SECONDS
        self._last_alert_time: dict[str, float] = {}

    def trigger_unauthorised_alert(self, event: Event) -> None:
        """
        Evaluate and dispatch an alert if it passes cooldown constraints.
        Only triggers for unauthorised events.
        """
        if not config.ALERTS_ENABLED:
            return
            
        if event.status != "unauthorised":
            return
            
        now = time.monotonic()
        
        # Cooldown is per known person. For unknown identities, use the specific
        # tracking session's event_id so distinct unknown faces generate distinct alerts
        # instead of getting globally suppressed together.
        key = str(event.person_id) if event.person_id is not None else str(event.event_id)
        
        last = self._last_alert_time.get(key, 0.0)
        if (now - last) < self.cooldown_sec:
            self._log.debug("Alert suppressed for %s (cooldown active: %.1fs remaining)", 
                            key, self.cooldown_sec - (now - last))
            return
            
        self._last_alert_time[key] = now
        
        message = f"Unauthorised presence detected. Event ID: {event.event_id[:8]}"
        self._log.warning("ALERT FIRED: %s", message)
        
        # Persist alert to DB
        self._repo.add_alert(
            event_id=event.event_id,
            alert_type="UNAUTHORISED_PRESENCE",
            message=message
        )
        
        # Optional Email via a lightweight, fire-and-forget daemon thread.
        # This is built as a best-effort send to avoid blocking the real-time webcam inference loop.
        # It is NOT a durable async task queue or enterprise messaging broker.
        if config.EMAIL_ALERTS_ENABLED and config.EMAIL_RECIPIENT:
            self._send_email_async(
                subject="SecureVision Alert: Unauthorised Presence",
                body=f"An unauthorised person was detected at {event.created_at}.\n\n"
                     f"Event ID: {event.event_id}\n\n"
                     f"Please check the dashboard to review snapshots and video evidence."
            )
            
    def _send_email_async(self, subject: str, body: str) -> None:
        def task():
            self._email_svc.send_email(
                to=config.EMAIL_RECIPIENT,
                subject=subject,
                body=body,
                sender=config.EMAIL_SENDER
            )
        t = threading.Thread(target=task, daemon=True)
        t.start()
