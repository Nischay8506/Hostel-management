# Gap-feature acceptance — 22 October 2026

Target: local Vite at `http://127.0.0.1:5179`, isolated SQLite API at port 8019, synthetic owner/resident/branch records. Real provider delivery was disabled. Checks used the supported in-app browser. This log supersedes the earlier browser-unavailable status for the journeys listed here; other unexecuted journeys in `ACCEPTANCE.md` remain unverified.

| Check | Observed result |
|---|---|
| Public page | Configured advance of INR 5,000 visible with the 2-person plan; custom branch FAQ, map link/embed, WhatsApp link, enquiry consent and private tracking form exposed. Illustrative room fallback clearly labelled. |
| Management sign-in | Synthetic password accepted; test-provider OTP required; successful verification opened dashboard. No real phone message sent. |
| Dashboard | Six additional operational KPIs rendered with the authorized branch data. |
| Fee plan | Configured advance displayed in the list and create form. Empty submit showed inline errors for missing plan name and monthly fee, focused the first field and exposed errors to accessibility APIs. |
| Monthly billing | Generated one synthetic October invoice; confirmation shown and ledger displayed INR 8,500 outstanding with due date and overdue status. |
| Payment drilldown | Opened the specific invoice's dialog; invoice number, total/balance, empty payment history and invoice download available. |
| Financial analytics | Paid-only selection updated report to zero outstanding and no matching resident invoices; sorting controls present. Numeric multi-row ordering is covered by the frontend test. |
| Resident lifecycle | Deactivate control verified in the main Residents screen as well as Overview. Financial balance/session guards are covered by backend tests. |
| Identity documents | Staff review dialog renders the private file chooser/upload controls alongside manual review. Encrypted storage, invalid-content rejection, removal, audit and branch isolation are covered by backend tests. |
| Desktop ledger | At 1365×900, filters fit the panel after adding consistent padding and shrink/wrap behavior. Screenshot: `ledger-desktop-2026-10-22.jpg`. |
| Mobile ledger | At 390×844, fields stack, buttons remain accessible and tables scroll inside the panel. Observed document scroll width equals viewport content width (375px, excluding scrollbar); no page-wide horizontal overflow. Screenshot: `ledger-mobile-2026-10-22.jpg`. |
| Browser console | No warning/error entries returned during dashboard inspection. Later screens showed no application error in their visible state; exhaustive network/console monitoring was not performed. |
| Financial PDFs | Synthetic invoice and settlement rendered to PNG and visually inspected: original emblem, aligned columns/amounts, readable metadata, margins and footer/page number; no overlap or clipping. Automated parsing also verifies a long document spans multiple pages. |

Screenshots contain synthetic local data only. No real payments, admissions, identity documents or messages were created. The original illustrative property image was not represented as a genuine property photograph.

Not covered by this targeted browser pass: full resident/branch-admin interactive journeys, all device sizes, map-provider availability, actual SMS/WhatsApp/email delivery, production hosting, load/concurrency testing or a full assistive-technology audit. Automated tests cover the relevant endpoint permissions and workflows separately.
