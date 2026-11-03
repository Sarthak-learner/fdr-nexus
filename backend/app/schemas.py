from datetime import date
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator, model_validator

class InstitutionIn(BaseModel):
    name: str = Field(min_length=2, max_length=300)
    aicte_id: Optional[str] = Field(default=None, max_length=64)
    city: str = ""
    state: str = ""
    source: Optional[str] = "manual"
    source_details: Optional[str] = ""

    @field_validator("name")
    @classmethod
    def strip_name(cls, v):
        v = (v or "").strip()
        if len(v) < 2:
            raise ValueError("Institution name must have at least 2 characters")
        return v

    @field_validator("aicte_id")
    @classmethod
    def blank_none(cls, v):
        cleaned = (v or "").strip()
        return cleaned if cleaned else None

    @field_validator("city", "state")
    @classmethod
    def strip_str(cls, v):
        return (v or "").strip()

class FDRIn(BaseModel):
    institution_id: int
    bank_name: str = Field(min_length=2, max_length=200)
    branch: str = ""
    reference_no: str = Field(min_length=3, max_length=100)
    amount: float = Field(gt=0)
    currency: str = "INR"
    issue_date: date
    maturity_date: date
    document_ref: str = ""
    remarks: str = ""
    @model_validator(mode="after")
    def dates(self):
        if self.maturity_date <= self.issue_date:
            raise ValueError("maturity_date must be after issue_date")
        return self

class FDRReview(BaseModel):
    review_status: Optional[Literal["pending", "approved", "rejected", "changes_requested"]] = None
    # 'bank_verified' deliberately not settable: needs an authorized verification source
    verification_status: Optional[Literal["unverified", "under_review", "rejected"]] = None
    renewal_status: Optional[Literal["none", "submitted", "renewed"]] = None
    remarks: Optional[str] = None

class ReleaseIn(BaseModel):
    fdr_id: int
    reason: str = Field(min_length=5)

class DecisionIn(BaseModel):
    status: Literal["approved", "rejected"]
    reviewer_remarks: str = Field(min_length=3)

class DiscrepancyUpdate(BaseModel):
    status: Literal["open", "resolved", "dismissed"]
    notes: str = ""


class LoginIn(BaseModel):
    username: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=256)


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=12, max_length=256)
    role: Literal["admin", "institution", "officer"]
    institution_ids: list[int] = Field(default_factory=list, max_length=100)
    is_active: bool = True

    @field_validator("username")
    @classmethod
    def clean_username(cls, value):
        value = value.strip().casefold()
        if not value or any(ch.isspace() for ch in value):
            raise ValueError("Username must not contain whitespace")
        return value

    @field_validator("institution_ids")
    @classmethod
    def unique_institutions(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("institution_ids must not contain duplicates")
        return value


class UserUpdate(BaseModel):
    password: Optional[str] = Field(default=None, min_length=12, max_length=256)
    role: Optional[Literal["admin", "institution", "officer"]] = None
    institution_ids: Optional[list[int]] = Field(default=None, max_length=100)
    is_active: Optional[bool] = None

    @field_validator("institution_ids")
    @classmethod
    def unique_institutions(cls, value):
        if value is not None and len(value) != len(set(value)):
            raise ValueError("institution_ids must not contain duplicates")
        return value
