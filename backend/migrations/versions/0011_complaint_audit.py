"""Keep an append-only history for complaint submissions and responses."""
from alembic import op
import sqlalchemy as sa

revision = '0011_complaint_audit'
down_revision = '0010_branch_publication'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'complaint_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('complaint_id', sa.Integer(), sa.ForeignKey('complaints.id'), nullable=False),
        sa.Column('actor_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('old_status', sa.String(20), nullable=True),
        sa.Column('new_status', sa.String(20), nullable=False),
        sa.Column('old_response', sa.Text(), nullable=True),
        sa.Column('new_response', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_complaint_events_complaint_id', 'complaint_events', ['complaint_id'])


def downgrade():
    op.drop_index('ix_complaint_events_complaint_id', table_name='complaint_events')
    op.drop_table('complaint_events')
