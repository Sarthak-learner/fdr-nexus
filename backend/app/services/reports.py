"""Authorized reporting queries built from persisted FDR Nexus records."""

from collections import defaultdict
from datetime import date, datetime, time
from decimal import Decimal
import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models as m
from ..config import WARN_DAYS
from .maturity import maturity_details


def format_money(amount, currency="INR"):
    if amount is None:
        return "—"
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return "—"
    if currency == "INR":
        return f"₹{value:,.2f}"
    return f"{currency or 'INR'} {value:,.2f}"


def _allowed_ids(db: Session, actor: m.User):
    if actor.role == "admin":
        return None
    return {row.institution_id for row in db.query(m.UserInstitution).filter_by(user_id=actor.id).all()}


def scoped_fdrs(db: Session, actor: m.User, from_date: date | None = None,
                to_date: date | None = None, institution_id: int | None = None):
    allowed = _allowed_ids(db, actor)
    if institution_id is not None and allowed is not None and institution_id not in allowed:
        raise HTTPException(403, "You are not permitted to report on this institution")

    query = db.query(m.FDRRecord).join(m.Institution)
    if allowed is not None:
        query = query.filter(m.FDRRecord.institution_id.in_(allowed)) if allowed else query.filter(False)
    if institution_id is not None:
        query = query.filter(m.FDRRecord.institution_id == institution_id)
    if from_date:
        query = query.filter(m.FDRRecord.maturity_date >= from_date)
    if to_date:
        query = query.filter(m.FDRRecord.maturity_date <= to_date)
    return query.order_by(m.FDRRecord.maturity_date.asc(), m.FDRRecord.id.asc()).all()


def _date_window(from_date, to_date):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(422, "from_date must be on or before to_date")
    return from_date, to_date


def _status_counts(rows):
    counts = defaultdict(int)
    for fdr in rows:
        counts[maturity_details(fdr.maturity_date)["maturity_category"]] += 1
    return dict(counts)


def _amounts(rows):
    by_currency = defaultdict(Decimal)
    for fdr in rows:
        try:
            by_currency[fdr.currency or "INR"] += Decimal(str(fdr.amount or 0))
        except Exception:
            continue
    return by_currency


def _amount_payload(rows):
    amounts = _amounts(rows)
    breakdown = [
        {"currency": currency, "value": float(value), "formatted": format_money(value, currency)}
        for currency, value in sorted(amounts.items())
    ]
    total = sum(amounts.values(), Decimal("0"))
    return {
        "total_deposit_value": float(total),
        "total_deposit_value_formatted": format_money(total, "INR") if len(amounts) <= 1 else "Multiple currencies",
        "currency_breakdown": breakdown,
    }


def _date_range_payload(from_date, to_date):
    return {"from_date": from_date, "to_date": to_date, "date_field": "maturity_date"}


def _validation_error_count(row):
    try:
        parsed = json.loads(row.errors or "[]")
        return len(parsed) if isinstance(parsed, list) else 0
    except (TypeError, ValueError):
        return 0


def portfolio_summary(db: Session, actor: m.User, from_date=None, to_date=None, institution_id=None):
    from_date, to_date = _date_window(from_date, to_date)
    rows = scoped_fdrs(db, actor, from_date, to_date, institution_id)
    details = [maturity_details(row.maturity_date) for row in rows]
    counts = _status_counts(rows)
    pending = sum(row.review_status == "pending" for row in rows)
    upcoming = sum(0 < item["days_to_maturity"] <= WARN_DAYS for item in details)
    return {
        **_amount_payload(rows),
        "record_count": len(rows),
        "active_fdrs": counts.get("active", 0),
        "matured_today": counts.get("matured_today", 0),
        "overdue_fdrs": counts.get("overdue", 0),
        "upcoming_maturities": upcoming,
        "pending_reviews": pending,
        "status_counts": counts,
        "date_range": _date_range_payload(from_date, to_date),
        "institution_id": institution_id,
    }


def institution_summary(db: Session, actor: m.User, from_date=None, to_date=None, institution_id=None):
    from_date, to_date = _date_window(from_date, to_date)
    rows = scoped_fdrs(db, actor, from_date, to_date, institution_id)
    grouped = {}
    for fdr in rows:
        item = grouped.setdefault(fdr.institution_id, {"institution_id": fdr.institution_id, "institution_name": fdr.institution.name, "fdrs": []})
        item["fdrs"].append(fdr)

    output = []
    for item in grouped.values():
        fdrs = item.pop("fdrs")
        counts = _status_counts(fdrs)
        output.append({
            **item,
            **_amount_payload(fdrs),
            "fdr_count": len(fdrs),
            "active_fdrs": counts.get("active", 0),
            "matured_today": counts.get("matured_today", 0),
            "overdue_fdrs": counts.get("overdue", 0),
            "upcoming_maturities": sum(0 < maturity_details(row.maturity_date)["days_to_maturity"] <= WARN_DAYS for row in fdrs),
            "pending_reviews": sum(row.review_status == "pending" for row in fdrs),
        })
    output.sort(key=lambda row: row["institution_name"].casefold())
    return {"rows": output, "date_range": _date_range_payload(from_date, to_date), "institution_id": institution_id}


def upcoming_report(db: Session, actor: m.User, from_date=None, to_date=None, institution_id=None):
    from_date, to_date = _date_window(from_date, to_date)
    rows = scoped_fdrs(db, actor, from_date, to_date, institution_id)
    output = []
    for fdr in rows:
        details = maturity_details(fdr.maturity_date)
        if details["days_to_maturity"] <= 0 or details["days_to_maturity"] > WARN_DAYS:
            continue
        output.append({
            "fdr_id": fdr.id,
            "reference_no": fdr.reference_no,
            "institution_id": fdr.institution_id,
            "institution_name": fdr.institution.name,
            "bank_name": fdr.bank_name,
            "amount": fdr.amount,
            "amount_formatted": format_money(fdr.amount, fdr.currency),
            "currency": fdr.currency,
            "maturity_date": fdr.maturity_date,
            "days_to_maturity": details["days_to_maturity"],
            "maturity_category": details["maturity_category"],
        })
    return {"rows": output, "count": len(output), "date_range": _date_range_payload(from_date, to_date), "institution_id": institution_id, "warning_days": WARN_DAYS}


def pending_reviews(db: Session, actor: m.User, from_date=None, to_date=None, institution_id=None):
    from_date, to_date = _date_window(from_date, to_date)
    rows = [row for row in scoped_fdrs(db, actor, from_date, to_date, institution_id) if row.review_status == "pending"]
    return {
        "rows": [
            {
                "fdr_id": row.id,
                "reference_no": row.reference_no,
                "institution_id": row.institution_id,
                "institution_name": row.institution.name,
                "bank_name": row.bank_name,
                "amount": row.amount,
                "amount_formatted": format_money(row.amount, row.currency),
                "currency": row.currency,
                "maturity_date": row.maturity_date,
                "review_status": row.review_status,
                "created_at": row.created_at,
            }
            for row in rows
        ],
        "count": len(rows),
        "date_range": _date_range_payload(from_date, to_date),
        "institution_id": institution_id,
    }


def release_summary(db: Session, actor: m.User, from_date=None, to_date=None, institution_id=None):
    from_date, to_date = _date_window(from_date, to_date)
    allowed = _allowed_ids(db, actor)
    if institution_id is not None and allowed is not None and institution_id not in allowed:
        raise HTTPException(403, "You are not permitted to report on this institution")
    query = db.query(m.ReleaseRequest).join(m.FDRRecord).join(m.Institution)
    if allowed is not None:
        query = query.filter(m.FDRRecord.institution_id.in_(allowed)) if allowed else query.filter(False)
    if institution_id is not None:
        query = query.filter(m.FDRRecord.institution_id == institution_id)
    if from_date:
        query = query.filter(m.ReleaseRequest.created_at >= datetime.combine(from_date, time.min))
    if to_date:
        query = query.filter(m.ReleaseRequest.created_at < datetime.combine(to_date, time.max))
    rows = query.order_by(m.ReleaseRequest.created_at.desc()).all()
    by_status = defaultdict(int)
    for row in rows:
        by_status[row.status] += 1
    return {
        "count": len(rows),
        "status_counts": dict(by_status),
        "rows": [{
            "release_request_id": row.id,
            "fdr_id": row.fdr_id,
            "reference_no": row.fdr.reference_no,
            "institution_id": row.fdr.institution_id,
            "institution_name": row.fdr.institution.name,
            "reason": row.reason,
            "status": row.status,
            "reviewer_remarks": row.reviewer_remarks,
            "created_at": row.created_at,
            "decided_at": row.decided_at,
        } for row in rows],
        "date_range": {"from_date": from_date, "to_date": to_date, "date_field": "created_at"},
        "institution_id": institution_id,
    }


def import_history(db: Session, actor: m.User, from_date=None, to_date=None):
    from_date, to_date = _date_window(from_date, to_date)
    query = db.query(m.ImportJob)
    if from_date:
        query = query.filter(m.ImportJob.created_at >= datetime.combine(from_date, time.min))
    if to_date:
        query = query.filter(m.ImportJob.created_at < datetime.combine(to_date, time.max))
    rows = query.order_by(m.ImportJob.created_at.desc()).limit(500).all()
    return {
        "count": len(rows),
        "totals": {
            "total_rows": sum(row.total or 0 for row in rows),
            "imported": sum(row.imported or 0 for row in rows),
            "rejected": sum(row.rejected or 0 for row in rows),
            "duplicates": sum(row.duplicates or 0 for row in rows),
            "skipped": sum(row.skipped or 0 for row in rows),
            "validation_errors": sum(_validation_error_count(row) for row in rows),
        },
        "rows": [{
            "import_job_id": row.id,
            "kind": row.kind,
            "filename": row.filename,
            "total": row.total,
            "imported": row.imported,
            "rejected": row.rejected,
            "duplicates": row.duplicates,
            "skipped": row.skipped,
            "status": row.status,
            "validation_error_count": _validation_error_count(row),
            "created_at": row.created_at,
            "completed_at": row.completed_at,
        } for row in rows],
        "date_range": {"from_date": from_date, "to_date": to_date, "date_field": "created_at"},
    }
