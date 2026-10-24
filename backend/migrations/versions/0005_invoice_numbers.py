"""Add stable invoice numbers and issue dates.

Revision ID: 0005_invoice_numbers
Revises: 0004_stays_audit
"""
from alembic import op
from sqlalchemy import inspect,Column,String,Date,text

revision='0005_invoice_numbers'
down_revision='0004_stays_audit'
branch_labels=None
depends_on=None

def upgrade():
    bind=op.get_bind(); cols={c['name'] for c in inspect(bind).get_columns('invoices')}
    missing=[name for name in ('invoice_number','issued_on') if name not in cols]
    if missing:
        with op.batch_alter_table('invoices',recreate='always' if bind.dialect.name=='sqlite' else 'auto') as batch:
            if 'invoice_number' in missing: batch.add_column(Column('invoice_number',String(40),nullable=True))
            if 'issued_on' in missing: batch.add_column(Column('issued_on',Date(),nullable=True))
    rows=list(bind.execute(text('SELECT id,month FROM invoices WHERE invoice_number IS NULL OR issued_on IS NULL')))
    for row in rows:
        bind.execute(text('UPDATE invoices SET invoice_number=:number,issued_on=:issued WHERE id=:id'),
                     {'number':f'SW-LEGACY-{row.id:06d}','issued':row.month,'id':row.id})
    with op.batch_alter_table('invoices',recreate='always' if bind.dialect.name=='sqlite' else 'auto') as batch:
        batch.alter_column('invoice_number',existing_type=String(40),nullable=False)
        batch.alter_column('issued_on',existing_type=Date(),nullable=False)
    indexes={i['name'] for i in inspect(bind).get_indexes('invoices')}
    if 'ix_invoices_invoice_number' not in indexes: op.create_index('ix_invoices_invoice_number','invoices',['invoice_number'],unique=True)

def downgrade():
    raise RuntimeError('Downgrade is blocked to preserve issued invoice identifiers and dates.')
