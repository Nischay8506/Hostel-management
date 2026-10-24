from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from uuid import uuid4
import pytest
from PIL import Image
from pypdf import PdfReader
from cryptography.fernet import Fernet
from sqlalchemy import select
from test_workflows import ctx, resident, room, signin
from app import main, sms, whatsapp, services
from app.config import settings
from app.models import Resident, Outbox, Admission, IdentityDocument, User, BranchAdmin, Branch, OtpChallenge
from app.security import token_for, hashing
from app.services import local_today

def allocation(c,h,rid):
    room_id=room(c,h,capacity=2)
    assert c.put(f'/api/residents/{rid}/allocation',headers=h,json={'room_id':room_id,'discount':'0'}).status_code==200
    return room_id

def other_branch(sessions):
    with sessions() as db:
        branch=Branch(name='Private branch');db.add(branch);db.flush()
        user=User(email='other@example.com',password_hash=hashing.hash('OtherPassword123!'),role='branch_admin')
        db.add(user);db.flush();db.add(BranchAdmin(branch_id=branch.id,user_id=user.id));db.commit()
        return {'Authorization':'Bearer '+token_for(user,True)}

def test_sharing_advance_and_automatic_billing_wait_for_plan_day(ctx,monkeypatch):
    c,h,sessions=ctx;rid=resident(c,h);room_id=allocation(c,h,rid)
    month=local_today().replace(day=1);branch=c.get('/api/branches').json()[0]['id']
    plan={'branch_id':branch,'name':'Twin share','sharing':2,'monthly_fee':'8000','advance_amount':'6000',
          'billing_day':12,'due_day':20,'effective_from':month.isoformat()}
    assert c.post('/api/fee-plans',headers=h,json=plan).status_code==201
    monkeypatch.setattr(main,'local_today',lambda:month.replace(day=10))
    with sessions() as db: assert main.generate_monthly_invoices(db,month,scheduled=True)==0
    monkeypatch.setattr(main,'local_today',lambda:month.replace(day=12))
    with sessions() as db:
        assert main.generate_monthly_invoices(db,month,scheduled=True)==1
        assert main.generate_monthly_invoices(db,month,scheduled=True)==0
    ledger=c.get(f'/api/residents/{rid}/financial-ledger',headers=h).json()
    assert Decimal(ledger['configured_advance'])==6000 and Decimal(ledger['advance_remaining'])==6000
    assert c.post(f'/api/residents/{rid}/financial-ledger',headers=h,json={'account_type':'advance','action':'received','amount':'2000','method':'cash','idempotency_key':uuid4().hex}).status_code==201
    assert Decimal(c.get(f'/api/residents/{rid}/financial-ledger',headers=h).json()['advance_remaining'])==4000

def test_vacating_approval_blocks_debt_and_dashboard_is_branch_scoped(ctx):
    c,h,sessions=ctx;rid=resident(c,h);allocation(c,h,rid);rh=signin(c)
    month=local_today().replace(day=1).isoformat()
    assert c.post('/api/billing/generate',headers=h,json={'month':month}).status_code==200
    stay=c.post('/api/my/stay-requests',headers=rh,json={'request_type':'vacating','requested_move_out':(local_today()+timedelta(days=40)).isoformat()}).json()
    path=f'/api/stay-requests/{stay["id"]}'
    assert c.put(path,headers=h,json={'status':'approved'}).status_code==409
    dashboard=c.get('/api/dashboard',headers=h).json()
    assert all(key in dashboard for key in ['pending_admissions','pending_extensions','upcoming_moveouts','reminder_failures','cash_collected'])
    inv=c.get('/api/invoices',headers=h).json()[0]
    assert c.post('/api/payments',headers=h,json={'invoice_id':inv['id'],'amount':inv['amount'],'method':'cash','idempotency_key':uuid4().hex}).status_code==201
    assert c.put(path,headers=h,json={'status':'approved'}).status_code==200
    assert Decimal(c.get('/api/dashboard',headers=h).json()['cash_collected'])==Decimal(inv['amount'])
    other=c.get('/api/dashboard',headers=other_branch(sessions)).json()
    assert Decimal(other['cash_collected'])==0 and other['upcoming_moveouts']==0

def test_room_and_resident_archival_preserve_history_and_enforce_scope(ctx):
    c,h,sessions=ctx;rid=resident(c,h);room_id=allocation(c,h,rid);rh=signin(c)
    body={'active':False,'reason':'Resident departed with account settled'}
    assert c.put(f'/api/rooms/{room_id}/status',headers=h,json=body).status_code==409
    assert c.put(f'/api/residents/{rid}/status',headers=other_branch(sessions),json=body).status_code==403
    assert c.put(f'/api/residents/{rid}/status',headers=h,json=body).status_code==200
    assert c.get('/api/invoices',headers=rh).status_code==401
    assert c.request('DELETE',f'/api/rooms/{room_id}',headers=h,json=body).status_code==200
    branch=c.get('/api/branches').json()[0]['id']
    assert c.get(f'/api/public/branches/{branch}/availability').json()==[]
    assert len(c.get('/api/rooms',headers=h).json())==1
    assert c.put(f'/api/residents/{rid}/status',headers=h,json={**body,'active':True}).status_code==200
    assert c.get('/api/invoices',headers=rh).status_code==401
    assert c.put(f'/api/residents/{rid}/allocation',headers=h,json={'room_id':room_id,'discount':'0'}).status_code==404
    assert c.get('/api/lifecycle-history',headers=h).status_code==200

def test_private_enquiry_tracking_faqs_and_admission_notifications(ctx,monkeypatch):
    c,h,sessions=ctx;room(c,h);branch=c.get('/api/branches').json()[0]['id'];key=uuid4().hex
    payload={'branch_id':branch,'name':'Applicant','email':'new@example.com','phone':'9888888888','preferred_sharing':1,
        'move_in_date':local_today().isoformat(),'submission_key':key,'whatsapp_updates':True}
    created=c.post('/api/admissions',json=payload);assert created.status_code==201
    lookup={'email':payload['email'],'submission_key':key}
    assert c.post('/api/public/admissions/status',json={**lookup,'submission_key':uuid4().hex}).status_code==404
    assert c.post('/api/public/admissions/status',json=lookup).json()['status']=='pending'
    c.put(f'/api/admissions/{created.json()["id"]}',headers=h,json={'status':'approved','note':'Private review note'})
    result=c.post('/api/public/admissions/status',json=lookup)
    assert result.json()['status']=='approved' and 'Private review note' not in result.text and payload['phone'] not in result.text
    questions=[{'question':'Is parking available?','answer':'Ask our branch team before arrival.'}]
    assert c.put(f'/api/branches/{branch}/faqs',headers=h,json=questions).status_code==200
    assert c.get('/api/branches').json()[0]['faqs']==questions
    monkeypatch.setattr(services,'SessionLocal',sessions)
    with sessions() as db:
        for item in db.scalars(select(Outbox).where(Outbox.channel=='email')): item.cancelled=True
        db.commit()
    services.deliver_emails()
    assert any(message['kind']=='utility' and message['parameters']==[str(created.json()['id']),'approved'] for message in whatsapp.test_deliveries())

def test_identity_upload_is_encrypted_scoped_validated_and_audited(ctx,monkeypatch):
    c,h,sessions=ctx;rid=resident(c,h);rh=signin(c);other=other_branch(sessions)
    monkeypatch.setattr(settings,'identity_document_key',Fernet.generate_key().decode())
    image=BytesIO();Image.new('RGB',(20,20),'blue').save(image,format='PNG');content=image.getvalue()
    path=f'/api/residents/{rid}/identity-document'
    assert c.put(path,headers={**rh,'Content-Type':'image/png'},content=content).status_code==200
    with sessions() as db:
        document=db.scalar(select(IdentityDocument).where(IdentityDocument.resident_id==rid))
        assert document.encrypted_content!=content and content not in document.encrypted_content
    assert c.get(path+'/download',headers=other).status_code==403
    download=c.get(path+'/download',headers=h);assert download.content==content and download.headers['cache-control']=='no-store'
    assert c.put(path,headers={**rh,'Content-Type':'image/png'},content=b'not an image').status_code==422
    assert c.put(path,headers={**rh,'Content-Type':'image/png'},content=b'x'*(5*1024*1024+1)).status_code==413
    assert c.delete(path,headers=rh).status_code==200
    assert c.get(path,headers=h).json()['present'] is False
    assert any(e['action']=='document_download' for e in c.get('/api/lifecycle-history',headers=h).json())

def test_sms_fallback_keeps_password_and_one_time_challenge(ctx,monkeypatch):
    c,h,sessions=ctx;rid=resident(c,h)
    codes=[];monkeypatch.setattr(sms,'configured',lambda:True)
    monkeypatch.setattr(sms,'send_auth_code',lambda phone,code:codes.append(code))
    monkeypatch.setattr(whatsapp,'configured',lambda:False)
    response=c.post('/api/auth/login',json={'email':'resident@example.com','password':'Temporary123!'})
    assert response.status_code==200 and response.json()['channel']=='sms' and 'access_token' not in response.json()
    challenge=response.json()['challenge_id']
    verified=c.post('/api/auth/otp/verify',json={'challenge_id':challenge,'code':codes[-1]})
    assert verified.status_code==200
    assert c.get('/api/auth/me',headers={'Authorization':'Bearer '+verified.json()['access_token']}).status_code==200
    assert c.post('/api/auth/otp/verify',json={'challenge_id':challenge,'code':codes[-1]}).status_code==400

def test_analytics_status_filter_and_branded_paginated_pdf(ctx):
    c,h,sessions=ctx;rid=resident(c,h);allocation(c,h,rid)
    month=local_today().replace(day=1).isoformat();c.post('/api/billing/generate',headers=h,json={'month':month})
    path=f'/api/analytics/financial?from_date={month}&to_date={local_today()}&invoice_status=paid'
    report=c.get(path,headers=h);assert report.status_code==200
    assert Decimal(report.json()['summary']['billed'])==0
    assert report.json()['residents']==[]
    assert c.get(path.replace('paid','bad'),headers=h).status_code==422
    invoice=c.get('/api/invoices',headers=h).json()[0]
    pdf=PdfReader(BytesIO(c.get(f'/api/invoices/{invoice["id"]}/pdf',headers=h).content))
    assert 'Invoice' in pdf.pages[0].extract_text() and '8500.00' in pdf.pages[0].extract_text()
    assert len(pdf.pages[0].images)>0
    from app.documents import financial_document
    long=PdfReader(BytesIO(financial_document('Settlement','TEST',[('Note','Long note '*1000)],[('Refund',Decimal('50'))])))
    assert len(long.pages)>1 and '50.00' in ''.join(p.extract_text() for p in long.pages)
