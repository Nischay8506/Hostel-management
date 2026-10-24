from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, EmailStr, Field, model_validator, field_validator
from urllib.parse import urlsplit
Money = Decimal
class Login(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)
    channel: Literal['whatsapp','sms'] = 'whatsapp'
class OtpVerify(BaseModel):
    challenge_id: str = Field(min_length=36,max_length=36)
    code: str = Field(pattern=r'^\d{6}$')
class OtpResend(BaseModel):
    challenge_id: str = Field(min_length=36,max_length=36)
class NotificationPreference(BaseModel):
    whatsapp_enabled: bool
class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=128)
class RoomCreate(BaseModel):
    branch_id: int | None = Field(default=None,gt=0)
    number: str = Field(min_length=1,max_length=30,pattern=r'\S')
    floor: str = Field(min_length=1,max_length=30)
    capacity: int = Field(ge=1,le=8)
    monthly_fee: Money = Field(ge=0,le=1000000,decimal_places=2)
class RoomUpdate(BaseModel):
    number: str = Field(min_length=1,max_length=30,pattern=r'\S')
    floor: str = Field(min_length=1,max_length=30)
    capacity: int = Field(ge=1,le=8)
    monthly_fee: Money = Field(ge=0,le=1000000,decimal_places=2)
class FeePlanCreate(BaseModel):
    branch_id: int = Field(gt=0)
    name: str = Field(min_length=2,max_length=100,pattern=r'\S')
    sharing: int = Field(ge=1,le=8)
    advance_amount: Money = Field(default=Decimal("0"),ge=0,le=10000000,decimal_places=2)
    monthly_fee: Money = Field(ge=0,le=1000000,decimal_places=2)
    additional_charge_label: str = Field(default='',max_length=100)
    additional_charge_amount: Money = Field(default=Decimal("0"),ge=0,le=1000000,decimal_places=2)
    billing_day: int = Field(default=1,ge=1,le=28)
    due_day: int = Field(default=5,ge=1,le=28)
    effective_from: date
    effective_until: date | None = None
    @model_validator(mode='after')
    def check_dates(self):
        if self.effective_until is not None and self.effective_until<self.effective_from:
            raise ValueError('effective_until must be on or after effective_from')
        if self.additional_charge_label.strip()=='' and self.additional_charge_amount!=0:
            raise ValueError('Provide a label for the additional monthly charge')
        return self
class FeePlanUpdate(BaseModel):
    name: str = Field(min_length=2,max_length=100,pattern=r'\S')
    advance_amount: Money = Field(default=Decimal("0"),ge=0,le=10000000,decimal_places=2)
    monthly_fee: Money = Field(ge=0,le=1000000,decimal_places=2)
    additional_charge_label: str = Field(default='',max_length=100)
    additional_charge_amount: Money = Field(default=Decimal("0"),ge=0,le=1000000,decimal_places=2)
    billing_day: int = Field(ge=1,le=28)
    due_day: int = Field(ge=1,le=28)
    effective_until: date | None = None
    active: bool = True
    @model_validator(mode='after')
    def check_charge_label(self):
        if self.additional_charge_label.strip()=='' and self.additional_charge_amount!=0:
            raise ValueError('Provide a label for the additional monthly charge')
        return self
class ResidentFeePlanUpdate(BaseModel):
    fee_plan_id: int | None = Field(default=None,gt=0)
class ResidentCreate(BaseModel):
    branch_id: int | None = Field(default=None,gt=0)
    name: str = Field(min_length=2,max_length=100,pattern=r'\S')
    email: EmailStr
    phone: str = Field(pattern=r'^\d{10}$')
    guardian: str = Field(default='',max_length=100)
    guardian_phone: str = Field(default='',pattern=r'^(\d{10})?$')
    institution: str = Field(default='',max_length=150)
    joined_on: date
    aadhaar_last4: str | None = Field(default=None,pattern=r'^\d{4}$')
    temporary_password: str = Field(min_length=10,max_length=128)
class Allocation(BaseModel):
    room_id: int = Field(gt=0)
    discount: Money = Field(ge=0,le=1000000,decimal_places=2)
    reason: str = Field(default='',max_length=1000)
class IDReview(BaseModel):
    status: Literal['reviewed','rejected']
    note: str = Field(default='',max_length=1000)
    aadhaar_last4: str | None = Field(default=None,pattern=r'^\d{4}$')
class BillingRun(BaseModel):
    month: date
class PaymentCreate(BaseModel):
    invoice_id: int = Field(gt=0)
    amount: Money = Field(gt=0,le=1000000,decimal_places=2)
    method: Literal['cash','upi','bank']
    reference: str = Field(default='',max_length=100)
    idempotency_key: str = Field(min_length=10,max_length=64)
    paid_at: datetime | None = None
    payer_name: str = Field(default='',max_length=100)
    note: str = Field(default='',max_length=500)
class PaymentReversal(BaseModel):
    reason: str = Field(min_length=5,max_length=500,pattern=r'\S')
class ComplaintCreate(BaseModel):
    category: Literal['maintenance','food','cleaning','other']
    title: str = Field(min_length=3,max_length=150,pattern=r'\S')
    description: str = Field(min_length=5,max_length=3000,pattern=r'\S')
class ComplaintUpdate(BaseModel):
    status: Literal['open','in_progress','resolved']
    response: str = Field(default='',max_length=3000)
    resolution_note: str = Field(default='',max_length=1000)
class ComplaintAssignment(BaseModel):
    user_id: int | None = Field(default=None,gt=0)
class FAQEntry(BaseModel):
    question: str = Field(min_length=3,max_length=200,pattern=r'\S')
    answer: str = Field(min_length=3,max_length=2000,pattern=r'\S')

class BranchCreate(BaseModel):
    name: str = Field(min_length=2,max_length=100,pattern=r'\S')
    address: str = Field(default='',max_length=300)
    contact_phone: str = Field(default='',max_length=30)
    contact_email: EmailStr | Literal[''] = ''
    image_url: str = Field(default='',max_length=1000)
    faqs: list[FAQEntry] = Field(default_factory=list,max_length=20)
    description: str = Field(default='',max_length=2000)
    facilities: str = Field(default='',max_length=2000)
    rules: str = Field(default='',max_length=3000)
    notice_days: int | None = Field(default=None,ge=0,le=365)
    @field_validator('image_url')
    @classmethod
    def validate_image(cls,value):
        if not value: return value
        url=urlsplit(value)
        if url.scheme!='https' or not url.netloc or url.username or url.password or url.fragment:
            raise ValueError('Use a public HTTPS URL for an approved property image')
        return value
class BranchUpdate(BranchCreate):
    active: bool = True
class BranchAdminCreate(BaseModel):
    email: EmailStr
    phone: str = Field(pattern=r'^(\d{10}|\+\d{10,15})$')
    temporary_password: str = Field(min_length=12,max_length=128)
    branch_ids: list[int] = Field(min_length=1,max_length=20)
class AdmissionCreate(BaseModel):
    branch_id: int = Field(gt=0)
    name: str = Field(min_length=2,max_length=100,pattern=r'\S')
    email: EmailStr
    phone: str = Field(pattern=r'^\d{10}$')
    emergency_contact: str = Field(default='',max_length=100)
    emergency_phone: str = Field(default='',pattern=r'^(\d{10})?$')
    preferred_sharing: int = Field(ge=1,le=8)
    move_in_date: date
    message: str = Field(default='',max_length=2000)
    submission_key: str = Field(min_length=32,max_length=64,pattern=r'^[a-fA-F0-9-]+$')
    whatsapp_updates: bool = False

class AdmissionLookup(BaseModel):
    email: EmailStr
    submission_key: str = Field(min_length=32,max_length=64)

class LifecycleChange(BaseModel):
    active: bool
    reason: str = Field(min_length=5,max_length=500,pattern=r'\S')
class AdmissionDecision(BaseModel):
    status: Literal['needs_info','approved','rejected']
    note: str = Field(default='',max_length=2000)
class AdmissionEnroll(BaseModel):
    temporary_password: str = Field(min_length=10,max_length=128)
class StayRequestCreate(BaseModel):
    request_type: Literal['extension','vacating','shift']
    target_room_id: int | None = Field(default=None,gt=0)
    requested_move_out: date | None = None
    notice_exception_reason: str = Field(default='',max_length=1000)
    note: str = Field(default='',max_length=2000)
class StayRequestDecision(BaseModel):
    status: Literal['approved','rejected']
    note: str = Field(default='',max_length=2000)
class GatePassCreate(BaseModel):
    resident_id: int = Field(gt=0)
    valid_until: date | None = None
class FinancialLedgerCreate(BaseModel):
    account_type: Literal['deposit','advance']
    action: Literal['received','deduction']
    amount: Money = Field(gt=0,le=10000000,decimal_places=2)
    method: Literal['cash','upi','bank'] | None = None
    reference: str = Field(default='',max_length=100)
    reason: str = Field(default='',max_length=500)
    idempotency_key: str = Field(min_length=10,max_length=64)
class SettlementCreate(BaseModel):
    resident_id: int = Field(gt=0)
    proposed_refund: Money = Field(ge=0,le=10000000,decimal_places=2)
    note: str = Field(default='',max_length=1000)
class SettlementDecision(BaseModel):
    status: Literal['approved','rejected']
    note: str = Field(default='',max_length=1000)
class SettlementRefund(BaseModel):
    account_type: Literal['deposit','advance']
    amount: Money = Field(gt=0,le=10000000,decimal_places=2)
    method: Literal['cash','upi','bank']
    reference: str = Field(default='',max_length=100)
    idempotency_key: str = Field(min_length=10,max_length=64)

class DiscountCreate(BaseModel):
    percentage: Decimal = Field(gt=0,le=100,decimal_places=2)
    charge_scope: Literal['accommodation','all_monthly']
    max_amount: Money | None = Field(default=None,ge=0,le=1000000,decimal_places=2)
    effective_from: date
    effective_until: date
    reason: str = Field(min_length=5,max_length=500,pattern=r'\S')
    @model_validator(mode='after')
    def dates(self):
        if self.effective_until<self.effective_from:
            raise ValueError('Discount end date must follow its start date')
        if self.effective_from.day!=1 or self.effective_until.day!=1:
            raise ValueError('Discount dates identify billing months; use the first day of the month')
        return self
