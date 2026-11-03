# AICTE integration status

## Verified status

This MVP has **no live official AICTE integration**. The repository contains no
verified official API documentation, endpoint/request format, response schema,
authorized credentials, working configuration, or genuine API response. The
presence of `AICTE_API_BASE` and `AICTE_API_KEY` environment variables would
only indicate that values were entered; it does not establish an operational
integration.

`backend/app/integrations/aicte.py` is therefore an explicit placeholder. It
reports `Credentials required` when values are absent and
`Configured - adapter not implemented` when values are present. It never
reports `Connected`, returns fabricated institutions, or sets official
verification status.

## Available workflow

Manual institution registration remains available. Authorized administrators
and verification officers can preview and commit validated CSV/XLSX imports.
Imported institutions and FDRs are marked `source=imported` and carry the
import job ID, source filename, and original spreadsheet row. Imported data is
not AICTE-verified. Development seed data remains marked `dev-seed`.

The importer accepts only supported application fields. It validates file
format, headers, mappings, row values, institution references, duplicates and
dates on the backend before saving. A preview token is required for the final
commit. Invalid, duplicate and blank rows are reported in the import job; valid
rows may be committed as a documented partial import, with the final status
reported as `completed_with_issues`.

## Requirements for a real connection

Before implementing any live adapter, obtain from AICTE:

1. Official API or downloadable-source documentation.
2. A verified endpoint and request/authentication format.
3. A verified response schema and field semantics.
4. Written authorization and required credentials.
5. A working non-production configuration and a genuine test response.

Only then should `fetch_institutions()` be implemented against the documented
source. The project will not scrape restricted portals, bypass controls, or
claim official verification from a spreadsheet.
