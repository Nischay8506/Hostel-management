# Cityhive manual browser acceptance

Status on 2026-10-21: **not executed**. The supported browser tool returned “Local browser use is disabled in Work settings.” No replacement browser automation was used, and no screenshots or browser-console results are claimed. API tests and HTTP probes do not constitute browser acceptance.

Enable the supported browser in Work settings, or have an authorized tester execute this checklist on a disposable staging environment. Use synthetic accounts and two explicitly named test branches; never populate production with QA records. Do not capture passwords, OTPs, full identity documents, personal records or tokens in screenshots.

For each journey record URL, viewport, role, expected/actual result, HTTP failures, console errors, screenshot filename and tester/date. Capture at 1440×900, 1920×1080, 768×1024 and 390×844. Repeat the critical actions on mobile, not just the initial page load.

| Journey | Required completion and denied-state checks | Suggested screenshot |
|---|---|---|
| Public homepage | Original emblem, full Cityhive identity, both sign-in actions, legible representative-image caption, correct hero CTAs; no overflow | `01-home-<width>.png` |
| Branch setup | Owner creates/edits both synthetic branches; supplies actual test inventory; publication checklist blocks incomplete publication; unpublished/inactive branches stay private | `02-branch-setup.png` |
| Branch discovery | Both published cards; correct contact/photo data; `#branch-<id>` refresh selects the right branch; sharing/budget filters and zero-result reset work | `03-branches-<width>.png` |
| Availability | Allocate the last bed, refresh public inventory, verify it disappears; change configured fees, verify displayed accommodation/add-on amounts; prices are marked “from” when grouped by sharing | `04-rooms-<width>.png` |
| Contact/enquiry | Refresh `/#contact` and `/#enquire`; missing/invalid email/phone/date/sharing are blocked; duplicate-click/retry cannot create duplicate admissions; success supplies request ID and no reservation claim | `05-contact-<width>.png` |
| Failure states | Simulate network loss, slow API, HTML fallback and denied access; verify clear error, retry, loading and empty states; no false successful submission | `06-service-error.png` |
| Authentication | Owner, branch admin and resident: valid password → WhatsApp challenge → correct OTP → session; wrong/expired/replayed code, resend cooldown, required initial password change; no session before OTP | `07-auth.png` |
| Admission and identity | Staff requests info/approves/rejects; approved request enrolls once; manual last-four review records staff/timestamp; allocation is separate; resident sees own admission status/history | `08-admission.png` |
| Room/stay | Allocate without overcapacity; shift and inspect previous/new history; submit extension/vacating, review notice exception; unpaid invoice prevents scheduled release; paid eligible stay releases on date | `09-stay.png` |
| Fees/discounts | Create effective fee plan; bill once; enable percentage feature only in staging, approve eligible scope/cap/dates; reject overlaps/fixed stacking; revoke then confirm old invoice unchanged | `10-fees.png` |
| Payments/PDFs | Search invoice, record partial cash and UPI/bank payments, retry identical key, verify balances and both PDFs; reverse with reason and confirm audit/collections; another resident/branch must be denied download | `11-payment.png` |
| Deposits/settlement | Record deposit/advance, reasoned deduction, settlement approval, then separate actual refund; approval alone must not reduce refundable balance | `12-settlement.png` |
| Analytics | Compare daily/weekly/monthly totals, aging, resident delay/sample size and historical room attribution to fixtures; CSV matches; overdue drill-down finds the exact invoice | `13-analytics.png` |
| Complaints | Resident submits; authorized staff assigns/responds/resolves; resident sees own history; other branch cannot assign/respond or read | `14-complaints.png` |
| Basic passes | Issue/view/print/revoke; expired/revoked/vacated status shown; other resident/branch denied; no scanning/code-validation controls | `15-basic-pass.png` |
| Messages/account | Resident notification history contains only owned messages; portal opt-out cancels pending WhatsApp reminder; owner sees worker last success; verify real provider separately | `16-account.png` |
| Authorization attacks | Edit branch/resident/invoice/payment IDs and report query parameters; test tokenless and resident requests against staff endpoints and PDFs; backend must deny regardless of hidden UI controls | Record status codes without tokens |
| Accessibility | Tab through forms/navigation; modal traps focus and restores it; Escape closes eligible dialogs/mobile navigation; labels, focus outlines, contrast, reduced motion and screen-reader errors; no content hidden by sticky header | `17-keyboard-mobile.png` |

Provider acceptance is a separate test: use an authorized real recipient, approved Meta templates, SMTP inbox, signed callback and the deployed scheduler. Verify successful delivery, opted-out reminder cancellation and a worker restart. Keep evidence free of message secrets. PostgreSQL/container verification is described in `../DEPLOYMENT.md`.
