from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta
from email.message import EmailMessage
from io import BytesIO
import smtplib
import ssl
import textwrap
from sqlalchemy import select, func
from .models import Invoice, Payment, Resident, User, Branch, Outbox, Admission, now
from .config import settings
from .db import SessionLocal
from . import whatsapp

def invoice_pdf(invoice,resident,branch,paid,balance):
    from .documents import financial_document
    return financial_document('Invoice',invoice.invoice_number,
        [('Issued',invoice.issued_on),('Due',invoice.due_on),('Branch',branch.name),('Address',branch.address),
         ('Resident',resident.name),('Resident ID',resident.resident_code),('Room',invoice.room_number),('Billing period',invoice.month.strftime('%B %Y'))],
        [('Accommodation',invoice.base_fee),*(([(invoice.additional_charge_label,invoice.additional_charge_amount)]) if invoice.additional_charge_amount else []),
         ('Discount',-invoice.discount),('Total',invoice.amount),('Paid',paid),('Balance',balance)])

def document_pdf(lines):
    lines=[part for line in lines for part in (textwrap.wrap(str(line),width=83,replace_whitespace=False) or [''])]
    pages=[lines[offset:offset+39] for offset in range(0,len(lines),39)] or [[]]
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'',b'<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>']
    page_ids=[]
    for page in pages:
        page_id=len(objects)+1;page_ids.append(page_id)
        commands=['BT','/F1 10 Tf','50 790 Td']
        for index,line in enumerate(page):
            if index: commands.append('0 -18 Td')
            commands.append(f'({pdf_escape(line)}) Tj')
        commands.append('ET')
        stream='\n'.join(commands).encode('ascii')
        objects.extend([
            f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {page_id+1} 0 R >>'.encode(),
            b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream'])
    objects[1]=('<< /Type /Pages /Kids ['+' '.join(f'{p} 0 R' for p in page_ids)+f'] /Count {len(page_ids)} >>').encode()
    output=BytesIO();output.write(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n');offsets=[0]
    for i,obj in enumerate(objects,1):
        offsets.append(output.tell());output.write(f'{i} 0 obj\n'.encode());output.write(obj);output.write(b'\nendobj\n')
    xref=output.tell();output.write(f'xref\n0 {len(objects)+1}\n'.encode());output.write(b'0000000000 65535 f \n')
    for off in offsets[1:]: output.write(f'{off:010d} 00000 n \n'.encode())
    output.write(f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return output.getvalue()

def pdf_escape(value):
    ascii_value=str(value).encode('ascii','replace').decode('ascii')
    return ascii_value.replace('\\','\\\\').replace('(','\\(').replace(')','\\)')

def local_today(): return datetime.now(ZoneInfo('Asia/Kolkata')).date()
def paid_total(db, invoice_id):
    return db.scalar(select(func.coalesce(func.sum(Payment.amount),0)).where(Payment.invoice_id==invoice_id,Payment.reversed_at.is_(None))) or Decimal('0')
def receipt_text(db, payment):
    invoice = db.get(Invoice,payment.invoice_id)
    resident = db.get(Resident,invoice.resident_id)
    return (f"CITYHIVE LUXURY PG'S AND CO-SPACE - PAYMENT RECEIPT\nReceipt: SW-{payment.id:06d}\nResident: {resident.name}\n"
            f'Room: {invoice.room_number}\nFee month: {invoice.month:%B %Y}\n'
            f'Monthly fee: INR {invoice.base_fee:.2f}\nDiscount: INR {invoice.discount:.2f}\n'
            +(f'{invoice.additional_charge_label or "Additional configured charge"}: INR {invoice.additional_charge_amount:.2f}\n' if invoice.additional_charge_amount else '')+
            f'Invoice total: INR {invoice.amount:.2f}\n'
            f'Payment: INR {payment.amount:.2f}\n'
            f'Method: {payment.method}\nReference: {payment.reference or "—"}\n'
            f'Payer: {payment.payer_name or "Not specified"}\n'
            f'Recorded at (UTC): {payment.paid_at.isoformat()}\n'
            f'Balance after this payment: INR {invoice.amount-db.scalar(select(func.coalesce(func.sum(Payment.amount),0)).where(Payment.invoice_id==invoice.id,((Payment.reversed_at.is_(None))|(Payment.id==payment.id)),((Payment.paid_at<payment.paid_at)|((Payment.paid_at==payment.paid_at)&(Payment.id<=payment.id))))) :.2f}\n'
            +(f'PAYMENT REVERSED: {payment.reversal_reason}\n' if payment.reversed_at else '')+
            'This receipt records a payment confirmed by hostel management.\n')

def queue_reminders(db, branch_ids=None):
    today = local_today()
    count = 0
    # At most once per invoice/channel/local day, including the configured upcoming window.
    query=select(Invoice).where(Invoice.due_on<=today+timedelta(days=settings.upcoming_reminder_days)).with_for_update()
    if branch_ids is not None: query=query.where(Invoice.branch_id.in_(branch_ids))
    for invoice in db.scalars(query):
        balance = invoice.amount-paid_total(db,invoice.id)
        key = f'reminder:{invoice.id}:{today.isoformat()}'
        if balance<=0 or db.scalar(select(Outbox.id).where(Outbox.dedupe_key==key)): continue
        resident = db.get(Resident,invoice.resident_id)
        user = db.get(User,resident.user_id)
        body=f'Hi {resident.name},\nYour outstanding fee is INR {balance:.2f} for {invoice.month:%B %Y}. Due date: {invoice.due_on}. Please contact management to pay.\n'
        stage='Upcoming' if invoice.due_on>today else 'Due today' if invoice.due_on==today else 'Overdue'
        db.add(Outbox(user_id=user.id,branch_id=invoice.branch_id,dedupe_key=key,recipient=user.email,subject=f'Cityhive {stage.lower()} fee reminder · {invoice.month:%B %Y}',body=body,channel='email'))
        if resident.whatsapp_notifications and resident.whatsapp_consent_at and resident.phone and whatsapp.configured():
            db.add(Outbox(user_id=user.id,branch_id=invoice.branch_id,dedupe_key=f'{key}:whatsapp',recipient=resident.phone,
                subject=f'Cityhive fee reminder · {invoice.month:%B %Y}',body=body,channel='whatsapp'))
        db.flush()
        count += 1
    return count

def deliver_emails():
    # SMTP delivery is at-least-once: crash after SMTP acceptance can duplicate an email.
    with SessionLocal() as db:
        pending = db.scalars(select(Outbox).where(Outbox.sent_at.is_(None),Outbox.cancelled.is_(False),Outbox.attempts<5,
            (Outbox.next_attempt_at.is_(None)) | (Outbox.next_attempt_at<=now())).order_by(Outbox.id).limit(50).with_for_update(skip_locked=True)).all()
        for item in pending:
            if item.dedupe_key.startswith('reminder:'):
                invoice = db.get(Invoice,int(item.dedupe_key.split(':')[1]))
                balance = invoice.amount-paid_total(db,invoice.id)
                resident = db.get(Resident,invoice.resident_id)
                if balance<=0 or (item.channel=='whatsapp' and (not resident.whatsapp_notifications or not resident.whatsapp_consent_at or resident.phone!=item.recipient)):
                    item.cancelled = True
                    item.delivery_status = 'cancelled'
                    item.last_error = ''
                    continue
                resident = db.get(Resident,invoice.resident_id)
                item.body = (f'Hi {resident.name},\nYour outstanding fee is INR {balance:.2f} '
                             f'for {invoice.month:%B %Y}. Due date: {invoice.due_on}. '
                             'Please contact management to pay.\n')
            item.attempts += 1
            try:
                if item.channel=='whatsapp' and item.dedupe_key.startswith('admission-wa:'):
                    admission=db.get(Admission,int(item.dedupe_key.split(':')[1]))
                    if not admission or not admission.whatsapp_updates or admission.phone!=item.recipient:
                        item.cancelled=True;item.delivery_status='cancelled';continue
                    item.provider_message_id=whatsapp.send_admission_update(item.recipient,admission.id,item.dedupe_key.split(':')[2])
                elif item.channel=='whatsapp':
                    invoice=db.get(Invoice,int(item.dedupe_key.split(':')[1]))
                    resident=db.get(Resident,invoice.resident_id)
                    item.provider_message_id=whatsapp.send_reminder(item.recipient,invoice.invoice_number,invoice.month.strftime('%B %Y'),f'{balance:.2f}',invoice.due_on.isoformat())
                else:
                    msg = EmailMessage()
                    msg['From'],msg['To'],msg['Subject'] = settings.mail_from,item.recipient,item.subject
                    msg['Message-ID'] = f'<cityhive-{item.id}@cityhive.local>'
                    msg.set_content(item.body)
                    transport=smtplib.SMTP_SSL if settings.smtp_security=='ssl' else smtplib.SMTP
                    options={'context':ssl.create_default_context()} if settings.smtp_security=='ssl' else {}
                    with transport(settings.smtp_host,settings.smtp_port,timeout=10,**options) as smtp:
                        if settings.smtp_security=='starttls': smtp.starttls(context=ssl.create_default_context())
                        if settings.smtp_username: smtp.login(settings.smtp_username,settings.smtp_password)
                        smtp.send_message(msg)
                item.sent_at = now()
                item.delivery_status='submitted'
                item.last_error = ''
            except Exception as exc:
                item.last_error = 'SMTP delivery failed; automatic retry pending'
                item.delivery_status='retrying' if item.attempts<5 else 'failed'
                item.next_attempt_at=now()+timedelta(minutes=min(60,2**item.attempts))
                if item.channel=='whatsapp': item.last_error='WhatsApp delivery unavailable or failed; check provider configuration'
        db.commit()


def receipt_pdf(db,payment):
    from .documents import financial_document
    invoice=db.get(Invoice,payment.invoice_id)
    resident=db.get(Resident,invoice.resident_id)
    branch=db.get(Branch,invoice.branch_id)
    balance=invoice.amount-paid_total(db,invoice.id)
    return financial_document('Payment receipt',f'SW-{payment.id:06d}',
        [('Branch',branch.name if branch else 'Historical branch'),('Resident',resident.name),('Resident ID',resident.resident_code),
         ('Invoice',invoice.invoice_number),('Received',payment.paid_at),('Method',payment.method),('Reference',payment.reference),
         ('Status','REVERSED' if payment.reversed_at else 'PAYMENT RECORDED'),('Current invoice balance',f'INR {balance:.2f}')],
        [('Payment recorded',payment.amount),('Current invoice balance',balance)])
