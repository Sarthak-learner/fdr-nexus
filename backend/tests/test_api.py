import io
import json
import os, tempfile
import sqlite3
from datetime import date, datetime, timedelta
os.environ["FDR_DATA_DIR"] = tempfile.mkdtemp()
from fastapi.testclient import TestClient
from openpyxl import Workbook
from app.main import app
from app.auth import hash_password
from app.database import SessionLocal
from app import models as m
from app.services.maturity import maturity_details
from app.services.reminders import generate_maturity_reminders
from app.services.backup import backup_database, restore_database, verify_sqlite

c = TestClient(app)
db = SessionLocal()
db.add(m.User(username="admin", password_hash=hash_password("administrator test password"), role="admin"))
db.commit()
db.close()
login = c.post("/api/auth/login", json={"username": "admin", "password": "administrator test password"})
assert login.status_code == 200
assert any("fdr_session=" in value and "HttpOnly" in value and "SameSite=strict" in value for value in login.headers.get_list("set-cookie"))
assert any("fdr_csrf=" in value and "HttpOnly" not in value for value in login.headers.get_list("set-cookie"))
ADMIN = {"X-CSRF-Token": c.cookies.get("fdr_csrf")}


def preview_and_import(kind, filename, content, mapping=None):
    preview = c.post(
        "/api/imports/preview",
        data={"kind": kind, "mapping": json.dumps(mapping or {})},
        files={"file": (filename, content)},
        headers=ADMIN,
    )
    assert preview.status_code == 200, preview.text
    p = preview.json()
    execution = c.post(
        "/api/imports",
        data={
            "kind": kind,
            "mapping": json.dumps(p["mapped_fields"]),
            "preview_token": p["preview_token"],
        },
        files={"file": (filename, content)},
        headers=ADMIN,
    )
    assert execution.status_code == 201, execution.text
    return p, execution.json()

def test_health_and_empty_dashboard():
    assert c.get("/api/health").json()["status"] == "ok"
    d = c.get("/api/dashboard/summary").json()
    assert d["institutions"] == 0 and d["fdrs"] == 0
    assert d["aicte"]["state"] == "Credentials required"
    assert d["aicte"]["working_response_verified"] is False

def test_institution_fdr_flow():
    i = c.post("/api/institutions", json={"name": "Test Institute", "aicte_id": "T-1", "city": "Pune"}, headers=ADMIN)
    assert i.status_code == 201
    assert c.post("/api/institutions", json={"name": "Other", "aicte_id": "T-1"}, headers=ADMIN).status_code == 409
    base = {"institution_id": i.json()["id"], "bank_name": "Test Bank", "reference_no": "REF123", "amount": 100000,
            "issue_date": "2024-01-01", "maturity_date": "2030-01-01"}
    assert c.post("/api/fdrs", json={**base, "maturity_date": "2023-01-01"}, headers=ADMIN).status_code == 422
    ok = c.post("/api/fdrs", json=base, headers=ADMIN)
    assert ok.status_code == 201 and ok.json()["maturity_status"] == "valid"
    assert c.post("/api/fdrs", json=base, headers=ADMIN).status_code == 409
    assert len(c.get("/api/fdrs?q=ref123").json()) == 1

def test_role_protection_and_no_bank_verified():
    # X-Role is ignored; the authenticated admin identity remains authoritative.
    assert c.patch("/api/fdrs/1", json={"review_status": "approved"}, headers={**ADMIN, "X-Role": "institution"}).status_code == 200
    assert c.patch("/api/fdrs/1", json={"verification_status": "bank_verified"}, headers=ADMIN).status_code == 422

def test_import_and_release():
    csvd = b"aicte_id,bank_name,reference_no,amount,issue_date,maturity_date\nT-1,Bank,R900,5000,2020-01-01,2021-01-01\nT-1,Bank,R100,-5,2020-01-01,2021-01-01\nZZ,Bank,R110,5,2020-01-01,2021-01-01\n"
    before_fdrs = len(c.get("/api/fdrs").json())
    _, r = preview_and_import("fdrs", "a.csv", csvd)
    assert (r["imported"], r["rejected"]) == (1, 2)
    assert r["status"] == "completed_with_issues"
    assert len(c.get("/api/fdrs").json()) - before_fdrs == r["imported"]
    assert c.post("/api/discrepancies/scan", headers=ADMIN).json()["new_findings"] >= 1
    rel = c.post("/api/release-requests", json={"fdr_id": 1, "reason": "Course closed"}, headers=ADMIN).json()
    assert rel["status"] == "pending"
    assert c.patch(f"/api/release-requests/{rel['id']}", json={"status": "approved", "reviewer_remarks": "approved after review"}, headers=ADMIN).status_code == 200

def test_institution_validation_and_provenance():
    # 1. Reject too short or whitespace name
    assert c.post("/api/institutions", json={"name": " A ", "city": "Pune"}, headers=ADMIN).status_code == 422
    assert c.post("/api/institutions", json={"name": ""}, headers=ADMIN).status_code == 422

    # 2. Manual registration with default provenance
    res = c.post("/api/institutions", json={"name": "Government Polytechnic", "aicte_id": "GP-01", "city": "Nagpur", "state": "MH"}, headers=ADMIN)
    assert res.status_code == 201
    data = res.json()
    assert data["source"] == "manual"
    assert data["aicte_id"] == "GP-01"

    # 3. Duplicate AICTE ID conflict (returns 409 with specific detail)
    dup_id = c.post("/api/institutions", json={"name": "Different Name", "aicte_id": "GP-01", "city": "Mumbai"}, headers=ADMIN)
    assert dup_id.status_code == 409
    assert "GP-01" in dup_id.json()["detail"]

    # 4. Duplicate Name + City conflict
    dup_name_city = c.post("/api/institutions", json={"name": "Government Polytechnic", "city": "Nagpur"}, headers=ADMIN)
    assert dup_name_city.status_code == 409
    assert "Nagpur" in dup_name_city.json()["detail"]

    # 5. Same name in different city is allowed
    diff_city = c.post("/api/institutions", json={"name": "Government Polytechnic", "city": "Nashik", "aicte_id": "GP-02"}, headers=ADMIN)
    assert diff_city.status_code == 201

    # 6. Multiple institutions without AICTE ID in different cities allowed
    i1 = c.post("/api/institutions", json={"name": "Private College", "city": "City A"}, headers=ADMIN)
    i2 = c.post("/api/institutions", json={"name": "Private College", "city": "City B"}, headers=ADMIN)
    assert i1.status_code == 201 and i2.status_code == 201

    # 7. Forged directory provenance is strictly rejected when directory adapter is not configured
    forged = c.post("/api/institutions", json={
        "name": "Forged Institute of Tech",
        "aicte_id": "FRG-100",
        "city": "Bengaluru",
        "source": "directory-suggested",
        "source_details": '{"source": "Forged Directory", "external_id": "EXT-100"}'
    }, headers=ADMIN)
    assert forged.status_code == 422
    assert "Cannot claim directory provenance" in forged.json()["detail"]

    # 8. Forged source_details without source is also rejected
    forged_details = c.post("/api/institutions", json={
        "name": "Forged Details Institute",
        "city": "Delhi",
        "source_details": '{"source": "Fake Source"}'
    }, headers=ADMIN)
    assert forged_details.status_code == 422

    # 9. Reject client attempt to claim official-source or verified
    spoofed = c.post("/api/institutions", json={
        "name": "Spoofed Institute",
        "source": "official-source"
    }, headers=ADMIN)
    assert spoofed.status_code == 422

    # 10. Legitimate manual registration sets source=manual and empty source_details
    legit = c.post("/api/institutions", json={
        "name": "Legitimate Institute of Tech",
        "aicte_id": "LEG-100",
        "city": "Bengaluru",
        "source": "manual"
    }, headers=ADMIN)
    assert legit.status_code == 201
    assert legit.json()["source"] == "manual"
    assert legit.json()["source_details"] == ""

def test_external_directory_lookup():
    # 1. Lookup with empty/whitespace query
    empty = c.get("/api/institutions/lookup?q=").json()
    assert empty["available"] is False
    assert "Please enter" in empty["message"]

    # 2. Lookup with unconfigured credentials
    res = c.get("/api/institutions/lookup?q=Engineering").json()
    assert res["available"] is False
    assert res["configured"] is False
    assert res["suggestions"] == []
    assert "unavailable" in res["message"].lower() or "credentials" in res["message"].lower()


def test_valid_xlsx_import_and_explicit_column_mapping():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["College Name", "AICTE Permanent ID", "City", "State"])
    sheet.append(["Mapped XLSX College", "XLSX-01", "Surat", "Gujarat"])
    stream = io.BytesIO()
    workbook.save(stream)

    preview, result = preview_and_import(
        "institutions",
        "institutions.xlsx",
        stream.getvalue(),
        {"name": "College Name", "aicte_id": "AICTE Permanent ID", "city": "City", "state": "State"},
    )
    assert preview["mapped_fields"]["name"] == "College Name"
    assert preview["summary"] == {"total": 1, "valid": 1, "invalid": 0, "duplicates": 0, "skipped": 0}
    assert result["imported"] == 1
    imported = next(i for i in c.get("/api/institutions?q=Mapped").json() if i["name"] == "Mapped XLSX College")
    assert imported["source"] == "imported"
    assert imported["import_job_id"] == result["id"]
    assert json.loads(imported["source_details"])["row"] == 2


def test_import_preview_validation_duplicates_and_retry_idempotency():
    institution_csv = b"name,aicte_id,city\nImported Duplicate College,GP-01,Nagpur\nImported New College,NEW-01,Jaipur\n"
    preview, result = preview_and_import("institutions", "institutions.csv", institution_csv)
    assert preview["summary"]["duplicates"] == 1
    assert result["imported"] == 1 and result["duplicates"] == 1
    assert result["status"] == "completed_with_issues"

    # A retry of the identical file/mapping returns the original job and does
    # not create another institution or another import job.
    retry_preview, retry = preview_and_import("institutions", "institutions.csv", institution_csv)
    assert retry_preview["preview_token"] == preview["preview_token"]
    assert retry["id"] == result["id"] and retry["replayed"] is True
    assert len(c.get("/api/institutions?q=Imported").json()) == 1

    fdr_csv = b"aicte_id,bank_name,reference_no,amount,issue_date,maturity_date\nT-1,Test Bank,REF123,100,2024-01-01,2025-01-01\nT-1,Test Bank,BAD-DATE,not-money,2024-01-01,2025-01-01\nT-1,Test Bank,BAD-DATE-2,10,not-a-date,2025-01-01\n"
    p, r = preview_and_import("fdrs", "validation.csv", fdr_csv)
    assert p["summary"]["duplicates"] == 1 and p["summary"]["invalid"] == 2
    assert (r["imported"], r["rejected"], r["duplicates"]) == (0, 2, 1)


def test_malformed_empty_unsupported_and_missing_columns_are_rejected_without_jobs():
    before = len(c.get("/api/imports").json())
    cases = [
        ("empty.csv", b""),
        ("broken.csv", b'name,city\n"unterminated'),
        ("data.txt", b"name\nUnsupported"),
        ("no-name.csv", b"city,state\nPune,MH\n"),
    ]
    for filename, content in cases:
        response = c.post(
            "/api/imports/preview",
            data={"kind": "institutions", "mapping": "{}"},
            files={"file": (filename, content)},
            headers=ADMIN,
        )
        assert response.status_code == 422, (filename, response.text)
    assert len(c.get("/api/imports").json()) == before


def test_unauthorized_preview_and_import_are_rejected():
    content = b"name\nUnauthorized College\n"
    assert c.post(
        "/api/imports/preview",
        data={"kind": "institutions"},
        files={"file": ("unauthorized.csv", content)},
    ).status_code == 403


def test_commit_requires_preview_and_failed_execution_does_not_create_a_job(monkeypatch):
    content = b"name,aicte_id\nPreview Required College,PR-01\n"
    before_jobs = len(c.get("/api/imports").json())
    missing_preview = c.post(
        "/api/imports",
        data={"kind": "institutions"},
        files={"file": ("missing-preview.csv", content)},
        headers=ADMIN,
    )
    assert missing_preview.status_code == 422
    assert len(c.get("/api/imports").json()) == before_jobs

    from app.api import routes

    preview = c.post(
        "/api/imports/preview",
        data={"kind": "institutions"},
        files={"file": ("failed-execution.csv", content)},
        headers=ADMIN,
    ).json()
    monkeypatch.setattr(routes, "execute_import", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("simulated database failure")))
    failed = c.post(
        "/api/imports",
        data={"kind": "institutions", "mapping": json.dumps(preview["mapped_fields"]), "preview_token": preview["preview_token"]},
        files={"file": ("failed-execution.csv", content)},
        headers=ADMIN,
    )
    assert failed.status_code == 422
    assert len(c.get("/api/imports").json()) == before_jobs
    assert c.get("/api/institutions?q=Preview+Required").json() == []


def csrf_headers(client):
    return {"X-CSRF-Token": client.cookies.get("fdr_csrf")}


def logged_in(username, password):
    client = TestClient(app)
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return client


def create_managed_user(username, password, role, institution_ids, active=True):
    response = c.post(
        "/api/users",
        json={"username": username, "password": password, "role": role, "institution_ids": institution_ids, "is_active": active},
        headers=ADMIN,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_authentication_login_logout_and_expired_session():
    anonymous = TestClient(app)
    assert anonymous.get("/api/dashboard/summary").status_code == 401
    assert anonymous.get("/api/institutions").status_code == 401
    assert anonymous.post("/api/auth/login", json={"username": "admin"}).status_code == 422
    assert anonymous.post("/api/auth/login", json={"username": "admin", "password": "wrong password"}).status_code == 401
    assert anonymous.get("/api/dashboard/summary", headers={"X-Role": "admin"}).status_code == 401

    admin_client = logged_in("admin", "administrator test password")
    assert admin_client.get("/api/auth/me").json()["user"]["role"] == "admin"
    assert admin_client.post("/api/auth/logout", headers=csrf_headers(admin_client)).status_code == 204
    assert admin_client.get("/api/auth/me").status_code == 401

    expired_client = logged_in("admin", "administrator test password")
    db = SessionLocal()
    session = db.query(m.AuthSession).filter_by(token_hash=__import__("app.auth", fromlist=["token_hash"]).token_hash(expired_client.cookies.get("fdr_session"))).first()
    session.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    db.close()
    assert expired_client.get("/api/auth/me").status_code == 401


def test_role_matrix_and_institution_level_isolation():
    institutions = c.get("/api/institutions").json()
    own = next(row for row in institutions if row["name"] == "Test Institute")
    other = next(row for row in institutions if row["name"] == "Government Polytechnic")
    other_fdr = c.post(
        "/api/fdrs",
        json={
            "institution_id": other["id"], "bank_name": "Other Bank", "reference_no": "OTHER-1", "amount": 100,
            "issue_date": "2024-01-01", "maturity_date": "2030-01-01",
        },
        headers=ADMIN,
    )
    assert other_fdr.status_code == 201, other_fdr.text
    other_fdr_id = other_fdr.json()["id"]

    create_managed_user("institution.user", "institution user password", "institution", [own["id"]])
    create_managed_user("review.officer", "review officer password", "officer", [other["id"]])
    inactive = create_managed_user("inactive.user", "inactive user password", "institution", [own["id"]], active=False)
    assert c.post("/api/auth/login", json={"username": "inactive.user", "password": "inactive user password"}).status_code == 401

    institution_client = logged_in("institution.user", "institution user password")
    assert c.get("/api/users").status_code == 200
    assert institution_client.get("/api/users").status_code == 403
    assert {row["id"] for row in institution_client.get("/api/institutions").json()} == {own["id"]}
    assert institution_client.get(f"/api/institutions/{own['id']}").status_code == 200
    assert institution_client.get(f"/api/institutions/{other['id']}").status_code == 403
    own_fdr = institution_client.get("/api/fdrs").json()
    assert own_fdr and all(row["institution_id"] == own["id"] for row in own_fdr)
    assert institution_client.get(f"/api/fdrs/{other_fdr_id}").status_code == 403
    assert institution_client.patch(f"/api/fdrs/{other_fdr_id}", json={"review_status": "approved"}, headers=csrf_headers(institution_client)).status_code == 403
    assert institution_client.post(
        "/api/fdrs",
        json={
            "institution_id": other["id"], "bank_name": "Impersonated Bank", "reference_no": "IMPERSONATE-1", "amount": 100,
            "issue_date": "2024-01-01", "maturity_date": "2030-01-01",
        },
        headers=csrf_headers(institution_client),
    ).status_code == 403
    assert institution_client.post("/api/users", json={"username": "escalate", "password": "escalation password", "role": "admin"}, headers=csrf_headers(institution_client)).status_code == 403

    officer_client = logged_in("review.officer", "review officer password")
    assert officer_client.get("/api/users").status_code == 403
    assert officer_client.get(f"/api/fdrs/{other_fdr_id}").status_code == 200
    assert officer_client.get(f"/api/fdrs/{own_fdr[0]['id']}").status_code == 403
    assert officer_client.post(
        "/api/institutions",
        json={"name": "Officer Cannot Register"},
        headers=csrf_headers(officer_client),
    ).status_code == 403
    assert officer_client.post(
        "/api/imports/preview",
        data={"kind": "institutions"},
        files={"file": ("officer.csv", b"name\nOfficer Cannot Import\n")},
        headers=csrf_headers(officer_client),
    ).status_code == 403
    assert officer_client.patch(f"/api/fdrs/{other_fdr_id}", json={"review_status": "approved"}, headers=csrf_headers(officer_client)).status_code == 200

    release = c.post("/api/release-requests", json={"fdr_id": other_fdr_id, "reason": "Other course closed"}, headers=ADMIN)
    assert release.status_code == 201
    decision = officer_client.patch(
        f"/api/release-requests/{release.json()['id']}",
        json={"status": "approved", "reviewer_remarks": "Reviewed by assigned officer"},
        headers=csrf_headers(officer_client),
    )
    assert decision.status_code == 200

    officer_audit = officer_client.get("/api/audit").json()
    assert all(not (row["entity"] == "fdr" and row["entity_id"] == own_fdr[0]["id"]) for row in officer_audit)

    audit_rows = c.get("/api/audit").json()
    review_audit = next(row for row in audit_rows if row["action"] == "fdr.review" and row["entity_id"] == other_fdr_id)
    assert review_audit["actor_username"] == "review.officer"
    assert review_audit["actor_user_id"] is not None


def test_csrf_and_user_management_boundaries():
    assert c.post("/api/institutions", json={"name": "No CSRF College"}).status_code == 403
    assert c.post("/api/users", json={"username": "no-csrf", "password": "no csrf password", "role": "institution"}).status_code == 403
    users = c.get("/api/users").json()
    assert any(user["username"] == "admin" and "password" not in user for user in users)
    own = next(user for user in users if user["username"] == "institution.user")
    assert c.patch("/api/users/1", json={"role": "institution"}, headers=ADMIN).status_code == 409
    institution_client = logged_in("institution.user", "institution user password")
    assert institution_client.patch(f"/api/users/{own['id']}", json={"role": "admin"}, headers=csrf_headers(institution_client)).status_code == 403


def test_maturity_threshold_precedence():
    today = date(2026, 1, 1)
    expected = {
        -1: "overdue",
        0: "matured_today",
        1: "due_tomorrow",
        7: "due_within_7_days",
        8: "due_within_15_days",
        15: "due_within_15_days",
        16: "due_within_30_days",
        30: "due_within_30_days",
        31: "active",
    }
    for days, category in expected.items():
        details = maturity_details(today + timedelta(days=days), today=today)
        assert details["maturity_category"] == category
        assert details["days_to_maturity"] == days


REMINDER_FIXTURE_NUMBER = 0


def _create_reminder_fixture():
    global REMINDER_FIXTURE_NUMBER
    REMINDER_FIXTURE_NUMBER += 1
    suffix = REMINDER_FIXTURE_NUMBER
    db = SessionLocal()
    institution = m.Institution(name=f"Reminder Institution {suffix}", city="Pune", state="Maharashtra", source="manual")
    db.add(institution)
    db.flush()
    user = m.User(
        username=f"reminder.user.{suffix}",
        password_hash=hash_password("reminder user password"),
        role="institution",
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(m.UserInstitution(user_id=user.id, institution_id=institution.id))
    fdr = m.FDRRecord(
        institution_id=institution.id,
        bank_name="Reminder Bank",
        reference_no=f"REM-FDR-{suffix:03d}",
        amount=1000,
        issue_date=date(2024, 1, 1),
        maturity_date=date.today() + timedelta(days=20),
        source="institution-submitted",
    )
    db.add(fdr)
    db.commit()
    ids = institution.id, user.id, fdr.id
    db.close()
    return ids, user.username, institution.name


def test_reminder_generation_is_idempotent_and_handles_changed_maturity():
    (institution_id, user_id, fdr_id), _, _ = _create_reminder_fixture()
    today = date.today()
    db = SessionLocal()
    first = generate_maturity_reminders(db, today=today)
    db.commit()
    assert first["created"] >= 2  # administrator plus the assigned institution user
    initial = db.query(m.MaturityReminder).filter_by(fdr_id=fdr_id, superseded_at=None).all()
    assert {row.category for row in initial} == {"due_within_30_days"}

    second = generate_maturity_reminders(db, today=today)
    db.commit()
    assert second["created"] == 0
    assert len(db.query(m.MaturityReminder).filter_by(fdr_id=fdr_id, superseded_at=None).all()) == len(initial)

    fdr = db.get(m.FDRRecord, fdr_id)
    fdr.maturity_date = today + timedelta(days=5)
    db.commit()
    changed = generate_maturity_reminders(db, today=today)
    db.commit()
    assert changed["created"] == len(initial)
    assert changed["superseded"] == len(initial)
    active = db.query(m.MaturityReminder).filter_by(fdr_id=fdr_id, superseded_at=None).all()
    old = db.query(m.MaturityReminder).filter(m.MaturityReminder.fdr_id == fdr_id, m.MaturityReminder.superseded_at.is_not(None)).all()
    assert {row.category for row in active} == {"due_within_7_days"}
    assert len(old) == len(initial)

    fdr.maturity_date = today + timedelta(days=20)
    db.commit()
    restored = generate_maturity_reminders(db, today=today)
    db.commit()
    assert restored["created"] == len(initial)
    assert {row.category for row in db.query(m.MaturityReminder).filter_by(fdr_id=fdr_id, superseded_at=None).all()} == {"due_within_30_days"}

    invalid = m.FDRRecord(
        institution_id=institution_id,
        bank_name="Invalid Reminder Bank",
        reference_no="INVALID-REMINDER",
        amount=1000,
        issue_date=today,
        maturity_date=today,
        source="manual-test",
    )
    db.add(invalid)
    db.commit()
    generate_maturity_reminders(db, today=today)
    db.commit()
    assert db.query(m.MaturityReminder).filter_by(fdr_id=invalid.id).count() == 0
    db.close()


def test_notification_scope_unread_and_read_behavior():
    (institution_id, user_id, fdr_id), username, institution_name = _create_reminder_fixture()
    db = SessionLocal()
    generate_maturity_reminders(db, today=date.today())
    db.commit()
    db.close()

    institution_client = logged_in(username, "reminder user password")
    notifications = institution_client.get("/api/notifications")
    assert notifications.status_code == 200
    rows = notifications.json()
    assert len(rows) == 1
    assert rows[0]["fdr_id"] == fdr_id
    assert rows[0]["institution_name"] == institution_name
    assert rows[0]["is_read"] is False
    assert institution_client.get("/api/notifications/unread-count").json()["unread_count"] == 1

    marked = institution_client.patch(f"/api/notifications/{rows[0]['id']}/read", headers=csrf_headers(institution_client))
    assert marked.status_code == 200
    assert marked.json()["is_read"] is True
    assert institution_client.get("/api/notifications/unread-count").json()["unread_count"] == 0
    assert institution_client.get("/api/notifications?unread_only=true").json() == []

    db = SessionLocal()
    db.query(m.UserInstitution).filter_by(user_id=user_id, institution_id=institution_id).delete()
    db.commit()
    db.close()
    assert institution_client.get("/api/notifications").json() == []
    assert institution_client.patch(f"/api/notifications/{rows[0]['id']}/read", headers=csrf_headers(institution_client)).status_code == 404

    other = logged_in("review.officer", "review officer password")
    assert other.get("/api/notifications").json() == []
    assert other.patch(f"/api/notifications/{rows[0]['id']}/read", headers=csrf_headers(other)).status_code == 404


def test_reports_match_source_records_and_enforce_scope(tmp_path):
    source_rows = c.get("/api/fdrs").json()
    summary = c.get("/api/reports/summary").json()
    assert summary["record_count"] == len(source_rows)
    assert summary["total_deposit_value"] == sum(float(row["amount"]) for row in source_rows)

    institution_report = c.get("/api/reports/institutions").json()
    assert sum(row["fdr_count"] for row in institution_report["rows"]) == len(source_rows)
    assert c.get("/api/reports/upcoming-maturities").status_code == 200
    assert c.get("/api/reports/pending-reviews").status_code == 200
    assert c.get("/api/reports/releases").status_code == 200
    assert c.get("/api/reports/imports").status_code == 200

    csv_response = c.get("/api/reports/export.csv?report=summary")
    assert csv_response.status_code == 200
    assert "total_deposit_value" in csv_response.text.splitlines()[0]

    own = next(row for row in c.get("/api/institutions").json() if row["name"] == "Test Institute")
    institution_client = logged_in("institution.user", "institution user password")
    scoped = institution_client.get("/api/reports/summary").json()
    scoped_rows = institution_client.get("/api/fdrs").json()
    assert scoped["record_count"] == len(scoped_rows)
    assert institution_client.get("/api/reports/summary", params={"institution_id": own["id"]}).status_code == 200
    assert institution_client.get("/api/reports/imports").status_code == 403

    other = next(row for row in c.get("/api/institutions").json() if row["id"] != own["id"])
    assert institution_client.get("/api/reports/summary", params={"institution_id": other["id"]}).status_code == 403
    assert institution_client.get("/api/reports/export.csv", params={"report": "institutions", "institution_id": other["id"]}).status_code == 403

    audit_rows = c.get("/api/audit").json()
    assert any(row["action"] == "report.export" and row["entity"] == "report" for row in audit_rows)
    assert any(row["action"] == "notification.read" for row in audit_rows)


def test_backup_restore_is_integrity_checked_and_does_not_touch_live_db(tmp_path):
    backup_dir = tmp_path / "backups"
    result = backup_database(output_dir=backup_dir)
    backup_path = result["path"]
    assert result["integrity"] == "ok"
    assert backup_path.startswith(str(backup_dir))
    assert verify_sqlite(backup_path)["integrity"] == "ok"

    restored = tmp_path / "recovery" / "fdr_nexus.db"
    restored_result = restore_database(backup_path, restored)
    assert restored_result["integrity"] == "ok"
    with sqlite3.connect(restored) as connection:
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] >= 1
        assert connection.execute("SELECT COUNT(*) FROM fdr_records").fetchone()[0] == c.get("/api/fdrs").json().__len__()
