"""Bounded, server-side payment performance calculations.

Report scope is invoice billing month in [from_date, to_date]. Collections are
payment records dated in that same inclusive period. Open balances and aging
are as of `as_of` and include all payment methods. Invoices carry a room-number
snapshot, so room performance does not follow a resident's later room shift.
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session

from .models import Invoice, Payment, Resident, Room, User, Branch
from .services import local_today

ZERO = Decimal("0.00")
MAX_REPORT_INVOICES = 10000
MAX_REPORT_PAYMENTS = 100000
BUSINESS_TZ = ZoneInfo("Asia/Kolkata")


def datetime_start(day: date):
    return datetime.combine(day, time.min, BUSINESS_TZ).astimezone(timezone.utc).replace(tzinfo=None)


def datetime_end(day: date):
    return datetime_start(day + timedelta(days=1))


def financial_report(db: Session, user: User, start: date, end: date,
                     as_of: date | None = None, branch_id: int | None = None,
                     room_number: str | None = None, resident_id: int | None = None,
                     payment_method: str | None = None, invoice_status: str | None = None):
    if start > end:
        raise HTTPException(422, "from_date must be on or before to_date")
    if (end - start).days > 1095:
        raise HTTPException(422, "Report range cannot exceed three years")
    as_of = as_of or local_today()
    if payment_method not in {None, "cash", "upi", "bank"}:
        raise HTTPException(422, "Unsupported payment method")

    if invoice_status not in {None,'paid','due','overdue'}: raise HTTPException(422,'Unsupported invoice status')
    query = (select(Invoice, Resident)
             .join(Resident, Resident.id == Invoice.resident_id)
             .where(Invoice.month >= start.replace(day=1),
                    Invoice.month <= end.replace(day=1)))
    if branch_id is not None:
        query = query.where(Invoice.branch_id == branch_id)
    if room_number:
        query = query.where(Invoice.room_number == room_number.strip())
    if resident_id is not None:
        query = query.where(Invoice.resident_id == resident_id)
    rows = db.execute(query.order_by(Invoice.month, Invoice.id).limit(MAX_REPORT_INVOICES + 1)).all()
    if len(rows) > MAX_REPORT_INVOICES:
        raise HTTPException(422, "Report is too large; narrow the date or branch filters")

    invoice_ids = [invoice.id for invoice, _ in rows]
    payments_by_invoice: dict[int, list[Payment]] = defaultdict(list)
    if invoice_ids:
        payment_conditions=(Payment.invoice_id.in_(invoice_ids),Payment.paid_at<datetime_end(as_of),or_(Payment.reversed_at.is_(None),Payment.reversed_at>=datetime_end(as_of)))
        if (db.scalar(select(func.count(Payment.id)).where(*payment_conditions)) or 0)>MAX_REPORT_PAYMENTS:
            raise HTTPException(422,'Report has too many invoice payments; narrow the date or branch filters')
        for payment in db.scalars(select(Payment).where(*payment_conditions)
                                  .order_by(Payment.paid_at, Payment.id)):
            payments_by_invoice[payment.invoice_id].append(payment)

    residents: dict[int, dict] = {}
    rooms: dict[tuple[int | None, str], dict] = {}
    branches: dict[int | None, dict] = {}
    aging = {"not_due": ZERO, "1_7_days": ZERO, "8_30_days": ZERO,
             "31_60_days": ZERO, "61_plus_days": ZERO}
    collections = ZERO
    cash_collected = ZERO
    collected_today = ZERO
    billed = ZERO
    outstanding = ZERO
    overdue = ZERO
    overdue_invoice_count = 0
    settled_delays: list[int] = []
    on_time = 0
    recent_by_method: dict[str, Decimal] = defaultdict(lambda: ZERO)
    trend: dict[str, Decimal] = defaultdict(lambda: ZERO)
    daily: dict[str, Decimal] = defaultdict(lambda: ZERO)
    weekly: dict[str, Decimal] = defaultdict(lambda: ZERO)
    cash_by_staff: dict[int, Decimal] = defaultdict(lambda: ZERO)
    invoice_rows = []

    matched_ids=[]
    for invoice, resident in rows:
        all_payments = payments_by_invoice[invoice.id]
        paid = sum((Decimal(p.amount) for p in all_payments), ZERO)
        balance = max(ZERO, Decimal(invoice.amount) - paid)
        status='paid' if balance<=0 else 'overdue' if invoice.due_on<as_of else 'due'
        if invoice_status and invoice_status!=status: continue
        matched_ids.append(invoice.id)
        billed += Decimal(invoice.amount)
        settlement_date = None
        cumulative = ZERO
        for payment in all_payments:
            cumulative += Decimal(payment.amount)
            if settlement_date is None and cumulative >= Decimal(invoice.amount):
                settlement_date = (payment.paid_at.replace(tzinfo=timezone.utc) if payment.paid_at.tzinfo is None else payment.paid_at).astimezone(BUSINESS_TZ).date()

        report_branch_id=invoice.branch_id
        inv = invoice_rows_for(db, residents, rooms, branches, invoice, resident,report_branch_id)
        inv.update({"paid": paid, "balance": balance, "settlement_date": settlement_date})
        if settlement_date is not None:
            delay = max(0, (settlement_date - invoice.due_on).days)
            inv["settlement_delay_days"] = delay
            settled_delays.append(delay)
            if delay == 0:
                on_time += 1
            inv["recent_settled"] = True
        else:
            inv["settlement_delay_days"] = None
            inv["recent_settled"] = False
            days = max(0, (as_of - invoice.due_on).days)
            inv["current_days_past_due"] = days if balance > 0 else 0

        if balance > 0:
            outstanding += balance
            if invoice.due_on < as_of:
                overdue += balance
                overdue_invoice_count += 1
                days = (as_of - invoice.due_on).days
                bucket = "1_7_days" if days <= 7 else "8_30_days" if days <= 30 else "31_60_days" if days <= 60 else "61_plus_days"
            else:
                bucket = "not_due"
            aging[bucket] += balance
            inv["current_days_past_due"] = max(0, (as_of - invoice.due_on).days)
        else:
            inv["current_days_past_due"] = 0

        if balance > 0:
            rooms[(report_branch_id, invoice.room_number)]["overdue"] += balance if invoice.due_on < as_of else ZERO
            rooms[(report_branch_id, invoice.room_number)]["outstanding"] += balance
            residents[resident.id]["outstanding"] += balance
            if invoice.due_on < as_of:
                residents[resident.id]["overdue"] += balance
                residents[resident.id]["overdue_invoice_count"] += 1
                rooms[(report_branch_id,invoice.room_number)]["overdue_invoice_count"]=rooms[(report_branch_id,invoice.room_number)].get("overdue_invoice_count",0)+1
                residents[resident.id]["current_days_past_due"] = max(
                    residents[resident.id]["current_days_past_due"], (as_of - invoice.due_on).days)
        residents[resident.id]["billed"] += Decimal(invoice.amount)
        residents[resident.id]["paid"] += paid
        branch = branches.setdefault(report_branch_id, {"branch_id": report_branch_id,
            "branch_name": (db.get(Branch, report_branch_id).name if report_branch_id and db.get(Branch, report_branch_id) else "Unassigned"),
            "collected": ZERO, "overdue": ZERO, "outstanding": ZERO})
        branch["outstanding"] += balance
        if invoice.due_on < as_of:
            branch["overdue"] += balance
        residents[resident.id]["invoice_count"] += 1
        residents[resident.id]["settled_count"] += int(settlement_date is not None)
        if settlement_date is not None:
            residents[resident.id]["delay_sum"] += max(0, (settlement_date - invoice.due_on).days)
            residents[resident.id]["on_time_count"] += int(settlement_date <= invoice.due_on)
            last = residents[resident.id]["last_settled"]
            if last is None or invoice.month > last["month"]:
                residents[resident.id]["last_settled"] = {"month": invoice.month.isoformat(), "invoice_number": invoice.invoice_number}
        rooms[(report_branch_id, invoice.room_number)]["billed"] += Decimal(invoice.amount)
        rooms[(report_branch_id, invoice.room_number)]["paid"] += paid
        rooms[(report_branch_id, invoice.room_number)]["settled_count"] += int(settlement_date is not None)
        if settlement_date is not None:
            rooms[(report_branch_id, invoice.room_number)]["delay_sum"] += max(0, (settlement_date - invoice.due_on).days)
            rooms[(report_branch_id, invoice.room_number)]["on_time_count"] += int(settlement_date <= invoice.due_on)
        if balance > 0 and invoice.due_on < as_of:
            invoice_rows.append({"invoice_id": invoice.id, "invoice_number": invoice.invoice_number,
                "resident_id": resident.id, "resident_code":resident.resident_code,"resident_name": resident.name,
                "branch_id": invoice.branch_id, "room_number": invoice.room_number,
                "month": invoice.month.isoformat(), "due_on": invoice.due_on.isoformat(),
                "balance": str(balance), "current_days_past_due": (as_of - invoice.due_on).days})

    # Collections are transaction-date based and include payments made in the
    # period even when the related invoice belongs to an earlier billing month.
    payment_scope=(Payment.paid_at >= datetime_start(start), Payment.paid_at < datetime_end(end),Payment.reversed_at.is_(None))
    if invoice_status: payment_scope=(*payment_scope,Invoice.id.in_(matched_ids))
    payment_count_query=(select(func.count(Payment.id)).join(Invoice,Invoice.id==Payment.invoice_id)
                         .join(Resident,Resident.id==Invoice.resident_id).where(*payment_scope))
    if branch_id is not None:
        payment_count_query = payment_count_query.where(Invoice.branch_id == branch_id)
    if resident_id is not None:
        payment_count_query = payment_count_query.where(Resident.id == resident_id)
    if room_number:
        payment_count_query = payment_count_query.where(Invoice.room_number == room_number.strip())
    if payment_method:
        payment_count_query = payment_count_query.where(Payment.method == payment_method)
    if (db.scalar(payment_count_query) or 0)>MAX_REPORT_PAYMENTS:
        raise HTTPException(422,"Report has too many payment transactions; narrow the date or branch filters")
    # Group collections in SQL; only aggregate rows cross the database boundary.
    local_day=func.date(func.timezone('Asia/Kolkata',Payment.paid_at)) if db.bind.dialect.name=='postgresql' else func.date(Payment.paid_at,'+330 minutes')
    payment_query = (select(Invoice.branch_id,Invoice.room_number,Payment.method,Payment.recorded_by,local_day.label('day'),func.sum(Payment.amount).label('amount')).select_from(Payment)
                     .join(Invoice, Invoice.id == Payment.invoice_id)
                     .join(Resident, Resident.id == Invoice.resident_id)
                     .where(*payment_scope))
    if branch_id is not None: payment_query=payment_query.where(Invoice.branch_id==branch_id)
    if resident_id is not None: payment_query=payment_query.where(Resident.id==resident_id)
    if room_number: payment_query=payment_query.where(Invoice.room_number==room_number.strip())
    if payment_method: payment_query=payment_query.where(Payment.method==payment_method)
    payment_query=payment_query.group_by(Invoice.branch_id,Invoice.room_number,Payment.method,Payment.recorded_by,local_day)
    for group in db.execute(payment_query):
        amount=Decimal(group.amount)
        collections+=amount
        recent_by_method[group.method]+=amount
        day=group.day if isinstance(group.day,date) else date.fromisoformat(group.day)
        trend[day.strftime('%Y-%m')]+=amount
        daily[day.isoformat()]+=amount
        weekly[(day-timedelta(days=day.weekday())).isoformat()]+=amount
        if group.method=='cash':
            cash_collected+=amount
            if group.recorded_by: cash_by_staff[group.recorded_by]+=amount
        branch=branches.setdefault(group.branch_id,{'branch_id':group.branch_id,
            'branch_name':db.get(Branch,group.branch_id).name if group.branch_id and db.get(Branch,group.branch_id) else 'Unassigned',
            'collected':ZERO,'overdue':ZERO,'outstanding':ZERO})
        branch['collected']+=amount
        room=rooms.setdefault((group.branch_id,group.room_number),{'branch_id':group.branch_id,'room_number':group.room_number,
            'capacity':None,'occupied':0,'billed':ZERO,'paid':ZERO,'outstanding':ZERO,'overdue':ZERO,
            'settled_count':0,'delay_sum':0,'on_time_count':0})
        room['collected']=room.get('collected',ZERO)+amount

    today=local_today()
    today_query=(select(func.coalesce(func.sum(Payment.amount),0)).join(Invoice,Invoice.id==Payment.invoice_id)
                 .join(Resident,Resident.id==Invoice.resident_id)
                 .where(Payment.paid_at>=datetime_start(today),Payment.paid_at<datetime_end(today),Payment.reversed_at.is_(None)))
    if branch_id is not None: today_query=today_query.where(Invoice.branch_id==branch_id)
    if resident_id is not None: today_query=today_query.where(Resident.id==resident_id)
    if room_number: today_query=today_query.where(Invoice.room_number==room_number.strip())
    if payment_method: today_query=today_query.where(Payment.method==payment_method)
    if invoice_status: today_query=today_query.where(Invoice.id.in_(matched_ids))
    collected_today=Decimal(db.scalar(today_query) or ZERO)

    # Include current residents with no invoices in the selected period, so
    # their lack of history is represented with null delay metrics, not zero.
    if not room_number and not invoice_status:
        resident_query=select(Resident)
        if branch_id is not None: resident_query=resident_query.where(Resident.branch_id==branch_id)
        if resident_id is not None: resident_query=resident_query.where(Resident.id==resident_id)
        for resident in db.scalars(resident_query):
            if resident.id not in residents:
                current_room=db.get(Room,resident.room_id) if resident.room_id else None
                residents[resident.id]={"resident_id":resident.id,"resident_code":resident.resident_code,"resident_name":resident.name,
                    "branch_id":resident.branch_id,"current_room_number":current_room.number if current_room else None,
                    "billed":ZERO,"paid":ZERO,"outstanding":ZERO,"overdue":ZERO,
                    "overdue_invoice_count":0,"current_days_past_due":0,"invoice_count":0,
                    "settled_count":0,"delay_sum":0,"on_time_count":0,"last_settled":None}

    # Add currently configured rooms, including rooms with no invoice history.
    room_query = select(Room)
    if branch_id is not None:
        room_query = room_query.where(Room.branch_id == branch_id)
    if room_number: room_query=room_query.where(Room.number==room_number.strip())
    if resident_id is not None:
        room_query=room_query.where(Room.id==select(Resident.room_id).where(Resident.id==resident_id).scalar_subquery())
    for room in db.scalars(room_query.order_by(Room.branch_id, Room.number)):
        key = (room.branch_id, room.number)
        entry = rooms.setdefault(key, {"branch_id": room.branch_id, "room_number": room.number,
            "capacity": room.capacity, "occupied": 0, "billed": ZERO, "paid": ZERO,
            "outstanding": ZERO, "overdue": ZERO, "settled_count": 0,
            "delay_sum": 0, "on_time_count": 0})
        entry["capacity"] = room.capacity
        entry["occupied"] = db.scalar(select(func.count(Resident.id)).where(Resident.room_id == room.id,Resident.status=="active")) or 0

    def finalize(row):
        for key in ("billed", "paid", "outstanding", "overdue", "collected"):
            if key in row:
                row[key] = str(row[key])
        return row

    resident_rows = []
    for row in residents.values():
        row["fully_settled_invoice_count"] = row.pop("settled_count")
        row["average_settlement_delay_days"] = round(row.pop("delay_sum") / row["fully_settled_invoice_count"], 2) if row["fully_settled_invoice_count"] else None
        row["on_time_rate_percent"] = round(row.pop("on_time_count") * 100 / row["fully_settled_invoice_count"], 2) if row["fully_settled_invoice_count"] else None
        row["last_settled_invoice"] = row.pop("last_settled")
        resident_rows.append(finalize(row))
    room_rows = []
    for row in rooms.values():
        row.setdefault("collected",ZERO)
        row.setdefault("overdue_invoice_count",0)
        row["fully_settled_invoice_count"] = row.pop("settled_count")
        row["average_settlement_delay_days"] = round(row.pop("delay_sum") / row["fully_settled_invoice_count"], 2) if row["fully_settled_invoice_count"] else None
        row["on_time_rate_percent"] = round(row.pop("on_time_count") * 100 / row["fully_settled_invoice_count"], 2) if row["fully_settled_invoice_count"] else None
        room_rows.append(finalize(row))
    for branch in branches.values():
        branch["collected"] = str(branch["collected"])

    return {"from_date": start.isoformat(), "to_date": end.isoformat(), "as_of": as_of.isoformat(),
        "definitions": {"invoice_scope": "Billing month is within selected months; both endpoints are inclusive.",
            "collections": ("Payments on invoices matching the selected billing months and status, within the selected payment dates." if invoice_status else "Payment records dated within selected dates; filtered by method only when selected."),
            "collected_today": "Non-reversed payments dated today in Asia/Kolkata, honoring branch, room, resident, and payment-method filters, independent of the selected collection date range.",
            "outstanding": "Selected invoices' balances using all non-reversed payment records as of report date.",
            "settlement_delay": "max(0, full settlement date minus invoice due date), fully settled selected invoices only."},
        "summary": {"billed": str(billed), "collected": str(collections), "collected_today": str(collected_today),
            "cash_collected": str(cash_collected), "outstanding": str(outstanding), "overdue": str(overdue),
            "overdue_invoice_count": overdue_invoice_count,
            "overdue_resident_count": sum(1 for r in residents.values() if Decimal(r["overdue"]) > 0),
            "average_settlement_delay_days": round(sum(settled_delays) / len(settled_delays), 2) if settled_delays else None,
            "settled_invoice_count": len(settled_delays), "on_time_settlement_count": on_time,
            "on_time_rate_percent": round(on_time * 100 / len(settled_delays), 2) if settled_delays else None},
        "aging": {k: str(v) for k, v in aging.items()},
        "collections_by_month": [{"month": k, "amount": str(v)} for k, v in sorted(trend.items())],
        "collections_by_day": [{"day": k, "amount": str(v)} for k, v in sorted(daily.items())],
        "collections_by_week": [{"week": k, "amount": str(v)} for k, v in sorted(weekly.items())],
        "collections_by_method": [{"method": k, "amount": str(v)} for k, v in sorted(recent_by_method.items())],
        "collections_by_branch": list(branches.values()),
        "cash_by_staff": [{"staff_user_id": k, "staff_email": (db.get(User,k).email if db.get(User,k) else None), "amount": str(v)} for k, v in sorted(cash_by_staff.items())],
        "residents": sorted(resident_rows, key=lambda x: (Decimal(x["outstanding"]), x["average_settlement_delay_days"] or -1), reverse=True),
        "rooms": sorted(room_rows, key=lambda x: (Decimal(x["outstanding"]), x["branch_id"] or 0, x["room_number"]), reverse=True),
        "overdue_invoices": sorted(invoice_rows, key=lambda x: (-x["current_days_past_due"], -Decimal(x["balance"]))) }


def invoice_rows_for(db, residents, rooms, branches, invoice, resident, report_branch_id):
    if resident.id not in residents:
        current_room_number = None
        if resident.room_id:
            current = db.get(Room, resident.room_id)
            current_room_number = current.number if current else None
        residents[resident.id] = {"resident_id": resident.id, "resident_code":resident.resident_code,"resident_name": resident.name,
            "branch_id": report_branch_id, "current_room_number": (current_room_number if resident.branch_id==report_branch_id else None),
            "billed": ZERO, "paid": ZERO, "outstanding": ZERO, "overdue": ZERO,
            "overdue_invoice_count": 0, "current_days_past_due": 0, "invoice_count": 0,
            "settled_count": 0, "delay_sum": 0, "on_time_count": 0, "last_settled": None}
    key = (report_branch_id, invoice.room_number)
    if key not in rooms:
        rooms[key] = {"branch_id": report_branch_id, "room_number": invoice.room_number,
            "capacity": None, "occupied": 0, "billed": ZERO, "paid": ZERO,
            "outstanding": ZERO, "overdue": ZERO, "settled_count": 0,
            "delay_sum": 0, "on_time_count": 0}
    return {"invoice_id": invoice.id, "invoice_number": invoice.invoice_number,
            "resident_id": resident.id, "resident_code":resident.resident_code,"resident_name": resident.name,
            "branch_id": report_branch_id, "room_number": invoice.room_number,
            "month": invoice.month.isoformat(), "due_on": invoice.due_on.isoformat()}
