# Release file inventory

Exact changed/added files relative to the initial commit, recorded on 2026-10-21.

- `README.md`
- `VALIDATION.md`
- `backend/.dockerignore`
- `backend/.env.example`
- `backend/Dockerfile`
- `backend/alembic.ini`
- `backend/app/analytics.py`
- `backend/app/config.py`
- `backend/app/main.py`
- `backend/app/models.py`
- `backend/app/rate_limits.py`
- `backend/app/schemas.py`
- `backend/app/serve.py`
- `backend/app/services.py`
- `backend/app/whatsapp.py`
- `backend/app/worker.py`
- `backend/migrations/env.py`
- `backend/migrations/versions/0014_release_completion.py`
- `backend/scripts/db_maintenance.py`
- `backend/tests/test_migrations.py`
- `backend/tests/test_release.py`
- `backend/tests/test_runtime.py`
- `backend/tests/test_workflows.py`
- `compose.production.yaml`
- `docs/API_ROUTE_INVENTORY.md`
- `docs/CLIENT_PROJECT_AUDIT_2026-10-21.md`
- `docs/DEPLOYMENT.md`
- `docs/RELEASE_AUDIT_2026-10-21.md`
- `docs/RELEASE_FILES.md`
- `docs/implementation-report.md`
- `docs/live-http-evidence.json`
- `docs/local-release-evidence.json`
- `docs/recovery-report.md`
- `docs/ui-ux-benchmark.md`
- `docs/visual-qa/ACCEPTANCE.md`
- `frontend/.dockerignore`
- `frontend/.env.example`
- `frontend/Dockerfile.production`
- `frontend/nginx.conf`
- `frontend/package.json`
- `frontend/src/PortalExtras.jsx`
- `frontend/src/PublicSite.jsx`
- `frontend/src/api.js`
- `frontend/src/main.jsx`
- `frontend/src/portal.css`
- `frontend/src/public.css`
- `frontend/tests/api.test.js`
- `frontend/vite.config.js`

No dependency package was added or removed. The only new migration is `0014_release_completion`; all earlier migration files and existing private `.env` files are unchanged. Database backups are outside the repository and ignored database files are not release artifacts.
