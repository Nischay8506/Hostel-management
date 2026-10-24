"""Add retry scheduling to the existing notification outbox."""
from alembic import op
import sqlalchemy as sa

revision='0007_outbox_retry_schedule'
down_revision='0006_auth_finance_notifications'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('outbox',sa.Column('next_attempt_at',sa.DateTime(timezone=True),nullable=True))
    op.create_index('ix_payments_invoice_id','payments',['invoice_id'])

def downgrade():
    op.drop_index('ix_payments_invoice_id',table_name='payments')
    op.drop_column('outbox','next_attempt_at')
