import os
os.environ.setdefault('JWT_SECRET','test-secret-at-least-thirty-two-characters-long')
os.environ.setdefault('ADMIN_PASSWORD','TestOwner123!')
os.environ['JOBS_ENABLED']='false'
import pytest
from datetime import date, timedelta
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.db import Base, get_db
from app.models import User, Branch, BranchAdmin, Resident, Outbox, OtpChallenge, AuthAuditEvent, NotificationPreferenceEvent, PaymentAuditEvent, now
from app.security import hashing, token_for
from app.config import settings
from app.whatsapp import test_deliveries as read_test_deliveries, clear_test_deliveries
from app.services import local_today
@pytest.fixture()
def ctx(monkeypatch):
    clear_test_deliveries()
    monkeypatch.setattr(settings,'whatsapp_enabled',True)
    monkeypatch.setattr(settings,'whatsapp_provider','test')
    monkeypatch.setattr(settings,'app_environment','test')
    monkeypatch.setattr(settings,'whatsapp_auth_template_name','cityhive_test_auth')
    url=os.getenv('TEST_DATABASE_URL','sqlite://')
    if url!='sqlite://' and not (make_url(url).database or '').endswith('_test'):
        raise RuntimeError('TEST_DATABASE_URL must name a disposable database ending in _test')
    opts={'connect_args':{'check_same_thread':False},'poolclass':StaticPool} if url=='sqlite://' else {}
    schema=None
    if make_url(url).get_backend_name()=='postgresql':
        # A unique test schema avoids destructive changes to migrated tables,
        # including dormant historical tables not mapped by current models.
        schema='cityhive_test_'+uuid4().hex
        bootstrap=create_engine(url)
        with bootstrap.begin() as connection: connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        bootstrap.dispose()
        opts={'connect_args':{'options':f'-csearch_path={schema}'}}
    engine=create_engine(url,**opts)
    if schema is None: Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    sessions=sessionmaker(engine,expire_on_commit=False)
    with sessions() as db:
        db.add(User(email='owner@example.com',password_hash=hashing.hash('TestOwner123!'),role='admin',phone='9000000001')); db.commit()
        db.add(Branch(name='Branch A',published=True)); db.commit()
    def override():
        with sessions() as db: yield db
    app.dependency_overrides[get_db]=override
    c=TestClient(app)
    owner=login_with_otp(c,'owner@example.com','TestOwner123!')
    yield c,{'Authorization':'Bearer '+owner['access_token']},sessions
    app.dependency_overrides.clear(); engine.dispose()
    if schema:
        cleanup=create_engine(url)
        with cleanup.begin() as connection: connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        cleanup.dispose()
def resident(c,h,email='resident@example.com'):
    r=c.post('/api/residents',headers=h,json={'name':'Test Resident','email':email,'phone':'9000000000','joined_on':local_today().isoformat(),'temporary_password':'Temporary123!','aadhaar_last4':'1234'})
    assert r.status_code==201,r.text
    return r.json()['id']
def room(c,h,capacity=1):
    r=c.post('/api/rooms',headers=h,json={'number':'101','floor':'Ground','capacity':capacity,'monthly_fee':'8500.00'})
    assert r.status_code==201,r.text
    return r.json()['id']
def signin(c,email='resident@example.com'):
    r=login_with_otp(c,email,'Temporary123!')
    h={'Authorization':'Bearer '+r['access_token']}
    assert c.get('/api/invoices',headers=h).status_code==403
    assert c.post('/api/auth/password',headers=h,json={'current_password':'Temporary123!','new_password':'NewResident123!'}).status_code==200
    return h

def login_with_otp(c,email,password):
    started=c.post('/api/auth/login',json={'email':email,'password':password})
    assert started.status_code==200,started.text
    challenge=started.json()
    code=read_test_deliveries()[-1]['parameters'][0]
    verified=c.post('/api/auth/otp/verify',json={'challenge_id':challenge['challenge_id'],'code':code})
    assert verified.status_code==200,verified.text
    return verified.json()
def test_capacity_discount_and_onboarding(ctx):
    c,h,_=ctx; room_id=room(c,h); a=resident(c,h); b=resident(c,h,'other@example.com')
    assert c.put(f'/api/residents/{a}/allocation',headers=h,json={'room_id':room_id,'discount':'9000'}).status_code==400
    assert c.put(f'/api/residents/{a}/allocation',headers=h,json={'room_id':room_id,'discount':'500'}).status_code==200
    assert c.put(f'/api/residents/{b}/allocation',headers=h,json={'room_id':room_id,'discount':'0'}).status_code==409
    assert c.get('/api/rooms',headers=h).json()[0]['occupied']==1
    assert c.put(f'/api/residents/{a}/id-review',headers=h,json={'status':'reviewed'}).status_code==200
    assert c.get('/api/residents',headers=h).json()[1]['id_status']=='reviewed'
    assert c.get(f'/api/residents/{a}/verification-history',headers=h).json()[0]['new_status']=='reviewed'
    rh=signin(c)
    assert c.get('/api/rooms',headers=rh).status_code==403
    assert len(c.get('/api/residents',headers=rh).json())==1
    assert c.post('/api/rooms',headers=rh,json={'number':'hack','floor':'G','capacity':2,'monthly_fee':1}).status_code==403

def test_invoices_partial_payments_and_receipts(ctx):
    c,h,sessions=ctx; rid=resident(c,h); room_id=room(c,h)
    c.put(f'/api/residents/{rid}/allocation',headers=h,json={'room_id':room_id,'discount':'500'})
    month=local_today().replace(day=1).isoformat()
    assert c.post('/api/billing/generate',headers=h,json={'month':month}).json()=={'created':1}
    assert c.post('/api/billing/generate',headers=h,json={'month':month}).json()=={'created':0}
    i=c.get('/api/invoices',headers=h).json()[0]
    assert i['amount']=='8000.00'
    pdf=c.get(f"/api/invoices/{i['id']}/pdf",headers=h)
    assert pdf.status_code==200 and pdf.headers['content-type']=='application/pdf'
    assert pdf.content.startswith(b'%PDF-1.4') and i['invoice_number'].encode() in pdf.content
    assert b"CITYHIVE LUXURY PG'S AND CO-SPACE" in pdf.content
    c.put(f'/api/residents/{rid}/allocation',headers=h,json={'room_id':room_id,'discount':'1000'})
    assert c.get('/api/invoices',headers=h).json()[0]['amount']=='8000.00'
    p={'invoice_id':i['id'],'amount':'3000','method':'upi','reference':'UTR-123','idempotency_key':'unique-payment-key-1'}
    r=c.post('/api/payments',headers=h,json=p)
    assert r.status_code==201,r.text
    assert c.post('/api/payments',headers=h,json=p).json()['id']==r.json()['id']
    assert len(c.get('/api/payments',headers=h).json())==1
    assert c.post('/api/payments',headers=h,json={**p,'amount':'9000','idempotency_key':'unique-payment-key-2'}).status_code==400
    assert c.post('/api/payments',headers=h,json={**p,'amount':'4000'}).status_code==409
    receipt=c.get(f'/api/payments/{r.json()["id"]}/receipt',headers=h)
    assert 'Payment: INR 3000.00' in receipt.text and 'Balance after this payment: INR 5000.00' in receipt.text
    with sessions() as db:
        outbox=db.scalars(select(Outbox)).all()
        assert len(outbox)==1 and outbox[0].sent_at is None
    reminders=c.post('/api/reminders/run',headers=h).json()
    assert reminders['queued']==int(date.fromisoformat(i['due_on'])<=local_today()+timedelta(days=settings.upcoming_reminder_days))
    assert c.post('/api/reminders/run',headers=h).json()['queued']==0
    assert c.post('/api/payments',headers=h,json={**p,'amount':'5000','idempotency_key':'unique-payment-key-2'}).status_code==201
    assert c.get('/api/invoices',headers=h).json()[0]['status']=='paid'
    assert c.get(f'/api/payments/{r.json()["id"]}/receipt',headers=h).text==receipt.text
    resident(c,h,'other@example.com'); rh=signin(c,'other@example.com')
    assert c.get(f'/api/payments/{r.json()["id"]}/receipt',headers=rh).status_code==403
    assert c.get(f"/api/invoices/{i['id']}/pdf",headers=rh).status_code==403
    assert c.get('/api/payments',headers=rh).json()==[]

def test_payment_reversal_preserves_audit_and_reopens_balance(ctx):
    c,h,sessions=ctx; rid=resident(c,h); room_id=room(c,h)
    c.put(f'/api/residents/{rid}/allocation',headers=h,json={'room_id':room_id,'discount':'0'})
    c.post('/api/billing/generate',headers=h,json={'month':local_today().replace(day=1).isoformat()})
    invoice=c.get('/api/invoices',headers=h).json()[0]
    created=c.post('/api/payments',headers=h,json={'invoice_id':invoice['id'],'amount':'2500','method':'cash','reference':'','payer_name':'Test Payer','note':'Front desk','idempotency_key':'reverse-payment-test'}).json()
    assert c.get('/api/invoices',headers=h).json()[0]['balance']=='6000.00'
    reversed_response=c.post(f"/api/payments/{created['id']}/reverse",headers=h,json={'reason':'Duplicate cash entry recorded in error'})
    assert reversed_response.status_code==200 and reversed_response.json()['balance']=='8500.00'
    assert c.post(f"/api/payments/{created['id']}/reverse",headers=h,json={'reason':'Duplicate entry reversal'}).status_code==409
    payment_row=next(p for p in c.get('/api/payments',headers=h).json() if p['id']==created['id'])
    assert payment_row['reversed_at'] and payment_row['payer_name']=='Test Payer'
    receipt=c.get(f"/api/payments/{created['id']}/receipt",headers=h)
    assert 'PAYMENT REVERSED: Duplicate cash entry recorded in error' in receipt.text
    with sessions() as db:
        event=db.scalar(select(PaymentAuditEvent).where(PaymentAuditEvent.payment_id==created['id']))
        assert event.action=='reversed' and event.actor_user_id is not None
        assert db.scalar(select(Outbox.id).where(Outbox.dedupe_key==f'payment-reversal:{created["id"]}')) is not None
    report=c.get('/api/analytics/financial',headers=h,params={'from_date':local_today().replace(day=1),'to_date':local_today()}).json()
    assert report['summary']['collected']=='0.00' and report['summary']['cash_collected']=='0.00'

def test_financial_analytics_settlement_aging_history_and_csv(ctx):
    from datetime import timedelta
    from datetime import date
    c,h,_=ctx
    rid=resident(c,h)
    room_id=room(c,h)
    assert c.put(f'/api/residents/{rid}/allocation',headers=h,json={'room_id':room_id,'discount':'500'}).status_code==200
    month=local_today().replace(day=1).isoformat()
    assert c.post('/api/billing/generate',headers=h,json={'month':month}).json()['created']==1
    invoice=c.get('/api/invoices',headers=h).json()[0]
    start=local_today().replace(day=1)
    end=(start+timedelta(days=32)).replace(day=1)-timedelta(days=1)
    params={'from_date':start.isoformat(),'to_date':end.isoformat(),'as_of':local_today().isoformat()}
    payment={'invoice_id':invoice['id'],'amount':'3000','method':'cash','reference':'','idempotency_key':'analytics-cash-partial'}
    assert c.post('/api/payments',headers=h,json=payment).status_code==201
    partial=c.get('/api/analytics/financial',headers=h,params=params)
    assert partial.status_code==200,partial.text
    report=partial.json()
    assert report['summary']['outstanding']=='5000.00'
    assert report['summary']['overdue']=='5000.00'
    assert report['summary']['settled_invoice_count']==0
    assert report['residents'][0]['average_settlement_delay_days'] is None
    assert report['cash_by_staff'][0]['amount']=='3000.00'
    if (local_today()-date.fromisoformat(invoice['due_on'])).days in range(8,31):
        assert report['aging']['8_30_days']=='5000.00'
    assert c.post('/api/payments',headers=h,json={**payment,'amount':'5000','idempotency_key':'analytics-cash-settle'}).status_code==201
    new_room=c.post('/api/rooms',headers=h,json={'number':'102','floor':'First','capacity':1,'monthly_fee':'9000'}).json()['id']
    assert c.put(f'/api/residents/{rid}/allocation',headers=h,json={'room_id':new_room,'discount':'0'}).status_code==200
    settled=c.get('/api/analytics/financial',headers=h,params=params).json()
    delay=max(0,(local_today()-date.fromisoformat(invoice['due_on'])).days)
    assert settled['summary']['outstanding']=='0.00'
    assert settled['summary']['overdue']=='0.00'
    assert settled['summary']['settled_invoice_count']==1
    assert settled['summary']['average_settlement_delay_days']==delay
    historical=next(r for r in settled['rooms'] if r['room_number']=='101')
    assert historical['fully_settled_invoice_count']==1
    assert settled['residents'][0]['current_room_number']=='102'
    assert settled['residents'][0]['last_settled_invoice']['invoice_number']==invoice['invoice_number']
    exported=c.get('/api/analytics/financial.csv',headers=h,params=params)
    assert exported.status_code==200 and 'Resident Payment Performance' in exported.text

def test_financial_analytics_branch_scoping_and_resident_denial(ctx):
    c,h,sessions=ctx
    branch_a=c.get('/api/branches').json()[0]['id']
    branch_b=c.post('/api/branches',headers=h,json={'name':'Analytics Branch B'}).json()['id']
    resident_a=resident(c,h,'analytics-a@example.com')
    resident_b=c.post('/api/residents',headers=h,json={'branch_id':branch_b,'name':'Analytics Resident B','email':'analytics-b@example.com','phone':'9111111111','joined_on':local_today().isoformat(),'temporary_password':'Temporary123!'}).json()['id']
    room_a=c.post('/api/rooms',headers=h,json={'branch_id':branch_a,'number':'A-analytics','floor':'G','capacity':1,'monthly_fee':'1000'}).json()['id']
    room_b=c.post('/api/rooms',headers=h,json={'branch_id':branch_b,'number':'B-analytics','floor':'G','capacity':1,'monthly_fee':'2000'}).json()['id']
    c.put(f'/api/residents/{resident_a}/allocation',headers=h,json={'room_id':room_a,'discount':'0'})
    c.put(f'/api/residents/{resident_b}/allocation',headers=h,json={'room_id':room_b,'discount':'0'})
    c.post('/api/billing/generate',headers=h,json={'month':local_today().replace(day=1).isoformat()})
    start=local_today().replace(day=1).isoformat(); end=local_today().isoformat()
    selected={'from_date':start,'to_date':end,'branch_id':branch_b}
    assert c.get('/api/analytics/financial',headers=h,params=selected).json()['residents'][0]['resident_id']==resident_b
    with sessions() as db:
        account=User(email='analytics-branch-admin@example.com',password_hash=hashing.hash('BranchAdmin123!'),role='branch_admin')
        db.add(account);db.flush();db.add(BranchAdmin(user_id=account.id,branch_id=branch_a));db.commit()
        headers={'Authorization':'Bearer '+token_for(account,mfa_verified=True)}
    report=c.get('/api/analytics/financial',headers=headers,params={'from_date':start,'to_date':end})
    assert report.status_code==200
    assert {r['resident_id'] for r in report.json()['residents']}=={resident_a}
    assert c.get('/api/analytics/financial',headers=headers,params=selected).status_code==403
    login=login_with_otp(c,'analytics-a@example.com','Temporary123!')
    resident_headers={'Authorization':'Bearer '+login['access_token']}
    assert c.get('/api/analytics/financial',headers=resident_headers,params={'from_date':start,'to_date':end}).status_code==403

def test_whatsapp_otp_never_issues_jwt_before_verification_and_is_single_use(ctx):
    c,h,sessions=ctx
    r=resident(c,h)
    started_response=c.post('/api/auth/login',json={'email':'resident@example.com','password':'Temporary123!'})
    assert started_response.status_code==200
    started=started_response.json()
    assert 'access_token' not in started and 'code' not in started
    assert c.get('/api/invoices',headers={'Authorization':'Bearer '+started['challenge_id']}).status_code==401
    code=read_test_deliveries()[-1]['parameters'][0]
    with sessions() as db:
        challenge=db.scalar(select(OtpChallenge).where(OtpChallenge.challenge_id==started['challenge_id']))
        assert challenge is not None and challenge.code_hash!=code
        assert code not in challenge.code_hash
    verified=c.post('/api/auth/otp/verify',json={'challenge_id':started['challenge_id'],'code':code})
    assert verified.status_code==200 and 'access_token' in verified.json()
    assert c.get('/api/auth/me',headers={'Authorization':'Bearer '+verified.json()['access_token']}).status_code==200
    assert c.post('/api/auth/otp/verify',json={'challenge_id':started['challenge_id'],'code':code}).status_code==400
    with sessions() as db:
        account=db.scalar(select(User).where(User.email=='resident@example.com'))
        assert account.phone=='9000000000' and account.phone_verified_at is not None
        assert db.scalar(select(func.count(AuthAuditEvent.id)).where(AuthAuditEvent.event=='otp_verified',AuthAuditEvent.user_id==account.id))==1

def test_otp_attempt_limit_expiration_and_resend_replacement(ctx):
    from datetime import timedelta
    from app import whatsapp
    c,h,sessions=ctx; resident(c,h)
    start=c.post('/api/auth/login',json={'email':'resident@example.com','password':'Temporary123!'}).json()
    correct=read_test_deliveries()[-1]['parameters'][0]
    wrong='000000' if correct!='000000' else '000001'
    for _ in range(5):
        response=c.post('/api/auth/otp/verify',json={'challenge_id':start['challenge_id'],'code':wrong})
        assert response.status_code==400
    assert c.post('/api/auth/otp/verify',json={'challenge_id':start['challenge_id'],'code':correct}).status_code==400
    with sessions() as db:
        row=db.scalar(select(OtpChallenge).where(OtpChallenge.challenge_id==start['challenge_id']))
        row.created_at=now()-timedelta(seconds=61); row.last_sent_at=now()-timedelta(seconds=61); db.commit()
    expired=c.post('/api/auth/login',json={'email':'resident@example.com','password':'Temporary123!'}).json()
    with sessions() as db:
        challenge=db.scalar(select(OtpChallenge).where(OtpChallenge.challenge_id==expired['challenge_id']))
        challenge.expires_at=now()-timedelta(seconds=1); db.commit()
    assert c.post('/api/auth/otp/verify',json={'challenge_id':expired['challenge_id'],'code':read_test_deliveries()[-1]['parameters'][0]}).status_code==400
    with sessions() as db:
        row=db.scalar(select(OtpChallenge).where(OtpChallenge.challenge_id==expired['challenge_id']))
        row.created_at=now()-timedelta(seconds=61); row.last_sent_at=now()-timedelta(seconds=61); db.commit()
    resend_start=c.post('/api/auth/login',json={'email':'resident@example.com','password':'Temporary123!'}).json()
    old_code=read_test_deliveries()[-1]['parameters'][0]
    assert c.post('/api/auth/otp/resend',json={'challenge_id':resend_start['challenge_id']}).status_code==429
    with sessions() as db:
        row=db.scalar(select(OtpChallenge).where(OtpChallenge.challenge_id==resend_start['challenge_id']))
        row.created_at=now()-timedelta(seconds=61); row.last_sent_at=now()-timedelta(seconds=61); db.commit()
    resent=c.post('/api/auth/otp/resend',json={'challenge_id':resend_start['challenge_id']})
    assert resent.status_code==200 and resent.json()['challenge_id']!=resend_start['challenge_id']
    new_code=read_test_deliveries()[-1]['parameters'][0]
    assert new_code!=old_code
    assert c.post('/api/auth/otp/verify',json={'challenge_id':resend_start['challenge_id'],'code':old_code}).status_code==400
    assert c.post('/api/auth/otp/verify',json={'challenge_id':resent.json()['challenge_id'],'code':new_code}).status_code==200

def test_otp_disabled_and_provider_failure_fail_closed(ctx,monkeypatch):
    from app import whatsapp
    c,h,sessions=ctx; resident(c,h)
    with sessions() as db: before=db.scalar(select(func.count(OtpChallenge.id)))
    monkeypatch.setattr(settings,'whatsapp_enabled',False)
    response=c.post('/api/auth/login',json={'email':'resident@example.com','password':'Temporary123!'})
    assert response.status_code==503 and 'access_token' not in response.json()
    monkeypatch.setattr(settings,'whatsapp_enabled',True)
    def fail(*args,**kwargs): raise whatsapp.WhatsAppUnavailable('provider unavailable')
    monkeypatch.setattr(whatsapp,'send_auth_code',fail)
    response=c.post('/api/auth/login',json={'email':'resident@example.com','password':'Temporary123!'})
    assert response.status_code==503 and 'access_token' not in response.json()
    with sessions() as db: assert db.scalar(select(func.count(OtpChallenge.id)))==before

def test_resident_notification_consent_is_audited_and_scoped(ctx):
    c,h,sessions=ctx; rid=resident(c,h)
    auth=signin(c)
    current=c.get('/api/my/notification-preferences',headers=auth)
    assert current.status_code==200 and current.json()['whatsapp_enabled'] is False
    assert c.put('/api/my/notification-preferences',headers=auth,json={'whatsapp_enabled':True}).status_code==200
    assert c.put('/api/my/notification-preferences',headers=auth,json={'whatsapp_enabled':False}).json()['whatsapp_enabled'] is False
    with sessions() as db:
        events=db.scalars(select(NotificationPreferenceEvent).where(NotificationPreferenceEvent.resident_id==rid).order_by(NotificationPreferenceEvent.id)).all()
        assert [(e.enabled,e.source) for e in events]==[(True,'resident_portal'),(False,'resident_portal')]
    assert c.get('/api/my/notification-preferences',headers=h).status_code==403

def test_opted_in_whatsapp_reminder_uses_deduplicated_outbox(ctx,monkeypatch):
    from app import services
    c,h,sessions=ctx; rid=resident(c,h); room_id=room(c,h)
    assert c.put(f'/api/residents/{rid}/allocation',headers=h,json={'room_id':room_id,'discount':'0'}).status_code==200
    assert c.post('/api/billing/generate',headers=h,json={'month':local_today().replace(day=1).isoformat()}).status_code==200
    with sessions() as db:
        person=db.get(Resident,rid); person.whatsapp_notifications=True; person.whatsapp_consent_at=now(); db.commit()
    with sessions() as db:
        assert services.queue_reminders(db)==1; db.commit()
    with sessions() as db:
        assert services.queue_reminders(db)==0
        reminder=db.scalar(select(Outbox).where(Outbox.channel=='whatsapp'))
        assert reminder is not None and reminder.recipient=='9000000000' and reminder.sent_at is None
    monkeypatch.setattr(services,'SessionLocal',sessions)
    services.deliver_emails()
    assert any(item['kind']=='utility' for item in read_test_deliveries())

def test_complaint_privacy_and_response(ctx):
    c,h,_=ctx; resident(c,h); resident(c,h,'other@example.com'); rh=signin(c); other=signin(c,'other@example.com')
    r=c.post('/api/complaints',headers=rh,json={'category':'maintenance','title':'Ceiling fan','description':'The ceiling fan is not working.'})
    assert r.status_code==201
    assert c.get('/api/complaints',headers=other).json()==[]
    assert c.put(f'/api/complaints/{r.json()["id"]}',headers=rh,json={'status':'resolved','response':'Test'}).status_code==403
    assert c.put(f'/api/complaints/{r.json()["id"]}',headers=h,json={'status':'resolved','response':'Electrician fixed the fan.'}).status_code==200
    complaint=c.get('/api/complaints',headers=rh).json()[0]
    assert complaint['response']=='Electrician fixed the fan.'
    assert [(event['action'],event['new_status']) for event in complaint['history']]==[('submitted','open'),('updated','resolved')]
    assert complaint['history'][1]['old_response']==''
    assert complaint['history'][1]['new_response']=='Electrician fixed the fan.'

def test_validation_and_auth(ctx):
    c,h,_=ctx
    assert c.get('/api/residents').status_code==401
    assert c.post('/api/rooms',headers=h,json={'number':'101','floor':'Ground','capacity':0,'monthly_fee':-1}).status_code==422
    resident(c,h)
    assert c.post('/api/residents',headers=h,json={'name':'Bad','email':'bad@example.com','phone':'123','joined_on':local_today().isoformat(),'temporary_password':'Temporary123!','aadhaar_last4':'123456789012'}).status_code==422

def test_email_worker_success_retry_and_daily_dedup(ctx,monkeypatch):
    from app import services
    from datetime import date
    c,h,sessions=ctx; rid=resident(c,h); room_id=room(c,h)
    c.put(f'/api/residents/{rid}/allocation',headers=h,json={'room_id':room_id,'discount':'0'})
    c.post('/api/billing/generate',headers=h,json={'month':local_today().replace(day=1).isoformat()})
    i=c.get('/api/invoices',headers=h).json()[0]
    monkeypatch.setattr(services,'local_today',lambda:date.fromisoformat(i['month']).replace(day=10))
    with sessions() as db:
        assert services.queue_reminders(db)==1
        assert services.queue_reminders(db)==0
        db.commit()
    monkeypatch.setattr(services,'SessionLocal',sessions)
    class BrokenSMTP:
        def __init__(self,*a,**kw): raise OSError('offline')
    monkeypatch.setattr(services.smtplib,'SMTP',BrokenSMTP)
    services.deliver_emails()
    with sessions() as db:
        item=db.scalar(select(Outbox)); assert item.attempts==1 and item.sent_at is None and item.last_error
        item.next_attempt_at=services.now()-timedelta(seconds=1); db.commit()
    sent=[]
    class FakeSMTP:
        def __init__(self,*a,**kw): pass
        def __enter__(self): return self
        def __exit__(self,*a): pass
        def send_message(self,msg): sent.append(msg)
    monkeypatch.setattr(services.smtplib,'SMTP',FakeSMTP)
    services.deliver_emails(); services.deliver_emails()
    assert len(sent)==1 and sent[0]['To']=='resident@example.com'
    with sessions() as db:
        item=db.scalar(select(Outbox)); assert item.sent_at is not None and item.attempts==2 and not item.last_error

def test_settled_reminder_is_cancelled(ctx,monkeypatch):
    from app import services
    from datetime import date
    c,h,sessions=ctx; rid=resident(c,h); room_id=room(c,h)
    c.put(f'/api/residents/{rid}/allocation',headers=h,json={'room_id':room_id,'discount':'0'})
    c.post('/api/billing/generate',headers=h,json={'month':local_today().replace(day=1).isoformat()})
    i=c.get('/api/invoices',headers=h).json()[0]
    monkeypatch.setattr(services,'local_today',lambda:date.fromisoformat(i['month']).replace(day=10))
    with sessions() as db:
        assert services.queue_reminders(db)==1
        db.commit()
    r=c.post('/api/payments',headers=h,json={'invoice_id':i['id'],'amount':'8500','method':'cash','reference':'','idempotency_key':'settle-and-cancel-reminder'})
    assert r.status_code==201
    monkeypatch.setattr(services,'SessionLocal',sessions)
    sent=[]
    class FakeSMTP:
        def __init__(self,*a,**kw): pass
        def __enter__(self): return self
        def __exit__(self,*a): pass
        def send_message(self,msg): sent.append(msg)
    monkeypatch.setattr(services.smtplib,'SMTP',FakeSMTP)
    services.deliver_emails()
    assert len(sent)==1 and 'receipt' in sent[0]['Subject']
    with sessions() as db:
        reminder=db.scalar(select(Outbox).where(Outbox.dedupe_key.like('reminder:%')))
        assert reminder.cancelled and reminder.sent_at is None

def test_branch_setup_and_cross_branch_allocation_guard(ctx):
    c,h,_=ctx
    branch_a=c.get('/api/branches').json()[0]
    created=c.post('/api/branches',headers=h,json={'name':'Branch B','address':'Example address','contact_phone':'9000000000','description':'Second location','rules':'Configure rules'} )
    assert created.status_code==201
    branch_b=created.json()['id']
    resident_id=resident(c,h)
    room_id=c.post('/api/rooms',headers=h,json={'branch_id':branch_b,'number':'B-101','floor':'First','capacity':2,'monthly_fee':'9000.00'}).json()['id']
    assert c.put(f'/api/residents/{resident_id}/allocation',headers=h,json={'room_id':room_id,'discount':'0'}).status_code==409
    assert c.get('/api/branches').json()[0]['name']==branch_a['name']

def test_branch_admin_isolation_across_residents_rooms_invoices_and_payments(ctx):
    c,h,sessions=ctx
    branch_a=c.get('/api/branches').json()[0]['id']
    branch_b=c.post('/api/branches',headers=h,json={'name':'Branch B','address':'Example address','description':'A configured test location'}).json()['id']
    resident_a=resident(c,h,'a@example.com')
    response=c.post('/api/residents',headers=h,json={'branch_id':branch_b,'name':'Branch B Resident','email':'b@example.com','phone':'9111111111','joined_on':local_today().isoformat(),'temporary_password':'Temporary123!'})
    assert response.status_code==201,response.text
    resident_b=response.json()['id']
    room_a=c.post('/api/rooms',headers=h,json={'branch_id':branch_a,'number':'A-101','floor':'Ground','capacity':2,'monthly_fee':'8500'}).json()['id']
    room_b=c.post('/api/rooms',headers=h,json={'branch_id':branch_b,'number':'B-101','floor':'Ground','capacity':2,'monthly_fee':'9000'}).json()['id']
    assert c.put(f'/api/branches/{branch_b}/publication?published=true',headers=h).status_code==200
    assert c.put(f'/api/residents/{resident_a}/allocation',headers=h,json={'room_id':room_a,'discount':'0'}).status_code==200
    assert c.put(f'/api/residents/{resident_b}/allocation',headers=h,json={'room_id':room_b,'discount':'0'}).status_code==200
    admission_payload={'branch_id':branch_b,'name':'Branch B Applicant','email':'admission-b@example.com','phone':'9444444444','preferred_sharing':2,'move_in_date':local_today().isoformat(),'submission_key':uuid4().hex}
    admission=c.post('/api/admissions',json=admission_payload)
    assert admission.status_code==201,admission.text
    month=local_today().replace(day=1).isoformat()
    assert c.post('/api/billing/generate',headers=h,json={'month':month}).json()['created']==2
    invoices=c.get('/api/invoices',headers=h).json()
    inv_b=next(i for i in invoices if i['resident_id']==resident_b)
    payment=c.post('/api/payments',headers=h,json={'invoice_id':inv_b['id'],'amount':'100','method':'cash','reference':'','idempotency_key':'branch-b-payment-key'} )
    assert payment.status_code==201,payment.text
    with sessions() as db:
        admin_user=User(email='branch-a-admin@example.com',password_hash=hashing.hash('BranchAdmin123!'),role='branch_admin')
        db.add(admin_user);db.flush();db.add(BranchAdmin(user_id=admin_user.id,branch_id=branch_a));db.commit()
        headers={'Authorization':'Bearer '+token_for(admin_user,mfa_verified=True)}
    assert c.put(f'/api/branches/{branch_a}/publication?published=false',headers=headers).status_code==403
    assert {r['id'] for r in c.get('/api/residents',headers=headers).json()}=={resident_a}
    assert {r['id'] for r in c.get('/api/rooms',headers=headers).json()}=={room_a}
    assert len(c.get('/api/invoices',headers=headers).json())==1
    assert c.get('/api/invoices',headers=headers).json()[0]['resident_id']==resident_a
    assert c.get(f"/api/invoices/{inv_b['id']}/pdf",headers=headers).status_code==403
    assert c.get('/api/payments',headers=headers).json()==[]
    assert c.get(f'/api/payments/{payment.json()["id"]}/receipt',headers=headers).status_code==403
    assert c.get('/api/admissions',headers=headers).json()==[]
    assert c.put(f'/api/admissions/{admission.json()["id"]}',headers=headers,json={'status':'approved','note':''}).status_code==403
    assert c.put(f'/api/residents/{resident_b}/allocation',headers=headers,json={'room_id':room_b,'discount':'0'}).status_code==403
    assert c.put(f'/api/residents/{resident_b}/id-review',headers=headers,json={'status':'reviewed'}).status_code==403
    assert c.post('/api/rooms',headers=headers,json={'branch_id':branch_b,'number':'B-102','floor':'Ground','capacity':2,'monthly_fee':'9000'}).status_code==403
    assert all(e['recipient']!='admission-b@example.com' for e in c.get('/api/emails',headers=headers).json())
    assert c.put(f'/api/branches/{branch_b}',headers=headers,json={'name':'Branch B','active':True}).status_code==403
    assert c.post('/api/branch-admins',headers=headers,json={'email':'other@example.com','temporary_password':'Temporary123!','branch_ids':[branch_b]}).status_code==403

def test_owner_can_assign_branch_admin_and_account_must_change_password(ctx):
    c,h,_=ctx
    branch=c.get('/api/branches').json()[0]['id']
    created=c.post('/api/branch-admins',headers=h,json={'email':'assigned@example.com','phone':'9000000002','temporary_password':'BranchAdmin123!','branch_ids':[branch]})
    assert created.status_code==201,created.text
    assert c.get('/api/branch-admins',headers=h).json()[0]['branches']==['Branch A']
    login=login_with_otp(c,'assigned@example.com','BranchAdmin123!')
    ah={'Authorization':'Bearer '+login['access_token']}
    assert c.get('/api/residents',headers=ah).status_code==403
    changed=c.post('/api/auth/password',headers=ah,json={'current_password':'BranchAdmin123!','new_password':'BranchAdmin456!'})
    assert changed.status_code==200
    assert c.get('/api/residents',headers=ah).status_code==200

def test_public_admission_is_idempotent_reviewable_and_enrollable(ctx):
    c,h,_=ctx
    branch=c.get('/api/branches').json()[0]['id']
    r=c.post('/api/rooms',headers=h,json={'branch_id':branch,'number':'101','floor':'Ground','capacity':2,'monthly_fee':'8500'})
    assert r.status_code==201
    availability=c.get(f'/api/public/branches/{branch}/availability')
    assert availability.json()==[{'sharing':2,'monthly_fee':'8500.00','advance_amount':'0.00','additional_charge_label':'','additional_charge_amount':'0.00','available_beds':2}]
    payload={'branch_id':branch,'name':'Applicant Example','email':'applicant@example.com','phone':'9222222222','emergency_contact':'Emergency Example','emergency_phone':'9333333333','preferred_sharing':2,'move_in_date':local_today().isoformat(),'message':'Please contact me','submission_key':uuid4().hex}
    submitted=c.post('/api/admissions',json=payload)
    assert submitted.status_code==201,submitted.text
    replay=c.post('/api/admissions',json=payload)
    assert replay.status_code==201 and replay.json()['id']==submitted.json()['id'] and replay.json()['duplicate']
    assert c.post('/api/admissions',json={**payload,'submission_key':uuid4().hex}).status_code==409
    assert c.get('/api/admissions').status_code==401
    items=c.get('/api/admissions',headers=h).json()
    assert len(items)==1 and items[0]['status']=='pending'
    assert c.put(f"/api/admissions/{submitted.json()['id']}",headers=h,json={'status':'approved','note':'Room options confirmed'}).json()['status']=='approved'
    enrolled=c.post(f"/api/admissions/{submitted.json()['id']}/enroll",headers=h,json={'temporary_password':'Temporary123!'})
    assert enrolled.status_code==201,enrolled.text
    resident_row=next(r for r in c.get('/api/residents',headers=h).json() if r['id']==enrolled.json()['resident_id'])
    assert resident_row['branch_id']==branch and resident_row['room_id'] is None
    assert c.post(f"/api/admissions/{submitted.json()['id']}/enroll",headers=h,json={'temporary_password':'Temporary456!' }).status_code==409
    assert c.post('/api/admissions',json={**payload,'email':'full@example.com','preferred_sharing':3,'submission_key':uuid4().hex}).status_code==409

def test_public_branches_require_owner_publication_and_complete_listing(ctx):
    c,h,_=ctx
    internal=c.post('/api/branches',headers=h,json={'name':'Placeholder Location','address':'Locality, City','description':'Configure this location in branch settings.'}).json()['id']
    c.post('/api/rooms',headers=h,json={'branch_id':internal,'number':'P-101','floor':'First','capacity':2,'monthly_fee':'9500'})
    assert c.put(f'/api/branches/{internal}/publication?published=true',headers=h).status_code==409
    branch=c.post('/api/branches',headers=h,json={'name':'Second Location','address':'Locality, City','description':'Configured public description'}).json()['id']
    assert all(item['id']!=branch for item in c.get('/api/branches').json())
    assert c.put(f'/api/branches/{branch}/publication?published=true',headers=h).status_code==409
    c.post('/api/rooms',headers=h,json={'branch_id':branch,'number':'S-101','floor':'First','capacity':2,'monthly_fee':'9500'})
    assert c.put(f'/api/branches/{branch}/publication?published=true').status_code==401
    response=c.put(f'/api/branches/{branch}/publication?published=true',headers=h)
    assert response.status_code==200 and response.json()['published']
    assert any(item['id']==branch for item in c.get('/api/branches').json())
    assert c.put(f'/api/branches/{branch}/publication?published=false',headers=h).status_code==200
    assert all(item['id']!=branch for item in c.get('/api/branches').json())
    assert c.get(f'/api/public/branches/{branch}/availability').status_code==404

def test_room_edit_allocation_history_stays_and_scheduled_vacating(ctx,monkeypatch):
    from datetime import timedelta
    from app import main
    c,h,_=ctx
    room_id=room(c,h,capacity=2)
    resident_a=resident(c,h,'stay-a@example.com')
    resident_b=resident(c,h,'stay-b@example.com')
    c.put(f'/api/residents/{resident_a}/allocation',headers=h,json={'room_id':room_id,'discount':'0','reason':'Move in'})
    c.put(f'/api/residents/{resident_b}/allocation',headers=h,json={'room_id':room_id,'discount':'0'})
    assert c.put(f'/api/rooms/{room_id}',headers=h,json={'number':'101','floor':'Ground','capacity':1,'monthly_fee':'9000'}).status_code==409
    target=c.post('/api/rooms',headers=h,json={'number':'102','floor':'First','capacity':2,'monthly_fee':'9000'}).json()['id']
    assert c.put(f'/api/rooms/{target}',headers=h,json={'number':'102','floor':'Second','capacity':3,'monthly_fee':'9500'}).status_code==200
    rh=signin(c,'stay-a@example.com')
    future=local_today()+timedelta(days=40)
    extend=c.post('/api/my/stay-requests',headers=rh,json={'request_type':'extension','requested_move_out':future.isoformat(),'note':'Extend study term'})
    assert extend.status_code==201,extend.text
    assert c.put(f"/api/stay-requests/{extend.json()['id']}",headers=h,json={'status':'approved','note':'Approved'}).status_code==200
    assert c.get('/api/residents',headers=rh).json()[0]['planned_move_out']==future.isoformat()
    shift=c.post('/api/my/stay-requests',headers=rh,json={'request_type':'shift','target_room_id':target,'note':'Closer to common area'})
    assert shift.status_code==201,shift.text
    assert c.put(f"/api/stay-requests/{shift.json()['id']}",headers=h,json={'status':'approved','note':'Approved shift'}).status_code==200
    history=c.get(f'/api/residents/{resident_a}/allocation-history',headers=rh)
    assert [x['to_room'] for x in history.json()]==['102','101']
    branch_id=c.get('/api/branches').json()[0]['id']
    branch=c.get('/api/branches').json()[0]
    assert c.put(f"/api/branches/{branch_id}",headers=h,json={**branch,'notice_days':30}).status_code==200
    planned=local_today()+timedelta(days=1)
    payload={'request_type':'vacating','requested_move_out':planned.isoformat(),'note':'Moving out'}
    assert c.post('/api/my/stay-requests',headers=rh,json=payload).status_code==422
    payload['notice_exception_reason']='Employer relocation'
    vacate=c.post('/api/my/stay-requests',headers=rh,json=payload)
    assert vacate.status_code==201,vacate.text
    assert c.put(f"/api/stay-requests/{vacate.json()['id']}",headers=h,json={'status':'approved','note':'Exception approved'}).status_code==200
    assert c.post('/api/stays/process-moveouts',headers=h).json()['vacated']==0
    monkeypatch.setattr(main,'local_today',lambda:planned)
    assert c.post('/api/stays/process-moveouts',headers=h).json()['vacated']==1
    resident_info=c.get('/api/residents',headers=rh).json()[0]
    assert resident_info['status']=='vacated' and resident_info['room_id'] is None
    assert c.get('/api/rooms',headers=h).json()[1]['occupied']==0


def test_basic_gate_pass_records_remain_scoped_without_qr_or_validation(ctx):
    c,h,sessions=ctx
    branch_a=c.get('/api/branches',headers=h).json()[0]['id']
    branch_b=c.post('/api/branches',headers=h,json={'name':'Gate Pass Branch B'}).json()['id']
    resident_a=resident(c,h,'gate-a@example.com')
    b_response=c.post('/api/residents',headers=h,json={'branch_id':branch_b,'name':'Gate Pass Resident B','email':'gate-b@example.com','phone':'9111111111','joined_on':local_today().isoformat(),'temporary_password':'Temporary123!'})
    assert b_response.status_code==201,b_response.text
    resident_b=b_response.json()['id']

    issued_a=c.post('/api/gate-passes',headers=h,json={'resident_id':resident_a})
    issued_b=c.post('/api/gate-passes',headers=h,json={'resident_id':resident_b})
    assert issued_a.status_code==201,issued_a.text
    assert issued_b.status_code==201,issued_b.text
    pass_a,pass_b=issued_a.json(),issued_b.json()
    assert pass_a['resident_code'].startswith('CH-')
    assert pass_a['id']!=pass_b['id'] and 'pass_code' not in pass_a
    assert c.get(f'/api/gate-passes/{pass_a["id"]}/qr',headers=h).status_code==404
    assert c.get(f'/api/gate-passes/{pass_a["id"]}/validation-history',headers=h).status_code==404
    assert c.get('/api/gate-passes/validate/not-a-real-pass',headers=h).status_code==404
    assert c.post('/api/gate-passes',headers=h,json={'resident_id':resident_a,'valid_until':'2000-01-01'}).status_code==422

    resident_headers=signin(c,'gate-a@example.com')
    resident_passes=c.get('/api/gate-passes',headers=resident_headers)
    assert resident_passes.status_code==200
    assert [item['id'] for item in resident_passes.json()]==[pass_a['id']]
    assert c.post('/api/gate-passes',headers=resident_headers,json={'resident_id':resident_a}).status_code==403
    assert c.put(f'/api/gate-passes/{pass_a["id"]}/revoke',headers=resident_headers).status_code==403

    with sessions() as db:
        admin_user=User(email='gate-branch-admin@example.com',password_hash=hashing.hash('BranchAdmin123!'),role='branch_admin')
        db.add(admin_user);db.flush();db.add(BranchAdmin(user_id=admin_user.id,branch_id=branch_a));db.commit()
        branch_headers={'Authorization':'Bearer '+token_for(admin_user,mfa_verified=True)}
    visible=c.get('/api/gate-passes',headers=branch_headers)
    assert visible.status_code==200
    assert [item['id'] for item in visible.json()]==[pass_a['id']]
    assert c.put(f'/api/gate-passes/{pass_b["id"]}/revoke',headers=branch_headers).status_code==403
    assert c.put(f'/api/gate-passes/{pass_a["id"]}/revoke',headers=branch_headers).status_code==200
    assert c.put(f'/api/gate-passes/{pass_a["id"]}/revoke',headers=branch_headers).status_code==409
    resident_passes=c.get('/api/gate-passes',headers=resident_headers).json()
    assert resident_passes[0]['status']=='revoked' and resident_passes[0]['is_valid'] is False
    assert resident_passes[0]['resident_code']==pass_a['resident_code']


def test_effective_fee_plans_preserve_invoice_snapshots_and_scope(ctx,monkeypatch):
    from datetime import timedelta
    c,h,sessions=ctx
    branch_a=c.get('/api/branches',headers=h).json()[0]['id']
    branch_b=c.post('/api/branches',headers=h,json={'name':'Fee Plan Branch B'}).json()['id']
    resident_a=resident(c,h,'fee-a@example.com')
    resident_b=c.post('/api/residents',headers=h,json={'branch_id':branch_b,'name':'Fee Resident B','email':'fee-b@example.com',
        'phone':'9111111111','joined_on':local_today().isoformat(),'temporary_password':'Temporary123!'}).json()['id']
    room_a=c.post('/api/rooms',headers=h,json={'branch_id':branch_a,'number':'A-FEE','floor':'Ground','capacity':2,'monthly_fee':'8500'}).json()['id']
    c.post('/api/rooms',headers=h,json={'branch_id':branch_b,'number':'B-FEE','floor':'Ground','capacity':2,'monthly_fee':'9000'})
    assert c.put(f'/api/residents/{resident_a}/allocation',headers=h,json={'room_id':room_a,'discount':'500'}).status_code==200
    month=local_today().replace(day=1)
    end=month+timedelta(days=32); next_month=end.replace(day=1)
    plan_payload={'branch_id':branch_a,'name':'Double Sharing Plan','sharing':2,'monthly_fee':'10000.00',
        'additional_charge_label':'Laundry','additional_charge_amount':'350.00','billing_day':1,'due_day':10,
        'effective_from':month.isoformat()}
    created=c.post('/api/fee-plans',headers=h,json=plan_payload)
    assert created.status_code==201,created.text
    plan=created.json()
    assert c.post('/api/fee-plans',headers=h,json=plan_payload).status_code==409
    assert c.get(f'/api/public/branches/{branch_a}/availability').json()[0]=={
        'sharing':2,'monthly_fee':'10000.00','advance_amount':'0.00','additional_charge_label':'Laundry','additional_charge_amount':'350.00','available_beds':1}
    assert c.post('/api/billing/generate',headers=h,json={'month':month.isoformat()}).json()['created']==1
    invoice=c.get('/api/invoices',headers=h).json()[0]
    assert invoice['fee_plan_id']==plan['id'] and invoice['base_fee']=='10000.00'
    assert invoice['additional_charge_label']=='Laundry' and invoice['additional_charge_amount']=='350.00'
    assert invoice['discount']=='500.00' and invoice['amount']=='9850.00' and invoice['due_on']==month.replace(day=10).isoformat()
    pdf=c.get(f'/api/invoices/{invoice["id"]}/pdf',headers=h)
    assert b'Laundry' in pdf.content and b'350.00' in pdf.content
    payment=c.post('/api/payments',headers=h,json={'invoice_id':invoice['id'],'amount':'100','method':'cash','reference':'',
        'idempotency_key':'fee-plan-addon-receipt'})
    assert payment.status_code==201,payment.text
    receipt=c.get(f'/api/payments/{payment.json()["id"]}/receipt',headers=h)
    assert 'Laundry: INR 350.00' in receipt.text and 'Invoice total: INR 9850.00' in receipt.text
    # Close this plan after its already billed month, then start a distinct future plan.
    ended=c.put(f'/api/fee-plans/{plan["id"]}',headers=h,json={**{k:plan[k] for k in ('name','monthly_fee','additional_charge_label','additional_charge_amount','billing_day','due_day')},
        'effective_until':(next_month-timedelta(days=1)).isoformat(),'active':True})
    assert ended.status_code==200,ended.text
    successor=c.post('/api/fee-plans',headers=h,json={**plan_payload,'name':'Future Double Sharing Plan','monthly_fee':'11000.00',
        'additional_charge_label':'','additional_charge_amount':'0','effective_from':next_month.isoformat()})
    assert successor.status_code==201,successor.text
    changed=c.put(f'/api/fee-plans/{plan["id"]}',headers=h,json={**{k:plan[k] for k in ('name','monthly_fee','additional_charge_label','additional_charge_amount','billing_day','due_day')},
        'monthly_fee':'10500.00','effective_until':(next_month-timedelta(days=1)).isoformat(),'active':True})
    assert changed.status_code==409
    assert c.get('/api/invoices',headers=h).json()[0]['amount']=='9850.00'
    # New enrollments select the effective branch/sharing plan.
    payload={'branch_id':branch_a,'name':'Fee Plan Applicant','email':'fee-applicant@example.com','phone':'9222222222',
        'preferred_sharing':2,'move_in_date':local_today().isoformat(),'submission_key':uuid4().hex}
    admission=c.post('/api/admissions',json=payload)
    assert admission.status_code==201,admission.text
    assert c.put(f'/api/admissions/{admission.json()["id"]}',headers=h,json={'status':'approved','note':''}).status_code==200
    enrolled=c.post(f'/api/admissions/{admission.json()["id"]}/enroll',headers=h,json={'temporary_password':'Temporary234!'})
    assert enrolled.status_code==201,enrolled.text
    enrolled_resident=next(x for x in c.get('/api/residents',headers=h).json() if x['id']==enrolled.json()['resident_id'])
    assert enrolled_resident['fee_plan_id']==plan['id']
    from app import main
    monkeypatch.setattr(main,'local_today',lambda:next_month+timedelta(days=5))
    next_run=c.post('/api/billing/generate',headers=h,json={'month':next_month.isoformat()})
    assert next_run.status_code==200 and next_run.json()['created']==1,next_run.text
    next_invoices=[i for i in c.get('/api/invoices',headers=h).json() if i['month']==next_month.isoformat()]
    assert len(next_invoices)==1
    future_invoice=next(i for i in next_invoices if i['resident_id']==resident_a)
    assert future_invoice['fee_plan_id']==successor.json()['id'] and future_invoice['amount']=='10500.00'
    assert future_invoice['due_on']==next_month.replace(day=10).isoformat()
    historical=next(i for i in c.get('/api/invoices',headers=h).json() if i['id']==invoice['id'])
    assert historical['amount']=='9850.00' and historical['additional_charge_label']=='Laundry'
    # A branch administrator only sees and assigns plans within their branch.
    with sessions() as db:
        account=User(email='fee-branch-admin@example.com',password_hash=hashing.hash('BranchAdmin123!'),role='branch_admin')
        db.add(account);db.flush();db.add(BranchAdmin(user_id=account.id,branch_id=branch_a));db.commit()
        branch_headers={'Authorization':'Bearer '+token_for(account,mfa_verified=True)}
    assert {x['branch_id'] for x in c.get('/api/fee-plans',headers=branch_headers).json()}=={branch_a}
    assert c.put(f'/api/residents/{resident_b}/fee-plan',headers=branch_headers,json={'fee_plan_id':successor.json()['id']}).status_code==403


def test_deposit_advance_settlement_actual_refunds_and_branch_privacy(ctx):
    from datetime import timedelta
    c,h,sessions=ctx
    branch_a=c.get('/api/branches',headers=h).json()[0]['id']
    branch_b=c.post('/api/branches',headers=h,json={'name':'Settlement Branch B'}).json()['id']
    resident_a=resident(c,h,'settlement-a@example.com')
    resident_b=c.post('/api/residents',headers=h,json={'branch_id':branch_b,'name':'Settlement Resident B','email':'settlement-b@example.com',
        'phone':'9111111111','joined_on':local_today().isoformat(),'temporary_password':'Temporary123!'}).json()['id']
    room_a=c.post('/api/rooms',headers=h,json={'branch_id':branch_a,'number':'A-SET','floor':'Ground','capacity':1,'monthly_fee':'8500'}).json()['id']
    c.put(f'/api/residents/{resident_a}/allocation',headers=h,json={'room_id':room_a,'discount':'0'})
    month=local_today().replace(day=1).isoformat()
    c.post('/api/billing/generate',headers=h,json={'month':month})
    def ledger(account,action,amount,key,**extra):
        return c.post(f'/api/residents/{resident_a}/financial-ledger',headers=h,json={'account_type':account,'action':action,
            'amount':amount,'idempotency_key':key,**extra})
    received_deposit=ledger('deposit','received','4000','deposit-receipt-01',method='cash',reference='D-01')
    assert received_deposit.status_code==201,received_deposit.text
    assert ledger('deposit','received','4000','deposit-receipt-01',method='cash',reference='D-01').json()['duplicate'] is True
    assert ledger('deposit','received','4000','deposit-receipt-01',method='cash',reference='different').status_code==409
    assert ledger('advance','received','2000','advance-receipt-01',method='upi',reference='U-01').status_code==201
    assert ledger('deposit','deduction','500','deposit-deduction-1',reason='Lost room key').status_code==201
    assert ledger('deposit','deduction','5000','deposit-deduction-2',reason='Excess charge').status_code==409
    assert ledger('deposit','deduction','100','deposit-deduction-3',reason='').status_code==422
    with sessions() as db:
        db.get(Resident,resident_a).planned_move_out=local_today()+timedelta(days=1);db.commit()
    assert c.get(f'/api/residents/{resident_b}/financial-ledger',headers=h).status_code==200
    assert c.get(f'/api/residents/{resident_a}/financial-ledger').status_code==401
    resident_headers=signin(c,'settlement-a@example.com')
    assert c.get(f'/api/residents/{resident_b}/financial-ledger',headers=resident_headers).status_code==403
    resident_ledger=c.get(f'/api/residents/{resident_a}/financial-ledger',headers=resident_headers)
    assert resident_ledger.status_code==200 and resident_ledger.json()['events'][0]['actor_email'] is None
    assert c.post('/api/settlements',headers=h,json={'resident_id':resident_a,'proposed_refund':'6000','note':'Full return'}).status_code==409
    assert c.post('/api/settlements',headers=h,json={'resident_id':resident_a,'proposed_refund':'4500','note':''}).status_code==422
    created=c.post('/api/settlements',headers=h,json={'resident_id':resident_a,'proposed_refund':'4500','note':'Agreed utility adjustment'})
    assert created.status_code==201,created.text
    settlement=created.json()
    assert settlement['deposit_balance_snapshot']=='3500.00' and settlement['advance_balance_snapshot']=='2000.00'
    assert settlement['invoice_balance_snapshot']=='8500.00' and settlement['proposed_refund']=='4500.00'
    assert c.put(f'/api/settlements/{settlement["id"]}/decision',headers=h,json={'status':'approved','note':''}).status_code==422
    approved=c.put(f'/api/settlements/{settlement["id"]}/decision',headers=h,json={'status':'approved','note':'Outstanding invoice will be collected separately'})
    assert approved.status_code==200 and approved.json()['status']=='approved'
    assert c.post(f'/api/settlements/{settlement["id"]}/refund',headers=h,json={'account_type':'advance','amount':'2500',
        'method':'cash','reference':'R-1','idempotency_key':'settlement-refund-1'}).status_code==409
    refund={'account_type':'deposit','amount':'2500','method':'bank','reference':'R-1','idempotency_key':'settlement-refund-1'}
    first=c.post(f'/api/settlements/{settlement["id"]}/refund',headers=h,json=refund)
    assert first.status_code==201 and first.json()['settlement']['status']=='partially_refunded'
    assert c.post(f'/api/settlements/{settlement["id"]}/refund',headers=h,json=refund).json()['duplicate'] is True
    assert c.post(f'/api/settlements/{settlement["id"]}/refund',headers=h,json={**refund,'amount':'2000'}).status_code==409
    second=c.post(f'/api/settlements/{settlement["id"]}/refund',headers=h,json={'account_type':'advance','amount':'1000',
        'method':'upi','reference':'R-2','idempotency_key':'settlement-refund-2'})
    assert second.status_code==201 and second.json()['settlement']['status']=='partially_refunded'
    final=c.post(f'/api/settlements/{settlement["id"]}/refund',headers=h,json={'account_type':'deposit','amount':'1000',
        'method':'cash','reference':'R-3','idempotency_key':'settlement-refund-3'})
    assert final.status_code==201 and final.json()['settlement']['status']=='completed'
    assert final.json()['settlement']['refunded']=='4500.00'
    history=c.get(f'/api/settlements/{settlement["id"]}/history',headers=h)
    assert history.status_code==200 and [x['action'] for x in history.json()]==['proposed','approved','refund_recorded','refund_recorded','refund_recorded']
    assert c.get(f'/api/settlements/{settlement["id"]}/history',headers=resident_headers).json()[0]['actor_user_id'] is None
    assert c.get(f'/api/settlements/{settlement["id"]}/history',headers=signin(c,'settlement-b@example.com')).status_code==403
    zero=c.post('/api/settlements',headers=h,json={'resident_id':resident_a,'proposed_refund':'0','note':'No additional refund agreed'})
    assert zero.status_code==201,zero.text
    no_refund=c.put(f'/api/settlements/{zero.json()["id"]}/decision',headers=h,json={'status':'approved','note':'Outstanding invoice handled separately'})
    assert no_refund.status_code==200 and no_refund.json()['status']=='no_refund' and no_refund.json()['refunded']=='0'
    with sessions() as db:
        from app.models import FinancialLedgerEvent, SettlementEvent
        assert db.scalar(select(func.count(FinancialLedgerEvent.id)).where(FinancialLedgerEvent.settlement_id==settlement['id']))==3
        assert db.scalar(select(func.count(SettlementEvent.id)).where(SettlementEvent.settlement_id==settlement['id']))==5
    with sessions() as db:
        account=User(email='settlement-branch-admin@example.com',password_hash=hashing.hash('BranchAdmin123!'),role='branch_admin')
        db.add(account);db.flush();db.add(BranchAdmin(user_id=account.id,branch_id=branch_b));db.commit()
        branch_headers={'Authorization':'Bearer '+token_for(account,mfa_verified=True)}
    assert c.get(f'/api/residents/{resident_a}/financial-ledger',headers=branch_headers).status_code==403
    assert c.get(f'/api/settlements/{settlement["id"]}/history',headers=branch_headers).status_code==403


def test_complaint_assignment_and_history_are_branch_scoped(ctx):
    c,h,sessions=ctx
    branch_a=c.get('/api/branches',headers=h).json()[0]['id']
    branch_b=c.post('/api/branches',headers=h,json={'name':'Complaint Branch B'}).json()['id']
    resident_a=resident(c,h,'complaint-a@example.com')
    resident_b=c.post('/api/residents',headers=h,json={'branch_id':branch_b,'name':'Complaint Resident B','email':'complaint-b@example.com',
        'phone':'9111111111','joined_on':local_today().isoformat(),'temporary_password':'Temporary123!'}).json()['id']
    resident_a_headers=signin(c,'complaint-a@example.com')
    resident_b_headers=signin(c,'complaint-b@example.com')
    complaint=c.post('/api/complaints',headers=resident_a_headers,json={'category':'maintenance','title':'Room light',
        'description':'The light in my room is not working.'})
    assert complaint.status_code==201,complaint.text
    complaint_b=c.post('/api/complaints',headers=resident_b_headers,json={'category':'cleaning','title':'Shared area',
        'description':'The shared area needs cleaning.'}).json()['id']
    with sessions() as db:
        staff_a=User(email='complaint-a-staff@example.com',password_hash=hashing.hash('BranchAdmin123!'),role='branch_admin')
        staff_b=User(email='complaint-b-staff@example.com',password_hash=hashing.hash('BranchAdmin123!'),role='branch_admin')
        db.add_all([staff_a,staff_b]);db.flush();db.add_all([BranchAdmin(user_id=staff_a.id,branch_id=branch_a),BranchAdmin(user_id=staff_b.id,branch_id=branch_b)]);db.commit()
        staff_a_id,staff_b_id=staff_a.id,staff_b.id
        headers_a={'Authorization':'Bearer '+token_for(staff_a,mfa_verified=True)}
    listed=c.get(f'/api/complaint-assignees?branch_id={branch_a}',headers=h)
    assert listed.status_code==200 and staff_a_id in {x['id'] for x in listed.json()} and staff_b_id not in {x['id'] for x in listed.json()}
    assert c.get(f'/api/complaint-assignees?branch_id={branch_b}',headers=headers_a).status_code==403
    assert c.put(f'/api/complaints/{complaint.json()["id"]}/assignment',headers=h,json={'user_id':staff_b_id}).status_code==403
    assigned=c.put(f'/api/complaints/{complaint.json()["id"]}/assignment',headers=headers_a,json={'user_id':staff_a_id})
    assert assigned.status_code==200,assigned.text
    assert c.put(f'/api/complaints/{complaint_b}/assignment',headers=headers_a,json={'user_id':staff_a_id}).status_code==403
    updated=c.put(f'/api/complaints/{complaint.json()["id"]}',headers=headers_a,json={'status':'resolved','response':'The light was replaced.',
        'resolution_note':'Replacement bulb fitted and checked.'})
    assert updated.status_code==200,updated.text
    staff_view=c.get('/api/complaints',headers=headers_a).json()[0]
    assert staff_view['assigned_to_user_id']==staff_a_id and staff_view['resolved_at'] and staff_view['updated_at']
    assert staff_view['resolution_note']=='Replacement bulb fitted and checked.'
    assert [x['action'] for x in staff_view['history']]==['submitted','assigned','updated']
    resident_view=c.get('/api/complaints',headers=resident_a_headers).json()[0]
    assert resident_view['assigned_to_user_id'] is None
    assert resident_view['history'][1]['new_assignee_user_id'] is None
    assert c.get('/api/complaints',headers=resident_b_headers).json()[0]['id']==complaint_b
    assert c.put(f'/api/complaints/{complaint.json()["id"]}/assignment',headers=resident_a_headers,json={'user_id':staff_a_id}).status_code==403
