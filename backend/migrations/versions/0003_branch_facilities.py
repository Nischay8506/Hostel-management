"""Add configurable branch facilities for the public site.

Revision ID: 0003_branch_facilities
Revises: 0002_admissions
"""
from alembic import op
from sqlalchemy import inspect, Column, Text, text

revision='0003_branch_facilities'
down_revision='0002_admissions'
branch_labels=None
depends_on=None

def upgrade():
    bind=op.get_bind()
    if 'facilities' not in {c['name'] for c in inspect(bind).get_columns('branches')}:
        with op.batch_alter_table('branches',recreate='always' if bind.dialect.name=='sqlite' else 'auto') as batch:
            batch.add_column(Column('facilities',Text(),nullable=True))
    bind.execute(text("UPDATE branches SET facilities='' WHERE facilities IS NULL"))

def downgrade():
    raise RuntimeError('Downgrade is blocked to preserve configured branch facilities.')
