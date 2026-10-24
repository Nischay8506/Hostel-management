from datetime import date, datetime, timezone
from decimal import Decimal
import secrets
from sqlalchemy import String, ForeignKey, Numeric, Date, DateTime, UniqueConstraint, CheckConstraint, Text, Boolean, JSON, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def now(): return datetime.now(timezone.utc)
class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16))
    must_change_password: Mapped[bool] = mapped_column(default=False)
    phone: Mapped[str | None] = mapped_column(String(18),nullable=True)
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)
    active: Mapped[bool] = mapped_column(Boolean,default=True,server_default='1')
    session_version: Mapped[int] = mapped_column(default=0,server_default='0')
class Branch(Base):
    __tablename__ = 'branches'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    address: Mapped[str] = mapped_column(String(300), default='')
    contact_phone: Mapped[str] = mapped_column(String(30), default='')
    contact_email: Mapped[str] = mapped_column(String(254), default='', server_default='')
    image_url: Mapped[str] = mapped_column(String(1000), default='', server_default='')
    faqs: Mapped[list] = mapped_column(JSON,default=list,server_default='[]')
    description: Mapped[str] = mapped_column(Text, default='')
    facilities: Mapped[str] = mapped_column(Text, default='')
    rules: Mapped[str] = mapped_column(Text, default='')
    notice_days: Mapped[int | None] = mapped_column(nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    published: Mapped[bool] = mapped_column(Boolean, default=False, server_default='0')
class BranchAdmin(Base):
    __tablename__ = 'branch_admins'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id',ondelete='CASCADE'),primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey('branches.id',ondelete='CASCADE'),primary_key=True)
class Admission(Base):
    __tablename__ = 'admissions'
    __table_args__ = (UniqueConstraint('submission_key'),CheckConstraint('preferred_sharing BETWEEN 1 AND 8'))
    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey('branches.id'),index=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254),index=True)
    phone: Mapped[str] = mapped_column(String(15))
    emergency_contact: Mapped[str] = mapped_column(String(100),default='')
    emergency_phone: Mapped[str] = mapped_column(String(15),default='')
    preferred_sharing: Mapped[int]
    move_in_date: Mapped[date] = mapped_column(Date)
    message: Mapped[str] = mapped_column(Text,default='')
    submission_key: Mapped[str] = mapped_column(String(64))
    whatsapp_updates: Mapped[bool] = mapped_column(Boolean,default=False,server_default='0')
    status: Mapped[str] = mapped_column(String(20),default='pending',index=True)
    admin_note: Mapped[str] = mapped_column(Text,default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resident_id: Mapped[int | None] = mapped_column(ForeignKey('residents.id'),unique=True)
class AdmissionEvent(Base):
    __tablename__ = 'admission_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    admission_id: Mapped[int] = mapped_column(ForeignKey('admissions.id'))
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    old_status: Mapped[str] = mapped_column(String(20))
    new_status: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(Text,default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)
class Room(Base):
    __tablename__ = 'rooms'
    __table_args__ = (CheckConstraint('capacity BETWEEN 1 AND 8'), CheckConstraint('monthly_fee >= 0'))
    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey('branches.id'), index=True)
    number: Mapped[str] = mapped_column(String(30), unique=True)
    floor: Mapped[str] = mapped_column(String(30))
    capacity: Mapped[int]
    monthly_fee: Mapped[Decimal] = mapped_column(Numeric(12,2))
    active: Mapped[bool] = mapped_column(Boolean,default=True,server_default='1')
class FeePlan(Base):
    __tablename__ = 'fee_plans'
    __table_args__ = (
        CheckConstraint('sharing BETWEEN 1 AND 8'),
        CheckConstraint('monthly_fee >= 0 AND additional_charge_amount >= 0'),
        CheckConstraint('billing_day BETWEEN 1 AND 28 AND due_day BETWEEN 1 AND 28'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey('branches.id'),index=True)
    name: Mapped[str] = mapped_column(String(100))
    sharing: Mapped[int]
    advance_amount: Mapped[Decimal] = mapped_column(Numeric(12,2),default=0,server_default='0')
    monthly_fee: Mapped[Decimal] = mapped_column(Numeric(12,2))
    additional_charge_label: Mapped[str] = mapped_column(String(100),default='')
    additional_charge_amount: Mapped[Decimal] = mapped_column(Numeric(12,2),default=0)
    billing_day: Mapped[int] = mapped_column(default=1)
    due_day: Mapped[int] = mapped_column(default=5)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_until: Mapped[date | None] = mapped_column(Date,nullable=True)
    active: Mapped[bool] = mapped_column(Boolean,default=True,server_default='1')
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
class Resident(Base):
    __tablename__ = 'residents'
    __table_args__ = (CheckConstraint('discount >= 0'),UniqueConstraint('resident_code',name='uq_residents_resident_code'))
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_code: Mapped[str] = mapped_column(String(20),default=lambda: 'CH-'+secrets.token_hex(6).upper())
    branch_id: Mapped[int | None] = mapped_column(ForeignKey('branches.id'), index=True)
    fee_plan_id: Mapped[int | None] = mapped_column(ForeignKey('fee_plans.id'),nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(15))
    guardian: Mapped[str] = mapped_column(String(100), default='')
    guardian_phone: Mapped[str] = mapped_column(String(15), default='')
    institution: Mapped[str] = mapped_column(String(150), default='')
    joined_on: Mapped[date] = mapped_column(Date)
    planned_move_out: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20),default='active',server_default='active')
    room_id: Mapped[int | None] = mapped_column(ForeignKey('rooms.id'))
    discount: Mapped[Decimal] = mapped_column(Numeric(12,2), default=0)
    aadhaar_last4: Mapped[str | None] = mapped_column(String(4))
    id_status: Mapped[str] = mapped_column(String(20), default='pending')
    id_reviewed_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    id_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    whatsapp_notifications: Mapped[bool] = mapped_column(Boolean,default=False,server_default='0')
    whatsapp_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)
class AllocationEvent(Base):
    __tablename__ = 'allocation_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey('residents.id'),index=True)
    from_room_id: Mapped[int | None] = mapped_column(ForeignKey('rooms.id'))
    to_room_id: Mapped[int | None] = mapped_column(ForeignKey('rooms.id'))
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    reason: Mapped[str] = mapped_column(Text,default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)
class StayRequest(Base):
    __tablename__ = 'stay_requests'
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey('residents.id'),index=True)
    request_type: Mapped[str] = mapped_column(String(20))
    target_room_id: Mapped[int | None] = mapped_column(ForeignKey('rooms.id'))
    requested_move_out: Mapped[date | None] = mapped_column(Date)
    notice_exception_reason: Mapped[str] = mapped_column(Text,default='')
    note: Mapped[str] = mapped_column(Text,default='')
    status: Mapped[str] = mapped_column(String(20),default='pending',index=True)
    admin_note: Mapped[str] = mapped_column(Text,default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
class IdentityReviewEvent(Base):
    __tablename__ = 'identity_review_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey('residents.id'),index=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    old_status: Mapped[str] = mapped_column(String(20))
    new_status: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(Text,default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)
class Invoice(Base):
    __tablename__ = 'invoices'
    __table_args__ = (UniqueConstraint('resident_id','month'),UniqueConstraint('invoice_number'),CheckConstraint('amount >= 0'))
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String(40))
    issued_on: Mapped[date] = mapped_column(Date,default=date.today)
    resident_id: Mapped[int] = mapped_column(ForeignKey('residents.id'))
    branch_id: Mapped[int | None] = mapped_column(ForeignKey('branches.id'),index=True,nullable=True)
    fee_plan_id: Mapped[int | None] = mapped_column(ForeignKey('fee_plans.id'),nullable=True)
    month: Mapped[date] = mapped_column(Date)
    due_on: Mapped[date] = mapped_column(Date)
    room_number: Mapped[str] = mapped_column(String(30))
    base_fee: Mapped[Decimal] = mapped_column(Numeric(12,2))
    additional_charge_label: Mapped[str] = mapped_column(String(100),default='')
    additional_charge_amount: Mapped[Decimal] = mapped_column(Numeric(12,2),default=0)
    discount: Mapped[Decimal] = mapped_column(Numeric(12,2))
    discount_rule_id: Mapped[int | None] = mapped_column(ForeignKey('resident_discounts.id'),nullable=True)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5,2),default=0,server_default='0')
    amount: Mapped[Decimal] = mapped_column(Numeric(12,2))
class Payment(Base):
    __tablename__ = 'payments'
    __table_args__ = (CheckConstraint('amount > 0'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey('invoices.id'))
    amount: Mapped[Decimal] = mapped_column(Numeric(12,2))
    method: Mapped[str] = mapped_column(String(20))
    reference: Mapped[str] = mapped_column(String(100))
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    recorded_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now,index=True)
    payer_name: Mapped[str] = mapped_column(String(100),default='')
    note: Mapped[str] = mapped_column(String(500),default='')
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)
    reversed_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'),nullable=True)
    reversal_reason: Mapped[str] = mapped_column(String(500),default='')

class ResidentDiscount(Base):
    __tablename__ = 'resident_discounts'
    __table_args__ = (CheckConstraint('percentage > 0 AND percentage <= 100'),
                     CheckConstraint("charge_scope IN ('accommodation','all_monthly')"),
                     CheckConstraint('max_amount IS NULL OR max_amount >= 0'),
                     CheckConstraint('effective_until >= effective_from'))
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey('residents.id'),index=True)
    percentage: Mapped[Decimal] = mapped_column(Numeric(5,2))
    charge_scope: Mapped[str] = mapped_column(String(20))
    max_amount: Mapped[Decimal | None] = mapped_column(Numeric(12,2),nullable=True)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_until: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(String(500))
    approved_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)
    revoked_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'),nullable=True)

class JobState(Base):
    __tablename__ = 'job_state'
    name: Mapped[str] = mapped_column(String(40),primary_key=True)
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)
    last_succeeded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)
    status: Mapped[str] = mapped_column(String(20),default='never_run')

class RateLimitBucket(Base):
    __tablename__ = 'rate_limit_buckets'
    key: Mapped[str] = mapped_column(String(100),primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True),index=True)
    attempts: Mapped[int] = mapped_column(default=0)

class PaymentAuditEvent(Base):
    __tablename__ = 'payment_audit_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey('payments.id'),index=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(500),default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)

class OtpChallenge(Base):
    __tablename__ = 'otp_challenges'
    id: Mapped[int] = mapped_column(primary_key=True)
    challenge_id: Mapped[str] = mapped_column(String(36),unique=True,index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id',ondelete='CASCADE'),index=True)
    purpose: Mapped[str] = mapped_column(String(20),default='login')
    channel: Mapped[str] = mapped_column(String(16),default='whatsapp',server_default='whatsapp')
    phone: Mapped[str] = mapped_column(String(18))
    code_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)
    attempts: Mapped[int] = mapped_column(default=0)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)

class AuthAuditEvent(Base):
    __tablename__ = 'auth_audit_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id',ondelete='SET NULL'),nullable=True,index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id',ondelete='SET NULL'),nullable=True)
    event: Mapped[str] = mapped_column(String(32))
    ip_hash: Mapped[str] = mapped_column(String(64),default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)

class NotificationPreferenceEvent(Base):
    __tablename__ = 'notification_preference_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey('residents.id'),index=True)
    enabled: Mapped[bool] = mapped_column(Boolean)
    source: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)
class Complaint(Base):
    __tablename__ = 'complaints'
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey('residents.id'))
    category: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default='open')
    response: Mapped[str] = mapped_column(Text, default='')
    assigned_to_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'),nullable=True,index=True)
    resolution_note: Mapped[str] = mapped_column(Text,default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)
class ComplaintEvent(Base):
    __tablename__ = 'complaint_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey('complaints.id'), index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    action: Mapped[str] = mapped_column(String(20))
    old_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    new_status: Mapped[str] = mapped_column(String(20))
    old_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_response: Mapped[str] = mapped_column(Text, default='')
    old_assignee_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'),nullable=True)
    new_assignee_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'),nullable=True)
    resolution_note: Mapped[str] = mapped_column(Text,default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
class GatePass(Base):
    __tablename__ = 'gate_passes'
    id: Mapped[int] = mapped_column(primary_key=True)
    pass_code: Mapped[str] = mapped_column(String(64),unique=True,index=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey('residents.id'),index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)
    valid_until: Mapped[date | None] = mapped_column(Date,nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)
    revoked_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'),nullable=True)
class FinancialLedgerEvent(Base):
    __tablename__ = 'financial_ledger_events'
    __table_args__ = (CheckConstraint('amount > 0'),
                      CheckConstraint("account_type IN ('deposit','advance')"),
                      CheckConstraint("action IN ('received','deduction','refund')"))
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey('residents.id'),index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey('branches.id'),index=True)
    settlement_id: Mapped[int | None] = mapped_column(ForeignKey('final_settlements.id'),nullable=True,index=True)
    account_type: Mapped[str] = mapped_column(String(12))
    action: Mapped[str] = mapped_column(String(12))
    amount: Mapped[Decimal] = mapped_column(Numeric(12,2))
    method: Mapped[str | None] = mapped_column(String(20),nullable=True)
    reference: Mapped[str] = mapped_column(String(100),default='')
    reason: Mapped[str] = mapped_column(String(500),default='')
    idempotency_key: Mapped[str] = mapped_column(String(64),unique=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)
class FinalSettlement(Base):
    __tablename__ = 'final_settlements'
    __table_args__ = (CheckConstraint('proposed_refund >= 0'),
                      CheckConstraint("status IN ('pending','approved','rejected','partially_refunded','completed','no_refund')"))
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey('residents.id'),index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey('branches.id'),index=True)
    status: Mapped[str] = mapped_column(String(24),default='pending',index=True)
    deposit_balance_snapshot: Mapped[Decimal] = mapped_column(Numeric(12,2))
    advance_balance_snapshot: Mapped[Decimal] = mapped_column(Numeric(12,2))
    invoice_balance_snapshot: Mapped[Decimal] = mapped_column(Numeric(12,2))
    proposed_refund: Mapped[Decimal] = mapped_column(Numeric(12,2))
    note: Mapped[str] = mapped_column(String(1000),default='')
    decision_note: Mapped[str] = mapped_column(String(1000),default='')
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    decided_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'),nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)
class SettlementEvent(Base):
    __tablename__ = 'settlement_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    settlement_id: Mapped[int] = mapped_column(ForeignKey('final_settlements.id'),index=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(24))
    old_status: Mapped[str | None] = mapped_column(String(24),nullable=True)
    new_status: Mapped[str] = mapped_column(String(24))
    note: Mapped[str] = mapped_column(String(1000),default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)
class Outbox(Base):
    __tablename__ = 'outbox'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'),nullable=True,index=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey('branches.id'),index=True)
    dedupe_key: Mapped[str] = mapped_column(String(120), unique=True)
    recipient: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled: Mapped[bool] = mapped_column(default=False)
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str] = mapped_column(String(100), default='')
    channel: Mapped[str] = mapped_column(String(20),default='email',server_default='email')
    delivery_status: Mapped[str] = mapped_column(String(20),default='queued',server_default='queued')
    provider_message_id: Mapped[str | None] = mapped_column(String(100),nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)

class LifecycleEvent(Base):
    __tablename__ = 'lifecycle_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    entity: Mapped[str] = mapped_column(String(20))
    entity_id: Mapped[int]
    branch_id: Mapped[int] = mapped_column(ForeignKey('branches.id'),index=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)

class IdentityDocument(Base):
    __tablename__ = 'identity_documents'
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey('residents.id'),unique=True)
    content_type: Mapped[str] = mapped_column(String(40))
    encrypted_content: Mapped[bytes] = mapped_column(LargeBinary)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)
