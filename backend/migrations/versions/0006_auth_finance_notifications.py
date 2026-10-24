"""Add OTP challenge storage, cash receipt metadata, and notification channel state.

Revision ID: 0006_auth_finance_notifications
Revises: 0005_invoice_numbers
"""
from alembic import op
import sqlalchemy as sa

revision='0006_auth_finance_notifications'
down_revision='0005_invoice_numbers'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('users',sa.Column('phone',sa.String(18),nullable=True))
    op.add_column('users',sa.Column('phone_verified_at',sa.DateTime(timezone=True),nullable=True))
    op.add_column('residents',sa.Column('whatsapp_notifications',sa.Boolean(),server_default=sa.false(),nullable=False))
    op.add_column('residents',sa.Column('whatsapp_consent_at',sa.DateTime(timezone=True),nullable=True))
    op.add_column('payments',sa.Column('payer_name',sa.String(100),server_default='',nullable=False))
    op.add_column('payments',sa.Column('note',sa.String(500),server_default='',nullable=False))
    op.add_column('payments',sa.Column('reversed_at',sa.DateTime(timezone=True),nullable=True))
    with op.batch_alter_table('payments') as batch:
        batch.add_column(sa.Column('reversed_by',sa.Integer(),nullable=True))
        batch.create_foreign_key('fk_payments_reversed_by_users','users',['reversed_by'],['id'])
    op.add_column('payments',sa.Column('reversal_reason',sa.String(500),server_default='',nullable=False))
    op.add_column('outbox',sa.Column('channel',sa.String(20),server_default='email',nullable=False))
    op.add_column('outbox',sa.Column('delivery_status',sa.String(20),server_default='queued',nullable=False))
    op.add_column('outbox',sa.Column('provider_message_id',sa.String(100),nullable=True))
    op.create_table('otp_challenges',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('challenge_id',sa.String(36),nullable=False,unique=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),
        sa.Column('purpose',sa.String(20),nullable=False,server_default='login'),
        sa.Column('phone',sa.String(18),nullable=False),
        sa.Column('code_hash',sa.String(64),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('last_sent_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('attempts',sa.Integer(),nullable=False,server_default='0'),
        sa.Column('consumed_at',sa.DateTime(timezone=True),nullable=True))
    op.create_index('ix_otp_challenges_challenge_id','otp_challenges',['challenge_id'],unique=True)
    op.create_index('ix_otp_challenges_user_id','otp_challenges',['user_id'])
    op.create_table('notification_preference_events',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('resident_id',sa.Integer(),sa.ForeignKey('residents.id'),nullable=False),
        sa.Column('enabled',sa.Boolean(),nullable=False),
        sa.Column('source',sa.String(40),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_notification_preference_events_resident_id','notification_preference_events',['resident_id'])
    op.create_table('auth_audit_events',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='SET NULL'),nullable=True),
        sa.Column('actor_user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='SET NULL'),nullable=True),
        sa.Column('event',sa.String(32),nullable=False),
        sa.Column('ip_hash',sa.String(64),nullable=False,server_default=''),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_auth_audit_events_user_id','auth_audit_events',['user_id'])
    op.create_table('payment_audit_events',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('payment_id',sa.Integer(),sa.ForeignKey('payments.id'),nullable=False),
        sa.Column('actor_user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('action',sa.String(20),nullable=False),
        sa.Column('reason',sa.String(500),nullable=False,server_default=''),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_payment_audit_events_payment_id','payment_audit_events',['payment_id'])

def downgrade():
    raise RuntimeError('Downgrade is blocked to preserve authentication and financial records.')
