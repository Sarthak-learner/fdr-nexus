import csv
import io
import json
import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import models as m, schemas as s
from ..auth import (
    AuthContext,
    auth_context,
    clear_auth_cookies,
    create_session,
    current_user,
    hash_password,
    normalize_username,
    require_csrf,
    set_auth_cookies,
    user_public,
    verify_password,
)
from ..config import MAX_UPLOAD_BYTES, WARN_DAYS
from ..database import get_db
from ..integrations.aicte import AicteAdapter
from ..services.audit import log, log_system
from ..services.discrepancy import scan
from ..services.importer import execute_import, preview_import
from ..services.maturity import maturity_details
from ..services.reports import (
    import_history,
    institution_summary,
    pending_reviews,
    portfolio_summary,
    release_summary,
    upcoming_report,
)

router = APIRouter(prefix="/api")


def need(*allowed):
    def dependency(context: AuthContext = Depends(auth_context)):
        if context.user.role not in allowed:
            raise HTTPException(403, "You are not permitted to perform this action")
        return context.user

    return dependency


def mutate(*allowed):
    def dependency(
        context: AuthContext = Depends(auth_context),
        _csrf=Depends(require_csrf),
    ):
        if context.user.role not in allowed:
            raise HTTPException(403, "You are not permitted to perform this action")
        return context.user

    return dependency


def get_or_404(db, model, id_):
    obj = db.get(model, id_)
    if not obj:
        raise HTTPException(404, f"{model.__name__} {id_} not found")
    return obj


def assigned_institution_ids(db: Session, actor: m.User):
    if actor.role == "admin":
        return None
    return {row.institution_id for row in db.query(m.UserInstitution).filter_by(user_id=actor.id).all()}


def ensure_institution_access(db: Session, actor: m.User, institution_id: int):
    get_or_404(db, m.Institution, institution_id)
    allowed = assigned_institution_ids(db, actor)
    if allowed is not None and institution_id not in allowed:
        raise HTTPException(403, "You are not permitted to access this institution")


def ensure_fdr_access(db: Session, actor: m.User, fdr: m.FDRRecord):
    ensure_institution_access(db, actor, fdr.institution_id)


def fdr_dict(f):
    d = {c.name: getattr(f, c.name) for c in f.__table__.columns}
    d["institution_name"] = f.institution.name
    d.update(maturity_details(f.maturity_date))
    return d


def scoped_fdr_query(db, actor, q="", status="", institution_id=None, review_status="", sort="maturity_date", desc=False):
    qs = db.query(m.FDRRecord).join(m.Institution)
    allowed = assigned_institution_ids(db, actor)
    if allowed is not None:
        qs = qs.filter(m.FDRRecord.institution_id.in_(allowed)) if allowed else qs.filter(False)
    if q:
        like = f"%{q}%"
        qs = qs.filter(
            (m.FDRRecord.reference_no.ilike(like))
            | (m.FDRRecord.bank_name.ilike(like))
            | (m.Institution.name.ilike(like))
        )
    if institution_id is not None:
        if allowed is not None and institution_id not in allowed:
            raise HTTPException(403, "You are not permitted to access this institution")
        qs = qs.filter(m.FDRRecord.institution_id == institution_id)
    if review_status:
        qs = qs.filter(m.FDRRecord.review_status == review_status)
    sortable = {"maturity_date", "amount", "created_at", "issue_date"}
    col = getattr(m.FDRRecord, sort if sort in sortable else "maturity_date")
    rows = qs.order_by(col.desc() if desc else col.asc()).all()
    out = [fdr_dict(f) for f in rows]
    return [f for f in out if not status or status in (f["maturity_status"], f["maturity_category"])]


def public_audit(a):
    return {c.name: getattr(a, c.name) for c in a.__table__.columns}


@router.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


# ---------- authentication ----------
@router.post("/auth/login")
def login(body: s.LoginIn, response: Response, db: Session = Depends(get_db)):
    username = normalize_username(body.username)
    user = db.query(m.User).filter_by(username=username).first()
    # Keep the response identical for unknown and invalid users.
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        log_system(db, "auth.login_failed", "user", user.id if user else None, "Invalid username or password")
        db.commit()
        raise HTTPException(401, "Invalid username or password")
    raw_token, csrf_token, _session = create_session(db, user)
    log(db, user, "auth.login", "user", user.id, "Successful login")
    db.commit()
    set_auth_cookies(response, raw_token, csrf_token)
    return {"user": user_public(db, user)}


@router.post("/auth/logout", status_code=204)
def logout(response: Response, context: AuthContext = Depends(auth_context), _csrf=Depends(require_csrf), db: Session = Depends(get_db)):
    context.session.revoked_at = datetime.utcnow()
    log(db, context.user, "auth.logout", "user", context.user.id, "Logout")
    db.commit()
    clear_auth_cookies(response)
    response.status_code = 204
    return response


@router.get("/auth/me")
def me(db: Session = Depends(get_db), actor: m.User = Depends(current_user)):
    return {"user": user_public(db, actor)}


# ---------- user management ----------
def replace_assignments(db: Session, user: m.User, institution_ids):
    ids = list(dict.fromkeys(institution_ids or []))
    if user.role in {"institution", "officer"} and not ids:
        raise HTTPException(422, "This role requires at least one assigned institution")
    if ids:
        existing = {row.id for row in db.query(m.Institution.id).filter(m.Institution.id.in_(ids)).all()}
        missing = sorted(set(ids) - existing)
        if missing:
            raise HTTPException(422, f"Unknown institution assignment(s): {missing}")
    user.institution_access.clear()
    user.institution_access.extend(m.UserInstitution(institution_id=id_) for id_ in ids)


@router.get("/users")
def list_users(db: Session = Depends(get_db), _actor: m.User = Depends(need("admin"))):
    return [
        {**user_public(db, user), "created_at": user.created_at, "updated_at": user.updated_at}
        for user in db.query(m.User).order_by(m.User.username).all()
    ]


@router.post("/users", status_code=201)
def create_user(body: s.UserCreate, db: Session = Depends(get_db), actor: m.User = Depends(mutate("admin"))):
    if db.query(m.User).filter_by(username=normalize_username(body.username)).first():
        raise HTTPException(409, "A user with this username already exists")
    user = m.User(
        username=normalize_username(body.username),
        password_hash=hash_password(body.password),
        role=body.role,
        is_active=body.is_active,
    )
    db.add(user)
    db.flush()
    replace_assignments(db, user, body.institution_ids)
    log(db, actor, "user.create", "user", user.id, f"Created user '{user.username}' with role '{user.role}'")
    db.commit()
    return user_public(db, user)


@router.patch("/users/{id}")
def update_user(id: int, body: s.UserUpdate, db: Session = Depends(get_db), actor: m.User = Depends(mutate("admin"))):
    user = get_or_404(db, m.User, id)
    changes = body.model_dump(exclude_none=True)
    if user.id == actor.id and ("role" in changes or changes.get("is_active") is False):
        raise HTTPException(409, "An administrator cannot change or deactivate their own role")
    if "role" in changes:
        user.role = changes.pop("role")
    if "password" in changes:
        user.password_hash = hash_password(changes.pop("password"))
    if "is_active" in changes:
        user.is_active = changes.pop("is_active")
    if "institution_ids" in changes:
        institution_ids = changes.pop("institution_ids")
        replace_assignments(db, user, institution_ids)
    if changes:
        raise HTTPException(422, "Unsupported user update")
    # Re-validate assignments when a role changed without a new assignment list.
    if user.role in {"institution", "officer"} and not user.institution_access:
        raise HTTPException(422, "This role requires at least one assigned institution")
    log(db, actor, "user.update", "user", user.id, f"Updated user '{user.username}'")
    db.commit()
    return user_public(db, user)


# ---------- dashboard ----------
@router.get("/dashboard/summary")
def summary(db: Session = Depends(get_db), actor: m.User = Depends(current_user)):
    fdrs = db.query(m.FDRRecord).join(m.Institution)
    allowed = assigned_institution_ids(db, actor)
    if allowed is not None:
        fdrs = fdrs.filter(m.FDRRecord.institution_id.in_(allowed)) if allowed else fdrs.filter(False)
    fdr_rows = fdrs.all()
    details = [maturity_details(f.maturity_date) for f in fdr_rows]
    upcoming = sorted(
        [f for f, item in zip(fdr_rows, details) if 0 < item["days_to_maturity"] <= WARN_DAYS],
        key=lambda f: f.maturity_date,
    )[:8]
    audit_q = db.query(m.AuditLog).order_by(m.AuditLog.id.desc())
    if actor.role == "institution":
        audit_q = audit_q.filter(m.AuditLog.actor_user_id == actor.id)
    audit_q = audit_q.limit(8)
    audit = audit_q.all()
    institution_q = db.query(m.Institution)
    if allowed is not None:
        institution_q = institution_q.filter(m.Institution.id.in_(allowed)) if allowed else institution_q.filter(False)
    discrepancy_q = db.query(m.Discrepancy).join(m.FDRRecord)
    release_q = db.query(m.ReleaseRequest).join(m.FDRRecord)
    if allowed is not None:
        discrepancy_q = discrepancy_q.filter(m.FDRRecord.institution_id.in_(allowed)) if allowed else discrepancy_q.filter(False)
        release_q = release_q.filter(m.FDRRecord.institution_id.in_(allowed)) if allowed else release_q.filter(False)
    imports = db.query(m.ImportJob).count()
    unread_maturity_reminders = (
        db.query(m.MaturityReminder)
        .filter(
            m.MaturityReminder.user_id == actor.id,
            m.MaturityReminder.superseded_at.is_(None),
            m.MaturityReminder.read_at.is_(None),
        )
        .count()
    )
    return {
        "institutions": institution_q.count(), "fdrs": len(fdr_rows),
        "valid": sum(item["maturity_status"] == "valid" for item in details),
        "expiring_soon": sum(item["maturity_status"] == "expiring_soon" for item in details),
        "expired": sum(item["maturity_status"] == "expired" for item in details),
        "due_within_30_days": sum(item["maturity_category"] == "due_within_30_days" for item in details),
        "due_within_15_days": sum(item["maturity_category"] == "due_within_15_days" for item in details),
        "due_within_7_days": sum(item["maturity_category"] == "due_within_7_days" for item in details),
        "due_tomorrow": sum(item["maturity_category"] == "due_tomorrow" for item in details),
        "matured_today": sum(item["maturity_category"] == "matured_today" for item in details),
        "overdue": sum(item["maturity_category"] == "overdue" for item in details),
        "unread_maturity_reminders": unread_maturity_reminders,
        "pending_verification": sum(1 for f in fdr_rows if f.verification_status in ("unverified", "under_review")),
        "open_discrepancies": discrepancy_q.filter(m.Discrepancy.status == "open").count(),
        "pending_releases": release_q.filter(m.ReleaseRequest.status == "pending").count(),
        "upcoming": [fdr_dict(f) for f in upcoming],
        "recent_audit": [public_audit(a) for a in audit],
        "aicte": AicteAdapter().status(imports), "warning_days": WARN_DAYS,
    }


# ---------- institutions ----------
@router.get("/institutions/lookup")
def lookup_institutions(_actor: m.User = Depends(current_user), q: str = ""):
    return AicteAdapter().lookup_institutions(q)


@router.get("/institutions")
def list_institutions(q: str = "", db: Session = Depends(get_db), actor: m.User = Depends(current_user)):
    qs = db.query(m.Institution)
    allowed = assigned_institution_ids(db, actor)
    if allowed is not None:
        qs = qs.filter(m.Institution.id.in_(allowed)) if allowed else qs.filter(False)
    if q:
        like = f"%{q}%"
        qs = qs.filter((m.Institution.name.ilike(like)) | (m.Institution.aicte_id.ilike(like)) | (m.Institution.city.ilike(like)))
    rows = qs.order_by(m.Institution.name).limit(500).all()
    return [{**{c.name: getattr(i, c.name) for c in i.__table__.columns}, "fdr_count": len(i.fdrs)} for i in rows]


@router.post("/institutions", status_code=201)
def create_institution(body: s.InstitutionIn, db: Session = Depends(get_db), actor: m.User = Depends(mutate("admin"))):
    if body.aicte_id:
        existing_id = db.query(m.Institution).filter_by(aicte_id=body.aicte_id).first()
        if existing_id:
            raise HTTPException(409, f"Institution already exists with AICTE ID '{body.aicte_id}' (matches '{existing_id.name}')")
    existing_name_city = db.query(m.Institution).filter(m.Institution.name.ilike(body.name), m.Institution.city.ilike(body.city)).first()
    if existing_name_city:
        loc = f" in '{body.city}'" if body.city else ""
        raise HTTPException(409, f"Institution already exists with name '{body.name}'{loc}")
    if (body.source or "manual").strip() != "manual" or (body.source_details and body.source_details.strip()):
        raise HTTPException(422, "Cannot claim directory provenance or official provenance; use manual registration")
    i = m.Institution(name=body.name, aicte_id=body.aicte_id, city=body.city, state=body.state, source="manual", source_details="")
    db.add(i); db.flush()
    log(db, actor, "institution.create", "institution", i.id, f"{i.name} [source: {i.source}]")
    db.commit()
    return {c.name: getattr(i, c.name) for c in i.__table__.columns}


@router.get("/institutions/{id}")
def get_institution(id: int, db: Session = Depends(get_db), actor: m.User = Depends(current_user)):
    i = get_or_404(db, m.Institution, id)
    ensure_institution_access(db, actor, i.id)
    return {**{c.name: getattr(i, c.name) for c in i.__table__.columns}, "fdrs": [fdr_dict(f) for f in i.fdrs]}


# ---------- FDRs ----------
@router.get("/fdrs")
def list_fdrs(q: str = "", status: str = "", institution_id: int = None, review_status: str = "", sort: str = "maturity_date", desc: bool = False,
              db: Session = Depends(get_db), actor: m.User = Depends(current_user)):
    return scoped_fdr_query(db, actor, q, status, institution_id, review_status, sort, desc)


@router.get("/fdrs/export.csv")
def export_fdrs(status: str = "", db: Session = Depends(get_db), actor: m.User = Depends(need("admin", "officer"))):
    rows = scoped_fdr_query(db, actor, status=status)
    buf = io.StringIO()
    cols = ["id", "institution_name", "bank_name", "branch", "reference_no", "amount", "currency", "issue_date", "maturity_date", "maturity_status", "review_status", "verification_status", "source"]
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    log(db, actor, "fdr.export", "fdr", None, f"{len(rows)} rows"); db.commit()
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=fdrs.csv"})


@router.post("/fdrs", status_code=201)
def create_fdr(body: s.FDRIn, db: Session = Depends(get_db), actor: m.User = Depends(mutate("admin", "institution"))):
    ensure_institution_access(db, actor, body.institution_id)
    if db.query(m.FDRRecord).filter(m.FDRRecord.institution_id == body.institution_id, m.FDRRecord.bank_name.ilike(body.bank_name.strip()), m.FDRRecord.reference_no.ilike(body.reference_no.strip())).first():
        raise HTTPException(409, "An FDR with this bank and reference number already exists for this institution")
    data = body.model_dump(); data["bank_name"] = data["bank_name"].strip(); data["reference_no"] = data["reference_no"].strip()
    f = m.FDRRecord(**data, source="institution-submitted")
    db.add(f); db.flush(); log(db, actor, "fdr.submit", "fdr", f.id, f"{f.bank_name} {f.reference_no}"); db.commit()
    return fdr_dict(f)


@router.get("/fdrs/{id}")
def get_fdr(id: int, db: Session = Depends(get_db), actor: m.User = Depends(current_user)):
    f = get_or_404(db, m.FDRRecord, id)
    ensure_fdr_access(db, actor, f)
    hist = db.query(m.AuditLog).filter_by(entity="fdr", entity_id=id).order_by(m.AuditLog.id.desc()).all()
    return {**fdr_dict(f), "history": [public_audit(a) for a in hist], "discrepancies": [{**{c.name: getattr(d, c.name) for c in d.__table__.columns}, "reference_no": f.reference_no} for d in db.query(m.Discrepancy).filter_by(fdr_id=id)]}


@router.patch("/fdrs/{id}")
def review_fdr(id: int, body: s.FDRReview, db: Session = Depends(get_db), actor: m.User = Depends(mutate("admin", "officer"))):
    f = get_or_404(db, m.FDRRecord, id)
    ensure_fdr_access(db, actor, f)
    changes = body.model_dump(exclude_none=True)
    for k, v in changes.items():
        setattr(f, k, v)
    log(db, actor, "fdr.review", "fdr", id, json.dumps(changes)); db.commit()
    return fdr_dict(f)


@router.get("/maturities")
def maturities(days: int = WARN_DAYS, status: str = "", db: Session = Depends(get_db), actor: m.User = Depends(current_user)):
    rows = scoped_fdr_query(db, actor, status=status)
    return [f for f in rows if status or f["days_to_maturity"] <= days]


# ---------- reports ----------
REPORT_ROLES = ("admin", "officer", "institution")


@router.get("/reports/summary")
def report_summary(from_date: date | None = None, to_date: date | None = None, institution_id: int | None = None,
                   db: Session = Depends(get_db), actor: m.User = Depends(need(*REPORT_ROLES))):
    return portfolio_summary(db, actor, from_date, to_date, institution_id)


@router.get("/reports/institutions")
def report_institutions(from_date: date | None = None, to_date: date | None = None, institution_id: int | None = None,
                        db: Session = Depends(get_db), actor: m.User = Depends(need(*REPORT_ROLES))):
    return institution_summary(db, actor, from_date, to_date, institution_id)


@router.get("/reports/upcoming-maturities")
def report_upcoming_maturities(from_date: date | None = None, to_date: date | None = None, institution_id: int | None = None,
                               db: Session = Depends(get_db), actor: m.User = Depends(need(*REPORT_ROLES))):
    return upcoming_report(db, actor, from_date, to_date, institution_id)


@router.get("/reports/pending-reviews")
def report_pending_reviews(from_date: date | None = None, to_date: date | None = None, institution_id: int | None = None,
                           db: Session = Depends(get_db), actor: m.User = Depends(need(*REPORT_ROLES))):
    return pending_reviews(db, actor, from_date, to_date, institution_id)


@router.get("/reports/releases")
def report_releases(from_date: date | None = None, to_date: date | None = None, institution_id: int | None = None,
                    db: Session = Depends(get_db), actor: m.User = Depends(need(*REPORT_ROLES))):
    return release_summary(db, actor, from_date, to_date, institution_id)


@router.get("/reports/imports")
def report_imports(from_date: date | None = None, to_date: date | None = None,
                   db: Session = Depends(get_db), actor: m.User = Depends(need("admin"))):
    return import_history(db, actor, from_date, to_date)


def _csv_scalar(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str, separators=(",", ":"))
    return "" if value is None else value


@router.get("/reports/export.csv")
def export_report_csv(report: str, from_date: date | None = None, to_date: date | None = None,
                      institution_id: int | None = None, db: Session = Depends(get_db),
                      actor: m.User = Depends(need(*REPORT_ROLES))):
    if report == "summary":
        data = portfolio_summary(db, actor, from_date, to_date, institution_id)
        rows = [data]
    elif report == "institutions":
        data = institution_summary(db, actor, from_date, to_date, institution_id)
        rows = data["rows"]
    elif report == "upcoming-maturities":
        data = upcoming_report(db, actor, from_date, to_date, institution_id)
        rows = data["rows"]
    elif report == "pending-reviews":
        data = pending_reviews(db, actor, from_date, to_date, institution_id)
        rows = data["rows"]
    elif report == "releases":
        data = release_summary(db, actor, from_date, to_date, institution_id)
        rows = data["rows"]
    elif report == "imports":
        if actor.role != "admin":
            raise HTTPException(403, "You are not permitted to export import history")
        data = import_history(db, actor, from_date, to_date)
        rows = data["rows"]
    else:
        raise HTTPException(422, "Unknown report. Use summary, institutions, upcoming-maturities, pending-reviews, releases, or imports")

    fields = sorted({key for row in rows for key in row.keys()}) if rows else ["message"]
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    if rows:
        for row in rows:
            writer.writerow({key: _csv_scalar(row.get(key)) for key in fields})
    else:
        writer.writerow({"message": "No records matched the selected filters."})
    log(db, actor, "report.export", "report", None, f"{report}: {len(rows)} rows")
    db.commit()
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={report}.csv"},
    )


# ---------- in-app maturity reminders ----------
def notification_dict(notification):
    fdr = notification.fdr
    details = maturity_details(fdr.maturity_date)
    return {
        "id": notification.id,
        "fdr_id": fdr.id,
        "reference_no": fdr.reference_no,
        "institution_name": fdr.institution.name,
        "maturity_date": fdr.maturity_date,
        "category": notification.category,
        "category_label": details["maturity_label"] if notification.category == details["maturity_category"] else notification.category.replace("_", " ").title(),
        "threshold_days": notification.threshold_days,
        "generated_at": notification.generated_at,
        "read_at": notification.read_at,
        "is_read": notification.read_at is not None,
    }


def scoped_notifications(db: Session, actor: m.User):
    query = (
        db.query(m.MaturityReminder)
        .join(m.FDRRecord)
        .join(m.Institution)
        .filter(
            m.MaturityReminder.user_id == actor.id,
            m.MaturityReminder.superseded_at.is_(None),
            m.FDRRecord.issue_date < m.FDRRecord.maturity_date,
        )
    )
    allowed = assigned_institution_ids(db, actor)
    if allowed is not None:
        query = query.filter(m.FDRRecord.institution_id.in_(allowed)) if allowed else query.filter(False)
    return query


@router.get("/notifications/unread-count")
def unread_notification_count(db: Session = Depends(get_db), actor: m.User = Depends(current_user)):
    count = scoped_notifications(db, actor).filter(m.MaturityReminder.read_at.is_(None)).count()
    return {"unread_count": count}


@router.get("/notifications")
def list_notifications(unread_only: bool = False, db: Session = Depends(get_db), actor: m.User = Depends(current_user)):
    query = scoped_notifications(db, actor)
    if unread_only:
        query = query.filter(m.MaturityReminder.read_at.is_(None))
    rows = query.order_by(m.MaturityReminder.generated_at.desc()).limit(100).all()
    return [notification_dict(row) for row in rows]


@router.patch("/notifications/{id}/read")
def mark_notification_read(id: int, db: Session = Depends(get_db), actor: m.User = Depends(mutate("admin", "institution", "officer"))):
    notification = scoped_notifications(db, actor).filter(m.MaturityReminder.id == id).first()
    if not notification or notification.superseded_at is not None:
        raise HTTPException(404, "Notification not found")
    if notification.read_at is None:
        notification.read_at = datetime.utcnow()
        log(db, actor, "notification.read", "maturity_reminder", notification.id, f"fdr {notification.fdr_id}")
        db.commit()
    return notification_dict(notification)


# ---------- discrepancies ----------
@router.get("/discrepancies")
def list_discrepancies(status: str = "", db: Session = Depends(get_db), actor: m.User = Depends(current_user)):
    qs = db.query(m.Discrepancy).join(m.FDRRecord)
    allowed = assigned_institution_ids(db, actor)
    if allowed is not None:
        qs = qs.filter(m.FDRRecord.institution_id.in_(allowed)) if allowed else qs.filter(False)
    if status:
        qs = qs.filter(m.Discrepancy.status == status)
    return [{**{c.name: getattr(d, c.name) for c in d.__table__.columns}, "reference_no": d.fdr.reference_no, "institution_name": d.fdr.institution.name, "label": "Potential discrepancy (not confirmed fraud)"} for d in qs.order_by(m.Discrepancy.id.desc()).all()]


@router.post("/discrepancies/scan")
def run_scan(db: Session = Depends(get_db), actor: m.User = Depends(mutate("admin"))):
    n = scan(db); log(db, actor, "discrepancy.scan", "discrepancy", None, f"{n} new findings"); db.commit()
    return {"new_findings": n}


@router.patch("/discrepancies/{id}")
def update_discrepancy(id: int, body: s.DiscrepancyUpdate, db: Session = Depends(get_db), actor: m.User = Depends(mutate("admin", "officer"))):
    d = get_or_404(db, m.Discrepancy, id); ensure_fdr_access(db, actor, d.fdr)
    d.status, d.notes = body.status, body.notes
    log(db, actor, "discrepancy.update", "discrepancy", id, f"{body.status}: {body.notes}"); db.commit()
    return {"id": id, "status": d.status}


# ---------- release requests ----------
@router.get("/release-requests")
def list_releases(db: Session = Depends(get_db), actor: m.User = Depends(current_user)):
    qs = db.query(m.ReleaseRequest).join(m.FDRRecord)
    allowed = assigned_institution_ids(db, actor)
    if allowed is not None:
        qs = qs.filter(m.FDRRecord.institution_id.in_(allowed)) if allowed else qs.filter(False)
    return [{**{c.name: getattr(x, c.name) for c in x.__table__.columns}, "reference_no": x.fdr.reference_no, "institution_name": x.fdr.institution.name} for x in qs.order_by(m.ReleaseRequest.id.desc())]


@router.post("/release-requests", status_code=201)
def create_release(body: s.ReleaseIn, db: Session = Depends(get_db), actor: m.User = Depends(mutate("admin", "institution"))):
    fdr = get_or_404(db, m.FDRRecord, body.fdr_id); ensure_fdr_access(db, actor, fdr)
    x = m.ReleaseRequest(**body.model_dump())
    db.add(x); db.flush(); log(db, actor, "release.request", "release", x.id, f"fdr {body.fdr_id}"); db.commit()
    return {"id": x.id, "status": x.status}


@router.patch("/release-requests/{id}")
def decide_release(id: int, body: s.DecisionIn, db: Session = Depends(get_db), actor: m.User = Depends(mutate("admin", "officer"))):
    x = get_or_404(db, m.ReleaseRequest, id); ensure_fdr_access(db, actor, x.fdr)
    if x.status != "pending":
        raise HTTPException(409, "Request already decided")
    x.status, x.reviewer_remarks, x.decided_at = body.status, body.reviewer_remarks, datetime.utcnow()
    log(db, actor, f"release.{body.status}", "release", id, body.reviewer_remarks); db.commit()
    return {"id": id, "status": x.status}


# ---------- data sources / imports / audit ----------
@router.get("/data-sources")
def data_sources(db: Session = Depends(get_db), _actor: m.User = Depends(current_user)):
    return [AicteAdapter().status(db.query(m.ImportJob).count())]


async def _read_import_upload(file: UploadFile) -> bytes:
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large")
    return content


@router.post("/imports/preview")
async def preview_import_route(kind: str = Form(...), file: UploadFile = File(...), mapping: str = Form("{}"), db: Session = Depends(get_db), _actor: m.User = Depends(mutate("admin"))):
    if kind not in ("institutions", "fdrs"):
        raise HTTPException(400, "kind must be 'institutions' or 'fdrs'")
    content = await _read_import_upload(file)
    try:
        return preview_import(db, kind, file.filename or "upload", content, mapping)
    except ValueError as e:
        db.rollback(); raise HTTPException(422, str(e))
    except Exception:
        logging.getLogger(__name__).exception("import preview failed"); db.rollback(); raise HTTPException(422, "Could not read file. Check it is a valid CSV/XLSX.")


@router.post("/imports", status_code=201)
async def run_import(kind: str = Form(...), file: UploadFile = File(...), preview_token: str = Form(...), mapping: str = Form("{}"), db: Session = Depends(get_db), actor: m.User = Depends(mutate("admin"))):
    if kind not in ("institutions", "fdrs"):
        raise HTTPException(400, "kind must be 'institutions' or 'fdrs'")
    content = await _read_import_upload(file)
    try:
        job, replayed = execute_import(db, kind, file.filename or "upload", content, mapping, preview_token)
    except ValueError as e:
        db.rollback(); raise HTTPException(422, str(e))
    except Exception:
        logging.getLogger(__name__).exception("import failed"); db.rollback(); raise HTTPException(422, "Import could not be completed. No changes were committed.")
    job.created_by_user_id = actor.id
    action = "import.replay" if replayed else "import.run"
    log(db, actor, action, "import", job.id, f"{kind}: {job.imported} imported, {job.rejected} rejected, {job.duplicates} duplicate, {job.skipped} skipped")
    db.commit()
    return import_dict(job, replayed=replayed)


def import_dict(j, replayed=False):
    d = {c.name: getattr(j, c.name) for c in j.__table__.columns}; d["errors"] = json.loads(j.errors or "[]"); d["column_mapping"] = json.loads(j.column_mapping or "{}"); d["replayed"] = replayed; return d


@router.get("/imports")
def list_imports(db: Session = Depends(get_db), _actor: m.User = Depends(need("admin"))):
    return [import_dict(j) for j in db.query(m.ImportJob).order_by(m.ImportJob.id.desc()).limit(50)]


@router.get("/imports/{id}")
def get_import(id: int, db: Session = Depends(get_db), _actor: m.User = Depends(need("admin"))):
    return import_dict(get_or_404(db, m.ImportJob, id))


@router.get("/audit")
def audit(db: Session = Depends(get_db), actor: m.User = Depends(need("admin", "officer"))):
    query = db.query(m.AuditLog)
    if actor.role == "officer":
        allowed = assigned_institution_ids(db, actor) or set()
        fdr_ids = {row.id for row in db.query(m.FDRRecord.id).filter(m.FDRRecord.institution_id.in_(allowed)).all()} if allowed else set()
        release_ids = {row.id for row in db.query(m.ReleaseRequest.id).join(m.FDRRecord).filter(m.FDRRecord.institution_id.in_(allowed)).all()} if allowed else set()
        discrepancy_ids = {row.id for row in db.query(m.Discrepancy.id).join(m.FDRRecord).filter(m.FDRRecord.institution_id.in_(allowed)).all()} if allowed else set()
        query = query.filter(
            (m.AuditLog.actor_user_id == actor.id)
            | ((m.AuditLog.entity == "fdr") & m.AuditLog.entity_id.in_(fdr_ids or {-1}))
            | ((m.AuditLog.entity == "release") & m.AuditLog.entity_id.in_(release_ids or {-1}))
            | ((m.AuditLog.entity == "discrepancy") & m.AuditLog.entity_id.in_(discrepancy_ids or {-1}))
        )
    return [public_audit(a) for a in query.order_by(m.AuditLog.id.desc()).limit(200)]
