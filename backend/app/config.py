from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from urllib.parse import urlsplit

class Settings(BaseSettings):
    database_url: str = 'postgresql+psycopg://hostel:hostel_local@localhost:5432/hostel'
    jwt_secret: str
    admin_email: str = 'owner@cityhive.local'
    admin_password: str
    admin_phone: str = ''
    smtp_host: str = 'localhost'
    smtp_port: int = 1025
    smtp_username: str = ''
    smtp_password: str = ''
    smtp_security: str = 'none'
    mail_from: str = 'billing@cityhive.local'
    jobs_enabled: bool = True
    app_environment: str = 'development'
    cors_origins: list[str] = ['http://localhost:5173', 'http://127.0.0.1:5173']
    auto_migrate: bool = True
    release_id: str = 'local'
    job_runner_token: str = ''
    upcoming_reminder_days: int = Field(default=3, ge=0, le=30)
    otp_expiry_seconds: int = Field(default=300, ge=60, le=900)
    otp_max_attempts: int = Field(default=5, ge=1, le=10)
    otp_resend_seconds: int = Field(default=60, ge=30, le=300)
    percentage_discounts_enabled: bool = False
    automatic_billing_enabled: bool = True
    identity_document_key: str = ''
    sms_enabled: bool = False
    twilio_account_sid: str = ''
    twilio_auth_token: str = ''
    twilio_from_number: str = ''
    whatsapp_admission_template_name: str = ''
    whatsapp_enabled: bool = False
    whatsapp_provider: str = 'cloud'
    whatsapp_phone_number_id: str = ''
    whatsapp_business_account_id: str = ''
    whatsapp_access_token: str = ''
    whatsapp_api_version: str = ''
    whatsapp_auth_template_name: str = ''
    whatsapp_reminder_template_name: str = ''
    whatsapp_verify_token: str = ''
    whatsapp_app_secret: str = ''
    whatsapp_country_code: str = '91'
    whatsapp_request_timeout: float = 8.0
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    def validate_runtime(self):
        if self.identity_document_key:
            from cryptography.fernet import Fernet
            try: Fernet(self.identity_document_key.encode())
            except Exception: raise RuntimeError('IDENTITY_DOCUMENT_KEY must be a Fernet key') from None
        if len(self.jwt_secret)<32 or len(self.admin_password)<10:
            raise RuntimeError('JWT_SECRET needs 32+ characters; ADMIN_PASSWORD needs 10+')
        if self.smtp_security not in {'none', 'starttls', 'ssl'}:
            raise RuntimeError('SMTP_SECURITY must be none, starttls or ssl')
        if bool(self.smtp_username) != bool(self.smtp_password):
            raise RuntimeError('Configure both SMTP_USERNAME and SMTP_PASSWORD')
        if self.app_environment.lower() in {'production', 'prod'}:
            if not self.database_url.startswith('postgresql+psycopg://'):
                raise RuntimeError('Production requires a persistent PostgreSQL DATABASE_URL')
            if self.auto_migrate:
                raise RuntimeError('Back up and migrate the production database first, then set AUTO_MIGRATE=false')
            if self.whatsapp_provider == 'test':
                raise RuntimeError('The test WhatsApp provider is forbidden in production')
            if not self.cors_origins or any(urlsplit(o).scheme != 'https' or not urlsplit(o).hostname or urlsplit(o).hostname in {'localhost','127.0.0.1','0.0.0.0','::1'} or bool(urlsplit(o).username or urlsplit(o).password or urlsplit(o).query or urlsplit(o).fragment) or urlsplit(o).path not in {'','/'} or '*' in o for o in self.cors_origins):
                raise RuntimeError('CORS_ORIGINS must contain explicit HTTPS frontend origins')
            if self.smtp_username and self.smtp_security == 'none':
                raise RuntimeError('Authenticated production email requires SMTP_SECURITY=starttls or ssl')
            if self.job_runner_token and len(self.job_runner_token) < 32:
                raise RuntimeError('JOB_RUNNER_TOKEN must contain at least 32 random characters')
            if any(value.startswith('replace-') for value in (self.jwt_secret, self.admin_password)):
                raise RuntimeError('Replace example secrets before production startup')

settings = Settings()
