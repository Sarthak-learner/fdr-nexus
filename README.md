# FDR NEXUS — Every instrument. One source of truth.
Security Deposit & FDR Management (independent project; not endorsed by AICTE).

## Run on Windows (PowerShell, two terminals)
**Backend** (Python 3.10+):
```
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
API docs: http://127.0.0.1:8000/docs
**Frontend** (Node 18+):
```
cd frontend
npm install
npm run dev
```
Open http://localhost:5173. The SQLite DB is created in `backend/data/` (gitignored) and persists across restarts.
Tests: `cd backend; pytest`. Optional dev-only fictional data: `python dev_seed/dev_seed.py` (labelled `dev-seed`, NOT AICTE data).

## Implemented (milestone 1)
Dashboard (DB-computed metrics), institutions CRUD + duplicate checks, FDR submit/list/search/filter/sort/detail/review, maturity monitoring (configurable window), in-app maturity reminders,
CSV/XLSX import with server-side preview/mapping, validation report, duplicate-safe import jobs and provenance, AICTE adapter + honest status, rule-based discrepancy scan, release/refund workflow, audit log, operational reports, CSV exports, backend tests.

## Security and setup notes
Authentication uses server-side opaque sessions in HttpOnly cookies, PBKDF2 password hashes, and CSRF protection for state-changing requests. Roles and institution scope are checked by the backend; browser storage and `X-Role` are not authorities.

For a new installation, set `BOOTSTRAP_ADMIN_USERNAME` and `BOOTSTRAP_ADMIN_PASSWORD` in `.env` before the first backend startup. The bootstrap runs only when the user table is empty; remove the bootstrap values after the administrator is created. Passwords are never stored in plaintext.

The prototype still needs a security review before real financial data is used. Document upload/storage, a live AICTE API, and automatic background-worker deployment remain out of scope.

## Maturity reminder operations

Reminder generation is a documented scheduled command, not an automatically configured background worker. Run it periodically from the backend environment:

```
cd backend
python -m app.commands.generate_reminders
```

On Windows, configure that command in Task Scheduler with the backend virtual-environment Python executable and `backend` as the working directory. The command runs in one database transaction and is safe to repeat. Configure upcoming reminder windows with `MATURITY_REMINDER_THRESHOLDS`, using descending positive day values ending in `1` (default: `30,15,7,1`). Matured-today and overdue reminders are always generated.

## Reports

Reports are generated from authorized persisted records; date filters on FDR reports apply to `maturity_date`, while release and import reports use `created_at`.

```
GET /api/reports/summary
GET /api/reports/institutions
GET /api/reports/upcoming-maturities
GET /api/reports/pending-reviews
GET /api/reports/releases
GET /api/reports/imports                 # administrator only
GET /api/reports/export.csv?report=summary
```

Use `from_date`, `to_date`, and `institution_id` where applicable. Institution users and officers receive only their assigned institution scope. CSV report exports use the same server-side authorization.

## Database migrations

The application retains its SQLite-compatible migration approach rather than adding an unconfigured Alembic dependency. Startup applies additive, versioned migrations in `schema_migrations`, preserves existing tables and rows, creates missing current-schema tables such as `maturity_reminders`, and fails startup if an upgrade cannot be completed. Current schema versions are recorded as:

- `1`: legacy compatibility columns
- `2`: current SQLAlchemy schema and maturity reminders

There is no automatic destructive downgrade. Back up the database before upgrading and use a verified restore to roll back an operator-approved change.

## Backup and recovery

Create a SQLite-consistent, timestamped and integrity-checked backup from `backend`:

```
python -m app.commands.backup_database --output-dir data/backups
```

The backup uses SQLite's online backup API and never prints credentials or password hashes. To test recovery without touching the live database:

```
python -m app.commands.restore_database data/backups/<backup-file> data/recovery-test/fdr_nexus.db
```

The restore command refuses to overwrite an existing target unless `--force` is explicitly supplied. For a live restore, stop the backend, take one more backup, restore to the configured database path, verify integrity, and start the backend again. Automated tests always restore to temporary paths.

## Windows Task Scheduler setup

Reminder generation is not configured automatically by this project. For a daily task:

1. Open **Task Scheduler** → **Create Task**.
2. Set the program to the absolute path `backend\venv\Scripts\python.exe`.
3. Set **Start in** to the absolute `backend` directory.
4. Set arguments to `-m app.commands.generate_reminders`.
5. Add a daily trigger at a quiet hour, such as 01:00, and enable **Run whether user is logged on or not** according to local policy.
6. Enable task history and configure restart-on-failure. The process returns a non-zero exit code if the database operation fails.
7. For a simple file log, use a `cmd.exe` action with arguments such as `/c "venv\Scripts\python.exe -m app.commands.generate_reminders >> data\reminders-task.log 2>&1"` while keeping **Start in** set to `backend`.

Repeated runs are idempotent and do not create duplicate reminders. Confirm the task manually with **Run** and inspect the generated output/log before relying on it operationally.
