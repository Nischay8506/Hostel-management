# Recovery report — 2026-10-21

> Historical snapshot. For the subsequent integration, migration and release checks, see [the current release audit](RELEASE_AUDIT_2026-10-21.md) and [VALIDATION.md](../VALIDATION.md). Earlier limitations and counts below describe their stated audit point.

## Scope and preservation

- Project root inspected: `project workspace`.
- The current React/Vite frontend, FastAPI backend, SQLAlchemy models, services, schemas, tests, Alembic revisions `0001`–`0010`, and Cityhive assets are present. The API route inventory still includes authentication, branch management, admissions, rooms, residents, allocation history, identity review, invoices/PDF, payments/receipts/reversals, reminders/outbox, complaints, stay requests, dashboards, and financial analytics/CSV.
- The project has no `.git` directory. A Codex session log exists and records source edits; it does not contain a full historical source-tree snapshot. No alternate project copy or source archive was found in the inspected Downloads, Desktop, and Documents locations.
- Both root and backend `.env` files were left unchanged. Their secrets were not copied into this report.
- Before further implementation, a permission-restricted copy of the project and a consistent SQLite backup were created under `recovery directory/`. A SHA-256 file manifest is stored there. The source project and databases remain in place.

## Database findings

- The earlier browser API explicitly ran with `DATABASE_URL=sqlite:////tmp/cityhive-qa-20261020.db`. Prior validation records describe this as disposable QA data. The file is still present, has no WAL/SHM sidecars, passes SQLite `integrity_check`, and is at Alembic revision `0005_invoice_numbers`.
- That QA database contains two test branches, two test rooms, one test admission, one test resident, one invoice, one payment, and three outbox rows. It is preserved unchanged at `/tmp/cityhive-qa-20261020.db` and copied to the protected recovery directory. These records are synthetic QA data and must not be shown as real public properties or resident data.
- The current backend configuration points to `backend/staywell.db`. That database passes integrity checking and is at revision `0010_branch_publication`; it contains one default branch and one user, but no rooms, admissions, residents, invoices, payments, or complaints. It was also backed up before any further work.
- The apparent loss of branch/workflow data in the browser came from restarting the API against `backend/staywell.db` instead of the earlier disposable QA database. Separately, the new public publication control hides branches whose `published` flag is false. No API route functions were removed.
- No Docker executable or PostgreSQL container/volume is available in this environment. No production PostgreSQL data source or backup was found. Therefore no production or real resident records have been recovered or verified.
- A separate disposable clone of the QA database was upgraded from revision `0005` to `0010`. SQLite integrity remained `ok`; counts for branches, rooms, admissions, residents, invoices, payments, and outbox were unchanged; the invoice retained branch attribution; and both test branches defaulted to unpublished. The recovered original and consistent backup were not migrated.

## Checks performed after protection

- `backend/.venv/bin/python -m pytest -q`: **22 passed**, one upstream Starlette/AnyIO deprecation warning. Tests use isolated fixtures; no application database was used.
- `backend/.venv/bin/python -m compileall -q app migrations tests`: passed.
- Bundled Node/Vite production build: passed (Vite 6.4.1; 1,578 modules transformed).

## Recovery limits and next safe steps

- The available QA database is suitable for isolated verification only, not as a live business database.
- Keep `backend/staywell.db` and `/tmp/cityhive-qa-20261020.db` as separate preserved sources. Do not merge QA rows into a real business database.
- To recover actual business records, locate the configured PostgreSQL volume/server or a verified business database backup, then snapshot and validate it before migration. No such source is available in this workspace.
- Public listings remain empty until an authorized owner configures complete branch details, adds inventory, and explicitly publishes a genuine branch.


## Follow-up implementation — 2026-10-21

- Added `0011_complaint_audit` with append-only complaint events and response/status history. The migration was tested on a separate clone of the recovered QA database, preserving existing QA row counts.
- After the pre-migration snapshot was secured, the configured local database `backend/staywell.db` was upgraded from `0010` to `0011` so the running API matches the updated source. It still passes SQLite integrity; branch/resident/room/invoice/payment counts are unchanged at 1/0/0/0/0. Complaint events count is zero. The QA source and recovery backups remain untouched.
- The local API health check returned `{"status":"ok"}`. The Vite page was re-inspected; it exposes both Resident sign in and Management sign in. Public branch and admission sections remain empty because the configured database has no complete, published genuine branches.
- Backend: 22 passed, one upstream deprecation warning. Python compilation and Vite production build passed after the source changes.

## Gate-pass follow-up — 2026-10-21

After preserving a fresh copy at `recovery directory/staywell-pre-0012.db`, the configured local SQLite DB was upgraded from `0011_complaint_audit` to `0012_resident_codes_gate_passes`. The new migration backfills opaque resident codes and creates gate-pass storage. The source QA database and its separate recovery snapshots were not changed. API health is `ok`; SQLite integrity is `ok`; users, branches, residents, rooms, invoices, and payments remain at `1/1/0/0/0/0`. The complete current test suite is 23 passed with one upstream deprecation warning; Python compilation and the Vite production build passed. Docker/PostgreSQL and browser automation remain unavailable in this environment.
