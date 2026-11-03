from datetime import datetime, date
from sqlalchemy import (Column, Integer, String, Float, Date, DateTime, Text, Boolean, ForeignKey,
                        UniqueConstraint, Index)
from sqlalchemy.orm import relationship
from .database import Base

now = datetime.utcnow


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(300), nullable=False)
    role = Column(String(20), nullable=False, index=True)  # admin | institution | officer
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)
    institution_access = relationship("UserInstitution", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("AuthSession", back_populates="user", cascade="all, delete-orphan")
    maturity_reminders = relationship("MaturityReminder", back_populates="user", cascade="all, delete-orphan")


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    csrf_token_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=now)
    last_seen_at = Column(DateTime, default=now)
    expires_at = Column(DateTime, nullable=False, index=True)
    revoked_at = Column(DateTime, nullable=True)
    user = relationship("User", back_populates="sessions")

class Institution(Base):
    __tablename__ = "institutions"
    id = Column(Integer, primary_key=True)
    aicte_id = Column(String(64), unique=True, nullable=True, index=True)
    name = Column(String(300), nullable=False, index=True)
    city = Column(String(120), default="")
    state = Column(String(120), default="")
    # provenance: manual | directory-suggested | imported | official-source | dev-seed
    source = Column(String(40), default="manual")
    source_details = Column(Text, default="")  # import filename/row or other provenance detail
    import_job_id = Column(Integer, ForeignKey("import_jobs.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=now)
    fdrs = relationship("FDRRecord", back_populates="institution")
    user_access = relationship("UserInstitution", back_populates="institution", cascade="all, delete-orphan")


class UserInstitution(Base):
    __tablename__ = "user_institutions"
    __table_args__ = (UniqueConstraint("user_id", "institution_id", name="uq_user_institution_access"),)
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=now)
    user = relationship("User", back_populates="institution_access")
    institution = relationship("Institution", back_populates="user_access")

class FDRRecord(Base):
    __tablename__ = "fdr_records"
    __table_args__ = (UniqueConstraint("institution_id", "bank_name", "reference_no", name="uq_fdr"),
                      Index("ix_fdr_maturity", "maturity_date"))
    id = Column(Integer, primary_key=True)
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=False)
    bank_name = Column(String(200), nullable=False)
    branch = Column(String(200), default="")
    reference_no = Column(String(100), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(8), default="INR")
    issue_date = Column(Date, nullable=False)
    maturity_date = Column(Date, nullable=False)
    document_ref = Column(String(300), default="")
    source = Column(String(40), default="institution-submitted")  # institution-submitted | imported | dev-seed
    review_status = Column(String(30), default="pending")  # pending|approved|rejected|changes_requested
    # bank_verified is reserved for a legitimate authorized verification source (not implemented)
    verification_status = Column(String(30), default="unverified")  # unverified|under_review|rejected|bank_verified
    renewal_status = Column(String(30), default="none")  # none|submitted|renewed
    remarks = Column(Text, default="")
    source_details = Column(Text, default="")  # import filename/row or other provenance detail
    import_job_id = Column(Integer, ForeignKey("import_jobs.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)
    institution = relationship("Institution", back_populates="fdrs")
    maturity_reminders = relationship("MaturityReminder", back_populates="fdr", cascade="all, delete-orphan")


class MaturityReminder(Base):
    __tablename__ = "maturity_reminders"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "fdr_id", "category", "maturity_date_snapshot",
            name="uq_maturity_reminder_instance",
        ),
        Index("ix_maturity_reminder_user_active", "user_id", "superseded_at", "read_at"),
    )
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    fdr_id = Column(Integer, ForeignKey("fdr_records.id"), nullable=False, index=True)
    category = Column(String(40), nullable=False)
    threshold_days = Column(Integer, nullable=False)
    maturity_date_snapshot = Column(Date, nullable=False)
    generated_at = Column(DateTime, default=now, nullable=False)
    read_at = Column(DateTime, nullable=True)
    superseded_at = Column(DateTime, nullable=True)
    user = relationship("User", back_populates="maturity_reminders")
    fdr = relationship("FDRRecord", back_populates="maturity_reminders")

class Discrepancy(Base):
    __tablename__ = "discrepancies"
    id = Column(Integer, primary_key=True)
    fdr_id = Column(Integer, ForeignKey("fdr_records.id"), nullable=False, index=True)
    rule = Column(String(60), nullable=False)
    reason = Column(Text, nullable=False)
    severity = Column(String(12), default="medium")
    detected_at = Column(DateTime, default=now)
    status = Column(String(20), default="open")  # open|resolved|dismissed
    notes = Column(Text, default="")
    fdr = relationship("FDRRecord")

class ReleaseRequest(Base):
    __tablename__ = "release_requests"
    id = Column(Integer, primary_key=True)
    fdr_id = Column(Integer, ForeignKey("fdr_records.id"), nullable=False, index=True)
    reason = Column(Text, nullable=False)
    status = Column(String(20), default="pending")  # pending|approved|rejected
    reviewer_remarks = Column(Text, default="")
    created_at = Column(DateTime, default=now)
    decided_at = Column(DateTime, nullable=True)
    fdr = relationship("FDRRecord")

class ImportJob(Base):
    __tablename__ = "import_jobs"
    id = Column(Integer, primary_key=True)
    kind = Column(String(20))  # institutions | fdrs
    filename = Column(String(300))
    total = Column(Integer, default=0)
    imported = Column(Integer, default=0)
    rejected = Column(Integer, default=0)
    duplicates = Column(Integer, default=0)
    skipped = Column(Integer, default=0)
    status = Column(String(30), default="completed")  # completed|completed_with_issues
    column_mapping = Column(Text, default="{}")
    file_sha256 = Column(String(64), nullable=True, index=True)
    errors = Column(Text, default="[]")  # JSON list of {row, problem}
    created_at = Column(DateTime, default=now)
    completed_at = Column(DateTime, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    actor_role = Column(String(20))
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    actor_username = Column(String(120), nullable=True)
    action = Column(String(60), index=True)
    entity = Column(String(40))
    entity_id = Column(Integer, nullable=True)
    detail = Column(Text, default="")
    at = Column(DateTime, default=now, index=True)
