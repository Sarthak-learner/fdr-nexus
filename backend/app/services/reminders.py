"""Idempotent in-app maturity reminder generation."""

from datetime import date, datetime

from sqlalchemy.orm import Session

from .. import models as m
from .maturity import maturity_details, reminder_details


def _authorized_users(db: Session, institution_id: int):
    """Yield active users who may see an institution's FDR reminders."""
    assigned = (
        db.query(m.User)
        .join(m.UserInstitution, m.UserInstitution.user_id == m.User.id)
        .filter(m.UserInstitution.institution_id == institution_id, m.User.is_active.is_(True))
        .all()
    )
    admins = db.query(m.User).filter(m.User.role == "admin", m.User.is_active.is_(True)).all()
    seen = set()
    for user in [*admins, *assigned]:
        if user.id not in seen:
            seen.add(user.id)
            yield user


def generate_maturity_reminders(db: Session, today: date | None = None) -> dict:
    """Create missing reminders and supersede stale-date reminders.

    This function does not commit. The caller owns the transaction, allowing
    the CLI command and tests to use the same behavior safely.
    """
    today = today or date.today()
    created = 0
    superseded = 0
    examined = 0
    stored_fdrs = db.query(m.FDRRecord).join(m.Institution).all()
    valid_fdrs = [
        fdr for fdr in stored_fdrs
        if fdr.issue_date is not None
        and fdr.maturity_date is not None
        and fdr.maturity_date > fdr.issue_date
    ]
    active_fdr_ids = {fdr.id for fdr in valid_fdrs}

    # A deleted/invalid record cannot create a reminder. Existing reminders
    # for deleted records are not expected because of the FK relationship, but
    # stale records are closed defensively if encountered.
    for reminder in db.query(m.MaturityReminder).all():
        if reminder.fdr_id not in active_fdr_ids and reminder.superseded_at is None:
            reminder.superseded_at = datetime.utcnow()
            superseded += 1

    for fdr in valid_fdrs:
        details = maturity_details(fdr.maturity_date, today=today)
        category, threshold, _label = reminder_details(details)
        if threshold is None:
            continue
        examined += 1
        current_snapshot = fdr.maturity_date
        for user in _authorized_users(db, fdr.institution_id):
            active_for_fdr = (
                db.query(m.MaturityReminder)
                .filter(
                    m.MaturityReminder.user_id == user.id,
                    m.MaturityReminder.fdr_id == fdr.id,
                    m.MaturityReminder.superseded_at.is_(None),
                )
                .all()
            )
            for old in active_for_fdr:
                if (
                    old.maturity_date_snapshot != current_snapshot
                    or old.category != category
                    or old.threshold_days != threshold
                ):
                    old.superseded_at = datetime.utcnow()
                    superseded += 1

            existing = (
                db.query(m.MaturityReminder)
                .filter(
                    m.MaturityReminder.user_id == user.id,
                    m.MaturityReminder.fdr_id == fdr.id,
                    m.MaturityReminder.category == category,
                    m.MaturityReminder.threshold_days == threshold,
                    m.MaturityReminder.maturity_date_snapshot == current_snapshot,
                )
                .first()
            )
            if existing:
                if existing.superseded_at is not None:
                    # A date can legitimately be corrected back to a prior
                    # value. Reuse the uniquely identified row instead of
                    # attempting to insert a duplicate historical instance.
                    existing.superseded_at = None
                    existing.read_at = None
                    existing.generated_at = datetime.utcnow()
                    created += 1
                continue
            db.add(m.MaturityReminder(
                user_id=user.id,
                fdr_id=fdr.id,
                category=category,
                threshold_days=threshold,
                maturity_date_snapshot=current_snapshot,
                generated_at=datetime.utcnow(),
            ))
            created += 1

    return {"created": created, "superseded": superseded, "examined": examined}
