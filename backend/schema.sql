-- Reference schema generated from current application models (2026-10-22).
-- Apply Alembic migrations, not this file, to upgrade an existing database.
-- Historical unmapped tables remain preserved by migrations.

CREATE TABLE users (
	id SERIAL NOT NULL,
	email VARCHAR(254) NOT NULL,
	password_hash VARCHAR(256) NOT NULL,
	role VARCHAR(16) NOT NULL,
	must_change_password BOOLEAN NOT NULL,
	phone VARCHAR(18),
	phone_verified_at TIMESTAMP WITH TIME ZONE,
	active BOOLEAN DEFAULT '1' NOT NULL,
	session_version INTEGER DEFAULT '0' NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (email)
);

CREATE TABLE branches (
	id SERIAL NOT NULL,
	name VARCHAR(100) NOT NULL,
	address VARCHAR(300) NOT NULL,
	contact_phone VARCHAR(30) NOT NULL,
	contact_email VARCHAR(254) DEFAULT '' NOT NULL,
	image_url VARCHAR(1000) DEFAULT '' NOT NULL,
	faqs JSON DEFAULT '[]' NOT NULL,
	description TEXT NOT NULL,
	facilities TEXT NOT NULL,
	rules TEXT NOT NULL,
	notice_days INTEGER,
	active BOOLEAN NOT NULL,
	published BOOLEAN DEFAULT '0' NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (name)
);

CREATE TABLE job_state (
	name VARCHAR(40) NOT NULL,
	last_started_at TIMESTAMP WITH TIME ZONE,
	last_succeeded_at TIMESTAMP WITH TIME ZONE,
	status VARCHAR(20) NOT NULL,
	PRIMARY KEY (name)
);

CREATE TABLE rate_limit_buckets (
	key VARCHAR(100) NOT NULL,
	window_start TIMESTAMP WITH TIME ZONE NOT NULL,
	attempts INTEGER NOT NULL,
	PRIMARY KEY (key)
);

CREATE INDEX ix_rate_limit_buckets_window_start ON rate_limit_buckets (window_start);

CREATE TABLE branch_admins (
	user_id INTEGER NOT NULL,
	branch_id INTEGER NOT NULL,
	PRIMARY KEY (user_id, branch_id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
	FOREIGN KEY(branch_id) REFERENCES branches (id) ON DELETE CASCADE
);

CREATE TABLE rooms (
	id SERIAL NOT NULL,
	branch_id INTEGER,
	number VARCHAR(30) NOT NULL,
	floor VARCHAR(30) NOT NULL,
	capacity INTEGER NOT NULL,
	monthly_fee NUMERIC(12, 2) NOT NULL,
	active BOOLEAN DEFAULT '1' NOT NULL,
	PRIMARY KEY (id),
	CHECK (capacity BETWEEN 1 AND 8),
	CHECK (monthly_fee >= 0),
	FOREIGN KEY(branch_id) REFERENCES branches (id),
	UNIQUE (number)
);

CREATE INDEX ix_rooms_branch_id ON rooms (branch_id);

CREATE TABLE fee_plans (
	id SERIAL NOT NULL,
	branch_id INTEGER NOT NULL,
	name VARCHAR(100) NOT NULL,
	sharing INTEGER NOT NULL,
	advance_amount NUMERIC(12, 2) DEFAULT '0' NOT NULL,
	monthly_fee NUMERIC(12, 2) NOT NULL,
	additional_charge_label VARCHAR(100) NOT NULL,
	additional_charge_amount NUMERIC(12, 2) NOT NULL,
	billing_day INTEGER NOT NULL,
	due_day INTEGER NOT NULL,
	effective_from DATE NOT NULL,
	effective_until DATE,
	active BOOLEAN DEFAULT '1' NOT NULL,
	created_by INTEGER NOT NULL,
	PRIMARY KEY (id),
	CHECK (sharing BETWEEN 1 AND 8),
	CHECK (monthly_fee >= 0 AND additional_charge_amount >= 0),
	CHECK (billing_day BETWEEN 1 AND 28 AND due_day BETWEEN 1 AND 28),
	FOREIGN KEY(branch_id) REFERENCES branches (id),
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE INDEX ix_fee_plans_branch_id ON fee_plans (branch_id);

CREATE TABLE otp_challenges (
	id SERIAL NOT NULL,
	challenge_id VARCHAR(36) NOT NULL,
	user_id INTEGER NOT NULL,
	purpose VARCHAR(20) NOT NULL,
	channel VARCHAR(16) DEFAULT 'whatsapp' NOT NULL,
	phone VARCHAR(18) NOT NULL,
	code_hash VARCHAR(64) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	last_sent_at TIMESTAMP WITH TIME ZONE NOT NULL,
	attempts INTEGER NOT NULL,
	consumed_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX ix_otp_challenges_challenge_id ON otp_challenges (challenge_id);

CREATE INDEX ix_otp_challenges_user_id ON otp_challenges (user_id);

CREATE TABLE auth_audit_events (
	id SERIAL NOT NULL,
	user_id INTEGER,
	actor_user_id INTEGER,
	event VARCHAR(32) NOT NULL,
	ip_hash VARCHAR(64) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL,
	FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_auth_audit_events_user_id ON auth_audit_events (user_id);

CREATE TABLE outbox (
	id SERIAL NOT NULL,
	user_id INTEGER,
	branch_id INTEGER,
	dedupe_key VARCHAR(120) NOT NULL,
	recipient VARCHAR(254) NOT NULL,
	subject VARCHAR(200) NOT NULL,
	body TEXT NOT NULL,
	sent_at TIMESTAMP WITH TIME ZONE,
	cancelled BOOLEAN NOT NULL,
	attempts INTEGER NOT NULL,
	last_error VARCHAR(100) NOT NULL,
	channel VARCHAR(20) DEFAULT 'email' NOT NULL,
	delivery_status VARCHAR(20) DEFAULT 'queued' NOT NULL,
	provider_message_id VARCHAR(100),
	next_attempt_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	FOREIGN KEY(user_id) REFERENCES users (id),
	FOREIGN KEY(branch_id) REFERENCES branches (id),
	UNIQUE (dedupe_key)
);

CREATE INDEX ix_outbox_branch_id ON outbox (branch_id);

CREATE INDEX ix_outbox_user_id ON outbox (user_id);

CREATE TABLE lifecycle_events (
	id SERIAL NOT NULL,
	entity VARCHAR(20) NOT NULL,
	entity_id INTEGER NOT NULL,
	branch_id INTEGER NOT NULL,
	actor_user_id INTEGER NOT NULL,
	action VARCHAR(20) NOT NULL,
	reason VARCHAR(500) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(branch_id) REFERENCES branches (id),
	FOREIGN KEY(actor_user_id) REFERENCES users (id)
);

CREATE INDEX ix_lifecycle_events_branch_id ON lifecycle_events (branch_id);

CREATE TABLE residents (
	id SERIAL NOT NULL,
	resident_code VARCHAR(20) NOT NULL,
	branch_id INTEGER,
	fee_plan_id INTEGER,
	user_id INTEGER NOT NULL,
	name VARCHAR(100) NOT NULL,
	phone VARCHAR(15) NOT NULL,
	guardian VARCHAR(100) NOT NULL,
	guardian_phone VARCHAR(15) NOT NULL,
	institution VARCHAR(150) NOT NULL,
	joined_on DATE NOT NULL,
	planned_move_out DATE,
	status VARCHAR(20) DEFAULT 'active' NOT NULL,
	room_id INTEGER,
	discount NUMERIC(12, 2) NOT NULL,
	aadhaar_last4 VARCHAR(4),
	id_status VARCHAR(20) NOT NULL,
	id_reviewed_by INTEGER,
	id_reviewed_at TIMESTAMP WITH TIME ZONE,
	whatsapp_notifications BOOLEAN DEFAULT '0' NOT NULL,
	whatsapp_consent_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	CHECK (discount >= 0),
	CONSTRAINT uq_residents_resident_code UNIQUE (resident_code),
	FOREIGN KEY(branch_id) REFERENCES branches (id),
	FOREIGN KEY(fee_plan_id) REFERENCES fee_plans (id),
	UNIQUE (user_id),
	FOREIGN KEY(user_id) REFERENCES users (id),
	FOREIGN KEY(room_id) REFERENCES rooms (id),
	FOREIGN KEY(id_reviewed_by) REFERENCES users (id)
);

CREATE INDEX ix_residents_branch_id ON residents (branch_id);

CREATE TABLE admissions (
	id SERIAL NOT NULL,
	branch_id INTEGER NOT NULL,
	name VARCHAR(100) NOT NULL,
	email VARCHAR(254) NOT NULL,
	phone VARCHAR(15) NOT NULL,
	emergency_contact VARCHAR(100) NOT NULL,
	emergency_phone VARCHAR(15) NOT NULL,
	preferred_sharing INTEGER NOT NULL,
	move_in_date DATE NOT NULL,
	message TEXT NOT NULL,
	submission_key VARCHAR(64) NOT NULL,
	whatsapp_updates BOOLEAN DEFAULT '0' NOT NULL,
	status VARCHAR(20) NOT NULL,
	admin_note TEXT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	reviewed_by INTEGER,
	reviewed_at TIMESTAMP WITH TIME ZONE,
	resident_id INTEGER,
	PRIMARY KEY (id),
	UNIQUE (submission_key),
	CHECK (preferred_sharing BETWEEN 1 AND 8),
	FOREIGN KEY(branch_id) REFERENCES branches (id),
	FOREIGN KEY(reviewed_by) REFERENCES users (id),
	UNIQUE (resident_id),
	FOREIGN KEY(resident_id) REFERENCES residents (id)
);

CREATE INDEX ix_admissions_email ON admissions (email);

CREATE INDEX ix_admissions_status ON admissions (status);

CREATE INDEX ix_admissions_branch_id ON admissions (branch_id);

CREATE TABLE allocation_events (
	id SERIAL NOT NULL,
	resident_id INTEGER NOT NULL,
	from_room_id INTEGER,
	to_room_id INTEGER,
	actor_user_id INTEGER,
	reason TEXT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(resident_id) REFERENCES residents (id),
	FOREIGN KEY(from_room_id) REFERENCES rooms (id),
	FOREIGN KEY(to_room_id) REFERENCES rooms (id),
	FOREIGN KEY(actor_user_id) REFERENCES users (id)
);

CREATE INDEX ix_allocation_events_resident_id ON allocation_events (resident_id);

CREATE TABLE stay_requests (
	id SERIAL NOT NULL,
	resident_id INTEGER NOT NULL,
	request_type VARCHAR(20) NOT NULL,
	target_room_id INTEGER,
	requested_move_out DATE,
	notice_exception_reason TEXT NOT NULL,
	note TEXT NOT NULL,
	status VARCHAR(20) NOT NULL,
	admin_note TEXT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	reviewed_by INTEGER,
	reviewed_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	FOREIGN KEY(resident_id) REFERENCES residents (id),
	FOREIGN KEY(target_room_id) REFERENCES rooms (id),
	FOREIGN KEY(reviewed_by) REFERENCES users (id)
);

CREATE INDEX ix_stay_requests_resident_id ON stay_requests (resident_id);

CREATE INDEX ix_stay_requests_status ON stay_requests (status);

CREATE TABLE identity_review_events (
	id SERIAL NOT NULL,
	resident_id INTEGER NOT NULL,
	reviewer_id INTEGER NOT NULL,
	old_status VARCHAR(20) NOT NULL,
	new_status VARCHAR(20) NOT NULL,
	note TEXT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(resident_id) REFERENCES residents (id),
	FOREIGN KEY(reviewer_id) REFERENCES users (id)
);

CREATE INDEX ix_identity_review_events_resident_id ON identity_review_events (resident_id);

CREATE TABLE resident_discounts (
	id SERIAL NOT NULL,
	resident_id INTEGER NOT NULL,
	percentage NUMERIC(5, 2) NOT NULL,
	charge_scope VARCHAR(20) NOT NULL,
	max_amount NUMERIC(12, 2),
	effective_from DATE NOT NULL,
	effective_until DATE NOT NULL,
	reason VARCHAR(500) NOT NULL,
	approved_by INTEGER NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	revoked_at TIMESTAMP WITH TIME ZONE,
	revoked_by INTEGER,
	PRIMARY KEY (id),
	CHECK (percentage > 0 AND percentage <= 100),
	CHECK (charge_scope IN ('accommodation','all_monthly')),
	CHECK (max_amount IS NULL OR max_amount >= 0),
	CHECK (effective_until >= effective_from),
	FOREIGN KEY(resident_id) REFERENCES residents (id),
	FOREIGN KEY(approved_by) REFERENCES users (id),
	FOREIGN KEY(revoked_by) REFERENCES users (id)
);

CREATE INDEX ix_resident_discounts_resident_id ON resident_discounts (resident_id);

CREATE TABLE notification_preference_events (
	id SERIAL NOT NULL,
	resident_id INTEGER NOT NULL,
	enabled BOOLEAN NOT NULL,
	source VARCHAR(40) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(resident_id) REFERENCES residents (id)
);

CREATE INDEX ix_notification_preference_events_resident_id ON notification_preference_events (resident_id);

CREATE TABLE complaints (
	id SERIAL NOT NULL,
	resident_id INTEGER NOT NULL,
	category VARCHAR(30) NOT NULL,
	title VARCHAR(150) NOT NULL,
	description TEXT NOT NULL,
	status VARCHAR(20) NOT NULL,
	response TEXT NOT NULL,
	assigned_to_user_id INTEGER,
	resolution_note TEXT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	resolved_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	FOREIGN KEY(resident_id) REFERENCES residents (id),
	FOREIGN KEY(assigned_to_user_id) REFERENCES users (id)
);

CREATE INDEX ix_complaints_assigned_to_user_id ON complaints (assigned_to_user_id);

CREATE TABLE gate_passes (
	id SERIAL NOT NULL,
	pass_code VARCHAR(64) NOT NULL,
	resident_id INTEGER NOT NULL,
	created_by INTEGER NOT NULL,
	valid_from TIMESTAMP WITH TIME ZONE NOT NULL,
	valid_until DATE,
	revoked_at TIMESTAMP WITH TIME ZONE,
	revoked_by INTEGER,
	PRIMARY KEY (id),
	FOREIGN KEY(resident_id) REFERENCES residents (id),
	FOREIGN KEY(created_by) REFERENCES users (id),
	FOREIGN KEY(revoked_by) REFERENCES users (id)
);

CREATE INDEX ix_gate_passes_resident_id ON gate_passes (resident_id);

CREATE UNIQUE INDEX ix_gate_passes_pass_code ON gate_passes (pass_code);

CREATE TABLE final_settlements (
	id SERIAL NOT NULL,
	resident_id INTEGER NOT NULL,
	branch_id INTEGER NOT NULL,
	status VARCHAR(24) NOT NULL,
	deposit_balance_snapshot NUMERIC(12, 2) NOT NULL,
	advance_balance_snapshot NUMERIC(12, 2) NOT NULL,
	invoice_balance_snapshot NUMERIC(12, 2) NOT NULL,
	proposed_refund NUMERIC(12, 2) NOT NULL,
	note VARCHAR(1000) NOT NULL,
	decision_note VARCHAR(1000) NOT NULL,
	created_by INTEGER NOT NULL,
	decided_by INTEGER,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	decided_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	CHECK (proposed_refund >= 0),
	CHECK (status IN ('pending','approved','rejected','partially_refunded','completed','no_refund')),
	FOREIGN KEY(resident_id) REFERENCES residents (id),
	FOREIGN KEY(branch_id) REFERENCES branches (id),
	FOREIGN KEY(created_by) REFERENCES users (id),
	FOREIGN KEY(decided_by) REFERENCES users (id)
);

CREATE INDEX ix_final_settlements_status ON final_settlements (status);

CREATE INDEX ix_final_settlements_branch_id ON final_settlements (branch_id);

CREATE INDEX ix_final_settlements_resident_id ON final_settlements (resident_id);

CREATE TABLE identity_documents (
	id SERIAL NOT NULL,
	resident_id INTEGER NOT NULL,
	content_type VARCHAR(40) NOT NULL,
	encrypted_content BYTEA NOT NULL,
	uploaded_by INTEGER NOT NULL,
	uploaded_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (resident_id),
	FOREIGN KEY(resident_id) REFERENCES residents (id),
	FOREIGN KEY(uploaded_by) REFERENCES users (id)
);

CREATE TABLE admission_events (
	id SERIAL NOT NULL,
	admission_id INTEGER NOT NULL,
	actor_user_id INTEGER,
	old_status VARCHAR(20) NOT NULL,
	new_status VARCHAR(20) NOT NULL,
	note TEXT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(admission_id) REFERENCES admissions (id),
	FOREIGN KEY(actor_user_id) REFERENCES users (id)
);

CREATE TABLE invoices (
	id SERIAL NOT NULL,
	invoice_number VARCHAR(40) NOT NULL,
	issued_on DATE NOT NULL,
	resident_id INTEGER NOT NULL,
	branch_id INTEGER,
	fee_plan_id INTEGER,
	month DATE NOT NULL,
	due_on DATE NOT NULL,
	room_number VARCHAR(30) NOT NULL,
	base_fee NUMERIC(12, 2) NOT NULL,
	additional_charge_label VARCHAR(100) NOT NULL,
	additional_charge_amount NUMERIC(12, 2) NOT NULL,
	discount NUMERIC(12, 2) NOT NULL,
	discount_rule_id INTEGER,
	discount_percent NUMERIC(5, 2) DEFAULT '0' NOT NULL,
	amount NUMERIC(12, 2) NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (resident_id, month),
	UNIQUE (invoice_number),
	CHECK (amount >= 0),
	FOREIGN KEY(resident_id) REFERENCES residents (id),
	FOREIGN KEY(branch_id) REFERENCES branches (id),
	FOREIGN KEY(fee_plan_id) REFERENCES fee_plans (id),
	FOREIGN KEY(discount_rule_id) REFERENCES resident_discounts (id)
);

CREATE INDEX ix_invoices_branch_id ON invoices (branch_id);

CREATE TABLE complaint_events (
	id SERIAL NOT NULL,
	complaint_id INTEGER NOT NULL,
	actor_user_id INTEGER,
	action VARCHAR(20) NOT NULL,
	old_status VARCHAR(20),
	new_status VARCHAR(20) NOT NULL,
	old_response TEXT,
	new_response TEXT NOT NULL,
	old_assignee_user_id INTEGER,
	new_assignee_user_id INTEGER,
	resolution_note TEXT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(complaint_id) REFERENCES complaints (id),
	FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE SET NULL,
	FOREIGN KEY(old_assignee_user_id) REFERENCES users (id),
	FOREIGN KEY(new_assignee_user_id) REFERENCES users (id)
);

CREATE INDEX ix_complaint_events_complaint_id ON complaint_events (complaint_id);

CREATE TABLE financial_ledger_events (
	id SERIAL NOT NULL,
	resident_id INTEGER NOT NULL,
	branch_id INTEGER NOT NULL,
	settlement_id INTEGER,
	account_type VARCHAR(12) NOT NULL,
	action VARCHAR(12) NOT NULL,
	amount NUMERIC(12, 2) NOT NULL,
	method VARCHAR(20),
	reference VARCHAR(100) NOT NULL,
	reason VARCHAR(500) NOT NULL,
	idempotency_key VARCHAR(64) NOT NULL,
	actor_user_id INTEGER NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CHECK (amount > 0),
	CHECK (account_type IN ('deposit','advance')),
	CHECK (action IN ('received','deduction','refund')),
	FOREIGN KEY(resident_id) REFERENCES residents (id),
	FOREIGN KEY(branch_id) REFERENCES branches (id),
	FOREIGN KEY(settlement_id) REFERENCES final_settlements (id),
	UNIQUE (idempotency_key),
	FOREIGN KEY(actor_user_id) REFERENCES users (id)
);

CREATE INDEX ix_financial_ledger_events_branch_id ON financial_ledger_events (branch_id);

CREATE INDEX ix_financial_ledger_events_settlement_id ON financial_ledger_events (settlement_id);

CREATE INDEX ix_financial_ledger_events_resident_id ON financial_ledger_events (resident_id);

CREATE TABLE settlement_events (
	id SERIAL NOT NULL,
	settlement_id INTEGER NOT NULL,
	actor_user_id INTEGER NOT NULL,
	action VARCHAR(24) NOT NULL,
	old_status VARCHAR(24),
	new_status VARCHAR(24) NOT NULL,
	note VARCHAR(1000) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(settlement_id) REFERENCES final_settlements (id),
	FOREIGN KEY(actor_user_id) REFERENCES users (id)
);

CREATE INDEX ix_settlement_events_settlement_id ON settlement_events (settlement_id);

CREATE TABLE payments (
	id SERIAL NOT NULL,
	invoice_id INTEGER NOT NULL,
	amount NUMERIC(12, 2) NOT NULL,
	method VARCHAR(20) NOT NULL,
	reference VARCHAR(100) NOT NULL,
	idempotency_key VARCHAR(64) NOT NULL,
	recorded_by INTEGER NOT NULL,
	paid_at TIMESTAMP WITH TIME ZONE NOT NULL,
	payer_name VARCHAR(100) NOT NULL,
	note VARCHAR(500) NOT NULL,
	reversed_at TIMESTAMP WITH TIME ZONE,
	reversed_by INTEGER,
	reversal_reason VARCHAR(500) NOT NULL,
	PRIMARY KEY (id),
	CHECK (amount > 0),
	FOREIGN KEY(invoice_id) REFERENCES invoices (id),
	UNIQUE (idempotency_key),
	FOREIGN KEY(recorded_by) REFERENCES users (id),
	FOREIGN KEY(reversed_by) REFERENCES users (id)
);

CREATE INDEX ix_payments_paid_at ON payments (paid_at);

CREATE TABLE payment_audit_events (
	id SERIAL NOT NULL,
	payment_id INTEGER NOT NULL,
	actor_user_id INTEGER NOT NULL,
	action VARCHAR(20) NOT NULL,
	reason VARCHAR(500) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(payment_id) REFERENCES payments (id),
	FOREIGN KEY(actor_user_id) REFERENCES users (id)
);

CREATE INDEX ix_payment_audit_events_payment_id ON payment_audit_events (payment_id);
