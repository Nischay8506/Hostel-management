"""Preserve the branch that issued each historical invoice."""
from alembic import op
import sqlalchemy as sa

revision='0008_invoice_branch_snapshot'
down_revision='0007_outbox_retry_schedule'
branch_labels=None
depends_on=None

def upgrade():
    with op.batch_alter_table('invoices') as batch:
        batch.add_column(sa.Column('branch_id',sa.Integer(),nullable=True))
        batch.create_foreign_key('fk_invoices_branch_id_branches','branches',['branch_id'],['id'])
    op.execute(sa.text('UPDATE invoices SET branch_id=(SELECT residents.branch_id FROM residents WHERE residents.id=invoices.resident_id)'))
    op.create_index('ix_invoices_branch_id','invoices',['branch_id'])

def downgrade():
    op.drop_index('ix_invoices_branch_id',table_name='invoices')
    with op.batch_alter_table('invoices') as batch:
        batch.drop_constraint('fk_invoices_branch_id_branches',type_='foreignkey')
        batch.drop_column('branch_id')
