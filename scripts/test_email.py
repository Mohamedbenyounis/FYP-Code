import sys
from pathlib import Path

# Add project root to sys.path
root = Path(__file__).resolve().parent.parent
sys.path.append(str(root))

from app import config
from app.services.email_service import EmailService

def test_send():
    print("--- SecureVision Email Test ---")
    print(f"SMTP Host: {config.EMAIL_SMTP_HOST}")
    print(f"Recipient: {config.EMAIL_RECIPIENT}")

    if "REPLACE" in config.EMAIL_RECIPIENT:
        print("\nERROR: Please update SV_EMAIL_RECIPIENT in your .env file first!")
        return

    svc = EmailService(
        config.EMAIL_SMTP_HOST, config.EMAIL_SMTP_PORT,
        config.EMAIL_USERNAME, config.EMAIL_PASSWORD
    )

    print("Sending...")
    success = svc.send_email(
        to=config.EMAIL_RECIPIENT,
        subject="SecureVision Test",
        body="It works!",
        sender=config.EMAIL_SENDER
    )
    print("SUCCESS!" if success else "FAILED!")

if __name__ == "__main__":
    test_send()
