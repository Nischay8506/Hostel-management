"""Index transaction-time collections and bound large payment reports."""
from alembic import op

revision='0009_payment_time_index'
down_revision='0008_invoice_branch_snapshot'
branch_labels=None
depends_on=None

def upgrade():
    op.create_index('ix_payments_paid_at','payments',['paid_at'])

def downgrade():
    op.drop_index('ix_payments_paid_at',table_name='payments')
