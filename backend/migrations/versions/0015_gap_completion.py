"""Complete operational features without deleting historical business records."""
from alembic import op
import sqlalchemy as sa

revision = '0015_gap_completion'
down_revision = '0014_release_completion'
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    additions = {
        'users': [sa.Column('active',sa.Boolean(),nullable=False,server_default=sa.true()),sa.Column('session_version',sa.Integer(),nullable=False,server_default='0')],
        'rooms': [sa.Column('active',sa.Boolean(),nullable=False,server_default=sa.true())],
        'branches': [sa.Column('faqs',sa.JSON(),nullable=False,server_default='[]')],
        'fee_plans': [sa.Column('advance_amount',sa.Numeric(12,2),nullable=False,server_default='0')],
        'admissions': [sa.Column('whatsapp_updates',sa.Boolean(),nullable=False,server_default=sa.false())],
        'otp_challenges': [sa.Column('channel',sa.String(16),nullable=False,server_default='whatsapp')],
    }
    for table, columns in additions.items():
        present = {c['name'] for c in sa.inspect(bind).get_columns(table)}
        with op.batch_alter_table(table) as batch:
            for column in columns:
                if column.name not in present: batch.add_column(column)
    tables = set(sa.inspect(bind).get_table_names())
    if 'lifecycle_events' not in tables:
        op.create_table('lifecycle_events',
            sa.Column('id',sa.Integer(),primary_key=True),
            sa.Column('entity',sa.String(20),nullable=False),
            sa.Column('entity_id',sa.Integer(),nullable=False),
            sa.Column('branch_id',sa.Integer(),sa.ForeignKey('branches.id'),nullable=False),
            sa.Column('actor_user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
            sa.Column('action',sa.String(20),nullable=False),
            sa.Column('reason',sa.String(500),nullable=False),
            sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
        op.create_index('ix_lifecycle_events_branch_id','lifecycle_events',['branch_id'])
    if 'identity_documents' not in tables:
        op.create_table('identity_documents',
            sa.Column('id',sa.Integer(),primary_key=True),
            sa.Column('resident_id',sa.Integer(),sa.ForeignKey('residents.id'),nullable=False,unique=True),
            sa.Column('content_type',sa.String(40),nullable=False),
            sa.Column('encrypted_content',sa.LargeBinary(),nullable=False),
            sa.Column('uploaded_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
            sa.Column('uploaded_at',sa.DateTime(timezone=True),nullable=False))

def downgrade():
    raise RuntimeError('Restore a verified backup; downgrade would discard document and lifecycle history.')
