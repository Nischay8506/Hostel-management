# Cityhive implementation report

> Historical snapshot. For the subsequent integration, migration and release checks, see [the current release audit](RELEASE_AUDIT_2026-10-21.md) and [VALIDATION.md](../VALIDATION.md). Earlier limitations and counts below describe their stated audit point.

Updated 2026-10-21. This report describes the current repository state; see [VALIDATION.md](../VALIDATION.md) for executed checks and limitations.

## Implemented in this pass

- Preserved the existing React/Vite and FastAPI/SQLAlchemy application and existing Cityhive emblem asset. The public experience presents backend-driven branches, available beds, room sharing, configured prices, branch details/facility empty states, and an admission enquiry journey. The branded management/resident workspace retains its existing operations and responsive styles.
- Added financial analytics API and CSV export. Server-side aggregation provides collections, cash totals, outstanding/overdue aging, overdue invoices, fully settled invoice delays and sample sizes, on-time rates, resident and invoice-time-room tables, branch summaries, cash by staff ID, and monthly/method trends. Owner and branch-admin authorization is applied before aggregation. Reports are bounded to three years and 10,000 invoices.
- Added cash payer name, payment timestamp, and internal note fields; payment reversals are auditable and excluded from balances and analytics. Existing invoice identifiers and `SW` receipt prefixes remain unchanged. Receipt balances are calculated as of each recorded payment.
- Added OTP challenge storage and MFA flow. Password validation creates a short-lived challenge; the normal JWT is issued only on a valid OTP. Codes are HMAC protected, single use, attempt limited, resend limited, and provider failures fail closed. A non-production test provider supports automated tests.
- Added resident WhatsApp reminder consent with audit history, configurable Cloud API template transport, and WhatsApp channel outbox queueing. Reminders only enter that channel when the resident opted in, has a phone number, and provider config is present. Outbox attempt state and exponential retry scheduling are visible to staff. Real Meta delivery and template approval have not been verified.
- Added Alembic revisions `0006_auth_finance_notifications`, `0007_outbox_retry_schedule`, `0008_invoice_branch_snapshot`, and `0009_payment_time_index` for OTP, consent, payment audit/reversal metadata, outbox channels/retry time, invoice-time branch attribution, and payment report indexes. Revision 0008 backfills the branch from the resident's current branch for legacy invoices; the original invoice branch cannot be reconstructed for a resident who shifted before this migration. Transaction-date analytics are capped at 100,000 payment records.
- Added this report and [a design benchmark](ui-ux-benchmark.md).

## Important files

- `frontend/src/main.jsx`, `frontend/src/style.css`, `frontend/public/cityhive-mark.png`
- `backend/app/analytics.py`, `backend/app/whatsapp.py`, `backend/app/main.py`, `backend/app/services.py`, `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/security.py`, `backend/app/config.py`
- `backend/migrations/versions/0006_auth_finance_notifications.py`, `backend/migrations/versions/0007_outbox_retry_schedule.py`, `backend/migrations/versions/0008_invoice_branch_snapshot.py`, `backend/migrations/versions/0009_payment_time_index.py`
- `backend/tests/test_workflows.py`, `backend/tests/test_migrations.py`
- `README.md`, `VALIDATION.md`, `docs/ui-ux-benchmark.md`

## API additions

- `GET /api/analytics/financial` and `GET /api/analytics/financial.csv`
- `PUT /api/payments/{payment_id}/reverse`
- `GET/PUT /api/my/notification-preferences`
- Existing `/api/auth/login`, `/api/auth/otp/verify`, and `/api/auth/otp/resend` now enforce the two-step password plus WhatsApp OTP flow.

## Visual evidence and known limitations

The local browser was opened at the public homepage and inspected at a 615-pixel viewport. It showed the actual supplied Cityhive emblem, both configured test branch records, live room availability/pricing, and the enquiry form. The in-app browser produced an inline screenshot for visual inspection, but the desktop screenshot capture utility could not save an image to disk; therefore this repository contains no saved before/after screenshot files. A full authenticated browser journey and desktop/mobile viewport matrix remain outstanding.

WhatsApp authentication and utility templates need approved Meta templates, API version, phone-number ID, access token, account setup, and end-to-end delivery verification. The current Meta API reference was rate-limited during review. Provider status is not evidence of template approval or message delivery. OTP IP throttling currently uses in-process memory and must be moved to shared storage for multi-worker deployments. Delivery callbacks/signature-verified status webhooks and explicit opt-out inbound commands are not implemented; resident portal opt-out is available.

PostgreSQL/Docker runtime, concurrent financial writes, deployment health, SMTP delivery, and worker restart persistence have not been verified in this environment. Do not treat this as production-ready.

## Recovery and complaint-history update — 2026-10-21

- Recovery investigation is documented in [recovery-report.md](recovery-report.md). It identified the prior browser's disposable QA SQLite database and the separate database now configured for the local backend. No production PostgreSQL source or backup was found.
- Added append-only complaint audit history in Alembic revision `0011_complaint_audit`. Submission and every staff response/status update record the actor, transition, response snapshot, and timestamp. Authorized complaint reads include the history; the portal can expand the activity timeline.
- The `0011` migration was applied to an isolated copy of the earlier QA database. SQLite integrity passed and all pre-existing branch, room, admission, resident, invoice, payment, and outbox counts remained unchanged.
- Backend suite after this change: **22 passed**, one upstream Starlette/AnyIO deprecation warning. Python compilation and Vite production build passed. The original QA and current configured application databases remain unchanged.


## Management entry and complaint history — 2026-10-21

- Added a clearly labeled Management sign in action in the public navigation and footer. It opens the existing role-aware authentication flow; authorization remains enforced by the backend.
- Added complaint audit history migration `0011_complaint_audit`, scoped API history, and an expandable activity timeline in the management/resident workspace.
- Current local verification: 22 backend tests passed (one upstream deprecation warning), Python compilation passed, Alembic head `0011_complaint_audit`, SQLite health/integrity passed, and Vite production build passed. PostgreSQL/Docker and a real owner OTP login remain unverified.

## Resident identifiers and gate passes — 2026-10-21

- Added Alembic revision `0012_resident_codes_gate_passes`. Existing residents receive unique random resident references through a backfill; new resident records receive generated references. Added durable gate-pass records with random unique codes, optional expiry, and issuing/revoking staff audit fields. Pass history is preserved and downgrade is blocked.
- Added branch-scoped staff listing, issuance, validation and revocation APIs, plus resident-owned listing. Validation returns only pass status and basic resident reference/name/room details. Revoked, expired, or vacated-resident passes do not validate.
- Added management and resident Gate passes pages, printable Cityhive passes using the supplied emblem, and resident-code display in resident records. Browser QA of this new UI could not run because local browser use is disabled in Work settings.
- The configured local database was backed up to `recovery directory/staywell-pre-0012.db` (SHA-256 `8c8352de380ed9484058551ca76ad6d79c6ccbad0a6f14117de3fa4f11be1e10`) before startup applied `0012`. API health and SQLite integrity passed; existing user/branch/resident/room/invoice/payment counts were preserved.
- Verification after implementation: **23 backend tests passed**, one upstream Starlette/AnyIO deprecation warning; Python compilation passed; Alembic head is `0012_resident_codes_gate_passes`; frontend production build passed. PostgreSQL, Docker, real WhatsApp, SMTP, and authenticated browser journeys remain unverified. See [VALIDATION.md](../VALIDATION.md) for the current scope and remaining work.
