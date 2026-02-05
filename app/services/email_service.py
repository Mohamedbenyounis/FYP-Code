"""
Email service stub for Iteration 8.
"""


class EmailService:
    """Stub email service for Iteration 8."""

    def __init__(self, smtp_host: str = "", smtp_port: int = 587, username: str = "", password: str = "") -> None:
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password

    def send_email(self, to: str, subject: str, body: str) -> bool:
        """Send an email notification. Stub returns False."""
        # TODO: Implement in Iteration 8
        return False
