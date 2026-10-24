# Cityhive API route inventory

Generated from FastAPI registration on 2026-10-22. This is a source inventory, not production execution evidence. Enquiry lookup requires email plus a private tracking key. Auth endpoints use password/OTP checks; the internal job endpoint uses its private header and webhook callbacks require signature verification.

| Method | Path | Handler | Access boundary |
|---|---|---|---|
| GET | /api/health | health | public or endpoint-specific verification |
| GET | /api/branches | branches | public or endpoint-specific verification |
| GET | /api/managed-branches | managed_branches | staff with branch scope |
| GET | /api/public/branches/{branch_id}/availability | public_availability | public or endpoint-specific verification |
| POST | /api/admissions | submit_admission | public or endpoint-specific verification |
| GET | /api/admissions | admissions | staff with branch scope |
| PUT | /api/admissions/{admission_id} | decide_admission | staff with branch scope |
| POST | /api/admissions/{admission_id}/enroll | enroll_admission | staff with branch scope |
| POST | /api/branches | add_branch | owner |
| PUT | /api/branches/{branch_id} | update_branch | owner |
| PUT | /api/branches/{branch_id}/publication | update_branch_publication | owner |
| POST | /api/branch-admins | add_branch_admin | owner |
| GET | /api/branch-admins | branch_admins | owner |
| POST | /api/auth/login | login | public or endpoint-specific verification |
| POST | /api/auth/otp/resend | resend_otp | public or endpoint-specific verification |
| POST | /api/auth/otp/verify | verify_otp | public or endpoint-specific verification |
| GET | /api/whatsapp/status | whatsapp_status | owner |
| GET | /api/auth/me | me | authenticated challenge/account |
| GET | /api/my/notification-preferences | my_notification_preferences | authenticated account with endpoint ownership checks |
| PUT | /api/my/notification-preferences | update_notification_preferences | authenticated account with endpoint ownership checks |
| POST | /api/auth/password | change_password | authenticated challenge/account |
| GET | /api/rooms | rooms | staff with branch scope |
| POST | /api/rooms | add_room | staff with branch scope |
| PUT | /api/rooms/{room_id} | update_room | staff with branch scope |
| GET | /api/fee-plans | fee_plans | staff with branch scope |
| POST | /api/fee-plans | create_fee_plan | staff with branch scope |
| PUT | /api/fee-plans/{plan_id} | update_fee_plan | staff with branch scope |
| PUT | /api/residents/{resident_id}/fee-plan | assign_resident_fee_plan | staff with branch scope |
| GET | /api/residents/{resident_id}/financial-ledger | resident_financial_ledger | authenticated account with endpoint ownership checks |
| POST | /api/residents/{resident_id}/financial-ledger | add_financial_ledger_event | staff with branch scope |
| GET | /api/settlements | settlements | authenticated account with endpoint ownership checks |
| POST | /api/settlements | create_settlement | staff with branch scope |
| PUT | /api/settlements/{settlement_id}/decision | decide_settlement | staff with branch scope |
| POST | /api/settlements/{settlement_id}/refund | record_settlement_refund | staff with branch scope |
| GET | /api/settlements/{settlement_id}/history | settlement_history | authenticated account with endpoint ownership checks |
| GET | /api/residents | residents | authenticated account with endpoint ownership checks |
| GET | /api/gate-passes | gate_passes | authenticated account with endpoint ownership checks |
| POST | /api/gate-passes | issue_gate_pass | staff with branch scope |
| PUT | /api/gate-passes/{pass_id}/revoke | revoke_gate_pass | staff with branch scope |
| POST | /api/residents | add_resident | staff with branch scope |
| PUT | /api/residents/{resident_id}/allocation | allocate | staff with branch scope |
| PUT | /api/residents/{resident_id}/id-review | review | staff with branch scope |
| GET | /api/residents/{resident_id}/allocation-history | allocation_history | authenticated account with endpoint ownership checks |
| GET | /api/residents/{resident_id}/verification-history | verification_history | authenticated account with endpoint ownership checks |
| GET | /api/invoices | invoices | authenticated account with endpoint ownership checks |
| GET | /api/invoices/{invoice_id}/pdf | invoice_download | authenticated account with endpoint ownership checks |
| POST | /api/billing/generate | billing | staff with branch scope |
| POST | /api/payments | payment | staff with branch scope |
| POST | /api/payments/{payment_id}/reverse | reverse_payment | staff with branch scope |
| GET | /api/payments | payments | authenticated account with endpoint ownership checks |
| GET | /api/payments/{payment_id}/receipt | receipt | authenticated account with endpoint ownership checks |
| POST | /api/reminders/run | remind | staff with branch scope |
| GET | /api/emails | emails | staff with branch scope |
| GET | /api/complaints | complaints | authenticated account with endpoint ownership checks |
| GET | /api/complaint-assignees | complaint_assignees | staff with branch scope |
| POST | /api/complaints | add_complaint | authenticated account with endpoint ownership checks |
| PUT | /api/complaints/{complaint_id} | update_complaint | staff with branch scope |
| PUT | /api/complaints/{complaint_id}/assignment | assign_complaint | staff with branch scope |
| GET | /api/my/stay-requests | my_stay_requests | authenticated account with endpoint ownership checks |
| POST | /api/my/stay-requests | create_stay_request | authenticated account with endpoint ownership checks |
| GET | /api/my/available-rooms | my_available_rooms | authenticated account with endpoint ownership checks |
| GET | /api/stay-requests | stay_requests | staff with branch scope |
| PUT | /api/stay-requests/{request_id} | decide_stay_request | staff with branch scope |
| POST | /api/stays/process-moveouts | process_moveouts | staff with branch scope |
| GET | /api/dashboard | dashboard | authenticated account with endpoint ownership checks |
| GET | /api/analytics/financial | financial_analytics | staff with branch scope |
| GET | /api/analytics/financial.csv | financial_analytics_csv | staff with branch scope |
| GET | /api/build | build_information | public or endpoint-specific verification |
| GET | /api/deployment-status | deployment_status | owner |
| POST | /api/internal/jobs/run | scheduled_job | public or endpoint-specific verification |
| GET | /api/payments/{payment_id}/receipt.pdf | receipt_download | authenticated account with endpoint ownership checks |
| GET | /api/my/notifications | my_notifications | authenticated account with endpoint ownership checks |
| GET | /api/admissions/{admission_id}/history | admission_history | authenticated account with endpoint ownership checks |
| GET | /api/residents/{resident_id}/discounts | discounts | authenticated account with endpoint ownership checks |
| POST | /api/residents/{resident_id}/discounts | approve_discount | staff with branch scope |
| PUT | /api/discounts/{discount_id}/revoke | revoke_discount | staff with branch scope |
| GET | /api/notifications/whatsapp/webhook | verify_whatsapp_webhook | public or endpoint-specific verification |
| POST | /api/notifications/whatsapp/webhook | whatsapp_delivery_webhook | public or endpoint-specific verification |
| PUT | /api/branches/{branch_id}/faqs | branch_faqs | owner |
| POST | /api/public/admissions/status | admission_status | public or endpoint-specific verification |
| PUT | /api/rooms/{room_id}/status | room_status | staff with branch scope |
| DELETE | /api/rooms/{room_id} | decommission_room | staff with branch scope |
| PUT | /api/residents/{resident_id}/status | resident_status | staff with branch scope |
| GET | /api/lifecycle-history | lifecycle_history | staff with branch scope |
| GET | /api/residents/{resident_id}/identity-document | document_info | authenticated account with endpoint ownership checks |
| PUT | /api/residents/{resident_id}/identity-document | upload_document | authenticated account with endpoint ownership checks |
| GET | /api/residents/{resident_id}/identity-document/download | download_document | authenticated account with endpoint ownership checks |
| DELETE | /api/residents/{resident_id}/identity-document | delete_document | authenticated account with endpoint ownership checks |
| GET | /api/settlements/{settlement_id}/pdf | settlement_pdf | authenticated account with endpoint ownership checks |
