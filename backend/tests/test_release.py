"""Release regressions. All records use the disposable workflow fixture."""
import hashlib
import hmac
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import pytest
from sqlalchemy import select
from fastapi import HTTPException
from test_workflows import ctx, resident, room, signin
from app.config import settings, Settings
from app.models import Branch, BranchAdmin, User, Resident, Invoice, Payment, Outbox, OtpChallenge, RateLimitBucket, JobState
from app.security import token_for, hashing
from app.services import local_today
from app import services, main, worker, whatsapp


def bill(c,h,rid):
    room_id=room(c,h,capacity=2)
    assert c.put(f'/api/residents/{rid}/allocation',headers=h,json={'room_id':room_id,'discount':'0'}).status_code==200
    assert c.post('/api/billing/generate',headers=h,json={'month':local_today().replace(day=1).isoformat()}).status_code==200
    return c.get('/api/invoices',headers=h).json()[0]


def outsider(sessions):
    with sessions() as db:
        branch=Branch(name='Private second branch');db.add(branch);db.flush()
        user=User(email='other-staff@example.com',role='branch_admin',password_hash=hashing.hash('TemporaryStaff123!'),must_change_password=False)
        db.add(user);db.flush();db.add(BranchAdmin(user_id=user.id,branch_id=branch.id));db.commit()
        return {'Authorization':'Bearer '+token_for(user,mfa_verified=True)}


def test_receipt_pdf_notifications_and_discount_isolation(ctx):
    c,h,sessions=ctx;rid=resident(c,h);i=bill(c,h,rid)
    payment=c.post('/api/payments',headers=h,json={'invoice_id':i['id'],'amount':'3000','method':'cash','idempotency_key':'release-receipt-payment'}).json()
    mine=signin(c)
    pdf=c.get(f"/api/payments/{payment['id']}/receipt.pdf",headers=mine)
    assert pdf.status_code==200 and pdf.content.startswith(b'%PDF-1.4')
    assert i['invoice_number'].encode() in pdf.content and b'CH-' in pdf.content
    assert b'Current invoice balance: INR 5500.00' in pdf.content
    assert 'attachment' in pdf.headers['content-disposition']
    assert len(c.get('/api/my/notifications',headers=mine).json())==1
    resident(c,h,'other@example.com');other=signin(c,'other@example.com');staff=outsider(sessions)
    for auth in [other,staff]:
        assert c.get(f"/api/payments/{payment['id']}/receipt.pdf",headers=auth).status_code==403
        assert c.get(f'/api/residents/{rid}/discounts',headers=auth).status_code==403
        assert c.get('/api/deployment-status',headers=auth).status_code==403
    assert c.get('/api/my/notifications',headers=other).json()==[]
    assert c.get(f"/api/payments/{payment['id']}/receipt.pdf").status_code==401


def test_identity_suffix_can_be_recorded_after_enrollment(ctx):
    c,h,sessions=ctx;rid=resident(c,h)
    with sessions() as db: db.get(Resident,rid).aadhaar_last4=None;db.commit()
    assert c.put(f'/api/residents/{rid}/id-review',headers=h,json={'status':'reviewed'}).status_code==400
    assert c.put(f'/api/residents/{rid}/id-review',headers=h,json={'status':'reviewed','aadhaar_last4':'5678','note':'Inspected in person'}).status_code==200
    rows=c.get(f'/api/residents/{rid}/verification-history',headers=h).json()
    assert len(rows)==1 and rows[0]['new_status']=='reviewed'
    with sessions() as db:
        r=db.get(Resident,rid);assert r.aadhaar_last4=='5678' and r.id_reviewed_by and r.id_reviewed_at
    private=c.put(f'/api/residents/{rid}/id-review',headers=h,json={'status':'reviewed','aadhaar_last4':'123456789012'})
    assert private.status_code==422 and '123456789012' not in private.text


def test_percentage_discount_requires_approval_and_preserves_invoice(ctx,monkeypatch):
    c,h,sessions=ctx;rid=resident(c,h);room_id=room(c,h)
    c.put(f'/api/residents/{rid}/allocation',headers=h,json={'room_id':room_id,'discount':'0'})
    month=local_today().replace(day=1).isoformat()
    rule={'percentage':'10','charge_scope':'accommodation','max_amount':'600','effective_from':month,'effective_until':month,'reason':'Approved retention discount'}
    monkeypatch.setattr(settings,'percentage_discounts_enabled',False)
    assert c.post(f'/api/residents/{rid}/discounts',headers=h,json=rule).status_code==409
    monkeypatch.setattr(settings,'percentage_discounts_enabled',True)
    assert c.post(f'/api/residents/{rid}/discounts',headers=h,json={**rule,'percentage':101}).status_code==422
    assert c.post(f'/api/residents/{rid}/discounts',headers=outsider(sessions),json=rule).status_code==403
    mine=signin(c)
    assert c.post(f'/api/residents/{rid}/discounts',headers=mine,json=rule).status_code==403
    approval=c.post(f'/api/residents/{rid}/discounts',headers=h,json=rule)
    assert approval.status_code==201,approval.text
    assert c.post(f'/api/residents/{rid}/discounts',headers=h,json=rule).status_code==409
    assert c.put(f'/api/residents/{rid}/allocation',headers=h,json={'room_id':room_id,'discount':'100'}).status_code==409
    assert c.post('/api/billing/generate',headers=h,json={'month':month}).json()=={'created':1}
    invoice=c.get('/api/invoices',headers=h).json()[0]
    assert invoice['discount']=='600.00' and invoice['discount_percent']=='10.00' and invoice['amount']=='7900.00'
    assert c.put(f"/api/discounts/{approval.json()['id']}/revoke",headers=h).status_code==200
    assert c.post('/api/billing/generate',headers=h,json={'month':month}).json()=={'created':0}
    assert c.get('/api/invoices',headers=h).json()[0]==invoice
    assert c.post(f'/api/residents/{rid}/discounts',headers=h,json=rule).status_code==409


def test_discount_all_monthly_scope_and_fixed_exclusion(ctx,monkeypatch):
    c,h,_=ctx;rid=resident(c,h);room_id=room(c,h)
    monkeypatch.setattr(settings,'percentage_discounts_enabled',True)
    month=local_today().replace(day=1).isoformat()
    plan=c.post('/api/fee-plans',headers=h,json={'branch_id':1,'name':'Actual fee','sharing':1,'monthly_fee':'8000','additional_charge_label':'Configured service','additional_charge_amount':'1000','billing_day':1,'due_day':5,'effective_from':month})
    assert plan.status_code==201,plan.text
    c.put(f'/api/residents/{rid}/allocation',headers=h,json={'room_id':room_id,'discount':'100'})
    rule={'percentage':'10','charge_scope':'all_monthly','effective_from':month,'effective_until':month,'reason':'Authorized fee reduction'}
    assert c.post(f'/api/residents/{rid}/discounts',headers=h,json=rule).status_code==409
    c.put(f'/api/residents/{rid}/allocation',headers=h,json={'room_id':room_id,'discount':'0'})
    assert c.post(f'/api/residents/{rid}/discounts',headers=h,json=rule).status_code==201
    assert c.post('/api/billing/generate',headers=h,json={'month':month}).status_code==200
    invoice=c.get('/api/invoices',headers=h).json()[0]
    assert invoice['discount']=='900.00' and invoice['amount']=='8100.00'


def test_upcoming_reminder_consent_recheck_and_secure_smtp(ctx,monkeypatch):
    c,h,sessions=ctx;rid=resident(c,h);i=bill(c,h,rid)
    with sessions() as db:
        db.get(Invoice,i['id']).due_on=local_today()+timedelta(days=2)
        r=db.get(Resident,rid);r.whatsapp_notifications=True;r.whatsapp_consent_at=datetime.now(timezone.utc);db.commit()
        assert services.queue_reminders(db)==1;db.commit()
        assert services.queue_reminders(db)==0
        assert 'upcoming' in db.scalar(select(Outbox).where(Outbox.channel=='email')).subject
        r.whatsapp_notifications=False;db.commit()
    events=[]
    class SMTP:
        def __init__(self,*args,**kwargs): events.append('connect')
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def starttls(self,context): events.append('tls');assert context.check_hostname
        def login(self,user,password): events.append('login')
        def send_message(self,message): events.append('send')
    monkeypatch.setattr(services,'SessionLocal',sessions)
    monkeypatch.setattr(services.smtplib,'SMTP',SMTP)
    monkeypatch.setattr(settings,'smtp_security','starttls');monkeypatch.setattr(settings,'smtp_username','test-user');monkeypatch.setattr(settings,'smtp_password','test-password')
    services.deliver_emails()
    assert events==['connect','tls','login','send']
    with sessions() as db:
        assert db.scalar(select(Outbox).where(Outbox.channel=='whatsapp')).cancelled
        assert db.scalar(select(Outbox).where(Outbox.channel=='email')).delivery_status=='submitted'


def test_signed_webhook_is_idempotent_and_does_not_regress_delivery(ctx,monkeypatch):
    c,h,sessions=ctx
    monkeypatch.setattr(settings,'whatsapp_app_secret','test-webhook-secret');monkeypatch.setattr(settings,'whatsapp_verify_token','test-verify')
    with sessions() as db:
        db.add(Outbox(branch_id=1,dedupe_key='webhook-test',recipient='9000000000',subject='Reminder',body='Test',channel='whatsapp',provider_message_id='provider-1',delivery_status='submitted'));db.commit()
    assert c.get('/api/notifications/whatsapp/webhook',params={'hub.mode':'subscribe','hub.verify_token':'wrong','hub.challenge':'123'}).status_code==403
    assert c.get('/api/notifications/whatsapp/webhook',params={'hub.mode':'subscribe','hub.verify_token':'test-verify','hub.challenge':'123'}).text=='123'
    def request(status,signed=True):
        body=json.dumps({'entry':[{'changes':[{'value':{'statuses':[{'id':'provider-1','status':status}]}}]}]}).encode()
        sig='sha256='+hmac.new(b'test-webhook-secret',body,hashlib.sha256).hexdigest()
        return c.post('/api/notifications/whatsapp/webhook',content=body,headers={'X-Hub-Signature-256':sig if signed else 'wrong','Content-Type':'application/json'})
    assert request('read',False).status_code==403
    for status in ['delivered','read','read','sent','failed']: assert request(status).status_code==200
    with sessions() as db: assert db.scalar(select(Outbox).where(Outbox.provider_message_id=='provider-1')).delivery_status=='read'


def test_rate_limits_persist_across_sessions_without_identity_plaintext(ctx):
    _,_,sessions=ctx
    from app.rate_limits import consume
    with sessions() as db: consume(db,'test-login','private-identity',2,3600)
    with sessions() as db: consume(db,'test-login','private-identity',2,3600)
    with sessions() as db:
        with pytest.raises(HTTPException) as failure: consume(db,'test-login','private-identity',2,3600)
        assert failure.value.status_code==429
        bucket=db.scalar(select(RateLimitBucket).where(RateLimitBucket.key.like('test-login:%')))
        assert bucket.attempts==3 and 'private-identity' not in bucket.key


def test_operational_status_worker_and_scheduler_authorization(ctx,monkeypatch):
    c,h,sessions=ctx
    monkeypatch.setattr(worker,'SessionLocal',sessions);monkeypatch.setattr(worker,'engine',sessions.kw['bind'])
    monkeypatch.setattr(main,'job_tick',lambda:None)
    monkeypatch.setattr(settings,'job_runner_token','test-scheduler-token-with-32-characters')
    assert c.post('/api/internal/jobs/run').status_code==401
    assert c.post('/api/internal/jobs/run',headers={'X-Cityhive-Job-Token':settings.job_runner_token}).json()=={'status':'ok'}
    status=c.get('/api/deployment-status',headers=h)
    assert status.status_code==200 and status.json()['scheduler']['status']=='ok'
    assert settings.job_runner_token not in status.text and settings.jwt_secret not in status.text
    assert status.json()['expected_revision']=='0015_gap_completion'
    with sessions() as db: assert db.get(JobState,'reminders-and-moveouts').last_succeeded_at
    def fail(): raise ValueError('do not expose this secret')
    monkeypatch.setattr(main,'job_tick',fail)
    with pytest.raises(RuntimeError,match='Scheduled processing failed'): worker.run_once()
    with sessions() as db: assert db.get(JobState,'reminders-and-moveouts').status=='failed'


def test_analytics_as_of_timezone_and_settlement_statistics(ctx):
    c,h,sessions=ctx;rid=resident(c,h);i=bill(c,h,rid)
    from app.analytics import financial_report
    with sessions() as db:
        invoice=db.get(Invoice,i['id']);invoice.month=date(2026,1,1);invoice.due_on=date(2026,1,31)
        # 19:00 UTC Jan 31 = 00:30 IST Feb 1. One day after due date.
        db.add(Payment(invoice_id=invoice.id,amount=Decimal('8500'),method='upi',reference='',idempotency_key='timezone-payment',paid_at=datetime(2026,1,31,19),recorded_by=1));db.commit()
        owner=db.get(User,1)
        prior=financial_report(db,owner,date(2026,1,1),date(2026,2,28),date(2026,1,31),branch_id=1)
        assert prior['summary']['outstanding']=='8500.00'
        report=financial_report(db,owner,date(2026,1,1),date(2026,2,28),date(2026,2,2),branch_id=1)
        assert report['residents'][0]['average_settlement_delay_days']==1
        assert report['rooms'][0]['average_settlement_delay_days']==1
        assert report['summary']['on_time_rate_percent']==0
        assert report['collections_by_month']==[{'month':'2026-02','amount':'8500.00'}]
        assert report['collections_by_day']==[{'day':'2026-02-01','amount':'8500.00'}]
        merged=main.merge_financial_reports([report],date(2026,1,1),date(2026,2,28),date(2026,2,2))
        assert merged['collections_by_day']==report['collections_by_day']
        assert merged['summary']['average_settlement_delay_days']==1


def test_publication_edits_retain_data_and_reject_new_incompleteness(ctx):
    c,h,_=ctx;room(c,h)
    values={'name':'Branch A','address':'Verified test address','description':'Verified test description','contact_email':'property@example.com','image_url':'https://example.com/property.jpg'}
    assert c.put('/api/branches/1',headers=h,json=values).status_code==200
    assert c.put('/api/branches/1',headers=h,json={**values,'notice_days':30}).status_code==200
    assert c.put('/api/branches/1',headers=h,json={**values,'address':''}).status_code==409
    assert c.get('/api/branches').json()[0]['contact_email']=='property@example.com'
    assert c.put('/api/branches/1',headers=h,json={**values,'image_url':'javascript:alert(1)'}).status_code==422


def test_config_rejects_unsafe_production_and_cors(ctx):
    c,h,_=ctx
    cfg=Settings(_env_file=None,jwt_secret='a'*40,admin_password='long-secure-password',app_environment='production',database_url='postgresql+psycopg://user:private@db/cityhive',auto_migrate=False,cors_origins=['https://city-hive-jxyilflx.onslate.in'])
    cfg.validate_runtime()
    for origin in ['https://localhost:8000','https://a:password@example.com','https://example.com?token=x','https://example.com/path','https://[::1]','*']:
        cfg.cors_origins=[origin]
        with pytest.raises(RuntimeError,match='CORS'): cfg.validate_runtime()
    response=c.options('/api/branches',headers={'Origin':'https://untrusted.example','Access-Control-Request-Method':'GET'})
    assert 'access-control-allow-origin' not in response.headers
    response=c.get('/api/build');assert response.headers['x-content-type-options']=='nosniff'
    assert response.headers['cache-control']=='no-store'


def test_cloud_authentication_payload_and_provider_errors_do_not_leak(ctx,monkeypatch):
    monkeypatch.setattr(settings,'whatsapp_provider','cloud');monkeypatch.setattr(settings,'whatsapp_phone_number_id','test-number');monkeypatch.setattr(settings,'whatsapp_access_token','secret-provider-token');monkeypatch.setattr(settings,'whatsapp_api_version','v-test')
    captured={}
    class Response:
        def raise_for_status(self): pass
        def json(self): return {'messages':[{'id':'test-message-id'}]}
    def post(url,**kwargs): captured.update(kwargs);return Response()
    monkeypatch.setattr(whatsapp.httpx,'post',post)
    assert whatsapp.send_auth_code('9000000000','123456')=='test-message-id'
    components=captured['json']['template']['components']
    assert components[0]['parameters'][0]['text']=='123456'
    assert components[1]=={'type':'button','sub_type':'url','index':'0','parameters':[{'type':'text','text':'123456'}]}
    def fail(*args,**kwargs): raise RuntimeError('secret-provider-token')
    monkeypatch.setattr(whatsapp.httpx,'post',fail)
    with pytest.raises(whatsapp.WhatsAppUnavailable) as error: whatsapp.send_auth_code('9000000000','123456')
    assert 'secret-provider-token' not in str(error.value)
