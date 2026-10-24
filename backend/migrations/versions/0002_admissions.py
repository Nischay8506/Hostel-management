"""Add public admission requests and review history.

Revision ID: 0002_admissions
Revises: 0001_branch_access
"""
from alembic import op
from app.db import Base
import app.models  # noqa: F401

revision='0002_admissions'
down_revision='0001_branch_access'
branch_labels=None
depends_on=None

def upgrade():
    bind=op.get_bind()
    Base.metadata.create_all(bind,tables=[Base.metadata.tables['admissions'],Base.metadata.tables['admission_events']])

def downgrade():
    raise RuntimeError('Downgrade is blocked because admission and review history must be preserved.')
