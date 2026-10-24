"""Add resident lifecycle fields, stay requests, and review/allocation history.

Revision ID: 0004_stays_audit
Revises: 0003_branch_facilities
"""
from alembic import op
from sqlalchemy import inspect, Column, Integer, Date, String, ForeignKey, text
from app.db import Base
import app.models  # noqa: F401

revision='0004_stays_audit'
down_revision='0003_branch_facilities'
branch_labels=None
depends_on=None

def upgrade():
    bind=op.get_bind()
    branch_cols={c['name'] for c in inspect(bind).get_columns('branches')}
    if 'notice_days' not in branch_cols:
        with op.batch_alter_table('branches',recreate='always' if bind.dialect.name=='sqlite' else 'auto') as batch:
            batch.add_column(Column('notice_days',Integer(),nullable=True))
    resident_cols={c['name'] for c in inspect(bind).get_columns('residents')}
    missing=[name for name in ('planned_move_out','status') if name not in resident_cols]
    if missing:
        with op.batch_alter_table('residents',recreate='always' if bind.dialect.name=='sqlite' else 'auto') as batch:
            if 'planned_move_out' in missing: batch.add_column(Column('planned_move_out',Date(),nullable=True))
            if 'status' in missing: batch.add_column(Column('status',String(20),nullable=True,server_default='active'))
    bind.execute(text("UPDATE residents SET status='active' WHERE status IS NULL"))
    with op.batch_alter_table('residents',recreate='always' if bind.dialect.name=='sqlite' else 'auto') as batch:
        batch.alter_column('status',existing_type=String(20),nullable=False,server_default='active')
    Base.metadata.create_all(bind,tables=[Base.metadata.tables[n] for n in ('allocation_events','stay_requests','identity_review_events')])

def downgrade():
    raise RuntimeError('Downgrade is blocked to preserve resident stay and audit history.')
