# Validation — chronological audit record (latest update 2026-10-24)

## Latest validation — persistent local setup, 2026-10-24

The user selected completion of the local setup. A dedicated `cityhive-local` Compose stack now runs the built Nginx frontend, FastAPI, PostgreSQL 16 and Mailpit. Both images built, migration `0015_gap_completion` applied, and all four services are healthy. Published ports bind only to `127.0.0.1`; the database has no host port. See [local setup and sign-in instructions](docs/LOCAL_SETUP.md).

Six focused local-delivery tests passed (one existing upstream deprecation warning), including refusal of production/external transports, password validation, OTP privacy/single use and inbox failure. The eight frontend tests and both normal/local builds passed. Browser owner sign-in using a Mailpit OTP succeeded; worker status is `ok` and document encryption is configured. The reverse proxy passed JSON health and 2 MB/7 MB request-boundary checks after increasing Nginx's limit to accommodate the application's 5 MB uploads.

The start/stop scripts were exercised. A full restart preserved the owner record/password hash and every private configuration value; the browser session remained valid. Services are left running for the user. No real provider delivery or production deployment is claimed. Screenshot: `docs/visual-qa/local-setup-2026-10-24.jpg`.

## Latest validation — PDF gap completion, 2026-10-22

This section supersedes the older snapshots below. See [all 38 PDF items mapped to current behavior](docs/GAP_COMPLETION_2026-10-22.md) and [targeted browser/PDF acceptance](docs/visual-qa/GAP_ACCEPTANCE_2026-10-22.md).

| Check | Actual result |
|---|---|
| SQLite backend | `TEST_DATABASE_URL=sqlite:// .venv/Scripts/python.exe -m pytest -q`: **47 passed**; one upstream Starlette/AnyIO deprecation warning. |
| PostgreSQL 16 migration | Disposable Docker database migrated through `0015_gap_completion` successfully. |
| PostgreSQL workflow/release/gap suite | `pytest tests/test_workflows.py tests/test_release.py tests/test_gaps.py -xq`: **43 passed**, one upstream warning, 77.15 seconds. Each workflow fixture uses an isolated generated schema. |
| Frontend tests | `npm test`: **8 passed**. |
| Frontend production build | `npm run build`: passed, Vite 6.4.1, 1,586 modules. The archive has no Git metadata, so revision metadata is unavailable. |
| Backend container | Python 3.12 image built with locked dependencies; non-root API container started against the disposable PostgreSQL instance with `AUTO_MIGRATE=false`; health returned `{"status":"ok"}` and build returned `cityhive-api`. |
| Browser | Synthetic owner OTP sign-in, dashboard, fee plans/inline validation, invoice generation/payment dialog, analytics filter, lifecycle and identity controls inspected. Desktop and mobile screenshots saved. |
| PDFs | Invoice and settlement PNG renders inspected; automated logo/text/multipage regression passed. |

No live provider credentials were used or messages sent. Genuine property photos and live SMS/WhatsApp/email configuration remain operator inputs. Production hosting, full Compose/recovery/concurrency testing and the live Slate/backend connection remain unverified. The earlier production-readiness limitations are not erased by local test success.

## Latest validation — integration/release work, 2026-10-21

This section supersedes older snapshots below for the current working tree. **The product is not yet production-ready or client-accepted.** See [the release audit](docs/RELEASE_AUDIT_2026-10-21.md), [deployment/recovery guide](docs/DEPLOYMENT.md), [all API routes](docs/API_ROUTE_INVENTORY.md), and [unexecuted browser checklist](docs/visual-qa/ACCEPTANCE.md).

### Actual checks and results

| Check | Command / method actually used | Result |
|---|---|---|
| Baseline backend | `TEST_DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q`, from `backend` before changes | 26 passed, one upstream warning |
| Baseline frontend | Bundled Node running `node_modules/vite/bin/vite.js build` from `frontend` | Passed; original assets matched observed live assets |
| Final backend suite | `TEST_DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q` from `backend` | **40 passed**, one upstream Starlette/AnyIO BlockingPortal deprecation warning; 7.15 seconds in the final run |
| Python compilation | `.venv/bin/python -m compileall -q app migrations scripts tests` from `backend` | Passed |
| Frontend API checks | `node --test tests/*.test.js` from `frontend` | **6 passed** |
| Final frontend production build | Same bundled Node running `node_modules/vite/bin/vite.js build` from `frontend` | Passed, Vite 6.4.1, 1,583 modules; JS `index-DaXHxuyZ.js`, CSS `index-DRAg6XJB.css` |
| Invalid production API guard | Build with `VITE_API_BASE_URL=http://127.0.0.1:8000/api` | Expected exit 1: `Production API requests require a public HTTPS backend.` Normal build then passed |
| Migration regression | Three migration tests, included in the 40-test suite | SQLite legacy/populated upgrade, replay, ambiguity rejection, all previous column/value preservation and old SW IDs passed |
| Real process startup/restart | `tests/test_runtime.py`, included in suite; separate temporary SQLite file and dynamically selected port | HTTP JSON health/build/branches; migration to head; user identity/hash and test record persist after process restart |
| Local API + frontend integration | HTTP GET through both `127.0.0.1:8000` and Vite `127.0.0.1:5173` | `/api/health`, `/api/build`, `/api/branches` return 200 JSON; public branches `[]` accurately reflects unpublished local data |
| Live Slate integration | Read-only HTTP GET, evidence in `docs/live-http-evidence.json` | **Still broken**: `/`, `/api/health`, `/api/build`, `/api/branches` all return identical 870-byte homepage HTML, SHA `7227c0a1c3ac420dd62ad44e235a7fc3bfcd35bebe70dcfab2a5cb5a5c64ebc9` |
| Docker | `docker compose version`; `docker compose up --build -d` | Both exit 127: `zsh:1: command not found: docker` |
| PostgreSQL availability | `command -v psql`, `command -v pg_isready`, listener inspection on 5432 | No tools on PATH and no local listener found. No PostgreSQL runtime, locks, migration, durability or Docker result claimed |
| Browser QA | Supported browser creation attempted | Tool returned `Local browser use is disabled in Work settings`. No alternate browser automation, screenshots or console results claimed |
| Source checks | `git diff HEAD --check`, scoped legacy/QR/fetch searches, applied migration byte comparison to Git HEAD | Passed; shared frontend `fetch` only; old revision files unchanged; retained legacy identifiers classified below/in audit |

### New coverage and resolved failures

The original 26 checks remain. Added coverage includes: receipt-PDF and notification privacy; branch-admin denial; identity suffix entry after enrollment; optional percentage approval validation/cap/scope/non-overlap/no fixed stacking/revocation/snapshot preservation; upcoming reminders and consent recheck; SMTP TLS/login ordering; signed webhook verification, replay and status ordering; persistent throttles; scheduler authorization and persistent success/failure state; as-of payment cutoff and IST settlement/day/week/month totals; publication edits and safe configured photo URLs; production settings and CORS; mocked Cloud API authentication body/button and safe provider errors; populated release migration preservation; real HTTP startup/restart.

Frontend checks cover API-origin validation, actual resource path mappings, HTML fallback rejection, validation-error redaction, PDF request routing and network-failure messages. They do not execute React user journeys.

An early regression run found an over-strict publication edit rule that rejected ordinary notice-period edits to an already-incomplete legacy branch. It was repaired to reject newly introduced publication problems while permitting unrelated repairs. A migration test still expecting the old head was updated to the new head, with stronger preservation assertions added. A new branch-admin test initially omitted verified-MFA claims in its synthetic test token; its fixture was corrected, retaining the application's authentication requirement. No failing authorization assertion was removed or weakened. The original reminder expectation now follows the configured upcoming window, and obsolete in-memory throttle fixture resets were removed after moving limits into the disposable database.

### Preservation and local migration

- Before implementation: original local SQLite at revision `0013_fees_settlements_complaint_assignment`; integrity `ok`; zero foreign-key violations; one user and one unpublished branch; all other business tables empty.
- Initial recovery: a private directory outside the repository containing a verified Git bundle, SQLite backup, protected env copies and manifest.
- Fresh pre-0014 backup: a private SQLite backup outside the repository; SHA-256 `e39084e1705494398f1159792ebf48337553bf295f54846db158125381c9adfe`.
- Stopped the confirmed local API process; verified the source still matched the backup; applied `0014_release_completion` to the same `backend/staywell.db`; compared all previous columns and values in all 25 business tables.
- After migration: 29 tables; existing counts unchanged; all three new tables empty; integrity `ok`; zero foreign-key violations. Original root/backend env files are byte-for-byte unchanged; historical applied revisions are byte-for-byte unchanged.
- Restarted the API against the same database. No QA data was copied into it. The absent published branches and unconfigured WhatsApp provider remain deliberate configuration gaps, not bypassed by test records or authentication changes.
- No production database, service configuration or remote Git branch was changed. No live production backup/restore or PostgreSQL migration is claimed. Local data/build hashes are in `docs/local-release-evidence.json`.

### Remaining blockers and intentional identifiers

The deployed backend URL/project and production database identity/access remain unknown; the owner reported they exist but could not identify the endpoint. Slate still points API traffic at its static site. Browser access is disabled. Docker/PostgreSQL and real WhatsApp/SMTP/scheduler delivery are unavailable for verification. Actual branch inventory, verified contact details and genuine property photographs must be supplied by management; one existing illustrative image remains clearly labeled. Large-volume load testing, PDF visual/multilingual acceptance, and production operational/security review remain outstanding. The lightweight PDF renderer replaces unsupported non-ASCII characters; use a licensed Unicode-capable renderer/font before issuing multilingual documents. The sender's SMTP acceptance/crash boundary remains at least once, not exactly once.

`staywell-token` remains a private session key; `staywell.db` remains the existing local filename; `SW` remains invoice/receipt numbering and filenames, including historical records. `pass_code` remains a required internal unique gate-pass column but is not exposed or validated. The old `gate_pass_validation_events` table remains dormant from immutable revision 0013. QR mentions are scope/history and negative endpoint tests only. There is no QR generator/scanner/API/control/dependency. Existing `cityhive.local` mail examples/Message-ID infrastructure are not public contact claims. No customer-facing Staywell business label was found in current application source.

## Historical validation snapshots

The sections below record earlier states and limitations at their stated dates. Statements that a feature was absent, counts were lower, migrations were older, or a throttle was in memory are historical, not the current release result.

The sections below preserve dated verification snapshots. The latest implementation and environment status are recorded at the end of this file; older “remaining work” statements describe their original audit dates.

Cityhive rebrand verification was performed on 2026-10-20. Customer-facing browser title, metadata, public/header/login/workspace wordmarks, receipt and invoice output, email subjects, and default sender are branded Cityhive. The provided Google business reference link could not be opened in the available browser tool, so no business details were inferred from it.

## Environment and preservation

- Existing root/backend `.env` files and `backend/staywell.db` were preserved.
- The workspace has no Git metadata, so Git status/diff could not be used to identify user-created changes.
- Docker and npm are unavailable in this environment. The preinstalled frontend dependencies and bundled Node/Vite runtime were used for the production build instead.
- Backend tests run against isolated in-memory SQLite unless `TEST_DATABASE_URL` is explicitly configured with a disposable `_test` database name.

## Checks run

- Baseline backend suite before implementation: **7 passed**.
- Baseline frontend production build: passed.
- Final backend suite after migrations and invoice PDF work: **13 passed, 1 warning** (Starlette TestClient references the deprecated AnyIO `BlockingPortal` alias).
- Alembic migration suite: included in the 13 passing tests. It upgrades a populated legacy SQLite fixture, reruns `upgrade head` idempotently, verifies invoice number/date backfill, and confirms ambiguous legacy ownership across multiple branches aborts.
- Backend Python compilation: passed earlier in this implementation; rerun after any future changes.
- Frontend production build command: `bundled Node executable node_modules/vite/bin/vite.js build` from `frontend/`; passed with Vite 6.4.1 (1,578 modules transformed).

## Coverage in the current suite

Tests cover resident onboarding/password change, manual identity review history, room capacity/allocation history, owner and resident privacy, monthly invoice idempotence and snapshots, partial payment and payment idempotence, receipt ownership, reminder deduplication/retry paths, complaint privacy and staff response, branch-admin assignment and isolation across resident/room/invoice/payment/admission/email records, public admission deduplication/review/enrollment and live availability, stay extension/shift/vacating lifecycle, and populated/ambiguous legacy migrations. Invoice PDF tests verify response format, resident ownership, and branch-admin isolation.

## Limits and remaining work

- Docker/PostgreSQL were unavailable. PostgreSQL migration execution, row-level/concurrent allocation behavior, Compose service startup, persistent-volume behavior, SMTP delivery, and production scheduling have **not** been verified here. SQLite success is not evidence of PostgreSQL deployment verification.
- Stay lifecycle has request/review, notice-period checks, scheduled vacating and balance gating. Security-deposit accounting, final settlement/refunds, request cancellation, and race-safe allocation locking across concurrent transactions remain unimplemented or unverified.
- Billing supports room monthly fee snapshots, fixed discounts, manual partial payments and balances. Configurable fee plans/add-ons, percentage discounts and eligibility, deposits, advances, admission fees, refunds/settlements, and financial adjustment history remain incomplete.
- Invoices are generated by an authorized manual billing action and idempotent per resident/month. There is no background billing scheduler, configured invoice due-date policy, or invoice itemization beyond accommodation and fixed discount.
- Reminder jobs run in the API worker while the service is running. Production scheduling/retry operations need deployment-level review; reminder delivery-status administration and in-app notification history are not implemented.
- At the 2026-10-20 audit point, unique resident IDs and gate passes were not implemented; the 2026-10-21 implementation is recorded in the “Resident IDs and gate passes” section below. A later scope correction removes the QR feature described in the older implementation snapshot.
- Complaint status/response is present, but assignment, administrative notes, and resolution audit history are not implemented.
- Browser QA on 2026-10-20 used the running local Vite page. The public homepage rendered the exact Cityhive title and identity, both configured branch records, live API-derived beds and monthly rates, branch detail and facility empty states, contact, FAQ, and the admission form. The browser screenshot showed the narrow/mobile navigation layout and hero without horizontal overflow at the captured viewport. A full desktop viewport comparison and browser console/network inspection were unavailable.
- Public navigation targets and branch selection controls were exposed in the accessibility tree. The admission form showed native required/contact/date controls and actual backend branch/sharing options. A new submission was not repeated during this visual pass to avoid duplicate QA records.
- This browser pass did not complete owner, branch-admin, or resident journeys, nor allocation, shifting, stay changes, invoice/receipt downloads, complaint response, or PDF access. Those authenticated workflows require valid test credentials/explicit branch-admin provisioning and are not claimed verified by the public page check. Existing backend tests continue to cover many corresponding API security and workflow paths.
- The redesign uses a CSS architectural illustration because no supplied property photograph or verified image asset was present. Font styling uses local/system fallbacks with no external font fetch. Responsive CSS includes mobile breakpoints, but a complete device matrix and assistive-technology audit were not performed.
- No external payment gateway, real SMTP provider, or authorized Aadhaar verification is configured.

Do not describe this build as production-ready until these remaining workflows, deployment controls, security review, and PostgreSQL/Docker verification are completed.


## UI/UX redesign QA (2026-10-20)

- Replaced the public landing page with a responsive Cityhive hospitality presentation, branch cards, inventory-backed room sharing/prices, configured branch details/facilities, admission workflow explanation, FAQ, and enquiry form. No property claims or contact details are fabricated; missing branch settings are explicitly shown as unconfigured.
- Updated shared application styling for public, sign-in, owner/admin, and resident views with a navy/royal-blue/gold system, focus states, reduced-motion handling, and responsive layouts. Existing app flows and APIs were left intact.
- Browser spot check: homepage/title and public content inspected through the accessibility tree and screenshot at the currently available narrow browser viewport. Branch A and QA South Branch returned current inventory (2 and 1 available beds respectively) and monthly rates (₹8,500 and ₹12,000). Branch addresses/facilities/contact fields are absent in disposable QA data and display explanatory empty states.
- Frontend production build rerun after the redesign: **passed**, Vite 6.4.1, 1,578 modules transformed. Backend tests rerun after the redesign: **13 passed, 1 upstream AnyIO deprecation warning**; Python compilation passed.
- Visual authenticated journeys, browser console/network diagnostics, desktop screenshot comparison, PostgreSQL/Docker runtime, and deployment readiness remain unverified as listed above. This application is not certified production-ready.


## Logo reference update (2026-10-21)

- Updated public header, footer, sign-in panel, and workspace brand marks to reflect the supplied hostel-sign reference: a circular dark badge, dotted ornamental ring, and stacked CITY / HIVE lettering. Updated the favicon and browser theme color to match. The source screenshot remains a visual reference and is not displayed as a cropped logo because it is a low-resolution perspective photo. The SVG is a clean UI rendering of visible identifying elements; review against the original sign for final brand approval.
- The full business name remains in prominent wordmarks; the badge uses the compact CITY HIVE display.

## Original emblem asset (2026-10-21)

- Replaced the interpreted badge with the user's supplied original City Hive emblem PNG. The uploaded image's transparent padding was cropped to the emblem bounds without altering the artwork. The exact PNG is used for all wordmark marks and the browser favicon.

## Premium workflow and finance implementation — 2026-10-21

### Implemented

- Added two-step WhatsApp OTP authentication for resident and staff accounts. Password-only login no longer issues the ordinary JWT. OTP challenge responses contain a masked phone, challenge ID, and expiry, not the code. OTP values are HMAC-protected in storage; verification is single use and attempt limited; resend invalidates the earlier challenge. A test-only in-memory WhatsApp provider is disabled in production.
- Added audited resident consent/opt-out for WhatsApp payment reminders, opt-in-gated utility-template outbox entries, a staff outbox view with channel/status, and bounded exponential retry scheduling. Email reminders remain on the existing outbox. WhatsApp entries are created only when opted in and messaging is configured.
- Added cash payment time, payer and note fields, auditable reversals, receipt balance-as-of-payment rendering, and exclusion of reversed payments from outstanding totals and analytics.
- Added server-side `/api/analytics/financial` and CSV export with date, branch, room, resident, and payment-method filters; aging, overdue invoice, settlement delay, on-time rate, resident and room reports, collection trends, method/branch totals, and cash totals by staff ID/email. Authorization is applied before aggregate queries. Limits are three years and 10,000 invoices.
- Added Alembic revisions `0006_auth_finance_notifications`, `0007_outbox_retry_schedule`, `0008_invoice_branch_snapshot`, and `0009_payment_time_index`. Revision 0008 adds invoice-time branch attribution and backfills legacy rows from the resident's branch at migration time. It cannot infer prior branch moves that were not historically recorded. Analytics caps reports at 10,000 invoices and 100,000 payments.
- Added resident Account-page notification preference control and financial analytics view. The public browser was inspected at 615-pixel width and showed the supplied original emblem and live configured test data (Branch A: 2 open beds from ₹8,500; QA South Branch: 1 open bed from ₹12,000), branch detail empty states, and admission enquiry form.

### Checks executed this turn

- Backend: `backend/.venv/bin/python -m pytest -q` — **21 passed, 1 upstream deprecation warning** (final run; includes workflow, OTP, analytics and isolation, payment reversal, retry, notification preference/outbox, and Alembic migration tests).
- Python compilation: `backend/.venv/bin/python -m compileall -q app migrations tests` — passed in the final combined check after revision `0009` was added.
- Alembic: `backend/.venv/bin/alembic heads` — `0009_payment_time_index (head)`.
- Frontend: bundled Node Vite production build — passed, Vite 6.4.1, 1,578 modules transformed (after analytics and preference UI changes).
- Browser: visual inspection completed at the public homepage, narrow viewport, with live API records. The page exposed two branches, room sharing, current availability/rates, and an admission form. No admission was submitted, no authenticated journeys were executed, and console/network error inspection was not performed.
- Screenshot artifact: inline browser screenshot was inspected, but `screencapture` returned `could not create image from display`; no before/after screenshot file could be saved. `docs/visual-qa/` is therefore not populated with image evidence.
- `docker compose up --build -d` was attempted and failed immediately with `zsh: command not found: docker`; `psql` and `npm` are also absent from PATH. Compose/PostgreSQL startup, migration execution on PostgreSQL, database persistence, SMTP, multi-process worker behavior, and real WhatsApp provider/template delivery remain unverified. The existing `backend/staywell.db` was preserved and not used as a disposable test database.

### Integration and security limitations

- The WhatsApp Cloud API needs real account configuration, approved authentication and utility templates, and current API-version verification. Meta's current API reference was rate-limited during research. The test provider confirms internal challenge flow only, not real delivery.
- OTP IP rate limits use process memory. Production multi-worker deployment needs a shared rate limiter. Phone number changes/recovery remain management-mediated; no self-service recovery flow or signed delivery-status webhook is present.
- Notification opt-out exists in the resident portal; inbound WhatsApp STOP handling, signature-verified webhook updates, provider delivery receipts, quiet hours, and scheduled upcoming-due notifications are not implemented. The existing worker runs with the API process and is not a separately supervised worker; restart behavior was not validated.
- Legacy invoice branch attribution is backfilled from the current resident branch. Historical shifts before revision 0008 cannot be inferred. Issued SW invoice and receipt identifiers remain preserved.
- Full authenticated browser journeys, saved desktop/mobile screenshots, accessibility audit, PostgreSQL concurrency checks, and production readiness review are outstanding. Do not call this deployment production-ready.

## UI/UX redesign reset — 2026-10-21

### Implemented

- Replaced the wireframe-building hero with an original, locally stored representative accommodation image (`frontend/public/representative-room.jpg`). It is labeled illustrative in the page and image alternative text; it is not represented as a Cityhive property photo. The image was generated for this project and compressed to JPEG (474 KB). The supplied Cityhive emblem remains unchanged.
- Reworked the public hero typography and column balance, fixed the inherited 258px operational-shell margin on the public `<main>`, and updated public section widths, branch listing hierarchy, room option pricing and responsive card styling. Branch cards now show the actual sharing option, available-bed count and configured monthly rate together.
- Added `branches.published`, migration `0010_branch_publication`, and an owner-only publication endpoint. New and migrated branches default to unpublished. Publishing requires an active branch, a public address, a description, and at least one configured room. The public branch and availability endpoints, plus admission submission, reject unpublished branches. Owner branch management shows publication status and controls.
- Updated the migration test's expected head revision and added workflow coverage for publication completeness, owner authentication, public visibility, unpublishing and direct availability access.

### Checks and browser review

- Backend: `backend/.venv/bin/python -m pytest -q` — **22 passed, 1 upstream Starlette/AnyIO deprecation warning**.
- Frontend: bundled Node/Vite production build — **passed**, Vite 6.4.1, 1,578 modules transformed.
- Migration: application startup applied Alembic through `0010_branch_publication` to the local SQLite database. Existing rows were not deleted or renamed; the new publication flag defaults false. This was a SQLite migration check, not PostgreSQL verification.
- Browser: inspected the updated public site at `http://127.0.0.1:5173/` using the in-app browser. The narrow available viewport was about 615px and showed the responsive menu and image-led hero; the desktop browser viewport was about 1280px and showed the repaired full-width hero with a three-line headline. During hot reload, the console first reported duplicate React root creation; the root is now reused through Vite HMR data. A fresh browser tab loaded without console warnings or errors. The same public app after API restart returned an empty branch listing and zero beds because no local branch is published in the configured database; admission submission therefore remains unavailable until an owner completes branch details, adds a room, and publishes it.
- Browser interaction did not submit an admission or alter branch publication. Owner, branch-admin and resident journeys were not exercised in the browser. Automated tests cover the publication authorization and branch isolation behavior.
- Browser screenshots were inspected inline, but no screenshot files could be saved into `docs/visual-qa/` using the available browser capture interface. Exact 1440px, 1920px and 390px viewport captures, a full-page capture, and an authenticated dashboard visual review remain outstanding.

### Remaining limits

- No genuine Cityhive property photographs were present in the workspace. The single representative image is illustrative; replace it with approved branch-specific photographs when available.
- No branch is currently published through the local app database. Since the existing admission API requires a branch ID and there is no configured general enquiries email/phone, a customer cannot submit a general enquiry while there are no published branches. The site explains that listings and enquiries are unavailable instead of inventing a contact route. Owner completion/publication is needed to enable the current admission workflow.
- Docker/PostgreSQL were not tested in this redesign pass. The UI’s exact target-width screenshots and authenticated portal visual QA remain incomplete. Do not describe this application or deployment as production-ready based on these checks.

## Recovery audit — 2026-10-21

A safe recovery pass was completed before additional source changes. The current source tree and both known SQLite databases were preserved in `recovery directory/`; see [the recovery report](docs/recovery-report.md). The project has no Git metadata, Docker is unavailable, and no production PostgreSQL source or backup was found.

The earlier browser session explicitly used `/tmp/cityhive-qa-20261020.db`, which prior validation identified as disposable QA data. That intact revision-`0005` database contains only two QA branches, two rooms, one admission, one resident, one invoice, one payment, and three outbox rows. The current API uses `backend/staywell.db`, revision `0010`, with a default branch and user but no resident workflows. The switch in database URL explains the missing browser records; it did not remove backend route functions. The public API additionally excludes unpublished branches.

A clone of the QA database migrated to revision `0010` successfully. SQLite integrity passed and all existing row counts were preserved; migration-created publication flags were false. The recovered source and current configured database were not migrated or overwritten.

Current isolated checks: backend **22 passed** (one upstream Starlette/AnyIO deprecation warning); Python compilation passed; Vite production build passed (Vite 6.4.1, 1,578 modules transformed). These checks do not verify PostgreSQL, Docker, real resident data, production email/WhatsApp delivery, or production readiness. No authenticated browser journey or new screenshot was produced during this recovery pass.

## Complaint audit history — 2026-10-21

Added revision `0011_complaint_audit` with append-only complaint submission and staff-update events. Complaint reads include scoped history and the portal exposes it as an expandable timeline. The migration was applied to an isolated clone of the recovered QA database: integrity passed and existing row counts for branches, rooms, admissions, residents, invoices, payments, and outbox remained unchanged. The original QA database and configured application database were not migrated.

Checks after this change: `backend/.venv/bin/python -m pytest -q` — **22 passed**, one upstream Starlette/AnyIO deprecation warning; Python compilation passed; Alembic head is `0011_complaint_audit`; Vite production build passed (Vite 6.4.1, 1,578 modules transformed). PostgreSQL and Docker remain unavailable. The local browser was not reloaded against the new API code in this pass.


## Local integration follow-up — 2026-10-21

After the pre-migration backup, the configured local SQLite database was upgraded to `0011_complaint_audit` and the API was restarted against that same configured file (not the QA database). `/api/health` returned `{"status":"ok"}`; `PRAGMA integrity_check` returned `ok`; existing branch/resident/room/invoice/payment counts remained 1/0/0/0/0. The complaint history table is present. The source QA database and its recovery copies were not changed.

The Vite page was re-inspected at the current browser tab. The public site accurately reports no published branches and no admission form; its current configured DB has only an unpublished default branch and no room inventory. Resident sign-in and a separate Management sign-in action are both visible. No authenticated browser journey or screenshot was completed.

## Resident IDs and gate passes — 2026-10-21 (initial implementation snapshot)

- Added migration `0012_resident_codes_gate_passes`: existing residents receive unique random `CH-…` reference codes; new residents get an opaque ID at creation; gate passes store a unique random reference, issuing staff member, resident, optional expiry, and revocation actor/time. Downgrade deliberately refuses to erase resident IDs or pass history.
- The first implementation included staff pass-code validation. That validation workflow was later removed by the scope correction at the end of this file; current gate-pass actions are listing, issue, basic print, and revoke.
- Added resident and staff portal views to see/print passes, staff issue/revoke actions, and resident IDs in the workspace. Printed basic passes use the supplied Cityhive emblem and omit resident contact and identity details.
- Current automated coverage verifies issue, expiry limits, resident-only listing, resident write denial, branch-admin read/revoke isolation, and revocation. The removed validation workflow is no longer tested as a supported feature.
- Preserved a fresh SQLite backup at `recovery directory/staywell-pre-0012.db` before applying the migration. Its SHA-256 is `8c8352de380ed9484058551ca76ad6d79c6ccbad0a6f14117de3fa4f11be1e10`; it records revision `0011_complaint_audit`. The configured `backend/staywell.db` was then upgraded at startup to `0012_resident_codes_gate_passes`. SQLite integrity is `ok`, API health is `{"status":"ok"}`, and user/branch/resident/room/invoice/payment/pass counts remain `1/1/0/0/0/0`.
- Current backend suite: **23 passed**, one upstream Starlette/AnyIO `BlockingPortal` deprecation warning. `python -m compileall -q app migrations tests` passed. Alembic reports `0012_resident_codes_gate_passes (head)`. Vite production build passed (Vite 6.4.1, 1,578 modules transformed).
- Browser visual or interaction QA was not possible during this pass: the available CUA browser inventory returned `Local browser use is disabled in Work settings` and no browser tabs. The frontend build and API tests are not substitutes for a browser journey. Docker is not installed in the execution environment; PostgreSQL and Compose remain unverified.

### Remaining delivery gaps

This pass completed resident IDs and basic gate passes, not the entire master product scope. Configurable fee plans, deposit/advance/refund settlement, percentage discount policy, and complaint assignment were implemented in later work. WhatsApp code paths have only test-provider coverage; real approved Meta templates, delivery callbacks, webhook authentication, quiet hours, and provider delivery have not been verified. Full owner, branch-admin, and resident browser journeys, PostgreSQL/Docker runtime, SMTP delivery, and production security review remain outstanding. Do not treat the application or deployment as production-ready.

### Legacy identifier audit

- `staywell.db` remains the configured SQLite filename for compatibility with existing local data; `.env` files were not renamed or rewritten.
- `staywell-token` remains the browser session-storage key to avoid silently invalidating existing browser sessions; it is not shown in customer-facing UI.
- `SW` remains in historical/current invoice and receipt numbering and email receipt references by design. Issued identifiers were not rewritten or renumbered.
- Customer-facing titles, visible navigation, email labels, invoices, and receipts remain Cityhive branded. No visible Staywell business name is intended.

## Remaining features and release verification — 2026-10-21 (pre-scope-correction snapshot)

### Delivered in this pass

- Added revision `0013_fees_settlements_complaint_assignment`. Fee plans are branch- and sharing-specific, effective-dated, and configure monthly billing day, due day, and optional labelled monthly charges. Admissions select a matching effective plan. Billing snapshots the base charge, add-on, discount, total, plan ID, room and due date into each invoice. A price change to a plan already used by an invoice is rejected; the plan can be ended and a successor created for a later cycle.
- Public availability now includes configured add-on details. Public room pricing shows a combined configured monthly total and the accommodation/add-on breakdown where an add-on exists.
- Added separate deposit and advance ledgers for amounts actually received, authorized deductions with reasons, and actual refunds. Final settlements snapshot deposit, advance and outstanding invoice balances, require staff approval, and record refund payments as separate ledger events. Idempotency keys, fixed-precision amounts, branch authorization, settlement event history and invoice-balance review are covered. The system does not automatically offset invoice debt or infer a deposit forfeiture/refund policy. A zero-refund decision is marked `no_refund`, not as a paid refund.
- Added branch-authorized complaint assignment, branch-filtered assignee choices, resolution notes and timestamps, and append-only assignment/update events. Resident views redact staff email and assignee identifiers and only return that resident's complaints.
- At this audit point, the implementation included protected QR output and staff code validation. The later scope correction at the end of this file removes those application routes and controls; the original Alembic revision remains unchanged.
- The invoice and receipt `SW` identifiers and historical issued numbers are unchanged. Fee plans, settlements and complaint assignment are available in the existing management portal; residents can view their own deposit/advance account and settlements.

### Checks and actual results

- Backend: `backend/.venv/bin/python -m pytest -q` — **26 passed, 1 upstream deprecation warning**. The warning is from Starlette's TestClient use of AnyIO `BlockingPortal`.
- Python: `backend/.venv/bin/python -m compileall -q app migrations tests` — passed.
- Frontend production build: `bundled Node executable ./node_modules/vite/bin/vite.js build` from `frontend/` — passed, Vite 6.4.1, 1,578 modules transformed. `npm` is not on this environment's PATH, so `npm run build` itself was unavailable; the same Vite build script ran through the bundled Node executable.
- Migration tests upgrade a populated legacy SQLite schema to `0013`, run the upgrade again, and check preserved invoice identifiers, defaults, and schema. The suite includes effective-price succession and historical snapshot tests, actual refund idempotency and settlement audit tests, complaint assignment/branch isolation tests, and basic gate-pass authorization tests.
- Local configured API database: `backend/staywell.db` was backed up before migration to `recovery directory/staywell-pre-0013.db` (SHA-256 `32ceeb0bbffac9327425ee04c8125b2f4ebb84a45d2e8f38b71d133c896dc837`). Backup and source passed SQLite integrity checks at revision `0012_resident_codes_gate_passes`, and row counts matched across 21 tables.
- The configured SQLite database was upgraded from `0012` to `0013_fees_settlements_complaint_assignment`; `alembic current` reports that revision as head. After migration: `PRAGMA integrity_check` is `ok`, `PRAGMA foreign_key_check` reports zero violations, all pre-existing table row counts match the backup, and each of the five new tables is empty. The API was restarted against the same file; `GET /api/health` returned `{"status":"ok"}`.

### Browser, Docker, PostgreSQL and delivery status

- Browser QA was attempted with the available CUA browser inventory. It returned no browser and the exact error `Local browser use is disabled in Work settings`. No browser journeys, visual layouts, console, or network behavior are claimed verified in this pass. Automated API tests are not browser verification.
- As an HTTP smoke check after restart, the frontend returned HTTP 200 and `/api/health` returned `{"status":"ok"}`. The configured local database has no published branches, so the public `/api/branches` endpoint returned `[]`; actual branch-detail and admission journeys could not be exercised against live branch data.
- `docker compose up --build -d` was attempted and failed with `zsh: command not found: docker`. There is no PostgreSQL listener on `127.0.0.1:5432` (`ConnectionRefusedError`), and `psql`, `pg_dump`, and `pg_isready` are absent from PATH. The running local app is configured for SQLite. PostgreSQL migrations, Compose health, persistence across container restarts, and row-lock/concurrency behavior are **not verified**.
- OTP and reminder workflow tests use the mock WhatsApp provider. No live WhatsApp Business Platform credentials, approved-template delivery, provider callbacks, or real recipient delivery were tested. The current local configuration has WhatsApp disabled; provider delivery is not claimed. The local background job setting is also disabled, so the periodic job loop did not run; reminder queue deduplication and retry behavior remain covered by automated tests and the staff API can run the reminder queue manually. No live SMTP delivery was exercised here.
- Analytics and branch-scoped report/export behavior are covered by the existing tests. No authenticated browser journey or real-data report export was performed.

### Compatibility audit

- `backend/staywell.db` and the Alembic SQLite URL are retained to continue using the existing database. The legacy owner address `owner@staywell.local` remains only in local environment configuration.
- `staywell-token` remains the session-storage key for compatibility with existing browser sessions; it is not shown in the UI.
- `SW` remains in the invoice and receipt numbering scheme, including `SW-LEGACY-…` migration identifiers and payment receipt references. Existing/current identifiers were not renumbered.
- Remaining `Staywell` occurrences are internal database/session identifiers, local owner configuration, and chronological validation/recovery documentation. No live customer-facing page or invoice intentionally displays the Staywell brand.

## Cityhive QR scope correction — 2026-10-21 (latest)

- Removed the QR image endpoint, pass-code validation and validation-history endpoints, the QR generation dependency, QR display in printable passes, and the staff validation panel. Gate-pass listing, staff issue/revoke, resident self-view, expiry/status, and basic printing remain. Basic printed passes contain the resident name and ID, room, validity, and status; they do not display a scan code.
- The API no longer returns the legacy `pass_code` value. Its required, unique database column remains and is still populated internally for schema compatibility; no route or UI reads it. The `GatePassValidationEvent` ORM model is removed, so the application no longer reads or writes validation events.
- No migration was added and no database DDL was run. Previously applied revision `0013_fees_settlements_complaint_assignment` remains unchanged; it historically creates `gate_pass_validation_events`. That table remains unmapped and dormant to preserve compatibility and any historical events. It is retained without an API, model, or UI path. The current configured SQLite DB has zero gate-pass rows and zero validation-event rows.
- Before changes, created `recovery directory/cityhive-pre-qr-removal-20261021.db` (SHA-256 `e39084e1705494398f1159792ebf48337553bf295f54846db158125381c9adfe`). Source and backup both passed `PRAGMA integrity_check`; both reported revision `0013_fees_settlements_complaint_assignment`. No database records or schema were changed by this scope correction.
- Backend suite after the correction: `backend/.venv/bin/python -m pytest -q` — **26 passed, 1 upstream Starlette/AnyIO deprecation warning**. Coverage includes public admission review/enrollment and the updated resident/staff gate-pass ownership and branch-scope workflow; tests confirm removed QR/validation URLs return 404.
- Python compilation: `backend/.venv/bin/python -m compileall -q app migrations tests` — passed.
- Frontend production build: bundled Node/Vite build — **passed**, Vite 6.4.1, 1,578 modules transformed. The printable basic pass retains resident identification and pass status without QR output.
- Database after-change check: recorded table counts are unchanged from the backup; integrity is `ok`, with zero foreign-key violations. Alembic remains at `0013_fees_settlements_complaint_assignment`.
- Remaining QR-related references are limited to the immutable historical revision that created the dormant event table, the legacy pass-code field retained for database compatibility, negative tests asserting removed endpoints are absent, and this scope/migration documentation. `qrcode` was removed from `backend/requirements.lock.txt`. No current frontend bundle, route, API response, or customer-facing control provides QR functionality.
- Browser visual QA was not performed in this pass; resident/admin gate-pass and public admission workflows were verified through backend API tests. Docker/PostgreSQL remain unverified as noted above. No broader production-readiness claim is made.

The product remains **not production-ready**. The main release blockers are browser journey verification, Docker/PostgreSQL integration and deployment checks, live WhatsApp/SMTP delivery verification, and a production security/recovery review. Other existing scope gaps such as payment-gateway processing, percentage-discount policy, provider delivery webhooks/STOP handling, and separately supervised background workers remain outside the completed workflows above.
