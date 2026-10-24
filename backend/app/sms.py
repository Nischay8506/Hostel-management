"""Optional SMS OTP delivery using Twilio's Messages API."""
import re
import httpx
from .config import settings
from .whatsapp import normalize_phone

class SMSUnavailable(Exception):
    pass

def configured():
    return bool(settings.sms_enabled and re.fullmatch(r'AC[0-9a-fA-F]{32}', settings.twilio_account_sid)
                and settings.twilio_auth_token and settings.twilio_from_number)

def send_auth_code(phone, code):
    if not configured(): raise SMSUnavailable('SMS verification is not configured.')
    try:
        response = httpx.post(
            f'https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json',
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            data={'To':'+'+normalize_phone(phone),'From':settings.twilio_from_number,
                  'Body':f'Your Cityhive verification code is {code}. It expires in {settings.otp_expiry_seconds//60} minutes.'},
            timeout=settings.whatsapp_request_timeout)
        response.raise_for_status()
        data=response.json()
        if not data.get('sid') or data.get('status') in {'failed','undelivered'}: raise ValueError()
    except Exception:
        raise SMSUnavailable('SMS verification could not be delivered.') from None
