"""Add stable resident identifiers and auditable gate passes."""
from alembic import op
import sqlalchemy as sa
import secrets

revision = '0012_resident_codes_gate_passes'
down_revision = '0011_complaint_audit'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('residents', sa.Column('resident_code', sa.String(length=20), nullable=True))
    bind = op.get_bind()
    resident_ids = [row[0] for row in bind.execute(sa.text(
        'SELECT id FROM residents WHERE resident_code IS NULL ORDER BY id'
    ))]
    for resident_id in resident_ids:
        code = 'CH-' + secrets.token_hex(6).upper()
        while bind.execute(sa.text('SELECT 1 FROM residents WHERE resident_code=:code'), {'code': code}).first():
            code = 'CH-' + secrets.token_hex(6).upper()
        bind.execute(sa.text('UPDATE residents SET resident_code=:code WHERE id=:id'), {'code': code, 'id': resident_id})
    with op.batch_alter_table('residents') as batch:
        batch.alter_column('resident_code', existing_type=sa.String(length=20), nullable=False)
        batch.create_unique_constraint('uq_residents_resident_code', ['resident_code'])

    op.create_table(
        'gate_passes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('pass_code', sa.String(length=64), nullable=False, unique=True),
        sa.Column('resident_id', sa.Integer(), sa.ForeignKey('residents.id'), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_until', sa.Date(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
    )
    op.create_index('ix_gate_passes_resident_id', 'gate_passes', ['resident_id'])


def downgrade():
    raise RuntimeError('Resident codes and issued gate-pass history are append-only; restore a backup to reverse this migration.')
