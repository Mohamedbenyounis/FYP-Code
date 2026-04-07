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

    def send_email(self, to: str, subject: str, body: str, sender: str = "securevision@localhost", image_path: str | None = None) -> bool:
        """
        Send an email notification via SMTP TLS.
        Optionally attaches an image as an inline related part.
        """
        if not self.smtp_host:
            self._log.warning("Email send skipped (no host configured)")
            return False
            
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = sender
        msg['To'] = to

        # Build HTML body if attachment exists, otherwise plain text
        if image_path:
            # We use an HTML body to reference the inline image via CID
            html_body = body.replace("\n", "<br>")
            html_body += '<br><br><img src="cid:snippet" style="max-width:100%; border:1px solid #ccc;">'
            msg.set_content(body) # Plain text fallback
            msg.add_alternative(html_body, subtype='html')

            try:
                import imghdr
                with open(image_path, 'rb') as f:
                    img_data = f.read()
                    img_type = imghdr.what(None, h=img_data) or 'jpeg'
                
                msg.get_payload()[1].add_related(
                    img_data,
                    maintype='image',
                    subtype=img_type,
                    cid='snippet'
                )
            except Exception as e:
                self._log.error("Failed to attach image %s: %s", image_path, str(e))
                # Continue sending without attachment
        else:
            msg.set_content(body)

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10.0) as server:
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
