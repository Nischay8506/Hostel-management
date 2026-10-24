"""WhatsApp Cloud API boundary. Test provider never exposes codes over HTTP."""
import threading
import httpx
from .config import settings

_lock=threading.Lock()
_test_deliveries=[]

class WhatsAppUnavailable(Exception):
    pass


def configured():
    if not settings.whatsapp_enabled:
        return False
    if settings.whatsapp_provider == 'test':
        return settings.app_environment.lower() not in {'production','prod'}
    return bool(settings.whatsapp_phone_number_id and settings.whatsapp_access_token
                and settings.whatsapp_api_version)


def status():
    if not settings.whatsapp_enabled:
        return {'enabled':False,'provider':settings.whatsapp_provider,'status':'disabled','reason':'WhatsApp messaging is disabled.'}
    if settings.whatsapp_provider == 'test':
        if settings.app_environment.lower() in {'production','prod'}:
            return {'enabled':False,'provider':'test','status':'misconfigured','reason':'Test provider is forbidden in production.'}
        return {'enabled':True,'provider':'test','status':'test_only','reason':'Messages are captured in process memory; no real WhatsApp messages are sent.'}
    missing=[key for key,value in [('phone number ID',settings.whatsapp_phone_number_id),('access token',settings.whatsapp_access_token),('API version',settings.whatsapp_api_version)] if not value]
    return {'enabled':not missing,'provider':'cloud_api','status':'ready' if not missing else 'disabled','reason':('Missing configuration: '+', '.join(missing)) if missing else 'Cloud API transport configured; approved templates and account permissions still require provider-side verification.'}


def normalize_phone(phone):
    digits=''.join(ch for ch in str(phone or '') if ch.isdigit())
    if len(digits)==10:
        digits=settings.whatsapp_country_code+digits
    if len(digits)<10 or len(digits)>15:
        raise WhatsAppUnavailable('A valid mobile number is required for WhatsApp delivery.')
    return digits


def _send_template(phone,template,parameters,kind):
    cfg=status()
    if not cfg['enabled']:
        raise WhatsAppUnavailable('WhatsApp messaging is not configured.')
    to=normalize_phone(phone)
    if settings.whatsapp_provider=='test':
        with _lock:
            _test_deliveries.append({'to':to,'template':template,'parameters':list(parameters),'kind':kind})
        return 'test-'+str(len(_test_deliveries))
    if not template:
        raise WhatsAppUnavailable('The required approved WhatsApp template is not configured.')
    body={"messaging_product":"whatsapp","to":to,"type":"template","template":{"name":template,"language":{"code":"en"},"components":[{"type":"body","parameters":[{"type":"text","text":str(value)} for value in parameters]}]}}
    if kind=='authentication':
        body['template']['components'].append({'type':'button','sub_type':'url','index':'0','parameters':[{'type':'text','text':str(parameters[0])}]})
    url=f"https://graph.facebook.com/{settings.whatsapp_api_version}/{settings.whatsapp_phone_number_id}/messages"
    try:
        response=httpx.post(url,json=body,headers={'Authorization':f'Bearer {settings.whatsapp_access_token}'},timeout=settings.whatsapp_request_timeout)
        response.raise_for_status()
        data=response.json()
        message_id=data.get('messages',[{}])[0].get('id')
        if not isinstance(message_id,str) or not message_id: raise ValueError('Missing provider message identifier')
        return message_id
    except Exception as exc:
        # Do not return/log provider bodies, access tokens, phone data, or OTPs.
        raise WhatsAppUnavailable('WhatsApp provider delivery failed.') from exc


def send_auth_code(phone,code):
    return _send_template(phone,settings.whatsapp_auth_template_name,[code],'authentication')


def send_reminder(phone,invoice_number,billing_period,balance,due_on):
    return _send_template(phone,settings.whatsapp_reminder_template_name,
                          [invoice_number,billing_period,str(balance),str(due_on)],'utility')


def test_deliveries():
    if settings.whatsapp_provider!='test' or settings.app_environment.lower() in {'production','prod'}:
        raise RuntimeError('Test message inspection is unavailable outside test mode.')
    with _lock:
        return [dict(item) for item in _test_deliveries]


def clear_test_deliveries():
    with _lock:
        _test_deliveries.clear()


def send_admission_update(phone,admission_id,status):
    return _send_template(phone,settings.whatsapp_admission_template_name,[str(admission_id),status],"utility")
