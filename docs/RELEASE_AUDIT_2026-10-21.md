# Cityhive Luxury PG's and Co-space — integration and release audit

Date: 21 October 2026 (Asia/Kolkata). This report supersedes the earlier client audit for current implementation status. **Client acceptance and production readiness are not yet established.** The source has been extended and checked locally; the changes have not been pushed or deployed during this work.

## What was found and repaired

The existing React/FastAPI product, original emblem, admissions, authentication, financial records, stay workflows and basic passes were retained. The initial working tree was clean at `b9f97989e403c22d8501da6b7055dc46e0b1873f`; the observed live JavaScript/CSS matched the initial local build. The baseline was rerun: 26 backend tests passed and Vite built successfully.

The live deployment's `/api/health` and `/api/branches` returned the same HTML homepage as `/`. Local development had been relying on Vite's proxy. In addition, authenticated dashboard loading requested camel-case resource URLs such as `/gatePasses`, `/feePlans` and `/complaintAssignees`, which did not match the backend. The shared API client now uses one configurable backend base for public requests, login, dashboards, exports and PDFs; the resource mapping is corrected. It rejects HTML masquerading as an API result and reports recoverable network errors.

Other repaired gaps:

- Backend container omitted Alembic migrations/configuration. Both are included, the service runs as a non-root user, and the entrypoint reads the AppSail listening port.
- Direct Alembic commands previously defaulted to SQLite regardless of the deployment environment. The configured database now supplies the default URL. Existing revision files were not modified.
- A historical revision name exceeds Alembic's default PostgreSQL version-column width. The migration environment widens that bookkeeping column while retaining historical IDs; PostgreSQL execution still needs real-environment verification.
- Percentage discounts now have an optional, disabled-by-default approval workflow with scope, cap, complete billing months, non-overlap, no stacking with fixed discounts, revocation, and immutable issued invoice snapshots.
- Receipts are available as authorized PDFs; the original text receipt API remains valid. Long documents paginate. Resident reference, branch, invoice, payment and balance information come from persisted records.
- Enrolled residents lacking an identity suffix can complete a manual last-four review with attribution/history. No full Aadhaar collection, document-upload system, or official verification claim was added.
- Resident notification/admission history, owner service status, published-branch setup guidance, configured contact email and approved photo URLs are available in the portal.
- OTP throttles are stored as HMAC-keyed database buckets. Expiry, attempts and cooldown are configurable. Authentication still fails closed until required OTP verification succeeds.
- A supervised worker / one-shot scheduler / authenticated job endpoint is available. It records starts, success and failure; PostgreSQL advisory locking is designed to prevent overlapping runs. Reminder queueing includes a configurable upcoming window and rechecks balance/consent before delivery.
- SMTP supports TLS and optional authentication. WhatsApp callbacks validate signatures, bound payload size, handle replay idempotently and avoid regressing delivered/read status. Real provider delivery has not been verified.
- Financial settlement averages were being reset after calculation. They now remain available in resident/room reports. As-of payment cutoffs and India business-date grouping are applied, day/week/month collection totals are aggregated in SQL, room collection totals are separate from payments against selected invoices, and overdue drill-down filters the exact invoice.
- Public discovery/contact/enquiry layouts were rebuilt within the existing application with the supplied emblem, configured inventory and clearly labeled existing illustrative imagery. Authenticated typography, forms, keyboard focus handling and responsive rules were extended. No fabricated branch, room, contact, pricing or review records were added.

## Feature and verification inventory

“API verified” below means disposable automated tests, not browser acceptance or production verification. Every registered API is listed in [API_ROUTE_INVENTORY.md](API_ROUTE_INVENTORY.md), including its access dependency. Visual and deployed journeys remain unverified across the UI.

| Feature / user journey | Current status and evidence | Main source / dependency |
|---|---|---|
| Homepage, navigation, original brand, contact anchors | Implemented; build and source checks pass. Browser appearance, keyboard behavior and viewport matrix unverified | `PublicSite.jsx`, `public.css`, existing `index.html` and emblem |
| Public branches, room options, pricing, availability | Existing API verified, including two test branches/publication/isolation. Configured local database has no published branch | `main.py`, `PublicSite.jsx`; management must supply real inventory/details |
| Admission submit/review/enroll/history | Deduplication, approval and account enrollment tested. History UI/API added. Full browser lifecycle unverified | `main.py`, `schemas.py`, `main.jsx`, `PortalExtras.jsx` |
| Owner, branch-admin, resident sign-in | Password/OTP/session timing, expiry, replay, resend and required-password-change API tests pass | `security.py`, `main.py`, `rate_limits.py`, `whatsapp.py`; live provider required |
| Room allocation/edit/history; shift/extension/vacating | Existing API workflows and capacity/notice/balance guards pass; source locks retained/extended | `main.py`, `models.py`, existing portal; real PostgreSQL concurrency unverified |
| Manual identity review | Last-four suffix and reviewer/history tests pass; UI supports missing suffix after enrollment | `main.py`, `schemas.py`, `main.jsx` |
| Fee plans, invoice snapshots, fixed discounts | Existing effective-plan succession and immutable invoice tests pass | `main.py`, existing migration 0013 |
| Percentage discount approvals | New tests pass for disabled mode, approval scope/cap, invalid percentage, overlap, fixed exclusion, role isolation, revocation and old invoice preservation | New `resident_discounts`, migration 0014, `PortalExtras.jsx`; opt-in management configuration |
| Cash/UPI/bank, partial payments, reversals | Existing idempotency, audit, balance and branch-isolation tests pass; UI supports search and actual receipt date | `main.py`, `main.jsx` |
| Invoice and receipt PDF access | PDF responses, brand/reference content and cross-resident/branch denial pass. PDF visual/multilingual acceptance unverified | `services.py`, download APIs and shared frontend client |
| Deposit/advance/settlement/actual refund | Existing tests pass; approval does not record money paid | Existing ledger/settlement models, APIs and finance dialog |
| Financial analytics and CSV | Existing plus new as-of/timezone/settlement-average tests pass. Day/week/month and historical room collections implemented in server-side aggregation | `analytics.py`, `main.py`, analytics UI; large-data load testing outstanding |
| Resident notifications/preferences | Owned history and pending-reminder opt-out checks pass; no other resident's messages exposed | `Outbox.user_id`, `services.py`, `PortalExtras.jsx` |
| Reminder execution / email outbox | Mock SMTP success/retry/cancellation and TLS ordering pass; worker state/failure/authorization tests pass | `worker.py`, `services.py`; production scheduler and inbox verification outstanding |
| WhatsApp authentication/reminders/callbacks | Mock transport payload, signature/replay/status-order checks pass. Approved templates and real delivery unverified | `whatsapp.py`, webhook handlers; Meta account setup required |
| Complaints/assignment/responses/history | Existing branch-scoped workflow and resident isolation tests pass | Existing models/APIs and portal |
| Resident IDs/basic gate passes | Existing ownership, branch scope, issue/revoke and removed-route tests pass; print is source checked only | Existing gate-pass API/portal; no QR feature |
| Deployment diagnostics/backup tooling | Startup, schema, worker status and local backup/integrity checks executed; production settings guard tested | `serve.py`, `worker.py`, `scripts/db_maintenance.py`, `DEPLOYMENT.md` |
| Slate → deployed FastAPI → PostgreSQL | **Broken/blocked externally**. Slate returns HTML for API paths; real backend URL and target database are unknown | Hosting configuration, frontend `VITE_API_BASE_URL`, backend CORS |
| Browser, Docker and PostgreSQL runtime | **Not verified**. Supported browser disabled; Docker command absent; no local PostgreSQL tools/listener detected | Enable browser and provide a disposable PostgreSQL/container environment |

## Data and migration evidence

- The running original API was confirmed to use `backend/staywell.db`, revision `0013_fees_settlements_complaint_assignment`, with one user, one unpublished branch and no other business records. This is local development data, not a statement about production.
- An initial private recovery directory outside the repository contains a verified Git bundle, SQLite backup, private copies of the existing env files and an inventory. No secrets are committed.
- Immediately before local migration, another online backup was made outside the repository. SHA-256: `e39084e1705494398f1159792ebf48337553bf295f54846db158125381c9adfe`.
- The original API was stopped; source data was compared to the backup; migration 0014 was applied to that same local database. All existing columns/values in all 25 business tables were compared and preserved. Only migration bookkeeping and additive schema changed. The three new tables are empty.
- Final local schema has 29 tables, one user, one branch, no published branch, and zero rooms/admissions/residents/invoices/payments/passes. SQLite integrity is `ok`; foreign-key violations are zero. Both `.env` files remain byte-for-byte unchanged. All historical revision files match Git HEAD.
- The API was restarted against the same file. Direct API and Vite-proxied `/api/health`, `/api/build` and `/api/branches` return HTTP 200 JSON. The empty public list is deliberate; no QA fixtures were inserted.
- The new tests also start a real HTTP process against a disposable SQLite file, run migrations, stop/restart it and confirm user identity/hash and a test marker persist. This is **SQLite restart verification only**.
- Production database migrations, backups, restores and deployments were not attempted because its identity/access could not be established.

Machine-readable evidence: [local state and artifact hashes](local-release-evidence.json), [live HTTP responses](live-http-evidence.json). Test results and exact commands: [VALIDATION.md](../VALIDATION.md).

## Test results

- Baseline rerun: **26 backend tests passed**, one upstream Starlette/AnyIO deprecation warning; original Vite build passed.
- Final suite: **40 backend tests passed**, the same upstream warning; **6 frontend API tests passed**.
- Python compilation: passed for application, migrations, scripts and tests.
- Frontend production build: passed, Vite 6.4.1, 1,583 modules. A deliberately invalid loopback production API setting was rejected as expected; the normal build was then rerun successfully.
- Migration checks: fresh/legacy populated schemas, upgrade replay, historical ID preservation and before/after column/value comparison passed on SQLite.
- `git diff HEAD --check`: passed. No dependencies were added or removed. Existing QR dependency removal was preserved.
- `docker compose version` and `docker compose up --build -d`: both failed immediately with `zsh:1: command not found: docker`. No Docker service or volume was touched.
- Browser: unavailable through the supported tool, so no screenshots, browser console results or completed visual journeys are claimed. Use [the precise manual acceptance checklist](visual-qa/ACCEPTANCE.md).

## Legacy identifiers retained

| Identifier | Classification and reason |
|---|---|
| `staywell-token` | Session-storage compatibility in login/logout. Not visible business branding |
| `staywell.db` | Existing local database filename and private configuration/recovery references; preserved to keep the correct database |
| `SW-...` | Existing invoice/receipt numbering, PDF filenames and receipt emails. No issued identifier or sequence was renamed |
| `gate_passes.pass_code` | Required legacy unique field populated for existing schema compatibility; not exposed in pass responses, printed passes or validation routes |
| `gate_pass_validation_events` | Dormant table from unchanged revision 0013; no current model/API/UI/worker writes it; historical records retained |
| QR wording in tests/docs | Scope documentation and negative tests requiring removed endpoints to return 404; no generator/scanner dependency or UI was reintroduced |
| `cityhive.local` | Local example sender and existing SMTP Message-ID domain; production sender must be verified. It is not a public business-contact claim |

Source searches found no customer-facing Staywell business label. Documents retain historical names where they explain compatibility/recovery; generated invoice/receipt tests assert Cityhive identity.

## Outstanding acceptance blockers and limitations

1. **Identify the backend and persistent database.** The owner reported that both exist but did not know their addresses. Follow the service-discovery steps in [DEPLOYMENT.md](DEPLOYMENT.md), then verify target/backup, migrate safely, deploy the API/worker and set Slate's real API URL/CORS. A frontend-only push would not fix the observed hosting fault.
2. **Run actual browser acceptance.** Enable the supported browser or use an authorized manual tester. Responsive CSS, focus trapping and build success do not prove layout, accessibility, real PDF downloads or completed user journeys.
3. **Run disposable PostgreSQL and Docker verification.** Check historical migrations including version-column handling, concurrency (allocation, payment, approval, OTP and worker locks), durable storage and restarts. SQLite cannot establish these results.
4. **Verify live OTP, reminder and SMTP delivery.** Supply account-approved templates, current API version, verified sender and worker schedule. Confirm callbacks and consent cancellation. Provider configuration flags and mock success are not delivery evidence. Inbound WhatsApp STOP commands remain outside the implemented portal opt-out mechanism.
5. **Supply genuine branch content.** No real property photo/contact/inventory was invented. The preserved local database has one incomplete branch, not two configured properties. Management must enter and publish the actual business data; don't import disposable QA branches. The existing generated room image is explicitly illustrative.
6. **Document operating limits.** Reports bound invoice/payment volumes and aggregate collections in SQL, but large-data load testing is outstanding. The current lightweight PDF renderer substitutes unsupported non-ASCII characters; a licensed embedded Unicode font/renderer is needed before issuing documents with names/scripts it cannot represent. PDFs require visual acceptance. SMTP delivery remains at least once across acceptance/crash boundaries.
7. **Finish production operational/security review.** Confirm proxy trust, platform log redaction, backups/restoration, monitoring/alerts, credential recovery and approved deployment settings on the real host. No penetration-test or production security certification is claimed.

## Files changed

See [RELEASE_FILES.md](RELEASE_FILES.md) for the exact working-tree file inventory. No existing database was replaced, no applied migration was edited, no production secrets were committed, and no Git push or live deployment was performed in this pass.
