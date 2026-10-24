"""Version the prototype schema and add branch administrator foundations.

Revision ID: 0001_branch_access
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision='0001_branch_access'
down_revision=None
branch_labels=None
depends_on=None

def upgrade():
    bind=op.get_bind(); tables=set(sa.inspect(bind).get_table_names())
    if 'users' not in tables:
        op.create_table('users',sa.Column('id',sa.Integer(),primary_key=True),
            sa.Column('email',sa.String(254),nullable=False,unique=True),sa.Column('password_hash',sa.String(256),nullable=False),
            sa.Column('role',sa.String(16),nullable=False),sa.Column('must_change_password',sa.Boolean(),nullable=False,server_default=sa.false()))
    if 'branches' not in tables:
        op.create_table('branches',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('name',sa.String(100),nullable=False,unique=True),
            sa.Column('address',sa.String(300),nullable=False,server_default=''),sa.Column('contact_phone',sa.String(30),nullable=False,server_default=''),
            sa.Column('description',sa.Text(),nullable=False,server_default=''),sa.Column('rules',sa.Text(),nullable=False,server_default=''),
            sa.Column('active',sa.Boolean(),nullable=False,server_default=sa.true()))
    if 'rooms' not in tables:
        op.create_table('rooms',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('branch_id',sa.Integer(),sa.ForeignKey('branches.id'),nullable=True),
            sa.Column('number',sa.String(30),nullable=False,unique=True),sa.Column('floor',sa.String(30),nullable=False),
            sa.Column('capacity',sa.Integer(),nullable=False),sa.Column('monthly_fee',sa.Numeric(12,2),nullable=False),
            sa.CheckConstraint('capacity BETWEEN 1 AND 8'),sa.CheckConstraint('monthly_fee >= 0'))
    if 'residents' not in tables:
        op.create_table('residents',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('branch_id',sa.Integer(),sa.ForeignKey('branches.id'),nullable=True),
            sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,unique=True),sa.Column('name',sa.String(100),nullable=False),
            sa.Column('phone',sa.String(15),nullable=False),sa.Column('guardian',sa.String(100),nullable=False,server_default=''),
            sa.Column('guardian_phone',sa.String(15),nullable=False,server_default=''),sa.Column('institution',sa.String(150),nullable=False,server_default=''),
            sa.Column('joined_on',sa.Date(),nullable=False),sa.Column('room_id',sa.Integer(),sa.ForeignKey('rooms.id'),nullable=True),
            sa.Column('discount',sa.Numeric(12,2),nullable=False,server_default='0'),sa.Column('aadhaar_last4',sa.String(4),nullable=True),
            sa.Column('id_status',sa.String(20),nullable=False,server_default='pending'),sa.Column('id_reviewed_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=True),
            sa.Column('id_reviewed_at',sa.DateTime(timezone=True),nullable=True),sa.CheckConstraint('discount >= 0'))
    if 'invoices' not in tables:
        op.create_table('invoices',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('resident_id',sa.Integer(),sa.ForeignKey('residents.id'),nullable=False),
            sa.Column('month',sa.Date(),nullable=False),sa.Column('due_on',sa.Date(),nullable=False),sa.Column('room_number',sa.String(30),nullable=False),
            sa.Column('base_fee',sa.Numeric(12,2),nullable=False),sa.Column('discount',sa.Numeric(12,2),nullable=False),sa.Column('amount',sa.Numeric(12,2),nullable=False),
            sa.UniqueConstraint('resident_id','month'),sa.CheckConstraint('amount >= 0'))
    if 'payments' not in tables:
        op.create_table('payments',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('invoice_id',sa.Integer(),sa.ForeignKey('invoices.id'),nullable=False),
            sa.Column('amount',sa.Numeric(12,2),nullable=False),sa.Column('method',sa.String(20),nullable=False),sa.Column('reference',sa.String(100),nullable=False),
            sa.Column('idempotency_key',sa.String(64),nullable=False,unique=True),sa.Column('recorded_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
            sa.Column('paid_at',sa.DateTime(timezone=True),nullable=False),sa.CheckConstraint('amount > 0'))
    if 'complaints' not in tables:
        op.create_table('complaints',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('resident_id',sa.Integer(),sa.ForeignKey('residents.id'),nullable=False),
            sa.Column('category',sa.String(30),nullable=False),sa.Column('title',sa.String(150),nullable=False),sa.Column('description',sa.Text(),nullable=False),
            sa.Column('status',sa.String(20),nullable=False),sa.Column('response',sa.Text(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    if 'outbox' not in tables:
        op.create_table('outbox',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('branch_id',sa.Integer(),sa.ForeignKey('branches.id'),nullable=True),
            sa.Column('dedupe_key',sa.String(120),nullable=False,unique=True),sa.Column('recipient',sa.String(254),nullable=False),
            sa.Column('subject',sa.String(200),nullable=False),sa.Column('body',sa.Text(),nullable=False),sa.Column('sent_at',sa.DateTime(timezone=True),nullable=True),
            sa.Column('cancelled',sa.Boolean(),nullable=False,server_default=sa.false()),sa.Column('attempts',sa.Integer(),nullable=False,server_default='0'),
            sa.Column('last_error',sa.String(100),nullable=False,server_default=''))
    if 'branch_admins' not in tables:
        op.create_table('branch_admins',sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='CASCADE'),primary_key=True),
            sa.Column('branch_id',sa.Integer(),sa.ForeignKey('branches.id',ondelete='CASCADE'),primary_key=True))
    # Legacy databases gain nullable IDs first so the explicit, auditable backfill below can run.
    for table in ('rooms','residents','outbox'):
        cols={c['name'] for c in sa.inspect(bind).get_columns(table)}
        if 'branch_id' not in cols:
            with op.batch_alter_table(table,recreate='always' if bind.dialect.name=='sqlite' else 'auto') as batch:
                batch.add_column(sa.Column('branch_id',sa.Integer(),sa.ForeignKey('branches.id',name=f'fk_{table}_branch_id_branches'),nullable=True))
    branch_count=bind.execute(sa.text('SELECT COUNT(*) FROM branches')).scalar_one()
    if branch_count == 0:
        cols={c['name'] for c in sa.inspect(bind).get_columns('branches')}
        if 'facilities' in cols:
            bind.execute(sa.text("INSERT INTO branches (name,address,contact_phone,description,facilities,rules,active) VALUES ('Branch A','','','Configure this location in branch settings.','','',TRUE)"))
        else:
            bind.execute(sa.text("INSERT INTO branches (name,address,contact_phone,description,rules,active) VALUES ('Branch A','','','Configure this location in branch settings.','',TRUE)"))
        ids=[bind.execute(sa.text('SELECT id FROM branches ORDER BY id LIMIT 1')).scalar_one()]
    else:
        ids=list(bind.execute(sa.text('SELECT id FROM branches ORDER BY id')).scalars())
    mismatch=bind.execute(sa.text('SELECT COUNT(*) FROM residents r JOIN rooms m ON m.id=r.room_id WHERE r.branch_id IS NOT NULL AND m.branch_id IS NOT NULL AND r.branch_id<>m.branch_id')).scalar_one()
    if mismatch:
        raise RuntimeError('Migration stopped: resident and assigned room branches disagree. Resolve those records explicitly, then rerun Alembic upgrade.')
    bind.execute(sa.text('UPDATE residents SET branch_id=(SELECT branch_id FROM rooms WHERE rooms.id=residents.room_id) WHERE room_id IS NOT NULL AND branch_id IS NULL'))
    unassigned_rooms=bind.execute(sa.text('SELECT COUNT(*) FROM rooms WHERE branch_id IS NULL')).scalar_one()
    unassigned_residents=bind.execute(sa.text('SELECT COUNT(*) FROM residents WHERE branch_id IS NULL')).scalar_one()
    if len(ids)>1 and (unassigned_rooms or unassigned_residents):
        raise RuntimeError('Migration stopped: legacy rooms or unallocated residents have no branch and multiple branches exist. Assign branch_id values explicitly, then rerun Alembic upgrade.')
    if len(ids)==1:
        default_id=ids[0]
        bind.execute(sa.text('UPDATE rooms SET branch_id=:id WHERE branch_id IS NULL'),{'id':default_id})
        bind.execute(sa.text('UPDATE residents SET branch_id=:id WHERE branch_id IS NULL'),{'id':default_id})
    for table in ('rooms','residents','outbox'):
        indexes={i['name'] for i in sa.inspect(bind).get_indexes(table)}
        name=f'ix_{table}_branch_id'
        if name not in indexes: op.create_index(name,table,['branch_id'])

def downgrade():
    raise RuntimeError('Downgrade is blocked to preserve branch and resident data.')
