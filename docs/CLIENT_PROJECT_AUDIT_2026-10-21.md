# Cityhive Luxury PG's and Co-space

> Historical snapshot. For the subsequent integration, migration and release checks, see [the current release audit](RELEASE_AUDIT_2026-10-21.md) and [VALIDATION.md](../VALIDATION.md). Earlier limitations and counts below describe their stated audit point.

## Project audit and client handover

**Review date:** 21 October 2026
**Project:** Cityhive PG and co-space management platform
**Review basis:** Current application source, project documentation, automated backend checks, frontend production build, and local SQLite database inspection.

## Executive summary

The existing Staywell application has been rebranded as Cityhive and extended with public accommodation enquiries, branch and resident operations, room allocation, fee plans, invoicing, payment records, settlements, reminders, analytics, and complaint handling. The original Cityhive emblem is used in the application. Existing business workflows and records were preserved during the recent QR scope correction.

The application has working backend and frontend components, and the current automated checks pass. This review does **not** certify the project for production deployment: Docker/PostgreSQL, real email and WhatsApp delivery, full authenticated browser journeys, production security review, and operational recovery procedures still need validation in the target environment.

## Application capabilities

### Public website and admission

- Cityhive-branded public website with branch listings, branch details, room-sharing options, availability, and configured charges sourced from the backend.
- Public admission enquiries with duplicate-submission protection, staff review, approval, and conversion into a resident account.
- Branch publication controls prevent incomplete or unpublished branch records from appearing as public listings.
- The local database currently has no published branches, so live public listings and admission submission are not available from that local dataset until branch information and inventory are configured and published.

### Staff, owner, and resident access

- Owner, branch-admin, and resident accounts use password sign-in followed by a one-time password challenge before a normal session is issued.
- Owners can manage branches and assign branch administrators. Branch-admin data access is restricted to assigned branches; residents see their own records.
- New residents receive unique Cityhive resident reference IDs. Staff can review identity documents manually; the application stores only an optional last-four suffix and does not perform government identity verification.

### Branch and accommodation operations

- Branch setup, publication, room creation and editing, capacity checks, resident allocation, and allocation history.
- Resident requests and staff decisions for stay extensions, room shifts, and vacating.
- Approved shifts preserve allocation history. Scheduled vacating observes the configured notice period and outstanding invoice balance rules.
- Basic gate-pass records support staff issue/revocation and resident/staff viewing and printing. QR generation, scanning, and pass-code validation are out of scope and removed.

### Fees and finance

- Effective-dated fee plans by branch and sharing type, with configured billing/due days and optional labelled monthly charges.
- Invoice records preserve the applicable room, price, discounts, additional charges, and due date as billing snapshots.
- Staff can record cash, UPI, or bank payments, including partial payments. Receipts and invoice PDFs are available through the existing application.
- Payment reversals are audited; reversed amounts are excluded from outstanding balances and analytics.
- Separate deposit and advance ledgers, reasoned deductions, settlement decisions, and actual refund records are supported. Approval alone does not mark a refund as paid.
- Fixed discounts are supported. Percentage-discount policy, payment-gateway processing, automatic debt offsets, and automatic deposit forfeiture/refund policy are not implemented.
- Financial analytics include collections, balances, overdue aging, room/resident summaries, and CSV export, with branch scope applied to staff access.
- Existing `SW` invoice and receipt identifiers were retained to protect historical numbering; issued identifiers were not rewritten.

### Complaints and communications

- Residents can submit complaints. Authorized staff can assign, respond, and record resolution notes; complaint history and assignment choices are branch-scoped.
- Email reminders use an outbox with deduplication and retry behavior. WhatsApp OTP and reminder paths exist, with resident reminder consent controls.
- Automated tests use a test WhatsApp provider. Live Meta delivery, approved templates, callbacks, live SMTP delivery, and production scheduling have not been verified.

## Technical overview

- **Frontend:** React with Vite; responsive public website and authenticated owner/admin/resident workspace.
- **Backend:** FastAPI with SQLAlchemy and role- and branch-scoped API authorization.
- **Database:** Alembic-managed schema. The configured local database is SQLite; the supplied Compose configuration defines PostgreSQL, but that stack has not been run in this environment.
- **Branding:** Customer-facing application identity is Cityhive. Legacy database and session identifiers remain internally for compatibility; they are not intended as visible business branding.

## Verification performed

- Backend suite: **26 passed** with one upstream Starlette/AnyIO deprecation warning.
- Focused resident admission and gate-pass access tests: **2 passed**.
- Python compilation: passed.
- Frontend production build: passed with Vite 6.4.1; 1,578 modules transformed. The bundled Node runtime was used because npm is not available on the environment PATH.
- API route inspection confirmed no QR or pass-validation route remains. Updated tests confirm removed routes return 404 and resident/branch-admin gate-pass access remains scoped.
- Local database revision: `0013_fees_settlements_complaint_assignment`. It contains 26 tables; current counts show one branch and one user, with no resident, room, admission, invoice, payment, or gate-pass records. This describes the local configured database only and should not be treated as the client's production dataset.
- Before the QR scope correction, the local database was backed up. Source and backup passed SQLite integrity checks; table sets and row counts matched after the code change, with zero foreign-key violations. No schema migration or database data change was made for QR removal.
- Browser-based authenticated acceptance testing was not performed in this review. Automated API tests are useful coverage but do not replace client acceptance testing in a browser.

## Findings and items to complete before launch

1. **Confirm the production environment.** Select and configure the production database, run the Compose/PostgreSQL migrations, verify health checks, persistent storage, backups, and restore procedures. PostgreSQL and Docker operation are not verified yet.
2. **Complete actual business setup.** Configure the real branches, contacts, rules, room inventory, sharing capacities, prices, charges, and publication details. The current local database does not contain that operating data.
3. **Configure and verify delivery services.** Set production email and WhatsApp credentials, approved message templates, sender identity, and delivery monitoring. Confirm consent and opt-out behavior with real test accounts.
4. **Run role-based browser acceptance tests.** Use owner, branch-admin, and resident accounts at both branches. Exercise admissions, room allocations and shifts, extension and vacating, invoices, payments, receipts, settlements, reminders, and complaints, including denied cross-branch and cross-resident access.
5. **Complete deployment security review.** Review production secrets, TLS, logging and personal-data handling, rate limiting across multiple workers, dependency/security updates, backup access, and incident response. No formal penetration test or production security sign-off is included in this audit.
6. **Confirm client policies.** Agree how discounts, deposits, advances, deductions, refunds, notice exceptions, and invoice corrections should be handled. The application records the configured/manual workflow; it does not infer business policy.

## Release assessment

**Current assessment: suitable for continued client review and controlled acceptance testing; production readiness is not established.** The core management workflows are present and automated backend checks pass, but production infrastructure, live communications, populated client data, full browser journeys, and formal security/recovery checks remain outstanding.

This audit describes the checked code and local configuration as of the review date. Production behavior depends on the target database, environment configuration, external providers, and client acceptance results.
