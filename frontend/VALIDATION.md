
## Final integration QA — 2026-10-20

### Disposable browser environment

- Started the API with `DATABASE_URL=sqlite:////tmp/cityhive-qa-20261020.db`, a QA-only owner login, and `JOBS_ENABLED=false`; started Vite on `127.0.0.1:5173`.
- `/api/health` returned `{"status":"ok"}`. The disposable database reached Alembic revision `0005_invoice_numbers` and contained only QA data (two branches, two rooms, one QA resident, one invoice, and one payment).
- Re-ran pytest: **13 passed, 1 upstream AnyIO deprecation warning**. Python compilation passed. Frontend production build passed (Vite 6.4.1; 1,578 modules transformed) before the browser-discovered UI fix; a final build after that fix is recorded in the handover.

### Browser journeys completed in the in-app browser

- Public home loaded with Cityhive branding and the two configured branch records. Selecting each branch showed its actual database availability and configured fee (`₹8,500` and `₹12,000` per resident/month in disposable QA data).
- Admission form rejected the reserved `.test` email domain with a field validation message; a synthetic QA address then submitted successfully, appeared in the staff queue, was approved, and enrolled through the UI.
- Owner login, branch creation, room creation on each branch, resident allocation, monthly invoice generation, and partial manual payment recording completed successfully.
- First resident login correctly stopped at the required temporary-password change screen. No password was changed by the agent; that step requires the user to take over. The browser tab was left at that screen.
- Browser viewport was the in-app panel (about 615 px wide). It demonstrated narrow-layout behavior. A resident-management table requires horizontal scrolling to reach its action column; the action became reachable after scrolling. Full desktop-width visual QA and device-emulated mobile breakpoints were not available through this browser surface.
- PDF and receipt download controls were visible and the PDF control was activated, but the browser provided no download completion signal. API tests cover PDF payload and access control. Complaint and stay-request journeys were not completed in the browser because the resident session is gated by first-login password change; API workflow tests remain the verification for those paths.
- A branch-admin account was not created in the browser. Assigning branch scope creates new security-sensitive access and requires action-time user confirmation. Existing API tests verify branch-admin isolation across residents, rooms, invoices, payments, admissions, and email activity.

### Defect found and fixed

The owner allocation dialog initially listed rooms from both branches, although the API rejected cross-branch assignment. The frontend now filters room options to the resident's branch. This was verified in the browser: a QA South Branch resident saw only its QA South room. Rebuild after this change is required and reported in the handover.

### Deployment limits

`docker`, `docker-compose`, `psql`, `pg_isready`, and `npm` were not installed in this environment. Compose and PostgreSQL health, migrations, persistence across restart, production job scheduling, and SMTP/Mailpit delivery remain unverified. The disposable SQLite API was started and migrated successfully, but this is not PostgreSQL verification. Reminder scheduling was disabled for the QA process; tests verify queue behavior and deduplication, not production scheduling.

### Legacy identifier classification

- User-visible branding is Cityhive in the site title/metadata, public and admin/resident shells, invoice PDF, receipt body, email subjects, and default fresh-install sender/account examples.
- Existing root/backend `.env` values retain `owner@staywell.local` so configured login identities remain unchanged. These files were not edited.
- `staywell.db` and the Alembic SQLite URL are retained to keep using the existing database file.
- `staywell-token` remains the browser session-storage key to preserve active sessions.
- `Message-ID` uses the legacy local mail domain as an email infrastructure identifier; it is not displayed in message content.
- `SW` remains in historical invoice and receipt identifiers. Issued invoice numbers were not renamed.
