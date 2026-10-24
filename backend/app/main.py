import asyncio
import csv
import hashlib
import hmac
import secrets
from uuid import uuid4
from io import StringIO, BytesIO
import logging
from pathlib import Path
from alembic import command
from alembic.config import Config
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text, inspect
from alembic.script import ScriptDirectory
from .models import ResidentDiscount, JobState
from .schemas import DiscountCreate
from .rate_limits import consume
from sqlalchemy import select, func, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from .config import settings
from .db import Base, engine, SessionLocal, get_db
from .models import User, Branch, BranchAdmin, Admission, AdmissionEvent, Room, FeePlan, Resident, Invoice, Payment, PaymentAuditEvent, Complaint, ComplaintEvent, GatePass, FinancialLedgerEvent, FinalSettlement, SettlementEvent, Outbox, AllocationEvent, StayRequest, IdentityReviewEvent, OtpChallenge, AuthAuditEvent, NotificationPreferenceEvent, now
from .schemas import Login, OtpVerify, OtpResend, NotificationPreference, PaymentReversal, PasswordChange, RoomCreate, RoomUpdate, FeePlanCreate, FeePlanUpdate, ResidentFeePlanUpdate, ResidentCreate, Allocation, IDReview, BillingRun, PaymentCreate, ComplaintCreate, ComplaintUpdate, ComplaintAssignment, FinancialLedgerCreate, SettlementCreate, SettlementDecision, SettlementRefund, BranchCreate, BranchUpdate, BranchAdminCreate, AdmissionCreate, AdmissionDecision, AdmissionEnroll, StayRequestCreate, StayRequestDecision, GatePassCreate
from .security import hashing, token_for, current_user, active_user, admin, staff, is_owner, is_staff
from .services import paid_total, receipt_text, receipt_pdf, invoice_pdf, queue_reminders, deliver_emails, local_today
from .analytics import financial_report
from . import whatsapp, sms

log = logging.getLogger(__name__)
def initialize():
    settings.validate_runtime()
    if len(settings.jwt_secret)<32 or len(settings.admin_password)<10:
        raise RuntimeError('JWT_SECRET needs 32+ characters; ADMIN_PASSWORD needs 10+')
    migration_config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))
    migration_config.set_main_option('sqlalchemy.url',settings.database_url.replace('%','%%'))
    if settings.auto_migrate:
        command.upgrade(migration_config,'head')
    else:
        with engine.connect() as connection:
            if 'alembic_version' not in inspect(connection).get_table_names() or connection.scalar(text('SELECT version_num FROM alembic_version')) != ScriptDirectory.from_config(migration_config).get_current_head():
                raise RuntimeError('Database migration required. Verify a backup and run alembic upgrade head before starting.')
    with SessionLocal() as db:
        if not db.scalar(select(Branch.id).limit(1)):
            db.add(Branch(name='Branch A',description='Configure this location in branch settings.'))
            db.commit()
        if not db.scalar(select(User).where(User.email==settings.admin_email.lower())):
            db.add(User(email=settings.admin_email.lower(),password_hash=hashing.hash(settings.admin_password),role='owner',phone=settings.admin_phone or None))
            db.commit()
        elif settings.admin_phone:
            owner=db.scalar(select(User).where(User.email==settings.admin_email.lower()))
            if owner and not owner.phone: owner.phone=settings.admin_phone; db.commit()
def job_tick():
    with SessionLocal() as db:
        process_due_moveouts(db)
        if settings.automatic_billing_enabled: generate_monthly_invoices(db,local_today().replace(day=1),scheduled=True)
        queue_reminders(db)
        db.commit()
    deliver_emails()
def process_due_moveouts(db,branch_ids=None):
    query=select(Resident).where(Resident.status=='active',Resident.room_id.is_not(None),Resident.planned_move_out.is_not(None),Resident.planned_move_out<=local_today()).with_for_update()
    if branch_ids is not None: query=query.where(Resident.branch_id.in_(branch_ids))
    moved=0
    for resident in db.scalars(query):
        invoices=db.scalars(select(Invoice).where(Invoice.resident_id==resident.id))
        outstanding=any(i.amount-paid_total(db,i.id)>0 for i in invoices)
        if outstanding: continue
        old_room_id=resident.room_id
        resident.room_id=None;resident.status='vacated'
        db.add(AllocationEvent(resident_id=resident.id,from_room_id=old_room_id,to_room_id=None,actor_user_id=None,
                              reason=f'Scheduled move-out completed on {local_today().isoformat()}'))
        db.flush();moved+=1
    return moved
async def jobs():
    while True:
        from .worker import run_once
        try: await asyncio.to_thread(run_once)
        except Exception: log.error('Background job failed; check worker status and configuration')
        await asyncio.sleep(60)
@asynccontextmanager
async def lifespan(app):
    initialize()
    task = asyncio.create_task(jobs()) if settings.jobs_enabled else None
    yield
    if task:
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass
app = FastAPI(title="Cityhive Luxury PG's and Co-space API",version='1.1.0',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=settings.cors_origins,allow_credentials=False,
                   allow_methods=['GET','POST','PUT','DELETE','OPTIONS'],allow_headers=['Authorization','Content-Type'],
                   expose_headers=['Content-Disposition'])

@app.exception_handler(RequestValidationError)
async def validation_error(request,exc):
    return JSONResponse(status_code=422,content={'detail':[{key:item[key] for key in ('loc','msg','type') if key in item} for item in exc.errors()]})

@app.exception_handler(SQLAlchemyError)
async def database_error(request,exc):
    # Do not expose SQL, parameters, credentials or personal records in errors.
    log.error('Database operation failed (%s)',type(exc).__name__)
    return JSONResponse(status_code=503,content={'detail':'Service temporarily unavailable. Please retry shortly.'})

@app.middleware('http')
async def response_security(request,call_next):
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Cache-Control']='no-store'
    return response

@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=409,content={'detail':'This record already exists or conflicts with another update. Refresh and retry.'})

@app.get('/api/health')
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {'status':'ok'}
def branch_data(b):
    return {'id':b.id,'name':b.name,'address':b.address,'contact_phone':b.contact_phone,
            'faqs':b.faqs,'contact_email':b.contact_email,'image_url':b.image_url,'description':b.description,'facilities':b.facilities,'rules':b.rules,'notice_days':b.notice_days,'active':b.active,'published':b.published}
def branch_scope(db,user):
    if is_owner(user): return None
    if user.role!='branch_admin': raise HTTPException(403,'Administrator access required')
    return list(db.scalars(select(BranchAdmin.branch_id).where(BranchAdmin.user_id==user.id)))
def require_branch(db,user,branch_id):
    scope=branch_scope(db,user)
    if scope is not None and branch_id not in scope: raise HTTPException(403,'This branch is outside your access')
    return branch_id
def require_resident_branch(db,user,resident):
    return require_branch(db,user,resident.branch_id)
def fee_plan_matches(plan,branch_id,sharing,period):
    return bool(plan and plan.active and plan.branch_id==branch_id and plan.sharing==sharing and
                plan.effective_from<=period and (plan.effective_until is None or plan.effective_until>=period))
def resolve_fee_plan(db,resident,room,period):
    if resident.fee_plan_id:
        plan=db.get(FeePlan,resident.fee_plan_id)
        if not plan or plan.branch_id!=resident.branch_id or plan.sharing!=room.capacity:
            raise HTTPException(409,'The resident fee plan does not match this branch and sharing type')
        if fee_plan_matches(plan,resident.branch_id,room.capacity,period):
            return plan
        # An assigned effective-dated plan may expire. Prefer its configured
        # successor for the same branch/sharing before considering legacy rates.
        successor=db.scalar(select(FeePlan).where(FeePlan.branch_id==resident.branch_id,FeePlan.sharing==room.capacity,
            FeePlan.active.is_(True),FeePlan.effective_from<=period,
            (FeePlan.effective_until.is_(None))|(FeePlan.effective_until>=period)
        ).order_by(FeePlan.effective_from.desc(),FeePlan.id.desc()).limit(1))
        if successor:
            return successor
        raise HTTPException(409,'No active fee plan covers this resident and billing period')
    return db.scalar(select(FeePlan).where(FeePlan.branch_id==resident.branch_id,FeePlan.sharing==room.capacity,
        FeePlan.active.is_(True),FeePlan.effective_from<=period,
        (FeePlan.effective_until.is_(None))|(FeePlan.effective_until>=period)).order_by(FeePlan.effective_from.desc(),FeePlan.id.desc()).limit(1))
def financial_balances(db,resident_id):
    result={'deposit':Decimal('0.00'),'advance':Decimal('0.00')}
    for event in db.scalars(select(FinancialLedgerEvent).where(FinancialLedgerEvent.resident_id==resident_id)):
        if event.action=='received': result[event.account_type]+=Decimal(event.amount)
        else: result[event.account_type]-=Decimal(event.amount)
    return result
def resident_invoice_balance(db,resident_id):
    amount=Decimal('0.00')
    for invoice in db.scalars(select(Invoice).where(Invoice.resident_id==resident_id)):
        amount+=max(Decimal('0.00'),Decimal(invoice.amount)-paid_total(db,invoice.id))
    return amount
def settlement_data(db,item):
    resident=db.get(Resident,item.resident_id)
    refunded=db.scalar(select(func.coalesce(func.sum(FinancialLedgerEvent.amount),0)).where(
        FinancialLedgerEvent.settlement_id==item.id,FinancialLedgerEvent.action=='refund')) or Decimal('0')
    return {'id':item.id,'resident_id':resident.id,'resident_name':resident.name,'resident_code':resident.resident_code,
        'branch_id':item.branch_id,'status':item.status,'deposit_balance_snapshot':str(item.deposit_balance_snapshot),
        'advance_balance_snapshot':str(item.advance_balance_snapshot),'invoice_balance_snapshot':str(item.invoice_balance_snapshot),
        'proposed_refund':str(item.proposed_refund),'refunded':str(refunded),'note':item.note,'decision_note':item.decision_note,
        'created_at':item.created_at,'decided_at':item.decided_at}
@app.get('/api/branches')
def branches(db: Session = Depends(get_db)):
    return [branch_data(b) for b in db.scalars(select(Branch).where(Branch.active.is_(True),Branch.published.is_(True)).order_by(Branch.id))]
@app.get('/api/managed-branches')
def managed_branches(db: Session = Depends(get_db),user: User = Depends(staff)):
    query=select(Branch).order_by(Branch.id)
    scope=branch_scope(db,user)
    if scope is not None: query=query.where(Branch.id.in_(scope))
    return [dict(branch_data(b),publication_issues=publication_issues(db,b)) for b in db.scalars(query)]
@app.get('/api/public/branches/{branch_id}/availability')
def public_availability(branch_id: int,db: Session = Depends(get_db)):
    branch=db.get(Branch,branch_id)
    if not branch or not branch.active or not branch.published: raise HTTPException(404,'Branch not found')
    result=[]
    for room in db.scalars(select(Room).where(Room.branch_id==branch_id,Room.active.is_(True)).order_by(Room.capacity,Room.monthly_fee)):
        occupied=db.scalar(select(func.count(Resident.id)).where(Resident.room_id==room.id,Resident.status=='active')) or 0
        if room.capacity>occupied:
            cycle=local_today().replace(day=1)
            plan=db.scalar(select(FeePlan).where(FeePlan.branch_id==branch_id,FeePlan.sharing==room.capacity,FeePlan.active.is_(True),
                FeePlan.effective_from<=cycle,(FeePlan.effective_until.is_(None))|(FeePlan.effective_until>=cycle)
            ).order_by(FeePlan.effective_from.desc(),FeePlan.id.desc()).limit(1))
            result.append({'sharing':room.capacity,'monthly_fee':str(plan.monthly_fee if plan else room.monthly_fee),
                           'advance_amount':str(plan.advance_amount) if plan else '0.00',
                           'additional_charge_label':plan.additional_charge_label if plan else '',
                           'additional_charge_amount':str(plan.additional_charge_amount if plan else Decimal('0.00')),
                           'available_beds':room.capacity-occupied})
    options={}
    for item in result:
        key=item['sharing']
        options.setdefault(key,{'sharing':key,'monthly_fee':item['monthly_fee'],'advance_amount':item['advance_amount'],'additional_charge_label':item['additional_charge_label'],
                                'additional_charge_amount':item['additional_charge_amount'],'available_beds':0})
        options[key]['available_beds']+=item['available_beds']
        if Decimal(item['monthly_fee'])<Decimal(options[key]['monthly_fee']): options[key]['monthly_fee']=item['monthly_fee']
    return sorted(options.values(),key=lambda x:x['sharing'])
@app.post('/api/admissions',status_code=201)
def submit_admission(data: AdmissionCreate,db: Session = Depends(get_db)):
    branch=db.get(Branch,data.branch_id)
    if not branch or not branch.active or not branch.published: raise HTTPException(404,'Branch not found')
    existing=db.scalar(select(Admission).where(Admission.submission_key==data.submission_key))
    if existing:
        same=(existing.branch_id==data.branch_id and existing.email==str(data.email).lower() and existing.name==data.name.strip() and
              existing.phone==data.phone and existing.preferred_sharing==data.preferred_sharing and existing.move_in_date==data.move_in_date)
        if not same:
            raise HTTPException(409,'Submission key has already been used')
        return {'id':existing.id,'status':existing.status,'duplicate':True}
    if data.move_in_date<local_today(): raise HTTPException(422,'Move-in date cannot be in the past')
    options=public_availability(data.branch_id,db)
    if not any(x['sharing']==data.preferred_sharing and x['available_beds']>0 for x in options):
        raise HTTPException(409,'That sharing option currently has no available beds')
    pending=db.scalar(select(Admission).where(Admission.branch_id==data.branch_id,Admission.email==str(data.email).lower(),Admission.status.in_(['pending','needs_info','approved','enrolled'])))
    if pending: raise HTTPException(409,'An admission request for this email is already being reviewed')
    values=data.model_dump();values['email']=str(data.email).lower();values['name']=data.name.strip()
    admission=Admission(**values)
    db.add(admission);db.flush()
    db.add(AdmissionEvent(admission_id=admission.id,old_status='',new_status='pending',note='Public admission request submitted'))
    db.add(Outbox(branch_id=admission.branch_id,dedupe_key=f'admission:{admission.id}:pending',recipient=admission.email,
                  subject=f'Admission enquiry received · {branch.name}',
                  body=f"Hello {admission.name},\nWe received your admission enquiry for {branch.name}. The management team will review it and contact you. Request number: {admission.id}.\nPrivate tracking key: {admission.submission_key}\nKeep this key private and use it with your email on the enquiry tracking page.\n"))
    from .gap_features import queue_admission_update
    queue_admission_update(db,admission)
    db.commit()
    return {'id':admission.id,'status':admission.status,'duplicate':False}
@app.get('/api/admissions')
def admissions(db: Session = Depends(get_db),user: User = Depends(staff)):
    query=select(Admission).order_by(Admission.created_at.desc(),Admission.id.desc())
    scope=branch_scope(db,user)
    if scope is not None: query=query.where(Admission.branch_id.in_(scope))
    return [{'id':a.id,'branch_id':a.branch_id,'name':a.name,'email':a.email,'phone':a.phone,
             'emergency_contact':a.emergency_contact,'emergency_phone':a.emergency_phone,
             'preferred_sharing':a.preferred_sharing,'move_in_date':a.move_in_date,'message':a.message,
             'status':a.status,'admin_note':a.admin_note,'created_at':a.created_at,'resident_id':a.resident_id}
            for a in db.scalars(query)]
@app.put('/api/admissions/{admission_id}')
def decide_admission(admission_id: int,data: AdmissionDecision,db: Session = Depends(get_db),user: User = Depends(staff)):
    admission=db.scalar(select(Admission).where(Admission.id==admission_id).with_for_update())
    if not admission: raise HTTPException(404,'Admission request not found')
    require_branch(db,user,admission.branch_id)
    if admission.status not in {'pending','needs_info'}: raise HTTPException(409,'This admission can no longer be reviewed')
    old=admission.status
    if data.status==old: raise HTTPException(409,'Choose a different review status')
    admission.status,admission.admin_note,admission.reviewed_by,admission.reviewed_at=data.status,data.note,user.id,now()
    db.add(AdmissionEvent(admission_id=admission.id,actor_user_id=user.id,old_status=old,new_status=data.status,note=data.note))
    branch=db.get(Branch,admission.branch_id)
    db.add(Outbox(branch_id=admission.branch_id,dedupe_key=f'admission:{admission.id}:{data.status}',recipient=admission.email,
                  subject=f'Admission enquiry update · {branch.name}',
                  body=f"Hello {admission.name},\nYour admission enquiry status is now: {data.status}.\n{data.note}\nRequest number: {admission.id}.\n"))
    from .gap_features import queue_admission_update
    queue_admission_update(db,admission)
    db.commit()
    return {'status':admission.status}
@app.post('/api/admissions/{admission_id}/enroll',status_code=201)
def enroll_admission(admission_id: int,data: AdmissionEnroll,db: Session = Depends(get_db),user: User = Depends(staff)):
    admission=db.scalar(select(Admission).where(Admission.id==admission_id).with_for_update())
    if not admission: raise HTTPException(404,'Admission request not found')
    require_branch(db,user,admission.branch_id)
    if admission.status!='approved' or admission.resident_id: raise HTTPException(409,'Only an approved admission can be enrolled once')
    if db.scalar(select(User.id).where(User.email==admission.email)): raise HTTPException(409,'An account already exists for this email')
    account=User(email=admission.email,password_hash=hashing.hash(data.temporary_password),role='resident',must_change_password=True)
    db.add(account);db.flush()
    admission_plan=db.scalar(select(FeePlan).where(FeePlan.branch_id==admission.branch_id,FeePlan.sharing==admission.preferred_sharing,
        FeePlan.active.is_(True),FeePlan.effective_from<=admission.move_in_date,
        (FeePlan.effective_until.is_(None))|(FeePlan.effective_until>=admission.move_in_date)
    ).order_by(FeePlan.effective_from.desc(),FeePlan.id.desc()).limit(1))
    resident=Resident(user_id=account.id,branch_id=admission.branch_id,fee_plan_id=admission_plan.id if admission_plan else None,name=admission.name,phone=admission.phone,
                      guardian=admission.emergency_contact,guardian_phone=admission.emergency_phone,
                      institution='',joined_on=admission.move_in_date,discount=Decimal('0'))
    db.add(resident);db.flush()
    old=admission.status;admission.status='enrolled';admission.resident_id=resident.id
    admission.reviewed_by=user.id;admission.reviewed_at=now()
    db.add(AdmissionEvent(admission_id=admission.id,actor_user_id=user.id,old_status=old,new_status='enrolled',note='Resident account created; room allocation pending'))
    from .gap_features import queue_admission_update
    queue_admission_update(db,admission)
    db.add(Outbox(user_id=account.id,branch_id=admission.branch_id,dedupe_key=f'admission:{admission.id}:enrolled',recipient=admission.email,subject='Cityhive admission enrolled',body=f'Your admission #{admission.id} is now enrolled. Contact management for account access.'))
    db.commit()
    return {'resident_id':resident.id,'message':'Resident account created. Share the temporary password securely; room allocation remains a separate step.'}
@app.post('/api/branches',status_code=201)
def add_branch(data: BranchCreate,db: Session = Depends(get_db),user: User = Depends(admin)):
    values=data.model_dump(); values['name']=data.name.strip()
    branch = Branch(**values)
    db.add(branch); db.commit()
    return {'id':branch.id}
@app.put('/api/branches/{branch_id}')
def update_branch(branch_id: int,data: BranchUpdate,db: Session = Depends(get_db),user: User = Depends(admin)):
    branch=db.scalar(select(Branch).where(Branch.id==branch_id).with_for_update())
    if not branch: raise HTTPException(404,'Branch not found')
    previous_issues=set(publication_issues(db,branch))
    for key,value in data.model_dump().items():
        if key=='faqs' and key not in data.model_fields_set: continue
        setattr(branch,key,value.strip() if isinstance(value,str) else value)
    if branch.published and set(publication_issues(db,branch))-previous_issues:
        raise HTTPException(409,'Unpublish the branch before removing required public details or deactivating it')
    db.commit()
    return {'message':'Branch updated'}
@app.put('/api/branches/{branch_id}/publication')
def update_branch_publication(branch_id: int,published: bool,db: Session = Depends(get_db),user: User = Depends(admin)):
    if not is_owner(user): raise HTTPException(403,'Only the owner can publish a branch')
    branch=db.get(Branch,branch_id)
    if not branch: raise HTTPException(404,'Branch not found')
    if published:
        if not branch.active: raise HTTPException(409,'Activate this branch before publishing it')
        if not branch.address.strip() or not branch.description.strip():
            raise HTTPException(409,'Add a public address and description before publishing this branch')
        public_copy=branch.description.casefold()
        if 'configure this location' in public_copy or 'branch settings' in public_copy:
            raise HTTPException(409,'Replace the internal placeholder with a public branch description before publishing')
        room_ids=list(db.scalars(select(Room.id).where(Room.branch_id==branch.id)))
        if not room_ids: raise HTTPException(409,'Add at least one room with a configured sharing capacity and monthly rate before publishing')
    branch.published=published
    db.commit()
    return {'published':branch.published}
@app.post('/api/branch-admins',status_code=201)
def add_branch_admin(data: BranchAdminCreate,db: Session = Depends(get_db),user: User = Depends(admin)):
    ids=set(data.branch_ids)
    branches_found=set(db.scalars(select(Branch.id).where(Branch.id.in_(ids))))
    if ids!=branches_found: raise HTTPException(404,'One or more branches were not found')
    account=db.scalar(select(User).where(User.email==str(data.email).lower()))
    if account and account.role!='branch_admin': raise HTTPException(409,'That email is already used by another account type')
    if not account:
        account=User(email=str(data.email).lower(),password_hash=hashing.hash(data.temporary_password),role='branch_admin',must_change_password=True,phone=data.phone)
        db.add(account); db.flush()
        db.add(AuthAuditEvent(user_id=account.id,actor_user_id=user.id,event='phone_assigned'))
    else:
        account.password_hash=hashing.hash(data.temporary_password)
        account.must_change_password=True
        if account.phone!=data.phone:
            account.phone=data.phone; account.phone_verified_at=None
            db.add(AuthAuditEvent(user_id=account.id,actor_user_id=user.id,event='phone_assigned'))
    db.execute(BranchAdmin.__table__.delete().where(BranchAdmin.user_id==account.id))
    db.add_all([BranchAdmin(user_id=account.id,branch_id=branch_id) for branch_id in sorted(ids)])
    db.commit()
    return {'id':account.id,'branch_ids':sorted(ids)}
@app.get('/api/branch-admins')
def branch_admins(db: Session = Depends(get_db),user: User = Depends(admin)):
    admins=db.scalars(select(User).where(User.role=='branch_admin').order_by(User.email))
    result=[]
    for account in admins:
        ids=list(db.scalars(select(BranchAdmin.branch_id).where(BranchAdmin.user_id==account.id).order_by(BranchAdmin.branch_id)))
        result.append({'id':account.id,'email':account.email,'branch_ids':ids,
                       'branches':[db.get(Branch,bid).name for bid in ids if db.get(Branch,bid)]})
    return result
@app.post('/api/auth/login')
def login(data: Login, request: Request, db: Session = Depends(get_db)):
    consume(db,'login',request.client.host if request.client else 'unknown',10,60)
    user = db.scalar(select(User).where(User.email==data.email.strip().lower()))
    if not user or not user.active or not hashing.verify(data.password,user.password_hash): raise HTTPException(401,'Incorrect email or password')
    phone=user.phone
    if user.role=='resident':
        resident=db.scalar(select(Resident).where(Resident.user_id==user.id))
        phone=resident.phone if resident else None
    if not phone:
        raise HTTPException(503,'WhatsApp verification cannot start because no mobile number is registered. Contact management to update the account contact.')
    return create_otp_challenge(db,user,phone,request,channel=data.channel)

def utc_aware(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value

def audit_auth(db,user_id,event,request):
    ip=request.client.host if request.client else ''
    ip_hash=hmac.new(settings.jwt_secret.encode(),ip.encode(),hashlib.sha256).hexdigest() if ip else ''
    db.add(AuthAuditEvent(user_id=user_id,event=event,ip_hash=ip_hash))

def mask_phone(phone):
    digits=''.join(ch for ch in str(phone) if ch.isdigit())
    return '•••• '+digits[-2:] if len(digits)>=2 else '••••'

def otp_hash(challenge_id,code):
    return hmac.new(settings.jwt_secret.encode(),f'{challenge_id}:{code}'.encode(),hashlib.sha256).hexdigest()

def otp_send_allowed(db,user_id,phone,request):
    consume(db,'otp-send',request.client.host if request.client else 'unknown',20,3600)
    db.scalar(select(User).where(User.id==user_id).with_for_update())
    moment=now()
    latest=db.scalar(select(OtpChallenge).where(OtpChallenge.user_id==user_id)
                     .order_by(OtpChallenge.created_at.desc(),OtpChallenge.id.desc()).limit(1))
    if latest and utc_aware(latest.created_at)>moment-timedelta(seconds=settings.otp_resend_seconds):
        raise HTTPException(429,'Please wait before requesting another verification code.')
    recent=db.scalar(select(func.count(OtpChallenge.id)).where(OtpChallenge.user_id==user_id,OtpChallenge.created_at>=moment-timedelta(hours=1))) or 0
    if recent>=5: raise HTTPException(429,'Too many verification codes requested. Try again later.')
    phone_recent=db.scalar(select(func.count(OtpChallenge.id)).where(OtpChallenge.phone==phone,OtpChallenge.created_at>=moment-timedelta(hours=1))) or 0
    if phone_recent>=5: raise HTTPException(429,'Too many verification codes requested. Try again later.')
    return moment

def create_otp_challenge(db,user,phone,request,previous=None,channel='whatsapp'):
    if channel=='whatsapp' and not whatsapp.configured() and sms.configured(): channel='sms'
    if (channel=='whatsapp' and not whatsapp.configured()) or (channel=='sms' and not sms.configured()):
        raise HTTPException(503,'Verification delivery is currently unavailable.')
    phone=str(phone).strip()
    moment=otp_send_allowed(db,user.id,phone,request)
    challenge_id=str(uuid4())
    code=f'{secrets.randbelow(1_000_000):06d}'
    challenge=OtpChallenge(challenge_id=challenge_id,user_id=user.id,purpose='login',phone=phone,channel=channel,
        code_hash=otp_hash(challenge_id,code),created_at=moment,last_sent_at=moment,
        expires_at=moment+timedelta(seconds=settings.otp_expiry_seconds),attempts=0)
    db.execute(update(OtpChallenge).where(OtpChallenge.user_id==user.id,OtpChallenge.consumed_at.is_(None)).values(consumed_at=moment))
    if previous:
        previous.consumed_at=moment
    db.add(challenge); db.flush()
    try:
        if channel=='sms': sms.send_auth_code(phone,code)
        else:
            try: whatsapp.send_auth_code(phone,code)
            except whatsapp.WhatsAppUnavailable:
                if not sms.configured(): raise
                sms.send_auth_code(phone,code);channel='sms';challenge.channel=channel
    except (whatsapp.WhatsAppUnavailable,sms.SMSUnavailable) as exc:
        db.rollback()
        raise HTTPException(503,'Verification code could not be delivered. Try again later.') from exc
    audit_auth(db,user.id,'otp_sent',request)
    db.commit()
    return {'challenge_id':challenge_id,'masked_phone':mask_phone(phone),
            'expires_in_seconds':settings.otp_expiry_seconds,'resend_after_seconds':settings.otp_resend_seconds,'channel':channel,'message':f'Enter the verification code sent by {channel}.'}

@app.post('/api/auth/otp/resend')
def resend_otp(data: OtpResend,request: Request,db: Session=Depends(get_db)):
    previous=db.scalar(select(OtpChallenge).where(OtpChallenge.challenge_id==data.challenge_id).with_for_update())
    if not previous or previous.consumed_at or utc_aware(previous.expires_at)<=now():
        raise HTTPException(400,'This verification challenge is unavailable. Sign in again.')
    user=db.get(User,previous.user_id)
    if not user: raise HTTPException(400,'This verification challenge is unavailable. Sign in again.')
    return create_otp_challenge(db,user,previous.phone,request,previous=previous,channel=previous.channel)

@app.post('/api/auth/otp/verify')
def verify_otp(data: OtpVerify,request: Request,db: Session=Depends(get_db)):
    consume(db,'otp-verify',request.client.host if request.client else 'unknown',50,3600)
    challenge=db.scalar(select(OtpChallenge).where(OtpChallenge.challenge_id==data.challenge_id).with_for_update())
    if not challenge or challenge.consumed_at:
        raise HTTPException(400,'The verification code is invalid or expired. Sign in again.')
    moment=now()
    if utc_aware(challenge.expires_at)<=moment:
        challenge.consumed_at=moment; audit_auth(db,challenge.user_id,'otp_expired',request); db.commit()
        raise HTTPException(400,'The verification code has expired. Sign in again.')
    if challenge.attempts>=settings.otp_max_attempts:
        challenge.consumed_at=moment; audit_auth(db,challenge.user_id,'otp_locked',request); db.commit()
        raise HTTPException(429,'Too many incorrect codes. Sign in again to request a new code.')
    challenge.attempts+=1
    if not hmac.compare_digest(challenge.code_hash,otp_hash(challenge.challenge_id,data.code)):
        if challenge.attempts>=settings.otp_max_attempts: challenge.consumed_at=moment
        audit_auth(db,challenge.user_id,'otp_invalid',request); db.commit()
        raise HTTPException(400,'The verification code is incorrect.')
    user=db.get(User,challenge.user_id)
    if not user or not user.active:
        challenge.consumed_at=moment; db.commit(); raise HTTPException(400,'The verification challenge is unavailable.')
    challenge.consumed_at=moment
    user.phone=challenge.phone; user.phone_verified_at=moment
    db.execute(update(OtpChallenge).where(OtpChallenge.user_id==user.id,
        OtpChallenge.id!=challenge.id,OtpChallenge.consumed_at.is_(None)).values(consumed_at=moment))
    audit_auth(db,user.id,'otp_verified',request); db.commit()
    return {'access_token':token_for(user,mfa_verified=True,channel=challenge.channel),'token_type':'bearer'}

@app.get('/api/whatsapp/status')
def whatsapp_status(user: User=Depends(admin)):
    return whatsapp.status()
@app.get('/api/auth/me')
def me(user: User = Depends(current_user)):
    return {'id':user.id,'email':user.email,'role':user.role,'must_change_password':user.must_change_password}
@app.get('/api/my/notification-preferences')
def my_notification_preferences(db: Session=Depends(get_db),user: User=Depends(active_user)):
    if user.role!='resident': raise HTTPException(403,'Resident account required')
    resident=resident_for(db,user)
    return {'whatsapp_enabled':resident.whatsapp_notifications,'whatsapp_consent_at':resident.whatsapp_consent_at,
            'phone_available':bool(resident.phone),'whatsapp_available':whatsapp.configured()}
@app.put('/api/my/notification-preferences')
def update_notification_preferences(data: NotificationPreference,db: Session=Depends(get_db),user: User=Depends(active_user)):
    if user.role!='resident': raise HTTPException(403,'Resident account required')
    resident=resident_for(db,user)
    if data.whatsapp_enabled and (not resident.phone or not whatsapp.configured()):
        raise HTTPException(409,'WhatsApp notifications are unavailable until a phone number and provider are configured.')
    resident.whatsapp_notifications=data.whatsapp_enabled
    resident.whatsapp_consent_at=now() if data.whatsapp_enabled else None
    db.add(NotificationPreferenceEvent(resident_id=resident.id,enabled=data.whatsapp_enabled,source='resident_portal'))
    db.commit()
    return {'whatsapp_enabled':resident.whatsapp_notifications,'whatsapp_consent_at':resident.whatsapp_consent_at,
            'phone_available':bool(resident.phone),'whatsapp_available':whatsapp.configured()}
@app.post('/api/auth/password')
def change_password(data: PasswordChange, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not hashing.verify(data.current_password,user.password_hash): raise HTTPException(400,'Current password is incorrect')
    if data.current_password==data.new_password: raise HTTPException(400,'Choose a different password')
    user.password_hash = hashing.hash(data.new_password)
    user.must_change_password = False
    db.commit()
    return {'message':'Password changed'}
def resident_for(db,user):
    resident = db.scalar(select(Resident).where(Resident.user_id==user.id))
    if not resident: raise HTTPException(404,'Resident record not found')
    return resident

def rooms_data(db,user=None):
    query=select(Room).order_by(Room.number)
    if user is not None:
        scope=branch_scope(db,user)
        if scope is not None: query=query.where(Room.branch_id.in_(scope))
    rooms = db.scalars(query).all()
    return [{'id':r.id,'active':r.active,'branch_id':r.branch_id,'number':r.number,'floor':r.floor,'capacity':r.capacity,'monthly_fee':str(r.monthly_fee),
             'occupied':db.scalar(select(func.count(Resident.id)).where(Resident.room_id==r.id,Resident.status=='active'))} for r in rooms]
@app.get('/api/rooms')
def rooms(db: Session = Depends(get_db), user: User = Depends(staff)):
    return rooms_data(db,user)
@app.post('/api/rooms',status_code=201)
def add_room(data: RoomCreate,db: Session = Depends(get_db),user: User = Depends(staff)):
    values=data.model_dump()
    if values['branch_id'] is None:
        scope=branch_scope(db,user)
        if scope is not None:
            if len(scope)!=1: raise HTTPException(400,'Select an explicitly assigned branch')
            values['branch_id']=scope[0]
        else:
            values['branch_id']=db.scalar(select(Branch.id).order_by(Branch.id).limit(1))
    if not db.get(Branch,values['branch_id']): raise HTTPException(404,'Branch not found')
    require_branch(db,user,values['branch_id'])
    room = Room(**values)
    room.number = room.number.strip()
    db.add(room); db.commit()
    return {'id':room.id}
@app.put('/api/rooms/{room_id}')
def update_room(room_id: int,data: RoomUpdate,db: Session = Depends(get_db),user: User = Depends(staff)):
    room=db.scalar(select(Room).where(Room.id==room_id).with_for_update())
    if not room: raise HTTPException(404,'Room not found')
    require_branch(db,user,room.branch_id)
    occupied=db.scalar(select(func.count(Resident.id)).where(Resident.room_id==room.id,Resident.status=='active')) or 0
    if data.capacity<occupied: raise HTTPException(409,'Capacity cannot be set below current occupancy')
    room.number,room.floor,room.capacity,room.monthly_fee=data.number.strip(),data.floor.strip(),data.capacity,data.monthly_fee
    db.commit()
    return {'message':'Room updated'}
def fee_plan_data(plan):
    return {'id':plan.id,'branch_id':plan.branch_id,'name':plan.name,'sharing':plan.sharing,
        'advance_amount':str(plan.advance_amount),'monthly_fee':str(plan.monthly_fee),'additional_charge_label':plan.additional_charge_label,
        'additional_charge_amount':str(plan.additional_charge_amount),'billing_day':plan.billing_day,'due_day':plan.due_day,
        'effective_from':plan.effective_from,'effective_until':plan.effective_until,'active':plan.active}
def fee_plan_overlap(db,branch_id,sharing,start,end,exclude_id=None):
    query=select(FeePlan.id).where(FeePlan.branch_id==branch_id,FeePlan.sharing==sharing,
        FeePlan.active.is_(True),
        (FeePlan.effective_until.is_(None))|(FeePlan.effective_until>=start),
        FeePlan.effective_from<= (end or date.max))
    if exclude_id is not None: query=query.where(FeePlan.id!=exclude_id)
    return db.scalar(query.limit(1)) is not None
@app.get('/api/fee-plans')
def fee_plans(db: Session=Depends(get_db),user: User=Depends(staff)):
    query=select(FeePlan).order_by(FeePlan.branch_id,FeePlan.sharing,FeePlan.effective_from.desc(),FeePlan.id.desc())
    scope=branch_scope(db,user)
    if scope is not None: query=query.where(FeePlan.branch_id.in_(scope))
    return [fee_plan_data(x) for x in db.scalars(query)]
@app.post('/api/fee-plans',status_code=201)
def create_fee_plan(data: FeePlanCreate,db: Session=Depends(get_db),user: User=Depends(staff)):
    branch=db.get(Branch,data.branch_id)
    if not branch or not branch.active: raise HTTPException(404,'Branch not found')
    require_branch(db,user,data.branch_id)
    if fee_plan_overlap(db,data.branch_id,data.sharing,data.effective_from,data.effective_until):
        raise HTTPException(409,'This branch already has an overlapping fee plan for that sharing type')
    values=data.model_dump();values['name']=data.name.strip();values['additional_charge_label']=data.additional_charge_label.strip()
    plan=FeePlan(**values,created_by=user.id);db.add(plan);db.commit();db.refresh(plan)
    return fee_plan_data(plan)
@app.put('/api/fee-plans/{plan_id}')
def update_fee_plan(plan_id: int,data: FeePlanUpdate,db: Session=Depends(get_db),user: User=Depends(staff)):
    plan=db.get(FeePlan,plan_id)
    if not plan: raise HTTPException(404,'Fee plan not found')
    require_branch(db,user,plan.branch_id)
    used=db.scalar(select(Invoice.id).where(Invoice.fee_plan_id==plan.id).limit(1)) is not None
    changed_pricing=(Decimal(data.monthly_fee)!=Decimal(plan.monthly_fee) or Decimal(data.additional_charge_amount)!=Decimal(plan.additional_charge_amount)
        or data.additional_charge_label.strip()!=plan.additional_charge_label or data.billing_day!=plan.billing_day or data.due_day!=plan.due_day)
    if used and changed_pricing: raise HTTPException(409,'This fee plan is on issued invoices; create a new effective plan to preserve its history')
    if data.effective_until and data.effective_until<plan.effective_from: raise HTTPException(422,'End date must not precede the start date')
    latest_invoice=db.scalar(select(func.max(Invoice.month)).where(Invoice.fee_plan_id==plan.id))
    if latest_invoice and data.effective_until and data.effective_until<latest_invoice:
        raise HTTPException(409,'End date cannot precede an invoiced billing period')
    if data.active and fee_plan_overlap(db,plan.branch_id,plan.sharing,plan.effective_from,data.effective_until,plan.id):
        raise HTTPException(409,'This change would overlap another plan for the same sharing type')
    plan.advance_amount=data.advance_amount
    plan.name=data.name.strip();plan.additional_charge_label=data.additional_charge_label.strip();plan.monthly_fee=data.monthly_fee
    plan.additional_charge_amount=data.additional_charge_amount;plan.billing_day=data.billing_day;plan.due_day=data.due_day
    plan.effective_until=data.effective_until;plan.active=data.active;db.commit()
    return {'message':'Fee plan updated'}
@app.put('/api/residents/{resident_id}/fee-plan')
def assign_resident_fee_plan(resident_id: int,data: ResidentFeePlanUpdate,db: Session=Depends(get_db),user: User=Depends(staff)):
    resident=db.get(Resident,resident_id)
    if not resident: raise HTTPException(404,'Resident not found')
    require_resident_branch(db,user,resident)
    if data.fee_plan_id is None:
        resident.fee_plan_id=None;db.commit();return {'message':'Resident will use the effective branch plan or legacy room rate'}
    plan=db.get(FeePlan,data.fee_plan_id)
    if not plan: raise HTTPException(404,'Fee plan not found')
    if plan.branch_id!=resident.branch_id or not plan.active: raise HTTPException(422,'Fee plan must be active and belong to the resident branch')
    if resident.room_id:
        room=db.get(Room,resident.room_id)
        if room.capacity!=plan.sharing: raise HTTPException(422,'Fee plan sharing must match the resident room capacity')
    if plan.effective_until and plan.effective_until<local_today(): raise HTTPException(422,'Fee plan is no longer effective')
    resident.fee_plan_id=plan.id;db.commit()
    return {'message':'Resident fee plan assigned'}
def ledger_event_data(db,event,include_actor=True):
    actor=db.get(User,event.actor_user_id)
    return {'id':event.id,'resident_id':event.resident_id,'branch_id':event.branch_id,'settlement_id':event.settlement_id,
        'account_type':event.account_type,'action':event.action,'amount':str(event.amount),'method':event.method,
        'reference':event.reference,'reason':event.reason,'actor_email':actor.email if include_actor and actor else None,'created_at':event.created_at}
@app.get('/api/residents/{resident_id}/financial-ledger')
def resident_financial_ledger(resident_id: int,db: Session=Depends(get_db),user: User=Depends(active_user)):
    resident=db.get(Resident,resident_id)
    if not resident: raise HTTPException(404,'Resident not found')
    if is_staff(user): require_resident_branch(db,user,resident)
    elif resident.user_id!=user.id: raise HTTPException(403,'Financial ledger belongs to another resident')
    events=db.scalars(select(FinancialLedgerEvent).where(FinancialLedgerEvent.resident_id==resident_id).order_by(FinancialLedgerEvent.created_at.desc(),FinancialLedgerEvent.id.desc()))
    return {'balances':{key:str(value) for key,value in financial_balances(db,resident_id).items()},
            'configured_advance':resident_data(db,resident)['configured_advance'],
            'advance_remaining':str(max(Decimal('0'),Decimal(resident_data(db,resident)['configured_advance'])-financial_balances(db,resident_id)['advance'])),
            'events':[ledger_event_data(db,event,include_actor=is_staff(user)) for event in events]}
@app.post('/api/residents/{resident_id}/financial-ledger',status_code=201)
def add_financial_ledger_event(resident_id: int,data: FinancialLedgerCreate,db: Session=Depends(get_db),user: User=Depends(staff)):
    resident=db.scalar(select(Resident).where(Resident.id==resident_id).with_for_update())
    if not resident: raise HTTPException(404,'Resident not found')
    require_resident_branch(db,user,resident)
    if resident.branch_id is None: raise HTTPException(409,'Resident has no assigned branch')
    if data.action=='received' and data.method is None: raise HTTPException(422,'Select the method used to receive the money')
    if data.action=='deduction' and len(data.reason.strip())<5: raise HTTPException(422,'A deduction reason of at least five characters is required')
    if data.action=='deduction' and data.method is not None: raise HTTPException(422,'Deductions do not have a payment method')
    existing=db.scalar(select(FinancialLedgerEvent).where(FinancialLedgerEvent.idempotency_key==data.idempotency_key))
    if existing:
        matches=(existing.resident_id==resident_id and existing.account_type==data.account_type and existing.action==data.action
            and Decimal(existing.amount)==data.amount and existing.method==data.method and existing.reference==data.reference.strip()
            and existing.reason==data.reason.strip())
        if not matches: raise HTTPException(409,'This ledger idempotency key was used for a different event')
        return {'id':existing.id,'duplicate':True,'balances':{k:str(v) for k,v in financial_balances(db,resident_id).items()}}
    open_settlement=db.scalar(select(FinalSettlement.id).where(FinalSettlement.resident_id==resident_id,
        FinalSettlement.status.in_(['pending','approved','partially_refunded'])).limit(1))
    if open_settlement: raise HTTPException(409,'Resolve the open final settlement before changing this ledger')
    if data.action=='deduction' and financial_balances(db,resident_id)[data.account_type]<data.amount:
        raise HTTPException(409,'Deduction exceeds the available account balance')
    event=FinancialLedgerEvent(resident_id=resident_id,branch_id=resident.branch_id,account_type=data.account_type,
        action=data.action,amount=data.amount,method=data.method,reference=data.reference.strip(),reason=data.reason.strip(),
        idempotency_key=data.idempotency_key,actor_user_id=user.id)
    db.add(event);db.commit();db.refresh(event)
    return {'id':event.id,'balances':{k:str(v) for k,v in financial_balances(db,resident_id).items()}}
@app.get('/api/settlements')
def settlements(db: Session=Depends(get_db),user: User=Depends(active_user)):
    query=select(FinalSettlement).order_by(FinalSettlement.created_at.desc(),FinalSettlement.id.desc())
    if is_staff(user):
        scope=branch_scope(db,user)
        if scope is not None: query=query.where(FinalSettlement.branch_id.in_(scope))
    else: query=query.where(FinalSettlement.resident_id==resident_for(db,user).id)
    return [settlement_data(db,item) for item in db.scalars(query)]
@app.post('/api/settlements',status_code=201)
def create_settlement(data: SettlementCreate,db: Session=Depends(get_db),user: User=Depends(staff)):
    resident=db.scalar(select(Resident).where(Resident.id==data.resident_id).with_for_update())
    if not resident: raise HTTPException(404,'Resident not found')
    require_resident_branch(db,user,resident)
    if resident.branch_id is None: raise HTTPException(409,'Resident has no assigned branch')
    if resident.status!='vacated' and resident.planned_move_out is None:
        raise HTTPException(409,'A final settlement can be prepared only for a resident with a recorded vacating date')
    if db.scalar(select(FinalSettlement.id).where(FinalSettlement.resident_id==resident.id,
        FinalSettlement.status.in_(['pending','approved','partially_refunded'])).limit(1)):
        raise HTTPException(409,'This resident already has an open settlement')
    balances=financial_balances(db,resident.id)
    available=balances['deposit']+balances['advance']
    if data.proposed_refund>available: raise HTTPException(409,'Proposed refund exceeds recorded deposit and advance balances')
    if data.proposed_refund<available and not data.note.strip():
        raise HTTPException(422,'Explain why the proposed refund is below the recorded available balance')
    item=FinalSettlement(resident_id=resident.id,branch_id=resident.branch_id,status='pending',
        deposit_balance_snapshot=balances['deposit'],advance_balance_snapshot=balances['advance'],
        invoice_balance_snapshot=resident_invoice_balance(db,resident.id),proposed_refund=data.proposed_refund,
        note=data.note.strip(),created_by=user.id)
    db.add(item);db.flush()
    db.add(SettlementEvent(settlement_id=item.id,actor_user_id=user.id,action='proposed',old_status=None,new_status='pending',note=item.note))
    db.commit();db.refresh(item)
    return settlement_data(db,item)
@app.put('/api/settlements/{settlement_id}/decision')
def decide_settlement(settlement_id: int,data: SettlementDecision,db: Session=Depends(get_db),user: User=Depends(staff)):
    item=db.scalar(select(FinalSettlement).where(FinalSettlement.id==settlement_id).with_for_update())
    if not item: raise HTTPException(404,'Settlement not found')
    require_branch(db,user,item.branch_id)
    if item.status!='pending': raise HTTPException(409,'Only a pending settlement can be decided')
    resident=db.scalar(select(Resident).where(Resident.id==item.resident_id).with_for_update())
    if data.status=='approved' and item.invoice_balance_snapshot>0 and len(data.note.strip())<5:
        raise HTTPException(422,'Explain how the outstanding invoice balance was considered before approval')
    if data.status=='approved' and item.proposed_refund>sum(financial_balances(db,resident.id).values()):
        raise HTTPException(409,'Current ledger balance is below the proposed refund')
    old=item.status
    if data.status=='rejected': item.status='rejected'
    elif item.proposed_refund==0: item.status='no_refund'
    else: item.status='approved'
    item.decision_note=data.note.strip();item.decided_by=user.id;item.decided_at=now()
    db.add(SettlementEvent(settlement_id=item.id,actor_user_id=user.id,action=data.status,old_status=old,new_status=item.status,note=item.decision_note))
    db.commit()
    return settlement_data(db,item)
@app.post('/api/settlements/{settlement_id}/refund',status_code=201)
def record_settlement_refund(settlement_id: int,data: SettlementRefund,db: Session=Depends(get_db),user: User=Depends(staff)):
    item=db.scalar(select(FinalSettlement).where(FinalSettlement.id==settlement_id).with_for_update())
    if not item: raise HTTPException(404,'Settlement not found')
    require_branch(db,user,item.branch_id)
    existing=db.scalar(select(FinancialLedgerEvent).where(FinancialLedgerEvent.idempotency_key==data.idempotency_key))
    if existing:
        if existing.settlement_id!=item.id or existing.action!='refund' or Decimal(existing.amount)!=data.amount or existing.account_type!=data.account_type or existing.method!=data.method or existing.reference!=data.reference.strip():
            raise HTTPException(409,'This refund idempotency key was used for a different event')
        return {'id':existing.id,'duplicate':True,'settlement':settlement_data(db,item)}
    if item.status not in {'approved','partially_refunded'}: raise HTTPException(409,'Only an approved settlement can be refunded')
    refunded=db.scalar(select(func.coalesce(func.sum(FinancialLedgerEvent.amount),0)).where(
        FinancialLedgerEvent.settlement_id==item.id,FinancialLedgerEvent.action=='refund')) or Decimal('0')
    if refunded+data.amount>item.proposed_refund: raise HTTPException(409,'Refund exceeds the approved settlement amount')
    if financial_balances(db,item.resident_id)[data.account_type]<data.amount:
        raise HTTPException(409,'Refund exceeds the available balance in that account')
    event=FinancialLedgerEvent(resident_id=item.resident_id,branch_id=item.branch_id,settlement_id=item.id,
        account_type=data.account_type,action='refund',amount=data.amount,method=data.method,reference=data.reference.strip(),
        reason=f'Approved final settlement #{item.id}',idempotency_key=data.idempotency_key,actor_user_id=user.id)
    db.add(event);db.flush()
    new_status='completed' if refunded+data.amount==item.proposed_refund else 'partially_refunded'
    old=item.status;item.status=new_status
    db.add(SettlementEvent(settlement_id=item.id,actor_user_id=user.id,action='refund_recorded',old_status=old,new_status=new_status,
        note=f'{data.method}: {data.amount}'))
    db.commit();db.refresh(event)
    return {'id':event.id,'settlement':settlement_data(db,item)}
@app.get('/api/settlements/{settlement_id}/history')
def settlement_history(settlement_id: int,db: Session=Depends(get_db),user: User=Depends(active_user)):
    item=db.get(FinalSettlement,settlement_id)
    if not item: raise HTTPException(404,'Settlement not found')
    if is_staff(user): require_branch(db,user,item.branch_id)
    elif item.resident_id!=resident_for(db,user).id: raise HTTPException(403,'Settlement belongs to another resident')
    return [{'action':x.action,'old_status':x.old_status,'new_status':x.new_status,'note':x.note,
             'actor_user_id':x.actor_user_id if is_staff(user) else None,'created_at':x.created_at}
        for x in db.scalars(select(SettlementEvent).where(SettlementEvent.settlement_id==item.id).order_by(SettlementEvent.created_at,SettlementEvent.id))]
def resident_data(db,r):
    room = db.get(Room,r.room_id) if r.room_id else None
    plan=db.get(FeePlan,r.fee_plan_id) if r.fee_plan_id else None
    cycle=local_today().replace(day=1)
    if plan and (plan.branch_id!=r.branch_id or (room and plan.sharing!=room.capacity) or
                 not fee_plan_matches(plan,r.branch_id,plan.sharing,cycle)):
        plan=None
    if not plan and room:
        plan=db.scalar(select(FeePlan).where(FeePlan.branch_id==r.branch_id,FeePlan.sharing==room.capacity,
            FeePlan.active.is_(True),FeePlan.effective_from<=cycle,
            (FeePlan.effective_until.is_(None))|(FeePlan.effective_until>=cycle)
        ).order_by(FeePlan.effective_from.desc(),FeePlan.id.desc()).limit(1))
    if plan and (plan.branch_id!=r.branch_id or (room and plan.sharing!=room.capacity)):
        plan=None
    base=Decimal(plan.monthly_fee if plan else room.monthly_fee) if room else None
    additional=Decimal(plan.additional_charge_amount) if plan and room else Decimal('0.00')
    discount_amount,_=applicable_discount(db,r,base,additional,cycle) if room else (Decimal('0'),None)
    admission=db.scalar(select(Admission).where(Admission.resident_id==r.id))
    branch=db.get(Branch,r.branch_id)
    return {'admission_id':admission.id if admission else None,'admission_status':admission.status if admission else 'Direct admission',
            'branch_name':branch.name if branch else None,'id':r.id,'resident_code':r.resident_code,'branch_id':r.branch_id,'name':r.name,'email':db.get(User,r.user_id).email,'phone':r.phone,'guardian':r.guardian,
            'guardian_phone':r.guardian_phone,'institution':r.institution,'joined_on':r.joined_on,'planned_move_out':r.planned_move_out,'status':r.status,'room_id':r.room_id,
            'room_number':room.number if room else None,'discount':str(r.discount),'fee_plan_id':plan.id if plan else None,
            'monthly_fee':str(base+additional-discount_amount) if room else None,
            'configured_advance':str(plan.advance_amount) if plan else '0.00',
            'additional_charge_label':plan.additional_charge_label if plan else '',
            'aadhaar_last4':r.aadhaar_last4,'id_status':r.id_status,'id_reviewed_at':r.id_reviewed_at}
@app.get('/api/residents')
def residents(db: Session = Depends(get_db),user: User = Depends(active_user)):
    if is_staff(user):
        query=select(Resident).order_by(Resident.id.desc())
        scope=branch_scope(db,user)
        if scope is not None: query=query.where(Resident.branch_id.in_(scope))
        rows=db.scalars(query).all()
    else: rows=[resident_for(db,user)]
    return [resident_data(db,r) for r in rows]

def gate_pass_data(db,pass_record):
    resident=db.get(Resident,pass_record.resident_id)
    room=db.get(Room,resident.room_id) if resident and resident.room_id else None
    revoked=pass_record.revoked_at is not None
    expired=pass_record.valid_until is not None and pass_record.valid_until<local_today()
    status='revoked' if revoked else ('expired' if expired else ('inactive' if resident.status!='active' else 'active'))
    return {'id':pass_record.id,'resident_id':resident.id,'resident_code':resident.resident_code,
            'resident_name':resident.name,'branch_id':resident.branch_id,'room_number':room.number if room else None,
            'valid_from':pass_record.valid_from,'valid_until':pass_record.valid_until,'revoked_at':pass_record.revoked_at,
            'status':status,'is_valid':status=='active'}

@app.get('/api/gate-passes')
def gate_passes(db: Session = Depends(get_db),user: User = Depends(active_user)):
    query=select(GatePass).join(Resident,Resident.id==GatePass.resident_id).order_by(GatePass.id.desc())
    if is_staff(user):
        scope=branch_scope(db,user)
        if scope is not None: query=query.where(Resident.branch_id.in_(scope))
    else:
        resident=resident_for(db,user)
        query=query.where(GatePass.resident_id==resident.id)
    return [gate_pass_data(db,p) for p in db.scalars(query)]

@app.post('/api/gate-passes',status_code=201)
def issue_gate_pass(data: GatePassCreate,db: Session = Depends(get_db),user: User = Depends(staff)):
    resident=db.get(Resident,data.resident_id)
    if not resident: raise HTTPException(404,'Resident not found')
    require_resident_branch(db,user,resident)
    if resident.status!='active': raise HTTPException(409,'Gate passes can only be issued to active residents')
    if data.valid_until is not None and (data.valid_until<local_today() or data.valid_until>(local_today()+timedelta(days=365))):
        raise HTTPException(422,'Pass expiry must be today or within the next year')
    record=GatePass(pass_code=secrets.token_urlsafe(32),resident_id=resident.id,created_by=user.id,valid_until=data.valid_until)
    db.add(record);db.commit();db.refresh(record)
    return gate_pass_data(db,record)

@app.put('/api/gate-passes/{pass_id}/revoke')
def revoke_gate_pass(pass_id: int,db: Session = Depends(get_db),user: User = Depends(staff)):
    record=db.get(GatePass,pass_id)
    if not record: raise HTTPException(404,'Gate pass not found')
    require_resident_branch(db,user,db.get(Resident,record.resident_id))
    if record.revoked_at is not None: raise HTTPException(409,'Gate pass is already revoked')
    record.revoked_at=now();record.revoked_by=user.id;db.commit()
    return {'message':'Gate pass revoked'}
@app.post('/api/residents',status_code=201)
def add_resident(data: ResidentCreate,db: Session = Depends(get_db),user: User = Depends(staff)):
    if data.joined_on>local_today(): raise HTTPException(400,'Joining date cannot be in the future')
    new_user = User(email=str(data.email).lower(),password_hash=hashing.hash(data.temporary_password),role='resident',must_change_password=True)
    db.add(new_user); db.flush()
    details = data.model_dump(exclude={'email','temporary_password'})
    if details.get('branch_id') is None:
        scope=branch_scope(db,user)
        if scope is not None:
            if len(scope)!=1: raise HTTPException(400,'Select an explicitly assigned branch')
            details['branch_id']=scope[0]
        else: details['branch_id']=db.scalar(select(Branch.id).order_by(Branch.id).limit(1))
    if not db.get(Branch,details['branch_id']): raise HTTPException(404,'Branch not found')
    require_branch(db,user,details['branch_id'])
    details['name'] = details['name'].strip()
    resident = Resident(user_id=new_user.id,**details)
    db.add(resident); db.commit()
    return {'id':resident.id,'message':'Account created. Share the temporary password privately; it must be changed at first login.'}
@app.put('/api/residents/{resident_id}/allocation')
def allocate(resident_id: int,data: Allocation,db: Session = Depends(get_db),user: User = Depends(staff)):
    # Lock resident then all involved rooms in ID order, including the old room.
    resident = db.scalar(select(Resident).where(Resident.id==resident_id).with_for_update())
    if not resident: raise HTTPException(404,'Resident not found')
    require_resident_branch(db,user,resident)
    room_ids = sorted({r for r in [data.room_id,resident.room_id] if r is not None})
    locked = db.scalars(select(Room).where(Room.id.in_(room_ids)).order_by(Room.id).with_for_update()).all()
    room = next((r for r in locked if r.id==data.room_id),None)
    if not room or not room.active: raise HTTPException(404,'Active room not found')
    require_branch(db,user,room.branch_id)
    if resident.branch_id != room.branch_id: raise HTTPException(409,'Resident and room must belong to the same branch')
    occupied = db.scalar(select(func.count(Resident.id)).where(Resident.room_id==room.id,Resident.id!=resident.id,Resident.status=='active'))
    if resident.status!='active': raise HTTPException(409,'Vacated residents cannot be allocated')
    if occupied>=room.capacity: raise HTTPException(409,'This room is full')
    plan=resolve_fee_plan(db,resident,room,local_today().replace(day=1))
    base_fee=Decimal(plan.monthly_fee) if plan else room.monthly_fee
    if data.discount>base_fee: raise HTTPException(400,'Discount cannot exceed accommodation fee')
    if data.discount and db.scalar(select(ResidentDiscount.id).where(ResidentDiscount.resident_id==resident.id,ResidentDiscount.revoked_at.is_(None),ResidentDiscount.effective_until>=local_today().replace(day=1))):
        raise HTTPException(409,'Revoke the percentage approval before assigning a fixed discount')
    previous_room_id=resident.room_id
    resident.room_id,resident.discount = room.id,data.discount
    if previous_room_id!=room.id:
        db.add(AllocationEvent(resident_id=resident.id,from_room_id=previous_room_id,to_room_id=room.id,actor_user_id=user.id,reason=data.reason))
    db.commit()
    return {'message':'Room allocated. Existing invoices remain unchanged.'}
@app.put('/api/residents/{resident_id}/id-review')
def review(resident_id: int,data: IDReview,db: Session = Depends(get_db),user: User = Depends(staff)):
    resident = db.get(Resident,resident_id)
    if not resident: raise HTTPException(404,'Resident not found')
    require_resident_branch(db,user,resident)
    if data.aadhaar_last4 is not None: resident.aadhaar_last4=data.aadhaar_last4
    if not resident.aadhaar_last4: raise HTTPException(400,'Record only the last four digits after inspecting the document privately')
    old_status=resident.id_status
    resident.id_status,resident.id_reviewed_by,resident.id_reviewed_at = data.status,user.id,now()
    db.add(IdentityReviewEvent(resident_id=resident.id,reviewer_id=user.id,old_status=old_status,new_status=data.status,note=data.note))
    db.commit()
    return {'message':'Manual document review recorded; this is not UIDAI verification.'}
@app.get('/api/residents/{resident_id}/allocation-history')
def allocation_history(resident_id: int,db: Session = Depends(get_db),user: User = Depends(active_user)):
    resident=db.get(Resident,resident_id)
    if not resident: raise HTTPException(404,'Resident not found')
    if is_staff(user): require_resident_branch(db,user,resident)
    elif resident.user_id!=user.id: raise HTTPException(403,'Resident record belongs to another account')
    rows=db.scalars(select(AllocationEvent).where(AllocationEvent.resident_id==resident_id).order_by(AllocationEvent.created_at.desc(),AllocationEvent.id.desc()))
    return [{'from_room_id':x.from_room_id,'from_room':db.get(Room,x.from_room_id).number if x.from_room_id else None,
             'to_room_id':x.to_room_id,'to_room':db.get(Room,x.to_room_id).number if x.to_room_id else None,
             'actor_user_id':x.actor_user_id,'reason':x.reason,'created_at':x.created_at} for x in rows]
@app.get('/api/residents/{resident_id}/verification-history')
def verification_history(resident_id: int,db: Session = Depends(get_db),user: User = Depends(active_user)):
    resident=db.get(Resident,resident_id)
    if not resident: raise HTTPException(404,'Resident not found')
    if is_staff(user): require_resident_branch(db,user,resident)
    elif resident.user_id!=user.id: raise HTTPException(403,'Resident record belongs to another account')
    rows=db.scalars(select(IdentityReviewEvent).where(IdentityReviewEvent.resident_id==resident_id).order_by(IdentityReviewEvent.created_at.desc(),IdentityReviewEvent.id.desc()))
    return [{'old_status':x.old_status,'new_status':x.new_status,'reviewer_id':x.reviewer_id,'note':x.note,'created_at':x.created_at} for x in rows]

def invoices_data(db,user):
    query = select(Invoice).order_by(Invoice.month.desc(),Invoice.id.desc())
    if is_staff(user):
        scope=branch_scope(db,user)
        if scope is not None: query=query.where(Invoice.branch_id.in_(scope))
    else: query = query.where(Invoice.resident_id==resident_for(db,user).id)
    result=[]
    for i in db.scalars(query):
        paid = paid_total(db,i.id)
        result.append({'id':i.id,'resident_id':i.resident_id,'resident_name':db.get(Resident,i.resident_id).name,
                       'invoice_number':i.invoice_number,'issued_on':i.issued_on,'month':i.month,'due_on':i.due_on,'branch_id':i.branch_id,'room_number':i.room_number,'base_fee':str(i.base_fee),
                       'fee_plan_id':i.fee_plan_id,'additional_charge_label':i.additional_charge_label,'additional_charge_amount':str(i.additional_charge_amount),
                       'discount_percent':str(i.discount_percent),'discount':str(i.discount),'amount':str(i.amount),'paid':str(paid),'balance':str(i.amount-paid),
                       'status':'paid' if paid>=i.amount else ('overdue' if i.due_on<local_today() else 'due')})
    return result
@app.get('/api/invoices')
def invoices(db: Session = Depends(get_db),user: User = Depends(active_user)):
    return invoices_data(db,user)
@app.get('/api/invoices/{invoice_id}/pdf')
def invoice_download(invoice_id: int,db: Session = Depends(get_db),user: User = Depends(active_user)):
    invoice=db.get(Invoice,invoice_id)
    if not invoice: raise HTTPException(404,'Invoice not found')
    resident=db.get(Resident,invoice.resident_id)
    if is_staff(user): require_branch(db,user,invoice.branch_id)
    elif resident.user_id!=user.id: raise HTTPException(403,'Invoice belongs to another resident')
    branch=db.get(Branch,invoice.branch_id)
    paid=paid_total(db,invoice.id);balance=invoice.amount-paid
    return Response(invoice_pdf(invoice,resident,branch,paid,balance),media_type='application/pdf',
                    headers={'Content-Disposition':f'attachment; filename="{invoice.invoice_number}.pdf"'})
def applicable_discount(db,resident,base_fee,additional_amount,month):
    rule=db.scalar(select(ResidentDiscount).where(ResidentDiscount.resident_id==resident.id,ResidentDiscount.revoked_at.is_(None),ResidentDiscount.effective_from<=month,ResidentDiscount.effective_until>=month))
    amount=min(base_fee,Decimal(resident.discount))
    if rule:
        if resident.discount: raise HTTPException(409,'Fixed and percentage discounts cannot be combined')
        eligible=base_fee+(additional_amount if rule.charge_scope=='all_monthly' else Decimal('0'))
        amount=(eligible*rule.percentage/100).quantize(Decimal('0.01'))
        if rule.max_amount is not None: amount=min(amount,rule.max_amount)
    return amount,rule

@app.post('/api/billing/generate')
def billing(data: BillingRun,db: Session = Depends(get_db),user: User = Depends(staff)):
    month = data.month.replace(day=1)
    if month>local_today().replace(day=1): raise HTTPException(400,'Generate invoices only for the current or a past month')
    return {'created':generate_monthly_invoices(db,month,branch_scope(db,user))}

def generate_monthly_invoices(db,month,scope=None,scheduled=False):
    count=0
    query=select(Resident).where(Resident.room_id.is_not(None),Resident.status=='active').order_by(Resident.id).with_for_update()
    if scope is not None: query=query.where(Resident.branch_id.in_(scope))
    for resident in db.scalars(query):
        if resident.joined_on.replace(day=1)>month: continue
        if db.scalar(select(Invoice.id).where(Invoice.resident_id==resident.id,Invoice.month==month)): continue
        room = db.get(Room,resident.room_id)
        plan=resolve_fee_plan(db,resident,room,month)
        if plan and month==local_today().replace(day=1) and local_today().day<plan.billing_day:
            if scheduled: continue
            raise HTTPException(409,f'Monthly billing for this branch/sharing plan begins on day {plan.billing_day}')
        base_fee=Decimal(plan.monthly_fee) if plan else Decimal(room.monthly_fee)
        additional_amount=Decimal(plan.additional_charge_amount) if plan else Decimal('0.00')
        additional_label=plan.additional_charge_label if plan else ''
        due_day=plan.due_day if plan else 5
        invoice_number=f'SW-{resident.branch_id:03d}-{month:%Y%m}-{resident.id:06d}'
        discount_amount,discount_rule=applicable_discount(db,resident,base_fee,additional_amount,month)
        invoice_amount=base_fee+additional_amount-discount_amount
        db.add(Invoice(invoice_number=invoice_number,issued_on=local_today(),resident_id=resident.id,branch_id=resident.branch_id,fee_plan_id=plan.id if plan else None,
                       month=month,due_on=month.replace(day=due_day),room_number=room.number,base_fee=base_fee,additional_charge_label=additional_label,
                       additional_charge_amount=additional_amount,discount=discount_amount,amount=invoice_amount,
                       discount_rule_id=discount_rule.id if discount_rule else None,discount_percent=discount_rule.percentage if discount_rule else 0))
        db.flush(); count+=1
    db.commit()
    return count
@app.post('/api/payments',status_code=201)
def payment(data: PaymentCreate,db: Session = Depends(get_db),user: User = Depends(staff)):
    invoice = db.scalar(select(Invoice).where(Invoice.id==data.invoice_id).with_for_update())
    if not invoice: raise HTTPException(404,'Invoice not found')
    invoice_resident=db.get(Resident,invoice.resident_id)
    require_branch(db,user,invoice.branch_id)
    existing = db.scalar(select(Payment).where(Payment.idempotency_key==data.idempotency_key))
    if existing:
        if (existing.invoice_id,existing.amount,existing.method,existing.reference,existing.payer_name,existing.note)!=(data.invoice_id,data.amount,data.method,data.reference,data.payer_name,data.note):
            raise HTTPException(409,'Payment key was already used for another request')
        return {'id':existing.id,'message':'Payment was already recorded'}
    if data.amount>invoice.amount-paid_total(db,invoice.id): raise HTTPException(400,'Payment exceeds outstanding balance')
    if data.method!='cash' and not data.reference.strip(): raise HTTPException(400,'UPI or bank payment reference is required')
    paid_at=data.paid_at or now()
    if paid_at.tzinfo is None: raise HTTPException(422,'Payment date and time must include a timezone')
    if paid_at.astimezone(timezone.utc)>datetime.now(timezone.utc)+timedelta(minutes=5):
        raise HTTPException(422,'Payment date and time cannot be in the future')
    p = Payment(**data.model_dump(exclude={'paid_at'}),paid_at=paid_at,recorded_by=user.id)
    db.add(p); db.flush()
    resident = invoice_resident
    db.add(Outbox(user_id=resident.user_id,branch_id=invoice.branch_id,dedupe_key=f'receipt:{p.id}',recipient=db.get(User,resident.user_id).email,
                  subject=f"Cityhive payment receipt SW-{p.id:06d}",body=receipt_text(db,p)))
    db.commit()
    return {'id':p.id,'message':'Payment recorded; receipt email queued'}

@app.post('/api/payments/{payment_id}/reverse')
def reverse_payment(payment_id: int,data: PaymentReversal,db: Session=Depends(get_db),user: User=Depends(staff)):
    payment=db.scalar(select(Payment).where(Payment.id==payment_id).with_for_update())
    if not payment: raise HTTPException(404,'Payment not found')
    invoice=db.scalar(select(Invoice).where(Invoice.id==payment.invoice_id).with_for_update())
    resident=db.get(Resident,invoice.resident_id)
    require_branch(db,user,invoice.branch_id)
    if payment.reversed_at: raise HTTPException(409,'This payment has already been reversed')
    payment.reversed_at=now(); payment.reversed_by=user.id; payment.reversal_reason=data.reason.strip()
    db.add(PaymentAuditEvent(payment_id=payment.id,actor_user_id=user.id,action='reversed',reason=data.reason.strip()))
    resident_user=db.get(User,resident.user_id)
    key=f'payment-reversal:{payment.id}'
    if resident_user:
        db.add(Outbox(user_id=resident.user_id,branch_id=invoice.branch_id,dedupe_key=key,recipient=resident_user.email,
            subject=f'Cityhive payment update · SW-{payment.id:06d}',body=receipt_text(db,payment)))
    db.commit()
    return {'id':payment.id,'status':'reversed','balance':str(invoice.amount-paid_total(db,invoice.id))}

@app.get('/api/payments')
def payments(db: Session = Depends(get_db),user: User = Depends(active_user)):
    query = select(Payment).join(Invoice).order_by(Payment.id.desc())
    if is_staff(user):
        scope=branch_scope(db,user)
        if scope is not None: query=query.where(Invoice.branch_id.in_(scope))
    else: query=query.where(Invoice.resident_id==resident_for(db,user).id)
    return [{'id':p.id,'invoice_id':p.invoice_id,'amount':str(p.amount),'method':p.method,'reference':p.reference,'paid_at':p.paid_at,
             'payer_name':p.payer_name,'note':p.note,'recorded_by':p.recorded_by,'reversed_at':p.reversed_at,
             'reversal_reason':p.reversal_reason} for p in db.scalars(query)]
@app.get('/api/payments/{payment_id}/receipt',response_class=PlainTextResponse)
def receipt(payment_id: int,db: Session = Depends(get_db),user: User = Depends(active_user)):
    p = db.get(Payment,payment_id)
    if not p: raise HTTPException(404,'Receipt not found')
    invoice = db.get(Invoice,p.invoice_id)
    if is_staff(user): require_branch(db,user,invoice.branch_id)
    elif invoice.resident_id!=resident_for(db,user).id: raise HTTPException(403,'Receipt belongs to another resident')
    return receipt_text(db,p)
@app.post('/api/reminders/run')
def remind(db: Session = Depends(get_db),user: User = Depends(staff)):
    count=queue_reminders(db,branch_scope(db,user)); db.commit()
    return {'queued':count}
@app.get('/api/emails')
def emails(db: Session = Depends(get_db),user: User = Depends(staff)):
    query=select(Outbox).order_by(Outbox.id.desc()).limit(100)
    scope=branch_scope(db,user)
    if scope is not None: query=query.where(Outbox.branch_id.in_(scope))
    return [{'id':e.id,'recipient':e.recipient,'subject':e.subject,'channel':e.channel,'delivery_status':e.delivery_status,
             'sent_at':e.sent_at,'cancelled':e.cancelled,'attempts':e.attempts,'last_error':e.last_error} for e in db.scalars(query)]
@app.get('/api/complaints')
def complaints(db: Session = Depends(get_db),user: User = Depends(active_user)):
    query = select(Complaint).order_by(Complaint.id.desc())
    if is_staff(user):
        scope=branch_scope(db,user)
        if scope is not None: query=query.join(Resident,Resident.id==Complaint.resident_id).where(Resident.branch_id.in_(scope))
    else: query=query.where(Complaint.resident_id==resident_for(db,user).id)
    records=list(db.scalars(query))
    events_by_complaint={}
    if records:
        for event in db.scalars(select(ComplaintEvent).where(ComplaintEvent.complaint_id.in_([c.id for c in records])).order_by(ComplaintEvent.created_at,ComplaintEvent.id)):
            events_by_complaint.setdefault(event.complaint_id,[]).append({
                'action':event.action,'old_status':event.old_status,'new_status':event.new_status,
                'old_response':event.old_response,'new_response':event.new_response,'created_at':event.created_at,
                'old_assignee_user_id':event.old_assignee_user_id,'new_assignee_user_id':event.new_assignee_user_id,
                'resolution_note':event.resolution_note,
            })
    return [{'id':c.id,'resident_name':db.get(Resident,c.resident_id).name,'branch_id':db.get(Resident,c.resident_id).branch_id,
             'category':c.category,'title':c.title,'description':c.description,'status':c.status,'response':c.response,
             'assigned_to_user_id':c.assigned_to_user_id if is_staff(user) else None,
             'assigned_to_email':db.get(User,c.assigned_to_user_id).email if is_staff(user) and c.assigned_to_user_id else None,
             'resolution_note':c.resolution_note,'created_at':c.created_at,'updated_at':c.updated_at,'resolved_at':c.resolved_at,
             'history':events_by_complaint.get(c.id,[]) if is_staff(user) else [dict(event,old_assignee_user_id=None,new_assignee_user_id=None) for event in events_by_complaint.get(c.id,[])]} for c in records]
@app.get('/api/complaint-assignees')
def complaint_assignees(branch_id: int | None=None,db: Session=Depends(get_db),user: User=Depends(staff)):
    scope=branch_scope(db,user)
    if branch_id is not None:
        require_branch(db,user,branch_id)
    branch_admin_ids=select(BranchAdmin.user_id)
    if branch_id is not None: branch_admin_ids=branch_admin_ids.where(BranchAdmin.branch_id==branch_id)
    elif scope is not None: branch_admin_ids=branch_admin_ids.where(BranchAdmin.branch_id.in_(scope))
    query=select(User).where((User.role.in_(['admin','owner','superadmin']))|(User.id.in_(branch_admin_ids))).order_by(User.email)
    return [{'id':x.id,'email':x.email,'role':x.role} for x in db.scalars(query)]
@app.post('/api/complaints',status_code=201)
def add_complaint(data: ComplaintCreate,db: Session = Depends(get_db),user: User = Depends(active_user)):
    if user.role!='resident': raise HTTPException(403,'Sign in as a resident to submit a complaint')
    c = Complaint(resident_id=resident_for(db,user).id,**data.model_dump())
    db.add(c); db.flush()
    db.add(ComplaintEvent(complaint_id=c.id,actor_user_id=user.id,action='submitted',old_status=None,new_status=c.status,old_response=None,new_response=c.response))
    db.commit()
    return {'id':c.id}
@app.put('/api/complaints/{complaint_id}')
def update_complaint(complaint_id: int,data: ComplaintUpdate,db: Session = Depends(get_db),user: User = Depends(staff)):
    c = db.get(Complaint,complaint_id)
    if not c: raise HTTPException(404,'Complaint not found')
    require_resident_branch(db,user,db.get(Resident,c.resident_id))
    old_status,old_response=c.status,c.response
    c.status,c.response,c.resolution_note,c.updated_at=data.status,data.response,data.resolution_note.strip(),now()
    c.resolved_at=now() if data.status=='resolved' else None
    db.add(ComplaintEvent(complaint_id=c.id,actor_user_id=user.id,action='updated',old_status=old_status,new_status=c.status,
        old_response=old_response,new_response=c.response,old_assignee_user_id=c.assigned_to_user_id,
        new_assignee_user_id=c.assigned_to_user_id,resolution_note=c.resolution_note))
    db.commit()
    return {'message':'Complaint updated'}
@app.put('/api/complaints/{complaint_id}/assignment')
def assign_complaint(complaint_id: int,data: ComplaintAssignment,db: Session=Depends(get_db),user: User=Depends(staff)):
    complaint=db.get(Complaint,complaint_id)
    if not complaint: raise HTTPException(404,'Complaint not found')
    resident=db.get(Resident,complaint.resident_id);require_resident_branch(db,user,resident)
    target=db.get(User,data.user_id) if data.user_id is not None else None
    if data.user_id is not None:
        if not target or not is_staff(target): raise HTTPException(422,'Choose an active management user')
        if target.role=='branch_admin' and not db.get(BranchAdmin,(target.id,resident.branch_id)):
            raise HTTPException(403,'Assignee is not authorized for this branch')
    old=complaint.assigned_to_user_id;complaint.assigned_to_user_id=data.user_id;complaint.updated_at=now()
    db.add(ComplaintEvent(complaint_id=complaint.id,actor_user_id=user.id,action='assigned',old_status=complaint.status,
        new_status=complaint.status,old_response=complaint.response,new_response=complaint.response,
        old_assignee_user_id=old,new_assignee_user_id=data.user_id,resolution_note=complaint.resolution_note))
    db.commit()
    return {'message':'Complaint assignment updated'}
def stay_request_data(db,request):
    resident=db.get(Resident,request.resident_id)
    return {'id':request.id,'resident_id':request.resident_id,'resident_name':resident.name,'branch_id':resident.branch_id,
            'request_type':request.request_type,'target_room_id':request.target_room_id,
            'target_room':db.get(Room,request.target_room_id).number if request.target_room_id else None,
            'requested_move_out':request.requested_move_out,'notice_exception_reason':request.notice_exception_reason,
            'note':request.note,'status':request.status,'admin_note':request.admin_note,'created_at':request.created_at}
@app.get('/api/my/stay-requests')
def my_stay_requests(db: Session = Depends(get_db),user: User = Depends(active_user)):
    if is_staff(user): raise HTTPException(403,'Resident access required')
    resident=resident_for(db,user)
    return [stay_request_data(db,r) for r in db.scalars(select(StayRequest).where(StayRequest.resident_id==resident.id).order_by(StayRequest.created_at.desc()))]
@app.post('/api/my/stay-requests',status_code=201)
def create_stay_request(data: StayRequestCreate,db: Session = Depends(get_db),user: User = Depends(active_user)):
    if is_staff(user): raise HTTPException(403,'Resident access required')
    resident=resident_for(db,user)
    if resident.status!='active': raise HTTPException(409,'Only active residents can submit stay requests')
    if db.scalar(select(StayRequest.id).where(StayRequest.resident_id==resident.id,StayRequest.status=='pending')):
        raise HTTPException(409,'Resolve your pending stay request before submitting another')
    if data.request_type=='shift':
        if resident.room_id is None: raise HTTPException(409,'A resident must have a room before requesting a shift')
        if data.target_room_id is None or data.requested_move_out is not None: raise HTTPException(422,'A shift request requires only a target room')
        room=db.scalar(select(Room).where(Room.id==data.target_room_id).with_for_update())
        if not room: raise HTTPException(404,'Target room not found')
        if room.branch_id!=resident.branch_id: raise HTTPException(409,'Shifts must remain within the resident\'s branch')
        if room.id==resident.room_id: raise HTTPException(409,'Resident is already assigned to that room')
        occupied=db.scalar(select(func.count(Resident.id)).where(Resident.room_id==room.id,Resident.status=='active')) or 0
        if occupied>=room.capacity: raise HTTPException(409,'Target room is full')
    else:
        if data.target_room_id is not None or data.requested_move_out is None: raise HTTPException(422,'Extension and vacating requests require a requested move-out date')
        if data.requested_move_out<=local_today(): raise HTTPException(422,'Requested move-out must be in the future')
        if data.request_type=='extension' and resident.planned_move_out and data.requested_move_out<=resident.planned_move_out:
            raise HTTPException(422,'An extension must be later than the current planned move-out')
        branch=db.get(Branch,resident.branch_id)
        if data.request_type=='vacating' and branch.notice_days is not None:
            earliest=local_today()+timedelta(days=branch.notice_days)
            if data.requested_move_out<earliest and not data.notice_exception_reason.strip():
                raise HTTPException(422,f'This branch requires {branch.notice_days} days of notice or an exception reason')
    request=StayRequest(resident_id=resident.id,**data.model_dump())
    db.add(request);db.commit()
    return {'id':request.id,'status':request.status}
@app.get('/api/my/available-rooms')
def my_available_rooms(db: Session = Depends(get_db),user: User = Depends(active_user)):
    if is_staff(user): raise HTTPException(403,'Resident access required')
    resident=resident_for(db,user)
    result=[]
    for room in db.scalars(select(Room).where(Room.branch_id==resident.branch_id,Room.active.is_(True)).order_by(Room.number)):
        occupied=db.scalar(select(func.count(Resident.id)).where(Resident.room_id==room.id,Resident.status=='active')) or 0
        if occupied<room.capacity and room.id!=resident.room_id:
            result.append({'id':room.id,'number':room.number,'capacity':room.capacity,'monthly_fee':str(room.monthly_fee),'available_beds':room.capacity-occupied})
    return result
@app.get('/api/stay-requests')
def stay_requests(db: Session = Depends(get_db),user: User = Depends(staff)):
    query=select(StayRequest).join(Resident,Resident.id==StayRequest.resident_id).order_by(StayRequest.created_at.desc())
    scope=branch_scope(db,user)
    if scope is not None: query=query.where(Resident.branch_id.in_(scope))
    return [stay_request_data(db,r) for r in db.scalars(query)]
@app.put('/api/stay-requests/{request_id}')
def decide_stay_request(request_id: int,data: StayRequestDecision,db: Session = Depends(get_db),user: User = Depends(staff)):
    request=db.scalar(select(StayRequest).where(StayRequest.id==request_id).with_for_update())
    if not request: raise HTTPException(404,'Stay request not found')
    resident=db.scalar(select(Resident).where(Resident.id==request.resident_id).with_for_update())
    require_resident_branch(db,user,resident)
    if request.status!='pending': raise HTTPException(409,'This stay request has already been reviewed')
    if data.status=='approved':
        if resident.status!='active': raise HTTPException(409,'This resident has already vacated')
        if request.request_type=='extension':
            if request.requested_move_out<=local_today() or (resident.planned_move_out and request.requested_move_out<=resident.planned_move_out):
                raise HTTPException(409,'The extension date is no longer valid')
            resident.planned_move_out=request.requested_move_out
        elif request.request_type=='vacating':
            if resident_invoice_balance(db,resident.id)>0:
                raise HTTPException(409,'Settle outstanding invoices before approving vacating')
            resident.planned_move_out=request.requested_move_out
        elif request.request_type=='shift':
            room_ids=sorted({i for i in (resident.room_id,request.target_room_id) if i is not None})
            locked=db.scalars(select(Room).where(Room.id.in_(room_ids)).order_by(Room.id).with_for_update()).all()
            target=next((room for room in locked if room.id==request.target_room_id),None)
            if not target or not target.active or target.branch_id!=resident.branch_id: raise HTTPException(409,'The requested room is no longer valid')
            occupied=db.scalar(select(func.count(Resident.id)).where(Resident.room_id==target.id,Resident.status=='active')) or 0
            if occupied>=target.capacity: raise HTTPException(409,'Target room is now full')
            previous=resident.room_id;resident.room_id=target.id
            db.add(AllocationEvent(resident_id=resident.id,from_room_id=previous,to_room_id=target.id,actor_user_id=user.id,
                                   reason=f'Approved resident shift request #{request.id}. {data.note}'.strip()))
    request.status,request.admin_note,request.reviewed_by,request.reviewed_at=data.status,data.note,user.id,now()
    db.commit()
    return {'status':request.status,'resident_status':resident.status,'room_id':resident.room_id,'planned_move_out':resident.planned_move_out}
@app.post('/api/stays/process-moveouts')
def process_moveouts(db: Session = Depends(get_db),user: User = Depends(staff)):
    count=process_due_moveouts(db,branch_scope(db,user));db.commit()
    return {'vacated':count}
@app.get('/api/dashboard')
def dashboard(db: Session = Depends(get_db),user: User = Depends(active_user)):
    data=invoices_data(db,user)
    current=local_today().replace(day=1)
    current_invoices=[i for i in data if i['month']==current]
    rooms=[r for r in rooms_data(db,user) if r['active']] if is_staff(user) else []
    complaint_query=select(func.count(Complaint.id)).where(Complaint.status!='resolved')
    if is_staff(user):
        scope=branch_scope(db,user)
        if scope is not None:
            complaint_query=complaint_query.join(Resident,Resident.id==Complaint.resident_id).where(Resident.branch_id.in_(scope))
            resident_count=db.scalar(select(func.count(Resident.id)).where(Resident.branch_id.in_(scope)))
        else: resident_count=db.scalar(select(func.count(Resident.id)))
    else:
        complaint_query=complaint_query.where(Complaint.resident_id==resident_for(db,user).id)
        resident_count=1
    from .gap_features import operational_kpis
    return {**operational_kpis(db,user), 'residents':resident_count,
            'beds':sum(r['capacity'] for r in rooms),'occupied':sum(r['occupied'] for r in rooms),
            'collected':str(sum((Decimal(i['paid']) for i in current_invoices),Decimal(0))),
            'outstanding':str(sum((Decimal(i['balance']) for i in data),Decimal(0))),
            'open_complaints':db.scalar(complaint_query),'month':current}

def authorized_financial_report(db,user,from_date,to_date,as_of,branch_id,room_number,resident_id,payment_method,invoice_status=None):
    as_of=as_of or local_today()
    scope=branch_scope(db,user)
    if branch_id is not None:
        require_branch(db,user,branch_id)
        if not db.get(Branch,branch_id): raise HTTPException(404,'Branch not found')
    if resident_id is not None:
        resident=db.get(Resident,resident_id)
        if not resident: raise HTTPException(404,'Resident not found')
        require_resident_branch(db,user,resident)
        if branch_id is not None and resident.branch_id!=branch_id:
            raise HTTPException(422,'Resident is outside the selected branch')
    if scope is not None and branch_id is None:
        # Aggregation itself is constrained to the actor's allowed branch IDs.
        if not scope:
            return financial_report(db,user,from_date,to_date,as_of,branch_id=0,
                                    room_number=room_number,resident_id=resident_id,
                                    payment_method=payment_method,invoice_status=invoice_status)
        reports=[financial_report(db,user,from_date,to_date,as_of,branch_id=bid,
                    room_number=room_number,resident_id=resident_id,
                    payment_method=payment_method,invoice_status=invoice_status) for bid in scope]
        return merge_financial_reports(reports,from_date,to_date,as_of)
    return financial_report(db,user,from_date,to_date,as_of,branch_id,
                            room_number,resident_id,payment_method,invoice_status)

def merge_financial_reports(reports,from_date,to_date,as_of):
    """Merge already-authorized per-branch aggregates without cross-scope SQL."""
    from decimal import Decimal
    summary={key:Decimal('0') for key in ('billed','collected','collected_today','cash_collected','outstanding','overdue')}
    summary.update({'overdue_invoice_count':0,'overdue_resident_count':0,
                    'average_settlement_delay_days':None,'settled_invoice_count':0,
                    'on_time_settlement_count':0,'on_time_rate_percent':None})
    aging={key:Decimal('0') for key in ('not_due','1_7_days','8_30_days','31_60_days','61_plus_days')}
    methods={}; trend={}; daily={}; weekly={}; staff_totals={}; residents=[]; rooms=[]; branches=[]; overdue_invoices=[]
    overdue_resident_ids=set()
    for report in reports:
        for key in ('billed','collected','collected_today','cash_collected','outstanding','overdue'):
            summary[key]+=Decimal(report['summary'][key])
        summary['overdue_invoice_count']+=report['summary']['overdue_invoice_count']
        summary['settled_invoice_count']+=report['summary']['settled_invoice_count']
        summary['on_time_settlement_count']+=report['summary']['on_time_settlement_count']
        for key,value in report['aging'].items(): aging[key]+=Decimal(value)
        for row in report['collections_by_method']: methods[row['method']]=methods.get(row['method'],Decimal('0'))+Decimal(row['amount'])
        for row in report['collections_by_month']: trend[row['month']]=trend.get(row['month'],Decimal('0'))+Decimal(row['amount'])
        for row in report.get('collections_by_day',[]): daily[row['day']]=daily.get(row['day'],Decimal('0'))+Decimal(row['amount'])
        for row in report.get('collections_by_week',[]): weekly[row['week']]=weekly.get(row['week'],Decimal('0'))+Decimal(row['amount'])
        for row in report['cash_by_staff']:
            staff_totals.setdefault(row['staff_user_id'],{'staff_email':row.get('staff_email'),'amount':Decimal('0')})
            staff_totals[row['staff_user_id']]['amount']+=Decimal(row['amount'])
        residents.extend(report['residents']); rooms.extend(report['rooms']); branches.extend(report['collections_by_branch']); overdue_invoices.extend(report['overdue_invoices'])
        for row in report['residents']:
            if Decimal(row['overdue'])>0: overdue_resident_ids.add(row['resident_id'])
    summary['overdue_resident_count']=len(overdue_resident_ids)
    settled=summary['settled_invoice_count']
    delay_pairs=[(r['average_settlement_delay_days'],r['fully_settled_invoice_count']) for r in residents if r['average_settlement_delay_days'] is not None]
    delay_count=sum(n for _,n in delay_pairs)
    summary['average_settlement_delay_days']=round(sum(v*n for v,n in delay_pairs)/delay_count,2) if delay_count else None
    summary['on_time_rate_percent']=round(summary['on_time_settlement_count']*100/settled,2) if settled else None
    summary['billed']=str(summary['billed']); summary['collected']=str(summary['collected']); summary['collected_today']=str(summary['collected_today']); summary['cash_collected']=str(summary['cash_collected']); summary['outstanding']=str(summary['outstanding']); summary['overdue']=str(summary['overdue'])
    return {'from_date':from_date.isoformat(),'to_date':to_date.isoformat(),'as_of':as_of.isoformat(),
        'definitions':reports[0]['definitions'] if reports else {},'summary':summary,
        'aging':{k:str(v) for k,v in aging.items()},
        'collections_by_month':[{'month':k,'amount':str(v)} for k,v in sorted(trend.items())],
        'collections_by_day':[{'day':k,'amount':str(v)} for k,v in sorted(daily.items())],
        'collections_by_week':[{'week':k,'amount':str(v)} for k,v in sorted(weekly.items())],
        'collections_by_method':[{'method':k,'amount':str(v)} for k,v in sorted(methods.items())],
        'collections_by_branch':branches,
        'cash_by_staff':[{'staff_user_id':k,'staff_email':v['staff_email'],'amount':str(v['amount'])} for k,v in sorted(staff_totals.items())],
        'residents':residents,'rooms':rooms,
        'overdue_invoices':sorted(overdue_invoices,key=lambda x:(-x['current_days_past_due'],-Decimal(x['balance'])))}

@app.get('/api/analytics/financial')
def financial_analytics(from_date: date, to_date: date, as_of: date | None = None,
        branch_id: int | None = None, room_number: str | None = None,
        resident_id: int | None = None, payment_method: str | None = None, invoice_status: str | None = None,
        db: Session = Depends(get_db), user: User = Depends(staff)):
    return authorized_financial_report(db,user,from_date,to_date,as_of,branch_id,
                                       room_number,resident_id,payment_method,invoice_status)

def csv_safe(value):
    text='' if value is None else str(value)
    return "'"+text if text.lstrip().startswith(('=','+','-','@')) or text.startswith(('\t','\r','\n')) else text

@app.get('/api/analytics/financial.csv')
def financial_analytics_csv(from_date: date, to_date: date, as_of: date | None = None,
        branch_id: int | None = None, room_number: str | None = None,
        resident_id: int | None = None, payment_method: str | None = None, invoice_status: str | None = None,
        db: Session = Depends(get_db), user: User = Depends(staff)):
    report=authorized_financial_report(db,user,from_date,to_date,as_of,branch_id,
                                       room_number,resident_id,payment_method,invoice_status)
    output=StringIO(); writer=csv.writer(output)
    writer.writerow(['Report','Resident Payment Performance','From',report['from_date'],'To',report['to_date'],'As of',report['as_of']])
    writer.writerow(['Resident ID','Resident','Branch ID','Current Room','Billed','Paid','Outstanding','Overdue','Overdue invoices','Average settlement delay days','Settled invoices','On-time settlement rate %'])
    for row in report['residents']:
        writer.writerow([row['resident_id'],csv_safe(row['resident_name']),row['branch_id'],csv_safe(row['current_room_number']),row['billed'],row['paid'],row['outstanding'],row['overdue'],row['overdue_invoice_count'],row['average_settlement_delay_days'],row['fully_settled_invoice_count'],row['on_time_rate_percent']])
    return Response(output.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="cityhive-financial-report.csv"'})

# Release operations are additive: historical API paths and identifiers remain valid.
def publication_issues(db,branch):
    issues=[]
    if not branch.active: issues.append('Activate this branch')
    if not branch.address.strip(): issues.append('Add the verified address or locality')
    if not branch.description.strip() or any(x in branch.description.casefold() for x in ['configure this location','branch settings']):
        issues.append('Write a public description')
    if not db.scalar(select(Room.id).where(Room.branch_id==branch.id,Room.active.is_(True)).limit(1)):
        issues.append('Add a room with sharing capacity and monthly charges')
    return issues

@app.get('/api/build')
def build_information():
    return {'service':'cityhive-api','version':app.version,'release':settings.release_id}

@app.get('/api/deployment-status')
def deployment_status(db: Session=Depends(get_db),user: User=Depends(admin)):
    job=db.get(JobState,'reminders-and-moveouts')
    cfg=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))
    revision=db.scalar(text('SELECT version_num FROM alembic_version')) if inspect(db.bind).has_table('alembic_version') else 'unversioned'
    return {'release':settings.release_id,'environment':settings.app_environment,
        'database_engine':db.bind.dialect.name,'schema_revision':revision,'expected_revision':ScriptDirectory.from_config(cfg).get_current_head(),
        'whatsapp':whatsapp.status(),'smtp':{'configured':settings.smtp_host not in {'','localhost'},'security':settings.smtp_security},
        'scheduler':{'mode':'api_process' if settings.jobs_enabled else 'external_worker_required','status':job.status if job else 'never_run',
                     'last_started_at':job.last_started_at if job else None,'last_succeeded_at':job.last_succeeded_at if job else None},
        'percentage_discounts_enabled':settings.percentage_discounts_enabled,'sms_configured':sms.configured(),
        'identity_documents_configured':bool(settings.identity_document_key),'automatic_billing_enabled':settings.automatic_billing_enabled}

@app.post('/api/internal/jobs/run')
def scheduled_job(request: Request):
    supplied=request.headers.get('X-Cityhive-Job-Token','')
    if not settings.job_runner_token or not hmac.compare_digest(supplied,settings.job_runner_token):
        raise HTTPException(401,'Scheduler authentication required')
    from .worker import run_once
    return run_once()

@app.get('/api/payments/{payment_id}/receipt.pdf')
def receipt_download(payment_id: int,db: Session=Depends(get_db),user: User=Depends(active_user)):
    payment=db.get(Payment,payment_id)
    if not payment: raise HTTPException(404,'Receipt not found')
    invoice=db.get(Invoice,payment.invoice_id)
    if is_staff(user): require_branch(db,user,invoice.branch_id)
    elif invoice.resident_id!=resident_for(db,user).id: raise HTTPException(403,'Receipt belongs to another resident')
    return Response(receipt_pdf(db,payment),media_type='application/pdf',
                    headers={'Content-Disposition':f'attachment; filename="SW-{payment.id:06d}.pdf"'})

@app.get('/api/my/notifications')
def my_notifications(db: Session=Depends(get_db),user: User=Depends(active_user)):
    resident_for(db,user)
    records=db.scalars(select(Outbox).where(Outbox.user_id==user.id).order_by(Outbox.id.desc()).limit(100))
    return [{'id':item.id,'subject':item.subject,'body':item.body,'channel':item.channel,
             'status':'cancelled' if item.cancelled else item.delivery_status,'sent_at':item.sent_at} for item in records]

@app.get('/api/admissions/{admission_id}/history')
def admission_history(admission_id: int,db: Session=Depends(get_db),user: User=Depends(active_user)):
    admission=db.get(Admission,admission_id)
    if not admission: raise HTTPException(404,'Admission not found')
    if is_staff(user): require_branch(db,user,admission.branch_id)
    elif admission.resident_id!=resident_for(db,user).id: raise HTTPException(403,'Admission belongs to another resident')
    return [{'old_status':item.old_status,'new_status':item.new_status,'note':item.note if is_staff(user) else '',
             'created_at':item.created_at} for item in db.scalars(select(AdmissionEvent).where(AdmissionEvent.admission_id==admission_id).order_by(AdmissionEvent.id))]

def discount_data(item):
    return {'id':item.id,'resident_id':item.resident_id,'percentage':str(item.percentage),'charge_scope':item.charge_scope,
        'max_amount':str(item.max_amount) if item.max_amount is not None else None,'effective_from':item.effective_from,
        'effective_until':item.effective_until,'reason':item.reason,'approved_by':item.approved_by,'created_at':item.created_at,
        'revoked_at':item.revoked_at}

@app.get('/api/residents/{resident_id}/discounts')
def discounts(resident_id: int,db: Session=Depends(get_db),user: User=Depends(active_user)):
    resident=db.get(Resident,resident_id)
    if not resident: raise HTTPException(404,'Resident not found')
    if is_staff(user): require_resident_branch(db,user,resident)
    elif resident.user_id!=user.id: raise HTTPException(403,'Discount belongs to another resident')
    return {'enabled':settings.percentage_discounts_enabled,'rules':[discount_data(item) for item in db.scalars(
        select(ResidentDiscount).where(ResidentDiscount.resident_id==resident.id).order_by(ResidentDiscount.id.desc()))]}

@app.post('/api/residents/{resident_id}/discounts',status_code=201)
def approve_discount(resident_id: int,data: DiscountCreate,db: Session=Depends(get_db),user: User=Depends(staff)):
    if not settings.percentage_discounts_enabled: raise HTTPException(409,'Percentage discounts have not been enabled by management')
    resident=db.scalar(select(Resident).where(Resident.id==resident_id).with_for_update())
    if not resident: raise HTTPException(404,'Resident not found')
    require_resident_branch(db,user,resident)
    if resident.discount: raise HTTPException(409,'Remove the fixed allocation discount before approving a percentage discount')
    if data.effective_from<local_today().replace(day=1): raise HTTPException(422,'Approval cannot begin before the current billing month')
    if db.scalar(select(Invoice.id).where(Invoice.resident_id==resident_id,Invoice.month>=data.effective_from,Invoice.month<=data.effective_until).limit(1)):
        raise HTTPException(409,'Select unbilled months; issued invoices cannot be changed')
    if db.scalar(select(ResidentDiscount.id).where(ResidentDiscount.resident_id==resident_id,ResidentDiscount.revoked_at.is_(None),
        ResidentDiscount.effective_from<=data.effective_until,ResidentDiscount.effective_until>=data.effective_from).limit(1)):
        raise HTTPException(409,'An approved discount already covers these months')
    item=ResidentDiscount(resident_id=resident.id,approved_by=user.id,**data.model_dump());db.add(item);db.commit()
    return discount_data(item)

@app.put('/api/discounts/{discount_id}/revoke')
def revoke_discount(discount_id: int,db: Session=Depends(get_db),user: User=Depends(staff)):
    item=db.get(ResidentDiscount,discount_id)
    if not item: raise HTTPException(404,'Discount not found')
    resident=db.scalar(select(Resident).where(Resident.id==item.resident_id).with_for_update())
    require_resident_branch(db,user,resident)
    if item.revoked_at: raise HTTPException(409,'Discount is already revoked')
    item.revoked_at=now();item.revoked_by=user.id;db.commit()
    return {'message':'Future application stopped. Issued invoice snapshots remain unchanged.'}

@app.get('/api/notifications/whatsapp/webhook')
def verify_whatsapp_webhook(request: Request):
    query=request.query_params
    if not settings.whatsapp_verify_token or query.get('hub.mode')!='subscribe' or not hmac.compare_digest(query.get('hub.verify_token',''),settings.whatsapp_verify_token):
        raise HTTPException(403,'Webhook verification failed')
    return PlainTextResponse(query.get('hub.challenge',''))

@app.post('/api/notifications/whatsapp/webhook')
async def whatsapp_delivery_webhook(request: Request,db: Session=Depends(get_db)):
    chunks=[];size=0
    async for chunk in request.stream():
        size+=len(chunk)
        if size>262144: raise HTTPException(413,'Payload too large')
        chunks.append(chunk)
    body=b''.join(chunks)
    signature=request.headers.get('X-Hub-Signature-256','')
    expected='sha256='+hmac.new(settings.whatsapp_app_secret.encode(),body,hashlib.sha256).hexdigest()
    if not settings.whatsapp_app_secret or not hmac.compare_digest(signature,expected): raise HTTPException(403,'Invalid webhook signature')
    import json
    try:
        payload=json.loads(body)
        updates=[status for entry in payload.get('entry',[]) for change in entry.get('changes',[]) for status in change.get('value',{}).get('statuses',[])]
    except (ValueError,AttributeError,TypeError): raise HTTPException(400,'Invalid webhook payload')
    rank={'queued':0,'retrying':0,'submitted':1,'sent':2,'failed':2.5,'delivered':3,'read':4}
    for update_ in updates:
        if not isinstance(update_,dict): continue
        status=update_.get('status')
        if not isinstance(update_.get('id'),str) or not update_['id']: continue
        if status not in {'sent','delivered','read','failed'}: continue
        record=db.scalar(select(Outbox).where(Outbox.channel=='whatsapp',Outbox.provider_message_id==update_.get('id')).with_for_update())
        if record and rank.get(status,0)>rank.get(record.delivery_status,0):
            record.delivery_status=status
            if status=='failed': record.last_error='Provider reported delivery failure; review the provider console'
    db.commit()
    return {'status':'accepted'}

from .gap_features import router as gap_router
app.include_router(gap_router)
