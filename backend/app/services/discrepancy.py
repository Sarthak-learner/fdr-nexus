from datetime import date
from ..models import FDRRecord, Discrepancy

def scan(db) -> int:
    """Rule-based checks. Findings are POTENTIAL discrepancies for human review, not confirmed fraud."""
    created = 0
    fdrs = db.query(FDRRecord).all()
    by_ref = {}
    for f in fdrs:
        by_ref.setdefault(f.reference_no.strip().lower(), []).append(f)

    def add(f, rule, reason, sev):
        nonlocal created
        if db.query(Discrepancy).filter_by(fdr_id=f.id, rule=rule).first():
            return
        db.add(Discrepancy(fdr_id=f.id, rule=rule, reason=reason, severity=sev))
        created += 1

    for f in fdrs:
        if f.maturity_date <= f.issue_date:
            add(f, "invalid_dates", "Maturity date is not after issue date.", "high")
        if f.maturity_date < date.today():
            add(f, "expired", "Instrument has passed its maturity date.", "medium")
        if not (f.branch or "").strip():
            add(f, "missing_branch", "Branch is missing.", "low")
        if not (f.document_ref or "").strip():
            add(f, "missing_document", "No supporting document reference attached.", "low")
        group = by_ref[f.reference_no.strip().lower()]
        if len(group) > 1:
            others = ", ".join(str(g.id) for g in group if g.id != f.id)
            add(f, "duplicate_reference", f"Reference number also appears on record(s): {others}.", "high")
    db.commit()
    return created
