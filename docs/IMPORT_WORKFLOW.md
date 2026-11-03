# Import workflow

FDR Nexus accepts UTF-8 CSV and XLSX files through the Data & Import page.
Only Administrator and Verification Officer roles can preview or commit an
import; the backend enforces this even if the prototype role selector is
changed in the browser.

## Supported fields

Institution imports:

- Required: `name`
- Optional: `aicte_id`, `city`, `state`

FDR imports:

- Required: `aicte_id`, `bank_name`, `reference_no`, `amount`, `issue_date`,
  `maturity_date`
- Optional: `branch`, `currency`, `document_ref`, `remarks`

The preview auto-maps exact supported names and a small documented alias set
(for example, `College Name` to `name` and `FDR Number` to `reference_no`).
Users can change the mapping in the preview. Unmapped columns are displayed
and ignored; `source`, `source_details`, and official verification fields are
not importable fields.

## Validation and execution

1. The backend checks the extension, actual parser format, UTF-8 CSV content,
   headers, duplicate headers, row shape, empty files, and the configured file
   size limit.
2. The backend resolves the mapping and validates every row before any record
   is written. Names, identifiers, references, positive monetary values,
   supported dates, maturity ordering, and FDR institution references are
   checked.
3. The UI displays detected columns, mapping, valid/invalid/duplicate/skipped
   counts, and a bounded row preview.
4. The final request must include the preview token for the same file and
   mapping. Execution repeats validation to protect against a stale preview.
5. Valid rows are written inside per-row savepoints in one database
   transaction. Row validation failures, duplicates, and blank rows are
   retained in the job error report. An unexpected database error rolls back
   the request; a successful partial import is marked
   `completed_with_issues`.

Institution duplicates are detected by AICTE ID or name plus city. FDR
duplicates are detected by institution, bank name, and reference number.
Existing records are never overwritten or deleted. A repeated file and
mapping is idempotent by SHA-256 and returns the original import job instead
of creating records again.

Imported institutions and FDRs have `source=imported`, an `import_job_id`, and
source details containing the sanitized filename and original spreadsheet row.
This provenance does not imply AICTE verification.
