# PDF gap completion — 22 October 2026

The supplied `cityhive-gap-analysis.pdf` contains 38 numbered findings. It describes an older project snapshot: many P1/P2 items already existed. This update adds the remaining application features to the existing React/FastAPI project and keeps historical records. The original PDF is unchanged. This is a local implementation and verification record; it does not claim a production deployment or live message delivery.

## Feature-by-feature result

| PDF item | Current result |
|---|---|
| 1 Resident IDs and gate passes | Existing unique resident references and private, scoped printable passes retained. |
| 2 Deposits | Existing deposit ledger, deductions and settlement workflow retained. |
| 3 Sharing-based advances | Added `advance_amount` to effective-dated branch/sharing fee plans; shown in public availability, fee plans and resident finance accounts. Recorded money remains separate from the configured amount. |
| 4 Percentage discounts | Existing staff approval, effective months, scope, caps and invoice snapshots retained; management enables the configuration. |
| 5 Refund workflow | Existing preparation, approval and actual refund recording retained; added branded settlement PDF. |
| 6 Vacating balance guard | Approval now rejects an outstanding invoice balance; the actual scheduled departure checks again. |
| 7 Complaint assignment | Existing scoped assignees, status, notes and history retained. |
| 8 Dashboard KPIs | Added pending admissions/extensions, departures within 30 days, overdue invoices, failed reminders and actual cash collected this calendar month. Branch scope applies. |
| 9 Due dates | Existing fee-plan billing/due-day configuration retained. |
| 10 Fee plans | Existing sharing/effective-date pricing extended with advances. Scheduled monthly billing now runs through the supervised worker, respecting billing day and invoice uniqueness. |
| 11 Admission notifications | Added consent-based WhatsApp status messages and enrollment notifications to the retrying outbox. Email receipts include the private enquiry tracking key. Live providers require configuration. |
| 12 Resident reference display | Existing reference display retained in staff/resident views and documents. |
| 13 In-app notifications | Existing resident history and staff message activity retained. |
| 14 Days overdue | Existing calculation/display retained. |
| 15 Performance sorting | Resident and room analytics can sort outstanding balances, overdue balances or settlement delay numerically, in either direction. |
| 16 Status filter | Added paid/due/overdue filtering to financial analytics and its CSV export. Existing ledger filter retained. |
| 17 Date-range ledger | Added inclusive from/to billing-month filters, combined with search and status. |
| 18 Payment drilldown | Added invoice-specific payment history with balance, receipt links and invoice download. |
| 19 Room removal | Added reversible decommission/reactivation with reason and audit history. Occupied rooms cannot be decommissioned; inactive rooms cannot receive allocations or appear as available stock. |
| 20 Resident inactive | Added scoped deactivation/reactivation with reason and audit. Outstanding accounts and open settlements block deactivation; successful deactivation releases the room and invalidates sessions/OTP challenges. Historical records remain. |
| 21 Enquiry tracking | Added public lookup using email plus a private high-entropy tracking key, with persistent request limits. Returns status/timestamps without internal staff notes or identity information. |
| 22 UI consistency | Extended existing styles with notifications, loading states, transitions, accessible table regions and responsive filter controls. |
| 23 Property photography | Existing configurable branch photo URL is supported. Genuine property photos were not supplied; the illustrative fallback stays labelled. |
| 24 Original logo | Existing supplied emblem retained; also embedded in financial PDFs. |
| 25 Contact/map | Added address-derived map embed/link and branch WhatsApp enquiry link when contact data exists. |
| 26 Editable FAQs | Owner-managed per-branch FAQ editor and public display, with bounded validated text. |
| 27 Mobile tables | Retained scroll containers, added keyboard focus and responsive controls. Desktop/mobile browser checks are recorded in the acceptance log. |
| 28 Inline validation | Native form constraints now produce field-level messages linked with ARIA; first invalid field receives focus. Server errors remain visible. |
| 29 Skeletons | Added reusable loading skeletons to public and authenticated loading views, with reduced-motion support. |
| 30 Financial PDF layout | Branded invoice, receipt and settlement renderer with embedded fonts, wrapped text, aligned amounts, tables and page numbers. Long content paginates. Existing invoice/receipt IDs are preserved. |
| 31 PostgreSQL/Docker | PostgreSQL 16 ran in a disposable Docker container. All migrations and 43 workflow tests passed. Full production Compose and hosting validation remain deployment tasks. |
| 32 SMS OTP fallback | Added optional Twilio SMS selection/fallback, retaining password plus expiring, single-use OTP and throttling. Tests use a fake provider. |
| 33 Identity-document upload | Added validated JPG/PNG/simple-PDF uploads, maximum 5 MB, encrypted database storage, protected downloads/removal and access audit. Requires a separate encryption key. Manual review remains separate from authoritative identity verification. |
| 34 Tests | Added seven workflow regressions and two frontend filter/sort tests; fixed CI to build/test the actual apps and run SQLite/PostgreSQL jobs. |
| 35 Job status | Existing persistent job/configuration status retained and extended for automatic billing, SMS and private document storage. |
| 36 Production configuration | Environment examples and deployment guide updated. Genuine provider credentials, approved templates, photos and the production backend address must be supplied by the operator. |
| 37 CORS | Existing explicit-origin configuration retained; DELETE allowed for the new scoped document route. |
| 38 Rate limits | Existing database-backed limits retained; enquiry lookup and identity upload use them too. |

## Verification

- SQLite: **47 backend tests passed**, including migration/restart checks and the seven new feature tests.
- PostgreSQL 16: clean migrations to **`0015_gap_completion`** passed; **43 workflow/release/gap tests passed**. Each workflow fixture uses a separate test schema and preserves the migrated public schema. Migration/runtime subprocess tests use SQLite fixtures separately.
- Frontend: **8 tests passed** and Vite production build passed.
- The backend Docker image built successfully with the locked dependencies. Its non-root API started against the test PostgreSQL database and returned healthy JSON. Temporary review servers and containers were stopped after verification.
- After the final UI/PDF/message changes, the production build, seven focused backend feature tests, Python compilation and container rebuild passed again.
- New tests cover cross-branch restrictions, balance guards, deactivated-session rejection even after reactivation, invoice scheduling/idempotence, enquiry privacy, admission outbox delivery, encrypted upload validation, SMS fallback, analytics filtering and PDF branding/pagination.
- Browser and rendered PDF results are recorded in [the current acceptance log](visual-qa/GAP_ACCEPTANCE_2026-10-22.md). This is targeted acceptance coverage, not an exhaustive device/accessibility audit.

## Operator setup

Apply `alembic upgrade head` against the intended database after backup and restore verification. The additive revision preserves financial and admission history; it refuses a destructive downgrade.

Configure private backend variables in [the deployment guide](DEPLOYMENT.md). Keep `IDENTITY_DOCUMENT_KEY` backed up separately and stable: changing it without re-encryption makes stored documents unreadable. Do not enable real delivery until the sender/phone/templates are verified. `AUTOMATIC_BILLING_ENABLED=true` generates eligible current-month invoices when the worker runs; use `false` for manual-only billing. No historical-month catch-up or proration is implied.

No real SMS/WhatsApp/email was sent during verification. No live application or production database was changed. Genuine property photography and successful live-provider/production deployment checks remain external dependencies.
