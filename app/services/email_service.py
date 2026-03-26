"""
Email service for Iteration 11.
"""
import smtplib
from email.message import EmailMessage
from app.services.logging_service import get_logger

class EmailService:
    """Minimal secure SMTP client."""

    def __init__(self, smtp_host: str = "", smtp_port: int = 587, username: str = "", password: str = "") -> None:
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self._log = get_logger()

    def send_email(self, to: str, subject: str, body: str, sender: str = "securevision@localhost") -> bool:
        """Send an email notification via SMTP TLS."""
        if not self.smtp_host:
            self._log.warning("Email send skipped (no host configured)")
            return False
            
        msg = EmailMessage()
        msg.set_content(body)
        msg['Subject'] = subject
        msg['From'] = sender
        msg['To'] = to

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10.0) as server:
                # Optionally use STARTTLS
                server.ehlo()
                if server.has_extn('STARTTLS'):
                    server.starttls()
                    server.ehlo()
                if self.username and self.password:
                    server.login(self.username, self.password)
                server.send_message(msg)
            self._log.info("Alert email sent successfully to %s", to)
            return True
        except Exception as e:
            self._log.error("Failed to send alert email: %s", str(e))
            return False
