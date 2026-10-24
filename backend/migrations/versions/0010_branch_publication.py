"""Add explicit owner-controlled public branch publication."""
from alembic import op
import sqlalchemy as sa

revision = '0010_branch_publication'
down_revision = '0009_payment_time_index'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('branches', sa.Column('published', sa.Boolean(), server_default=sa.false(), nullable=False))

def downgrade():
    op.drop_column('branches', 'published')
