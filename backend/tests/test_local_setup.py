"""Local-only OTP delivery must remain separate from production authentication."""
from email.message import EmailMessage
import re
import smtplib
import pytest
from test_workflows import ctx, resident
from app.config import settings
from app import whatsapp
from scripts import local_server


def local_settings(monkeypatch):
    for key, value in dict(app_environment='local', whatsapp_provider='test',
                           whatsapp_enabled=True, sms_enabled=False, smtp_host='mail',
                           smtp_port=1025, smtp_username='', smtp_password='').items():
        monkeypatch.setattr(settings, key, value)
    # Track the original function so the test-only installation is undone.
    monkeypatch.setattr(whatsapp, 'send_auth_code', whatsapp.send_auth_code)


@pytest.mark.parametrize('changes', [
    {'app_environment': 'production'},
    {'whatsapp_provider': 'cloud'},
    {'smtp_host': 'smtp.example.com'},
    {'sms_enabled': True},
])
def test_local_delivery_refuses_production_or_external_transports(monkeypatch, changes):
    local_settings(monkeypatch)
    for key, value in changes.items():
        monkeypatch.setattr(settings, key, value)
    with pytest.raises(RuntimeError, match='isolated local Compose'):
        local_server.install_local_delivery()


def test_local_inbox_otp_still_requires_password_and_single_use_code(ctx, monkeypatch):
    client, headers, _ = ctx
    resident(client, headers)
    local_settings(monkeypatch)
    messages = []

    class Inbox:
        def __init__(self, host, port, **kwargs):
            assert (host, port) == ('mail', 1025)
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def send_message(self, message):
            assert isinstance(message, EmailMessage)
            messages.append(message)

    monkeypatch.setattr(local_server.smtplib, 'SMTP', Inbox)
    local_server.install_local_delivery()
    assert client.post('/api/auth/login', json={'email':'resident@example.com','password':'WrongPassword'}).status_code == 401
    assert messages == []
    started = client.post('/api/auth/login', json={'email':'resident@example.com','password':'Temporary123!'})
    assert started.status_code == 200
    code = re.search(r'Verification code: (\d{6})', messages[0].get_content()).group(1)
    assert code not in started.text and 'access_token' not in started.json()
    assert messages[0]['To'] == 'local-otp@local.example'
    assert '9000000000' not in messages[0].as_string()
    payload = {'challenge_id': started.json()['challenge_id'], 'code': code}
    assert client.post('/api/auth/otp/verify', json=payload).status_code == 200
    assert client.post('/api/auth/otp/verify', json=payload).status_code == 400


def test_local_inbox_failure_never_issues_a_session(ctx, monkeypatch):
    client, headers, _ = ctx
    resident(client, headers)
    local_settings(monkeypatch)
    def unavailable(*args, **kwargs): raise smtplib.SMTPException('Unavailable')
    monkeypatch.setattr(local_server.smtplib, 'SMTP', unavailable)
    local_server.install_local_delivery()
    response = client.post('/api/auth/login', json={'email':'resident@example.com','password':'Temporary123!'})
    assert response.status_code == 503 and 'access_token' not in response.text
