"""Add public configuration, optional discount approvals and operational state.

No issued amount, historical identifier or existing business record is changed.
"""
from alembic import op
import sqlalchemy as sa

revision = '0014_release_completion'
down_revision = '0013_fees_settlements_complaint_assignment'
branch_labels = None
depends_on = None

def upgrade():
    bind=op.get_bind()
    tables=set(sa.inspect(bind).get_table_names())
    # Earlier historical revisions used current model metadata for fresh tables.
    # Inspect first so upgrading either a fresh or populated database is safe.
    if 'resident_discounts' not in tables:
        op.create_table('resident_discounts',
            sa.Column('id',sa.Integer(),primary_key=True),
            sa.Column('resident_id',sa.Integer(),sa.ForeignKey('residents.id'),nullable=False),
            sa.Column('percentage',sa.Numeric(5,2),nullable=False),
            sa.Column('charge_scope',sa.String(20),nullable=False),
            sa.Column('max_amount',sa.Numeric(12,2),nullable=True),
            sa.Column('effective_from',sa.Date(),nullable=False),
            sa.Column('effective_until',sa.Date(),nullable=False),
            sa.Column('reason',sa.String(500),nullable=False),
            sa.Column('approved_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
            sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
            sa.Column('revoked_at',sa.DateTime(timezone=True),nullable=True),
            sa.Column('revoked_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=True),
            sa.CheckConstraint('percentage > 0 AND percentage <= 100'),
            sa.CheckConstraint("charge_scope IN ('accommodation','all_monthly')"),
            sa.CheckConstraint('max_amount IS NULL OR max_amount >= 0'),
            sa.CheckConstraint('effective_until >= effective_from'))
        op.create_index('ix_resident_discounts_resident_id','resident_discounts',['resident_id'])
    if 'job_state' not in tables:
        op.create_table('job_state',sa.Column('name',sa.String(40),primary_key=True),
            sa.Column('last_started_at',sa.DateTime(timezone=True),nullable=True),
            sa.Column('last_succeeded_at',sa.DateTime(timezone=True),nullable=True),
            sa.Column('status',sa.String(20),nullable=False))
    if 'rate_limit_buckets' not in tables:
        op.create_table('rate_limit_buckets',sa.Column('key',sa.String(100),primary_key=True),
            sa.Column('window_start',sa.DateTime(timezone=True),nullable=False),
            sa.Column('attempts',sa.Integer(),nullable=False))
        op.create_index('ix_rate_limit_buckets_window_start','rate_limit_buckets',['window_start'])
    additions={
        'branches':[
            sa.Column('contact_email',sa.String(254),nullable=False,server_default=''),
            sa.Column('image_url',sa.String(1000),nullable=False,server_default='')],
        'invoices':[
            sa.Column('discount_rule_id',sa.Integer(),sa.ForeignKey('resident_discounts.id',name='fk_invoice_discount_rule'),nullable=True),
            sa.Column('discount_percent',sa.Numeric(5,2),nullable=False,server_default='0')],
        'outbox':[sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id',name='fk_outbox_user'),nullable=True)],
    }
    for table,columns in additions.items():
        present={c['name'] for c in sa.inspect(bind).get_columns(table)}
        missing=[column for column in columns if column.name not in present]
        if missing:
            with op.batch_alter_table(table) as batch:
                for column in missing: batch.add_column(column)
    indexes={i['name'] for i in sa.inspect(bind).get_indexes('outbox')}
    if 'ix_outbox_user_id' not in indexes: op.create_index('ix_outbox_user_id','outbox',['user_id'])
    # Email addresses are unique user identities. Never infer identity by a
    # potentially shared phone number for historical WhatsApp notifications.
    bind.execute(sa.text("UPDATE outbox SET user_id=(SELECT id FROM users WHERE users.email=outbox.recipient) WHERE user_id IS NULL AND channel='email'"))

def downgrade():
    raise RuntimeError('Restore a verified backup; this revision preserves approvals and notification history.')
