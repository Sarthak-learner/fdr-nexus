"""Authoritative CSV/XLSX import parsing, validation, preview and execution.

The importer deliberately has one analysis path.  Preview and execution both
run the same server-side validation; execution re-runs it so a stale preview
cannot bypass a duplicate or reference check.
"""

import csv
import hashlib
import io
import json
import math
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..models import FDRRecord, ImportJob, Institution


SUPPORTED_FIELDS = {
    "institutions": ("name", "aicte_id", "city", "state"),
    "fdrs": (
        "aicte_id",
        "bank_name",
        "branch",
        "reference_no",
        "amount",
        "currency",
        "issue_date",
        "maturity_date",
        "document_ref",
        "remarks",
    ),
}

REQUIRED_FIELDS = {
    "institutions": ("name",),
    "fdrs": ("aicte_id", "bank_name", "reference_no", "amount", "issue_date", "maturity_date"),
}

# These are explicit aliases for the fields already supported by the database;
# no unrelated spreadsheet column is inferred.
FIELD_ALIASES = {
    "name": {"name", "institution_name", "college_name", "institute_name"},
    "aicte_id": {"aicte_id", "aicte_permanent_id", "institution_aicte_id"},
    "city": {"city", "institution_city"},
    "state": {"state", "institution_state"},
    "bank_name": {"bank_name", "bank"},
    "branch": {"branch", "bank_branch"},
    "reference_no": {"reference_no", "reference_number", "fdr_reference", "fdr_number", "fdr_no", "receipt_no"},
    "amount": {"amount", "fdr_amount", "deposit_amount"},
    "currency": {"currency"},
    "issue_date": {"issue_date", "date_of_issue"},
    "maturity_date": {"maturity_date", "date_of_maturity"},
    "document_ref": {"document_ref", "document_reference"},
    "remarks": {"remarks", "remark", "notes"},
}

PREVIEW_ROWS = 50
MAX_REPORTED_ERRORS = 500


def safe_filename(filename: str) -> str:
    """Return a harmless display name without accepting path components."""

    candidate = re.split(r"[\\/]", str(filename or ""))[-1].strip().replace("\x00", "")
    if not candidate or candidate in {".", ".."}:
        return "upload"
    return candidate[:300]


def content_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _normalise_header(value) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _header_info(headers):
    display = []
    normalised = []
    seen = set()
    for value in headers:
        shown = str(value or "").strip()
        key = _normalise_header(shown)
        if not key:
            raise ValueError("The file contains a blank column header")
        if key in seen:
            raise ValueError(f"Duplicate column header '{shown}'")
        seen.add(key)
        display.append(shown)
        normalised.append(key)
    if not display:
        raise ValueError("The file has no headers")
    return display, normalised


def read_rows(filename: str, content: bytes):
    """Read a supported file and preserve original spreadsheet row numbers."""

    name = safe_filename(filename).lower()
    if not content:
        raise ValueError("The uploaded file is empty")

    if name.endswith(".csv"):
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("CSV files must be valid UTF-8 text") from exc
        reader = csv.reader(io.StringIO(text), strict=True)
        try:
            header_row = next(reader)
        except StopIteration as exc:
            raise ValueError("The uploaded file is empty") from exc
        headers, normalised_headers = _header_info(header_row)
        rows = []
        try:
            for row_number, values in enumerate(reader, start=2):
                if not values:
                    values = [""] * len(normalised_headers)
                if len(values) != len(normalised_headers):
                    raise ValueError(
                        f"Malformed CSV row {row_number}: expected {len(normalised_headers)} columns, found {len(values)}"
                    )
                rows.append((row_number, dict(zip(normalised_headers, values))))
        except csv.Error as exc:
            raise ValueError(f"Malformed CSV content near row {reader.line_num}") from exc
        if not rows:
            raise ValueError("The file contains headers but no data rows")
        return {"headers": headers, "normalised_headers": normalised_headers, "rows": rows}

    if name.endswith(".xlsx"):
        try:
            from openpyxl import load_workbook

            workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as exc:
            raise ValueError("The uploaded file is not a valid XLSX workbook") from exc
        try:
            worksheet = workbook.active
            iterator = worksheet.iter_rows(values_only=True)
            try:
                header_row = next(iterator)
            except StopIteration as exc:
                raise ValueError("The uploaded workbook has no headers") from exc
            headers, normalised_headers = _header_info(header_row)
            rows = []
            for row_number, values in enumerate(iterator, start=2):
                values = list(values)
                if len(values) < len(normalised_headers):
                    values.extend([None] * (len(normalised_headers) - len(values)))
                if len(values) > len(normalised_headers) and any(value not in (None, "") for value in values[len(normalised_headers):]):
                    raise ValueError(
                        f"Malformed XLSX row {row_number}: values exist outside the header columns"
                    )
                rows.append((row_number, dict(zip(normalised_headers, values[: len(normalised_headers)]))))
            if not rows:
                raise ValueError("The workbook contains headers but no data rows")
            return {"headers": headers, "normalised_headers": normalised_headers, "rows": rows}
        finally:
            workbook.close()

    raise ValueError("Only .csv or .xlsx files are supported")


def _parse_mapping(mapping, kind: str, headers):
    if kind not in SUPPORTED_FIELDS:
        raise ValueError("kind must be 'institutions' or 'fdrs'")
    if mapping in (None, "", {}):
        requested = {}
    elif isinstance(mapping, str):
        try:
            requested = json.loads(mapping)
        except json.JSONDecodeError as exc:
            raise ValueError("Column mapping must be valid JSON") from exc
    else:
        requested = mapping
    if not isinstance(requested, dict):
        raise ValueError("Column mapping must be an object of application field to source column")

    source_by_normalised = {_normalise_header(header): header for header in headers}
    mapping_out = {}
    used_sources = set()
    for target, source in requested.items():
        if target not in SUPPORTED_FIELDS[kind]:
            raise ValueError(f"Unsupported application field '{target}' for {kind} import")
        if source in (None, ""):
            continue
        source_key = _normalise_header(source)
        if source_key not in source_by_normalised:
            raise ValueError(f"Mapped source column '{source}' was not detected in the file")
        if source_key in used_sources:
            raise ValueError(f"Source column '{source_by_normalised[source_key]}' is mapped more than once")
        used_sources.add(source_key)
        mapping_out[target] = source_by_normalised[source_key]

    # Auto-map only known aliases.  An explicit mapping always wins.
    for target in SUPPORTED_FIELDS[kind]:
        if target in mapping_out:
            continue
        aliases = FIELD_ALIASES.get(target, {target})
        matches = [key for key in source_by_normalised if key in aliases]
        if len(matches) == 1 and matches[0] not in used_sources:
            mapping_out[target] = source_by_normalised[matches[0]]
            used_sources.add(matches[0])

    missing = [field for field in REQUIRED_FIELDS[kind] if field not in mapping_out]
    if missing:
        raise ValueError(
            f"Missing required column(s): {', '.join(missing)}. Detected: {', '.join(headers)}"
        )
    return mapping_out


def _value(row, mapping, field):
    source = mapping.get(field)
    return row.get(_normalise_header(source)) if source else None


def _text(value) -> str:
    return str(value).strip() if value is not None else ""


def _is_blank_row(row) -> bool:
    return all(value is None or (isinstance(value, str) and not value.strip()) for value in row.values())


def parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _text(value)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"invalid date '{text}' (use YYYY-MM-DD or DD/MM/YYYY)")


def parse_amount(value) -> float:
    if isinstance(value, bool) or value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError("amount is required and must be a monetary value")
    text = _text(value).replace(",", "")
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", text):
        raise ValueError("amount must be a valid monetary value")
    try:
        decimal = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("amount must be a valid monetary value") from exc
    if not decimal.is_finite() or decimal <= 0:
        raise ValueError("amount must be greater than 0")
    amount = float(decimal)
    if not math.isfinite(amount):
        raise ValueError("amount is outside the supported numeric range")
    return amount


def _validate_institution(row, mapping):
    name = _text(_value(row, mapping, "name"))
    if not name:
        raise ValueError("name is required")
    if len(name) < 2:
        raise ValueError("name must have at least 2 characters")
    if len(name) > 300:
        raise ValueError("name must be at most 300 characters")
    aicte_id = _text(_value(row, mapping, "aicte_id")) or None
    if aicte_id and len(aicte_id) > 64:
        raise ValueError("aicte_id must be at most 64 characters")
    city, state = _text(_value(row, mapping, "city")), _text(_value(row, mapping, "state"))
    if len(city) > 120 or len(state) > 120:
        raise ValueError("city and state must be at most 120 characters")
    return {"name": name, "aicte_id": aicte_id, "city": city, "state": state}


def _validate_fdr(row, mapping, institutions_by_aicte):
    aicte_id = _text(_value(row, mapping, "aicte_id"))
    if not aicte_id:
        raise ValueError("aicte_id is required to identify the institution")
    institution = institutions_by_aicte.get(aicte_id)
    if not institution:
        raise ValueError(f"no institution with aicte_id '{aicte_id}' - import institutions first")

    bank_name, reference_no = _text(_value(row, mapping, "bank_name")), _text(_value(row, mapping, "reference_no"))
    if len(bank_name) < 2:
        raise ValueError("bank_name is required and must have at least 2 characters")
    if len(bank_name) > 200:
        raise ValueError("bank_name must be at most 200 characters")
    if len(reference_no) < 3:
        raise ValueError("reference_no is required and must have at least 3 characters")
    if len(reference_no) > 100:
        raise ValueError("reference_no must be at most 100 characters")
    branch = _text(_value(row, mapping, "branch"))
    if len(branch) > 200:
        raise ValueError("branch must be at most 200 characters")
    currency = (_text(_value(row, mapping, "currency")) or "INR").upper()
    if len(currency) > 8:
        raise ValueError("currency must be at most 8 characters")
    amount = parse_amount(_value(row, mapping, "amount"))
    issue_date = parse_date(_value(row, mapping, "issue_date"))
    maturity_date = parse_date(_value(row, mapping, "maturity_date"))
    if maturity_date <= issue_date:
        raise ValueError("maturity_date must be after issue_date")
    document_ref = _text(_value(row, mapping, "document_ref"))
    if len(document_ref) > 300:
        raise ValueError("document_ref must be at most 300 characters")
    return {
        "institution_id": institution.id,
        "bank_name": bank_name,
        "branch": branch,
        "reference_no": reference_no,
        "amount": amount,
        "currency": currency,
        "issue_date": issue_date,
        "maturity_date": maturity_date,
        "document_ref": document_ref,
        "remarks": _text(_value(row, mapping, "remarks")),
        "institution": institution,
    }


def _key(value) -> str:
    return _text(value).casefold()


def _analysis(db, kind: str, filename: str, content: bytes, mapping=None):
    parsed = read_rows(filename, content)
    resolved_mapping = _parse_mapping(mapping, kind, parsed["headers"])
    institutions = db.query(Institution).all()
    institutions_by_aicte = {_text(item.aicte_id): item for item in institutions if _text(item.aicte_id)}
    existing_institution_ids = {_text(item.aicte_id) for item in institutions if _text(item.aicte_id)}
    existing_institution_names = {(_key(item.name), _key(item.city)) for item in institutions}
    existing_fdrs = {
        (item.institution_id, _key(item.bank_name), _key(item.reference_no))
        for item in db.query(FDRRecord).all()
    }

    outcomes = []
    seen_institution_ids = set()
    seen_institution_names = set()
    seen_fdrs = set()
    for row_number, row in parsed["rows"]:
        outcome = {"row": row_number, "raw": row, "status": "valid", "data": None, "problem": None}
        if _is_blank_row(row):
            outcome.update(status="skipped", problem="blank row skipped")
            outcomes.append(outcome)
            continue
        try:
            if kind == "institutions":
                data = _validate_institution(row, resolved_mapping)
                duplicate = data["aicte_id"] and (
                    data["aicte_id"] in existing_institution_ids or data["aicte_id"] in seen_institution_ids
                )
                name_key = (_key(data["name"]), _key(data["city"]))
                duplicate = duplicate or name_key in existing_institution_names or name_key in seen_institution_names
                if duplicate:
                    outcome.update(status="duplicate", problem="duplicate institution already exists or appears earlier in this file; skipped")
                else:
                    outcome["data"] = data
                    if data["aicte_id"]:
                        seen_institution_ids.add(data["aicte_id"])
                    seen_institution_names.add(name_key)
            else:
                data = _validate_fdr(row, resolved_mapping, institutions_by_aicte)
                fdr_key = (data["institution_id"], _key(data["bank_name"]), _key(data["reference_no"]))
                if fdr_key in existing_fdrs or fdr_key in seen_fdrs:
                    outcome.update(status="duplicate", problem="duplicate FDR already exists or appears earlier in this file; skipped")
                else:
                    outcome["data"] = data
                    seen_fdrs.add(fdr_key)
        except ValueError as exc:
            outcome.update(status="invalid", problem=str(exc))
        outcomes.append(outcome)

    summary = {
        "total": len(outcomes),
        "valid": sum(item["status"] == "valid" for item in outcomes),
        "invalid": sum(item["status"] == "invalid" for item in outcomes),
        "duplicates": sum(item["status"] == "duplicate" for item in outcomes),
        "skipped": sum(item["status"] == "skipped" for item in outcomes),
    }
    return parsed, resolved_mapping, outcomes, summary


def _public_error(outcome):
    return {"row": outcome["row"], "type": outcome["status"], "problem": outcome["problem"]}


def _mapping_json(mapping):
    return json.dumps(mapping, sort_keys=True, separators=(",", ":"))


def preview_token(kind: str, content: bytes, mapping) -> str:
    material = f"{kind}:{content_sha256(content)}:{_mapping_json(mapping)}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def preview_import(db, kind: str, filename: str, content: bytes, mapping=None):
    parsed, resolved_mapping, outcomes, summary = _analysis(db, kind, filename, content, mapping)
    mapped_preview = []
    for outcome in outcomes[:PREVIEW_ROWS]:
        mapped_values = {
            field: _text(outcome["raw"].get(_normalise_header(source)))
            for field, source in resolved_mapping.items()
        }
        mapped_preview.append({
            "row": outcome["row"],
            "status": outcome["status"],
            "values": mapped_values,
            "problem": outcome["problem"],
        })
    used_headers = {_normalise_header(source) for source in resolved_mapping.values()}
    return {
        "filename": safe_filename(filename),
        "kind": kind,
        "preview_token": preview_token(kind, content, resolved_mapping),
        "detected_columns": parsed["headers"],
        "mapped_fields": resolved_mapping,
        "unmapped_columns": [h for h in parsed["headers"] if _normalise_header(h) not in used_headers],
        "supported_fields": list(SUPPORTED_FIELDS[kind]),
        "required_fields": list(REQUIRED_FIELDS[kind]),
        "summary": summary,
        "rows": mapped_preview,
        "errors": [_public_error(item) for item in outcomes if item["status"] != "valid"][:MAX_REPORTED_ERRORS],
    }


def _existing_job(db, kind, file_hash, mapping_json):
    return (
        db.query(ImportJob)
        .filter(
            ImportJob.kind == kind,
            ImportJob.file_sha256 == file_hash,
            ImportJob.column_mapping == mapping_json,
            ImportJob.status.in_(("completed", "completed_with_issues")),
        )
        .order_by(ImportJob.id.asc())
        .first()
    )


def execute_import(db, kind: str, filename: str, content: bytes, mapping, supplied_preview_token: str):
    parsed, resolved_mapping, outcomes, summary = _analysis(db, kind, filename, content, mapping)
    expected_token = preview_token(kind, content, resolved_mapping)
    if not supplied_preview_token or supplied_preview_token != expected_token:
        raise ValueError("This file must be previewed successfully before it can be imported")

    file_hash = content_sha256(content)
    mapping_json = _mapping_json(resolved_mapping)
    previous = _existing_job(db, kind, file_hash, mapping_json)
    if previous:
        return previous, True

    job = ImportJob(
        kind=kind,
        filename=safe_filename(filename),
        total=summary["total"],
        column_mapping=mapping_json,
        file_sha256=file_hash,
        status="completed_with_issues" if any(summary[key] for key in ("invalid", "duplicates", "skipped")) else "completed",
    )
    db.add(job)
    db.flush()

    errors = []
    imported = rejected = duplicates = skipped = 0
    for outcome in outcomes:
        if outcome["status"] == "invalid":
            rejected += 1
            errors.append(_public_error(outcome))
            continue
        if outcome["status"] == "duplicate":
            duplicates += 1
            errors.append(_public_error(outcome))
            continue
        if outcome["status"] == "skipped":
            skipped += 1
            errors.append(_public_error(outcome))
            continue

        data = dict(outcome["data"])
        data.pop("institution", None)
        provenance = json.dumps({"source": "file-import", "filename": job.filename, "row": outcome["row"]})
        if kind == "institutions":
            record = Institution(**data, source="imported", source_details=provenance, import_job_id=job.id)
        else:
            record = FDRRecord(**data, source="imported", source_details=provenance, import_job_id=job.id)
        try:
            # The unique constraint remains the final race-safe duplicate guard
            # if another transaction changes the database after preview.
            with db.begin_nested():
                db.add(record)
                db.flush()
        except IntegrityError:
            duplicates += 1
            errors.append({"row": outcome["row"], "type": "duplicate", "problem": "duplicate record detected while saving; skipped"})
        except SQLAlchemyError:
            raise
        else:
            imported += 1

    job.imported = imported
    job.rejected = rejected
    job.duplicates = duplicates
    job.skipped = skipped
    job.status = "completed" if rejected == 0 and duplicates == 0 and skipped == 0 else "completed_with_issues"
    job.errors = json.dumps(errors[:MAX_REPORTED_ERRORS])
    job.completed_at = datetime.utcnow()
    db.flush()
    return job, False
