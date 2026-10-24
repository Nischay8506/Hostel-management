"""Admission tracking, lifecycle controls, protected documents and operational KPIs."""
from datetime import timedelta
from io import BytesIO
from decimal import Decimal
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .db import get_db
from .config import settings
from .models import (Admission, AdmissionEvent, Room, Resident, User, Invoice, Payment,
    Outbox, StayRequest, FinalSettlement, LifecycleEvent, IdentityDocument, IdentityReviewEvent,
    AllocationEvent, now)
from .schemas import AdmissionLookup, LifecycleChange, FAQEntry
from .security import active_user, staff, admin, is_staff
from .services import local_today
from .rate_limits import consume
from . import whatsapp

router = APIRouter()

@router.put('/api/branches/{branch_id}/faqs')
def branch_faqs(branch_id: int,data: list[FAQEntry],db: Session=Depends(get_db),user=Depends(admin)):
    from .models import Branch
    branch=db.get(Branch,branch_id)
    if not branch: raise HTTPException(404,'Branch not found')
    if len(data)>20: raise HTTPException(422,'Use at most 20 questions per branch')
    branch.faqs=[item.model_dump() for item in data];db.commit()
    return {'faqs':branch.faqs}

def core():
    from . import main
    return main

def queue_admission_update(db, admission):
    if not admission.whatsapp_updates: return
    # Configuration may be completed later; pending messages use normal retries.
    key=f'admission-wa:{admission.id}:{admission.status}'
    if db.scalar(select(Outbox.id).where(Outbox.dedupe_key==key)): return
    user_id=db.get(Resident,admission.resident_id).user_id if admission.resident_id else None
    db.add(Outbox(user_id=user_id,branch_id=admission.branch_id,dedupe_key=key,
        recipient=admission.phone,subject='Cityhive admission update',
        body=f'Admission #{admission.id}: {admission.status}',channel='whatsapp'))

@router.post('/api/public/admissions/status')
def admission_status(data: AdmissionLookup, request: Request, db: Session=Depends(get_db)):
    consume(db,'admission-lookup',request.client.host if request.client else 'unknown',15,60)
    item=db.scalar(select(Admission).where(Admission.submission_key==data.submission_key,
                                           Admission.email==str(data.email).lower()))
    if not item: raise HTTPException(404,'No enquiry matches those tracking details')
    # The high-entropy submission key is a private capability. Internal notes,
    # identity fields and staff identities are never returned to this endpoint.
    history=db.scalars(select(AdmissionEvent).where(AdmissionEvent.admission_id==item.id).order_by(AdmissionEvent.id))
    return {'id':item.id,'status':item.status,'created_at':item.created_at,
            'history':[{'status':e.new_status,'at':e.created_at} for e in history]}

def audit(db, entity, item, user, action, reason):
    db.add(LifecycleEvent(entity=entity,entity_id=item.id,branch_id=item.branch_id,
                         actor_user_id=user.id,action=action,reason=reason.strip()))

@router.put('/api/rooms/{room_id}/status')
def room_status(room_id: int,data: LifecycleChange,db: Session=Depends(get_db),user=Depends(staff)):
    m=core()
    room=db.scalar(select(Room).where(Room.id==room_id).with_for_update())
    if not room: raise HTTPException(404,'Room not found')
    m.require_branch(db,user,room.branch_id)
    if not data.active and db.scalar(select(Resident.id).where(Resident.room_id==room.id).limit(1)):
        raise HTTPException(409,'Move all allocated residents before decommissioning this room')
    room.active=data.active
    audit(db,'room',room,user,'activate' if data.active else 'decommission',data.reason)
    db.commit()
    return {'id':room.id,'active':room.active}

@router.delete('/api/rooms/{room_id}')
def decommission_room(room_id: int,data: LifecycleChange,db: Session=Depends(get_db),user=Depends(staff)):
    return room_status(room_id,data.model_copy(update={'active':False}),db,user)

@router.put('/api/residents/{resident_id}/status')
def resident_status(resident_id: int,data: LifecycleChange,db: Session=Depends(get_db),user=Depends(staff)):
    m=core()
    resident=db.scalar(select(Resident).where(Resident.id==resident_id).with_for_update())
    if not resident: raise HTTPException(404,'Resident not found')
    m.require_resident_branch(db,user,resident)
    if not data.active:
        if m.resident_invoice_balance(db,resident.id)>0 or any(v>0 for v in m.financial_balances(db,resident.id).values()):
            raise HTTPException(409,'Settle invoice, deposit and advance balances before deactivation')
        if db.scalar(select(FinalSettlement.id).where(FinalSettlement.resident_id==resident.id,
                FinalSettlement.status.in_(['pending','approved','partially_refunded'])).limit(1)):
            raise HTTPException(409,'Complete the open settlement before deactivation')
        if resident.room_id:
            db.add(AllocationEvent(resident_id=resident.id,from_room_id=resident.room_id,to_room_id=None,
                actor_user_id=user.id,reason='Administrative deactivation: '+data.reason))
        resident.room_id=None;resident.planned_move_out=None;resident.status='inactive'
        for stay in db.scalars(select(StayRequest).where(StayRequest.resident_id==resident.id,StayRequest.status=='pending')):
            stay.status='rejected';stay.admin_note='Resident deactivated: '+data.reason
            stay.reviewed_by=user.id;stay.reviewed_at=now()
    else:
        if resident.status!='inactive': raise HTTPException(409,'Only an inactive resident can be reactivated')
        resident.status='active'
    account=db.get(User,resident.user_id)
    account.active=data.active;account.session_version+=1
    from .models import OtpChallenge
    for challenge in db.scalars(select(OtpChallenge).where(OtpChallenge.user_id==account.id,OtpChallenge.consumed_at.is_(None))):
        challenge.consumed_at=now()
    audit(db,'resident',resident,user,'activate' if data.active else 'deactivate',data.reason)
    db.commit()
    return {'id':resident.id,'status':resident.status}

@router.get('/api/lifecycle-history')
def lifecycle_history(db: Session=Depends(get_db),user=Depends(staff)):
    scope=core().branch_scope(db,user)
    query=select(LifecycleEvent).order_by(LifecycleEvent.id.desc()).limit(200)
    if scope is not None: query=query.where(LifecycleEvent.branch_id.in_(scope))
    return [{'entity':e.entity,'entity_id':e.entity_id,'action':e.action,'reason':e.reason,
             'actor_user_id':e.actor_user_id,'at':e.created_at} for e in db.scalars(query)]

def document_resident(db,user,resident_id):
    resident=db.scalar(select(Resident).where(Resident.id==resident_id).with_for_update())
    if not resident: raise HTTPException(404,'Resident not found')
    if is_staff(user): core().require_resident_branch(db,user,resident)
    elif resident.user_id!=user.id: raise HTTPException(403,'Document belongs to another resident')
    return resident

def document_cipher():
    if not settings.identity_document_key:
        raise HTTPException(503,'Private document storage is not configured. Contact management.')
    try: return Fernet(settings.identity_document_key.encode())
    except ValueError: raise HTTPException(503,'Private document storage is unavailable') from None

def validate_document(content,content_type):
    try:
        if content_type in {'image/jpeg','image/png'}:
            from PIL import Image
            with Image.open(BytesIO(content)) as img:
                if img.format!=({'image/jpeg':'JPEG','image/png':'PNG'}[content_type]) or img.width*img.height>20_000_000:
                    raise ValueError()
                img.verify()
        elif content_type=='application/pdf':
            from pypdf import PdfReader
            reader=PdfReader(BytesIO(content),strict=True)
            if reader.is_encrypted or not 1<=len(reader.pages)<=10: raise ValueError()
            root=reader.trailer['/Root']
            if any(k in root for k in ('/OpenAction','/AA','/AcroForm')): raise ValueError()
            if any(k in root.get('/Names',{}) for k in ('/JavaScript','/EmbeddedFiles')): raise ValueError()
            if any(page.get('/AA') or page.get('/Annots') for page in reader.pages): raise ValueError()
        else: raise ValueError()
    except Exception:
        raise HTTPException(422,'Upload a valid JPG, PNG or simple PDF (up to 10 pages, no interactive content)') from None

@router.get('/api/residents/{resident_id}/identity-document')
def document_info(resident_id: int,db: Session=Depends(get_db),user=Depends(active_user)):
    document_resident(db,user,resident_id)
    doc=db.scalar(select(IdentityDocument).where(IdentityDocument.resident_id==resident_id))
    return {'configured':bool(settings.identity_document_key),'present':bool(doc),
            'content_type':doc.content_type if doc else None,'uploaded_at':doc.uploaded_at if doc else None}

@router.put('/api/residents/{resident_id}/identity-document')
async def upload_document(resident_id: int,request: Request,db: Session=Depends(get_db),user=Depends(active_user)):
    resident=document_resident(db,user,resident_id);cipher=document_cipher()
    consume(db,'document-upload',user.id,10,3600)
    content=bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content)>5*1024*1024: raise HTTPException(413,'Document must be 5 MB or smaller')
    content_type=request.headers.get('content-type','').split(';')[0]
    validate_document(bytes(content),content_type)
    doc=db.scalar(select(IdentityDocument).where(IdentityDocument.resident_id==resident_id))
    if not doc: doc=IdentityDocument(resident_id=resident_id);db.add(doc)
    doc.content_type=content_type;doc.encrypted_content=cipher.encrypt(bytes(content))
    doc.uploaded_by=user.id;doc.uploaded_at=now()
    old=resident.id_status;resident.id_status='pending';resident.id_reviewed_at=None;resident.id_reviewed_by=None
    db.add(IdentityReviewEvent(resident_id=resident.id,reviewer_id=user.id,old_status=old,new_status='pending',note='Identity document uploaded; manual review required'))
    audit(db,'resident',resident,user,'document_upload','Identity document uploaded')
    db.commit()
    return {'message':'Document stored privately and submitted for manual review'}

@router.get('/api/residents/{resident_id}/identity-document/download')
def download_document(resident_id: int,db: Session=Depends(get_db),user=Depends(active_user)):
    resident=document_resident(db,user,resident_id)
    doc=db.scalar(select(IdentityDocument).where(IdentityDocument.resident_id==resident_id))
    if not doc: raise HTTPException(404,'No identity document is stored')
    try: content=document_cipher().decrypt(doc.encrypted_content)
    except InvalidToken: raise HTTPException(503,'Document storage key is unavailable') from None
    audit(db,'resident',resident,user,'document_download','Identity document accessed');db.commit()
    ext={'image/jpeg':'jpg','image/png':'png','application/pdf':'pdf'}[doc.content_type]
    return Response(content,media_type=doc.content_type,headers={
        'Content-Disposition':f'attachment; filename="identity-document.{ext}"','Cache-Control':'no-store',
        'X-Content-Type-Options':'nosniff','Content-Security-Policy':"sandbox; default-src 'none'"})

@router.delete('/api/residents/{resident_id}/identity-document')
def delete_document(resident_id: int,db: Session=Depends(get_db),user=Depends(active_user)):
    resident=document_resident(db,user,resident_id)
    doc=db.scalar(select(IdentityDocument).where(IdentityDocument.resident_id==resident_id))
    if doc: db.delete(doc)
    audit(db,'resident',resident,user,'document_remove','Stored identity document removed');db.commit()
    return {'message':'Stored document removed; review history retained'}

@router.get('/api/settlements/{settlement_id}/pdf')
def settlement_pdf(settlement_id: int,db: Session=Depends(get_db),user=Depends(active_user)):
    item=db.get(FinalSettlement,settlement_id)
    if not item: raise HTTPException(404,'Settlement not found')
    document_resident(db,user,item.resident_id)
    data=core().settlement_data(db,item)
    from .documents import financial_document
    content=financial_document('Final settlement',f'CH-SET-{item.id:06d}',
        [('Resident',data['resident_name']),('Resident ID',data['resident_code']),('Status',item.status),
         ('Prepared',str(item.created_at)),('Note',item.note),('Decision',item.decision_note)],
        [('Deposit balance',item.deposit_balance_snapshot),('Advance balance',item.advance_balance_snapshot),
         ('Invoice balance at preparation',item.invoice_balance_snapshot),('Proposed refund',item.proposed_refund),
         ('Actual refund recorded',Decimal(data['refunded']))])
    return Response(content,media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="CH-SET-{item.id:06d}.pdf"','Cache-Control':'no-store'})

def operational_kpis(db,user):
    if not is_staff(user): return {}
    m=core();scope=m.branch_scope(db,user);today=local_today()
    def count(model,*conditions):
        query=select(func.count(model.id)).where(*conditions)
        if scope is not None:
            if model is StayRequest: query=query.join(Resident,Resident.id==StayRequest.resident_id).where(Resident.branch_id.in_(scope))
            else: query=query.where(model.branch_id.in_(scope))
        return db.scalar(query) or 0
    from .analytics import datetime_start, datetime_end
    cash=select(func.coalesce(func.sum(Payment.amount),0)).join(Invoice,Invoice.id==Payment.invoice_id).where(
        Payment.method=='cash',Payment.reversed_at.is_(None),Payment.paid_at>=datetime_start(today.replace(day=1)),Payment.paid_at<datetime_end(today))
    if scope is not None: cash=cash.where(Invoice.branch_id.in_(scope))
    return {'pending_admissions':count(Admission,Admission.status.in_(['pending','needs_info'])),
        'pending_extensions':count(StayRequest,StayRequest.request_type=='extension',StayRequest.status=='pending'),
        'upcoming_moveouts':count(Resident,Resident.status=='active',Resident.planned_move_out>=today,Resident.planned_move_out<=today+timedelta(days=30)),
        'overdue_invoice_count':sum(i['status']=='overdue' for i in m.invoices_data(db,user)),
        'reminder_failures':count(Outbox,Outbox.dedupe_key.like('reminder:%'),Outbox.cancelled.is_(False),Outbox.sent_at.is_(None),Outbox.attempts>=5),
        'cash_collected':str(db.scalar(cash) or 0)}
