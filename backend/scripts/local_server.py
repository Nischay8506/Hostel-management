"""Local Compose entrypoint: deliver fake login OTPs to its Mailpit inbox.

The production entrypoint remains app.serve. This entrypoint refuses all
environments except local and never adds an HTTP endpoint exposing OTPs.
"""
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
import smtplib
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import settings
from app import whatsapp


def install_local_delivery():
    if (settings.app_environment != 'local'
            or settings.whatsapp_provider != 'test'
            or not settings.whatsapp_enabled
            or settings.sms_enabled
            or settings.smtp_host != 'mail'
            or settings.smtp_port != 1025
            or settings.smtp_username or settings.smtp_password):
        raise RuntimeError('Local OTP delivery requires the isolated local Compose configuration')

    def send_local_code(phone, code):
        # Validate the mock destination without contacting an external provider.
        digits = whatsapp.normalize_phone(phone)
        message = EmailMessage()
        message['From'] = 'cityhive@local.example'
        message['To'] = 'local-otp@local.example'
        message['Subject'] = f'Cityhive local sign-in code (phone ending {digits[-4:]})'
        message.set_content(
            f'Local development only. No WhatsApp message was sent.\n\n'
            f'Verification code: {code}\n'
            f'Expires after {settings.otp_expiry_seconds // 60} minutes.\n'
            f'Created: {datetime.now(timezone.utc).isoformat()}\n\n'
            'Use this code on the Cityhive sign-in screen. Only the newest code is valid.'
        )
        try:
            with smtplib.SMTP('mail', 1025, timeout=10) as smtp:
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException):
            raise whatsapp.WhatsAppUnavailable('The local OTP inbox is unavailable') from None

    whatsapp.send_auth_code = send_local_code


if __name__ == '__main__':
    install_local_delivery()
    import uvicorn
    uvicorn.run('app.main:app', host='0.0.0.0', port=8000, access_log=False)
