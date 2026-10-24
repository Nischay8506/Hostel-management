"""Add effective fee plans, separate settlement ledgers, and complaint assignment."""
from alembic import op
import sqlalchemy as sa

revision = '0013_fees_settlements_complaint_assignment'
down_revision = '0012_resident_codes_gate_passes'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'fee_plans',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('sharing', sa.Integer(), nullable=False),
        sa.Column('monthly_fee', sa.Numeric(12, 2), nullable=False),
        sa.Column('additional_charge_label', sa.String(100), nullable=False, server_default=''),
        sa.Column('additional_charge_amount', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('billing_day', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('due_day', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('effective_until', sa.Date(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.CheckConstraint('sharing BETWEEN 1 AND 8', name='ck_fee_plans_sharing'),
        sa.CheckConstraint('monthly_fee >= 0 AND additional_charge_amount >= 0', name='ck_fee_plans_amounts'),
        sa.CheckConstraint('billing_day BETWEEN 1 AND 28 AND due_day BETWEEN 1 AND 28', name='ck_fee_plans_days'),
    )
    op.create_index('ix_fee_plans_branch_id', 'fee_plans', ['branch_id'])
    # SQLite cannot add a foreign key constraint with ALTER TABLE. Batch mode
    # keeps the revision portable while preserving existing resident/invoice rows.
    with op.batch_alter_table('residents') as batch:
        batch.add_column(sa.Column('fee_plan_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_residents_fee_plan_id_fee_plans', 'fee_plans', ['fee_plan_id'], ['id'])
    with op.batch_alter_table('invoices') as batch:
        batch.add_column(sa.Column('fee_plan_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('additional_charge_label', sa.String(100), nullable=False, server_default=''))
        batch.add_column(sa.Column('additional_charge_amount', sa.Numeric(12, 2), nullable=False, server_default='0'))
        batch.create_foreign_key('fk_invoices_fee_plan_id_fee_plans', 'fee_plans', ['fee_plan_id'], ['id'])

    with op.batch_alter_table('complaints') as batch:
        batch.add_column(sa.Column('assigned_to_user_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('resolution_note', sa.Text(), nullable=False, server_default=''))
        batch.add_column(sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key('fk_complaints_assigned_to_user_id_users', 'users', ['assigned_to_user_id'], ['id'])
    op.execute(sa.text('UPDATE complaints SET updated_at=created_at WHERE updated_at IS NULL'))
    with op.batch_alter_table('complaints') as batch:
        batch.alter_column('updated_at', existing_type=sa.DateTime(timezone=True), nullable=False)
    op.create_index('ix_complaints_assigned_to_user_id', 'complaints', ['assigned_to_user_id'])
    with op.batch_alter_table('complaint_events') as batch:
        batch.add_column(sa.Column('old_assignee_user_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('new_assignee_user_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('resolution_note', sa.Text(), nullable=False, server_default=''))
        batch.create_foreign_key('fk_complaint_events_old_assignee_user_id_users', 'users', ['old_assignee_user_id'], ['id'])
        batch.create_foreign_key('fk_complaint_events_new_assignee_user_id_users', 'users', ['new_assignee_user_id'], ['id'])

    op.create_table(
        'final_settlements',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('resident_id', sa.Integer(), sa.ForeignKey('residents.id'), nullable=False),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id'), nullable=False),
        sa.Column('status', sa.String(24), nullable=False, server_default='pending'),
        sa.Column('deposit_balance_snapshot', sa.Numeric(12, 2), nullable=False),
        sa.Column('advance_balance_snapshot', sa.Numeric(12, 2), nullable=False),
        sa.Column('invoice_balance_snapshot', sa.Numeric(12, 2), nullable=False),
        sa.Column('proposed_refund', sa.Numeric(12, 2), nullable=False),
        sa.Column('note', sa.String(1000), nullable=False, server_default=''),
        sa.Column('decision_note', sa.String(1000), nullable=False, server_default=''),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('decided_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('proposed_refund >= 0', name='ck_final_settlements_refund'),
        sa.CheckConstraint("status IN ('pending','approved','rejected','partially_refunded','completed','no_refund')", name='ck_final_settlements_status'),
    )
    op.create_index('ix_final_settlements_resident_id', 'final_settlements', ['resident_id'])
    op.create_index('ix_final_settlements_branch_id', 'final_settlements', ['branch_id'])
    op.create_index('ix_final_settlements_status', 'final_settlements', ['status'])
    op.create_table(
        'financial_ledger_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('resident_id', sa.Integer(), sa.ForeignKey('residents.id'), nullable=False),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id'), nullable=False),
        sa.Column('settlement_id', sa.Integer(), sa.ForeignKey('final_settlements.id'), nullable=True),
        sa.Column('account_type', sa.String(12), nullable=False),
        sa.Column('action', sa.String(12), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('method', sa.String(20), nullable=True),
        sa.Column('reference', sa.String(100), nullable=False, server_default=''),
        sa.Column('reason', sa.String(500), nullable=False, server_default=''),
        sa.Column('idempotency_key', sa.String(64), nullable=False, unique=True),
        sa.Column('actor_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('amount > 0', name='ck_financial_ledger_events_amount'),
        sa.CheckConstraint("account_type IN ('deposit','advance')", name='ck_financial_ledger_events_account_type'),
        sa.CheckConstraint("action IN ('received','deduction','refund')", name='ck_financial_ledger_events_action'),
    )
    op.create_index('ix_financial_ledger_events_resident_id', 'financial_ledger_events', ['resident_id'])
    op.create_index('ix_financial_ledger_events_branch_id', 'financial_ledger_events', ['branch_id'])
    op.create_index('ix_financial_ledger_events_settlement_id', 'financial_ledger_events', ['settlement_id'])
    op.create_table(
        'settlement_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('settlement_id', sa.Integer(), sa.ForeignKey('final_settlements.id'), nullable=False),
        sa.Column('actor_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('action', sa.String(24), nullable=False),
        sa.Column('old_status', sa.String(24), nullable=True),
        sa.Column('new_status', sa.String(24), nullable=False),
        sa.Column('note', sa.String(1000), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_settlement_events_settlement_id', 'settlement_events', ['settlement_id'])

    op.create_table(
        'gate_pass_validation_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('gate_pass_id', sa.Integer(), sa.ForeignKey('gate_passes.id'), nullable=False),
        sa.Column('actor_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('outcome', sa.String(20), nullable=False),
        sa.Column('checked_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_gate_pass_validation_events_gate_pass_id', 'gate_pass_validation_events', ['gate_pass_id'])


def downgrade():
    raise RuntimeError('Fee, settlement, complaint assignment, and gate-pass validation history are retained; restore a backup to reverse this migration.')
