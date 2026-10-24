# Run Cityhive locally on Windows

This setup runs the built website, API, PostgreSQL 16 and Mailpit in Docker Desktop. It is separate from the production configuration and earlier disposable review data. All published ports bind to this computer's loopback address.

## Open and sign in

1. Open **http://127.0.0.1:5179/** and choose **Management sign in**.
2. Read the owner email and generated initial password in **`.local/login.txt`** in the project folder. The owner email is `owner@cityhive.local`.
3. Leave **Local inbox (test WhatsApp)** selected and continue.
4. Open **http://127.0.0.1:8025/**. Read the newest **Cityhive local sign-in code** email and enter its six-digit code in Cityhive. Codes expire after five minutes and can be used once.

The local test transport sends no real WhatsApp or SMS. Application email stays in Mailpit; it is not delivered to external recipients. Do not use real identity documents or personal resident data in this development setup. The initial password note is not updated if you change your password in the app.

The database starts with an owner account and an unpublished **Branch A**. Enter your branch details, add rooms and fee plans, then publish the branch when its required information is complete. No sample residents, invoices or property claims are inserted into this persistent workspace.

## Start and stop

From the `City-Hive-main` folder in PowerShell:

```powershell
.\scripts\Start-Local.ps1
```

The script starts Docker Desktop if needed, generates private local configuration on the first run, builds the applications, applies migrations to the dedicated local database and waits for healthy services. It preserves the same passwords and document-encryption key on subsequent runs.

For a faster start after the images have already been built:

```powershell
.\scripts\Start-Local.ps1 -SkipBuild
```

To stop the local services while preserving data:

```powershell
.\scripts\Stop-Local.ps1
```

Docker Desktop must be running while the application is in use. Closing the browser does not stop the services. The stack uses the Compose project name `cityhive-local` and the named volume `cityhive-local_local_db`. The API is also available on **http://127.0.0.1:8019/docs**. PostgreSQL and SMTP have no exposed host ports.

## Local data and keys

The private `.local/cityhive.env` file contains the generated database password, owner bootstrap password, JWT secret and identity-document encryption key. `.local` is excluded from Git. Keep this file private and retain it with your local backups; database records alone cannot recover encrypted documents without the original key. Do not delete the Docker data volume. The launcher refuses to generate replacement secrets if it detects an existing local database volume without its configuration.

The database and identity documents survive ordinary stops/restarts. The local email inbox is for development and can be discarded when its container is recreated. Request a database backup before upgrading an instance containing valuable local data; production backup/restore procedures are documented separately in `DEPLOYMENT.md`.

## Verification on 24 October 2026

- Both images built and all four Compose services reached a healthy/running state.
- The local PostgreSQL schema is `0015_gap_completion`; the scheduling worker reports `ok` and private document storage is configured.
- Browser sign-in succeeded using the generated owner password and a test OTP delivered to Mailpit; the authenticated dashboard and service configuration loaded.
- A full stop/start preserved the owner record/password hash and the private configuration file, including the document key. The browser session remained valid after restart. All four services were left running.
- The website reverse proxy returned JSON from `/api/health`. A 2 MB upload request reached API authentication and a 7 MB request was rejected by Nginx. The application retains its stricter 5 MB document limit.
- Six new local-transport tests passed, covering production/external-provider refusal, wrong-password rejection, code privacy/single use and inbox failure. Eight frontend tests and normal/local production builds passed.

Local SMTP and test-provider success do not verify real message delivery or production hosting.
