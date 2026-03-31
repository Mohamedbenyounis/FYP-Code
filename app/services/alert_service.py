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

        Suppression key strategy (Iteration 11b):
        - Known person:   ``person:<person_id>``
        - Unknown entity:  ``unknown_track:<track_key>``
        - Fallback:        ``unknown:<event_id>``  (no suppression)
        """
        if not config.ALERTS_ENABLED:
            return
            
        if event.status != "unauthorised":
            return
            
        now = time.monotonic()
        
        # --- Derive suppression key from the best available identity ---
        #
        # Known person:     person_id is stable across events for the same
        #                   enrolled identity.
        # Unknown tracked:  track_key (e.g. "face_3") is stable for the same
        #                   physical entity across frames while it remains
        #                   associated by centroid proximity.
        # Fallback:         event_id (UUID) is unique per event, so
        #                   suppression effectively won't activate.  This
        #                   path should only occur in single-entity mode
        #                   or if tracking is not running.
        if event.person_id is not None:
            key = f"person:{event.person_id}"
        elif event.track_key is not None:
            key = f"unknown_track:{event.track_key}"
        else:
            key = f"unknown:{event.event_id}"
        
        last = self._last_alert_time.get(key, 0.0)
        if (now - last) < self.cooldown_sec:
            self._log.debug("Alert suppressed for %s (cooldown active: %.1fs remaining)", 
                            key, self.cooldown_sec - (now - last))
            return
            
        self._last_alert_time[key] = now
        
        message = f"Unauthorised presence detected. Event ID: {event.event_id[:8]}"
        self._log.warning("ALERT FIRED: %s  key=%s", message, key)
        
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
