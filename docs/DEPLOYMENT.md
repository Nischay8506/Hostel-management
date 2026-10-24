# Cityhive deployment and recovery

## Vercel (one project, frontend + API)

`vercel.json` defines two Vercel Services: `frontend/` (Vite) served at `/` and `backend/` (FastAPI, `app.main:app`) at `/api/*`. The browser calls the API on the same origin, so leave `VITE_API_BASE_URL` unset. Keep the project's Root Directory at the repository root.

1. Database: add Neon Postgres from the project's Storage tab (pick a region close to the function region). The injected `postgres://` `DATABASE_URL` is accepted; the app converts it to the psycopg 3 driver.
2. Migrate once from a machine with the backend dependencies installed: set `DATABASE_URL`, `JWT_SECRET` and `ADMIN_PASSWORD` in the shell, then run `python -m alembic upgrade head` in `backend/`.
3. Environment variables (Production): `APP_ENVIRONMENT=production`, `AUTO_MIGRATE=false`, `JOBS_ENABLED=false`, `JWT_SECRET` (32+ random chars), `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_PHONE`, `CORS_ORIGINS=["https://<project>.vercel.app"]`, `JOB_RUNNER_TOKEN` (32+ chars), `IDENTITY_DOCUMENT_KEY` (Fernet key), plus the WhatsApp Cloud API or Twilio SMS settings. Sign-in always requires an OTP, so at least one of those must be configured.
4. Scheduled work: `.github/workflows/scheduled-jobs.yml` calls `/api/internal/jobs/run` every 15 minutes once the `CITYHIVE_URL` and `JOB_RUNNER_TOKEN` repository secrets exist.

Vercel limits function request bodies to 4.5 MB, below the application's 5 MB identity-upload limit.

This repository has separate frontend and backend applications. Publishing the Vite build to Slate does not start FastAPI, PostgreSQL, or the reminder worker. The production backend address has not been identified in this session. Do not substitute the local SQLite file for the production database.

## Find the existing backend

1. Open the Catalyst project that contains the `city-hive-jxyilflx` Slate deployment.
2. Look for an existing **AppSail** service. If the backend is hosted elsewhere, open that provider's service dashboard instead. The existence of a backend was reported by the owner but has not been independently confirmed.
3. Copy the service's public HTTPS endpoint and project/service name. Do not copy credentials, access tokens, or a database connection string into chat.
4. Check `<backend HTTPS endpoint>/api/build` for JSON identifying `cityhive-api`, and `/api/health` for `{"status":"ok"}`. A homepage or an HTML response is not an API health response.
5. In the service's private environment configuration, confirm the intended persistent PostgreSQL instance, its database name, and backup status with the database owner. Record the revision and counts before upgrading.

If no service is listed, resolve where the reported existing backend is hosted before creating another service or database. A screenshot of the service list with secrets hidden is enough to help locate it.

## Slate frontend fields

| Field | Value |
|---|---|
| Repository | `Charan-Venkatesh/City-Hive` |
| Branch | `main`, after the reviewed release is pushed |
| Framework / Node | React + Vite / Node 22 |
| Root path | `frontend` |
| Install command | `npm ci` |
| Build command | `npm run build` |
| Build/output path | `dist` relative to `frontend` |
| App variable key | `VITE_API_BASE_URL` |
| App variable value | The verified backend HTTPS endpoint followed by `/api` |

Do not enter the explanatory words above as the variable value. For example, the shape is `https://YOUR-VERIFIED-API-HOST/api`; no real backend hostname is known here. Slate variables are applied at build time, so changing this variable requires a new build/deployment. Never put `DATABASE_URL`, `JWT_SECRET`, SMTP passwords, WhatsApp tokens, or scheduler tokens in `VITE_*` variables: these become public JavaScript.

`/api` remains the default for local development and for a server with a real reverse proxy, such as the supplied Nginx configuration. It is not sufficient for the currently observed Slate deployment, whose `/api/*` paths return the homepage. The Vite build rejects production HTTP/loopback API URLs. `build-info.json` records only the public API base, Git revision, and dirty-worktree flag so deployed versions can be compared.

Official references: [Slate environment variables](https://docs.catalyst.zoho.com/en/slate/help/environment-variables/) and [AppSail configuration and listening port](https://docs.catalyst.zoho.com/en/serverless/help/appsail/appsail-configurations/).

## Backend service

Use the existing Python/SQLAlchemy service and PostgreSQL instance. Deploy the contents of `backend`, including `app`, `migrations`, `alembic.ini`, `scripts`, and `requirements.lock.txt`.

- Install: `python -m pip install -r requirements.lock.txt` in the service environment.
- Startup: `python -m app.serve`. It reads `X_ZOHO_CATALYST_LISTEN_PORT` first, then `PORT`, then 8000, and binds to `0.0.0.0`. No shell interpolation of the provider port is needed.
- Set `APP_ENVIRONMENT=production`, `AUTO_MIGRATE=false`, the existing persistent `postgresql+psycopg://...` URL, strong private credentials, and `RELEASE_ID` to the deployed commit/release.
- Set `CORS_ORIGINS=["https://city-hive-jxyilflx.onslate.in"]` and include another exact HTTPS origin only if it is intentionally used. Never use `*`.
- Keep `PERCENTAGE_DISCOUNTS_ENABLED=false` unless management approves percentage discounts. The feature supports explicit staff approvals for complete billing months, accommodation-only or all-monthly scope, an optional cap, and revocation. It cannot stack with the allocation's fixed discount. Previously issued invoice amounts never change.
- The API refuses production startup with SQLite, automatic migrations, the mock WhatsApp provider, weak/example secrets, insecure authenticated SMTP, or unsuitable CORS origins.
- Configure the platform's ingress/body-size limits, TLS, health monitoring, private logs and restart policy. Trust only the platform's documented proxy addresses through `FORWARDED_ALLOW_IPS`; do not blindly trust arbitrary forwarded headers. Startup disables request access logs to avoid logging webhook verification query tokens. Platform logs need equivalent redaction.
- `/api/health` checks the database connection. Startup separately checks the Alembic revision. `/api/build` identifies the release. The owner's Account page shows `/api/deployment-status` with schema, provider configuration, and last worker completion, without secrets.

### Migration and backup sequence

Use the private backend environment and confirmed database target, from `backend/`:

```sh
python scripts/db_maintenance.py inspect
python scripts/db_maintenance.py backup /absolute/private/new-backup-directory
```

The utility never migrates, restores, drops, or recreates a database. SQLite uses its online backup API and checks integrity. PostgreSQL uses `pg_dump --format=custom`, passes credentials through the child environment rather than command arguments, and checks `pg_restore --list`. A readable archive alone is not a verified restore. Quiesce writes, restore the dump into a separately provisioned disposable database, verify revision/counts/relationships and required workflows, and retain the backup before upgrading the original target.

Only after target and restore verification:

```sh
python -m alembic current
python -m alembic upgrade head
python scripts/db_maintenance.py inspect
```

Expected head: `0015_gap_completion`. Compare before/after counts and issued identifiers. The latest revision adds sharing advances, FAQs, admission notification consent, active state/session versions, lifecycle audits and encrypted identity-document storage. It retains all existing business tables and data. Alembic's PostgreSQL version column is widened to 128 characters before migration, because a historical revision name exceeds the default 32-character width; the historical revision files remain unchanged.

Rollback is an operational recovery: stop writers, deploy the prior source and restore a verified backup into an explicitly selected recovery database, reconcile any writes since the backup, then switch the service only after approval by the data owner. Do not run a destructive downgrade or restore over an unidentified/live target. Do not run `docker compose down -v`.

## Scheduling and notifications

Choose one supervised operating mode:

1. A persistent worker process: `python -m app.worker`; set API `JOBS_ENABLED=false`.
2. A scheduler invokes `python -m app.worker --once` about once per minute; set API `JOBS_ENABLED=false`.
3. An authenticated server-side scheduler POSTs `/api/internal/jobs/run` with `X-Cityhive-Job-Token`. Configure a private random `JOB_RUNNER_TOKEN` of at least 32 characters; do not place it in the frontend. Set API `JOBS_ENABLED=false`.

The original in-process mode (`JOBS_ENABLED=true`) remains for local use. Do not rely on it on a host that suspends the API when idle. PostgreSQL advisory locking prevents overlapping worker runs; its live concurrent behavior still requires PostgreSQL verification. Worker state persists in `job_state`. A failed status or stale last-success timestamp needs an operator alert; the Account page is a diagnostic view, not an external monitoring service.

The worker processes scheduled move-outs, generates eligible current-month invoices when `AUTOMATIC_BILLING_ENABLED=true` (the default), queues upcoming/due/overdue reminders, and delivers the outbox. Automatic billing respects the fee plan's billing day and skips existing resident/month invoices; residents without a plan use the existing room-rate/default-due-day policy. It does not backfill historical months or prorate charges. Set `AUTOMATIC_BILLING_ENABLED=false` to retain manual-only billing. `UPCOMING_REMINDER_DAYS` defaults to 3 and can be set to 0. Reminder queueing is unique by invoice/channel/local date; balances and WhatsApp consent are checked again before sending. SMTP/provider acceptance followed by a crash can still cause a duplicate on retry (at-least-once delivery).

- SMTP: set the verified sender, host and port; use `SMTP_SECURITY=starttls` or `ssl` and authenticated credentials where required. `submitted` means provider acceptance, not confirmed inbox delivery.
- WhatsApp: supply the official Cloud API account/phone ID, access token, currently supported API version, approved English authentication copy-code template and utility reminder template. No real account/API-version/template combination was verified here. Authentication sends the OTP in body and button components. The four utility body parameters are invoice number, billing period, outstanding amount, due date. Verify these against the actual approved template.
- Signed delivery callback: `/api/notifications/whatsapp/webhook`, with private `WHATSAPP_APP_SECRET` and `WHATSAPP_VERIFY_TOKEN`. Signature validation and monotonic status updates are covered with mocked callbacks; register and verify it with Meta before claiming live delivery.
- All roles require password plus WhatsApp or configured SMS OTP. SMS can be selected explicitly and is used as fallback when WhatsApp is unavailable. No session is issued before OTP verification; missing provider configuration fails closed. Set the owner's actual `ADMIN_PHONE` if absent. Existing phone values are preserved. Staff-mediated number recovery must verify the account holder; do not disable OTP or use the test provider in production.
- Residents explicitly manage transactional WhatsApp reminder consent in Account. Incoming STOP-command processing is not implemented; portal opt-out is available. Live provider handling must follow the deployed consent policy.

## Optional container deployment

`compose.yaml` remains the local PostgreSQL/Mailpit/Vite setup. `compose.production.yaml` uses an **existing external PostgreSQL database**, a separate API/worker, and an Nginx-built frontend. It creates no production database and runs no migration automatically. Set `CITYHIVE_ENV_FILE` to an absolute private backend env file, migrate the confirmed target after backup, then use:

```sh
docker compose -f compose.production.yaml up --build -d
```

The web service binds only `127.0.0.1:8080`; put the hosting ingress with HTTPS in front. The backend image contains migrations and runs as a non-root user. On 2026-10-22, PostgreSQL 16 in a disposable Docker container passed migrations and 43 workflow tests. Full production Compose startup, multi-worker contention, external database persistence and production restart/recovery still require deployment validation. This file is configuration, not evidence of a successful production deployment.

## New optional integrations

- SMS: set `SMS_ENABLED=true`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` and `TWILIO_FROM_NUMBER` privately. Verify the sender and permitted destinations with the actual account before enabling it. The adapter uses the official [Twilio Message resource](https://www.twilio.com/docs/messaging/api/message-resource); test runs used a fake provider and sent no real SMS.
- Admission WhatsApp: set `WHATSAPP_ADMISSION_TEMPLATE_NAME` to an approved utility template with two body parameters in order: admission request number and new status. The applicant must opt in on the public enquiry form. Status changes queue separate outbox items; missing provider setup leaves them to the normal retry/failure handling.
- Private documents: generate a key once using `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` in a private terminal, then set `IDENTITY_DOCUMENT_KEY` only in the backend environment. Keep it in the secret store and include it in recovery procedures separately from database backups. Replacing the key requires decrypting/re-encrypting existing records; arbitrary key replacement loses access. Do not use the JWT secret for document storage.
- Uploads: allow a request body of at least 5 MB plus proxy overhead; the application streams and enforces a 5 MB maximum, validates content, accepts PNG/JPG or noninteractive PDFs of at most 10 pages, and audits access. This is bounded format validation, not malware scanning or authoritative identity verification. Set an operational retention policy before collecting real documents.
- Branch content: owners configure genuine photo URLs, verified addresses/phone numbers and FAQs. Maps and WhatsApp links derive from those fields. No real property photos or contact details were fabricated.
