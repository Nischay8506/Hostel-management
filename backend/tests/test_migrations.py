from pathlib import Path
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy import inspect

ROOT=Path(__file__).resolve().parents[1]
def legacy_database(path,branches=0):
    engine=create_engine(f'sqlite:///{path}')
    with engine.begin() as c:
        c.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY,email VARCHAR(254) UNIQUE NOT NULL,password_hash VARCHAR(256) NOT NULL,role VARCHAR(16) NOT NULL,must_change_password BOOLEAN NOT NULL)'))
        c.execute(text('CREATE TABLE rooms (id INTEGER PRIMARY KEY,number VARCHAR(30) UNIQUE NOT NULL,floor VARCHAR(30) NOT NULL,capacity INTEGER NOT NULL,monthly_fee NUMERIC(12,2) NOT NULL)'))
        c.execute(text("INSERT INTO rooms VALUES (1,'101','Ground',2,8500)"))
        c.execute(text('CREATE TABLE residents (id INTEGER PRIMARY KEY,user_id INTEGER UNIQUE NOT NULL,name VARCHAR(100) NOT NULL,phone VARCHAR(15) NOT NULL,guardian VARCHAR(100) NOT NULL,guardian_phone VARCHAR(15) NOT NULL,institution VARCHAR(150) NOT NULL,joined_on DATE NOT NULL,room_id INTEGER,discount NUMERIC(12,2) NOT NULL,aadhaar_last4 VARCHAR(4),id_status VARCHAR(20) NOT NULL,id_reviewed_by INTEGER,id_reviewed_at DATETIME)'))
        c.execute(text("INSERT INTO users VALUES (1,'r@example.test','hash','resident',0)"))
        c.execute(text("INSERT INTO residents VALUES (1,1,'Resident','9000000000','','','','2026-01-01',1,0,NULL,'pending',NULL,NULL)"))
        c.execute(text('CREATE TABLE invoices (id INTEGER PRIMARY KEY,resident_id INTEGER NOT NULL,month DATE NOT NULL,due_on DATE NOT NULL,room_number VARCHAR(30) NOT NULL,base_fee NUMERIC(12,2) NOT NULL,discount NUMERIC(12,2) NOT NULL,amount NUMERIC(12,2) NOT NULL,UNIQUE(resident_id,month))'))
        c.execute(text("INSERT INTO invoices VALUES (1,1,'2026-01-01','2026-01-05','101',8500,0,8500)"))
        if branches:
            c.execute(text('CREATE TABLE branches (id INTEGER PRIMARY KEY,name VARCHAR(100) UNIQUE NOT NULL,address VARCHAR(300) NOT NULL,contact_phone VARCHAR(30) NOT NULL,description TEXT NOT NULL,rules TEXT NOT NULL,active BOOLEAN NOT NULL)'))
            c.execute(text("INSERT INTO branches VALUES (1,'A','','','','',TRUE),(2,'B','','','','',TRUE)"))
    engine.dispose()

def config_for(path):
    cfg=Config(str(ROOT/'alembic.ini'))
    cfg.set_main_option('script_location',str(ROOT/'migrations'))
    cfg.set_main_option('sqlalchemy.url',f'sqlite:///{path}')
    return cfg

def test_populated_legacy_schema_is_backfilled_and_upgrade_is_idempotent(tmp_path):
    path=tmp_path/'legacy.sqlite';legacy_database(path)
    cfg=config_for(path)
    command.upgrade(cfg,'head');command.upgrade(cfg,'head')
    engine=create_engine(f'sqlite:///{path}')
    with engine.connect() as c:
        room=c.execute(text('SELECT branch_id FROM rooms WHERE id=1')).scalar_one()
        resident=c.execute(text('SELECT branch_id FROM residents WHERE id=1')).scalar_one()
        assert room==resident
        assert c.execute(text('SELECT version_num FROM alembic_version')).scalar_one()=='0015_gap_completion'
        assert c.execute(text("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='admissions'")).scalar_one()==1
        assert c.execute(text("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='complaint_events'")).scalar_one()==1
        assert c.execute(text('SELECT resident_code FROM residents WHERE id=1')).scalar_one().startswith('CH-')
        assert c.execute(text("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='gate_passes'")).scalar_one()==1
        assert c.execute(text("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='fee_plans'")).scalar_one()==1
        assert c.execute(text("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='financial_ledger_events'")).scalar_one()==1
        assert c.execute(text('SELECT additional_charge_amount FROM invoices WHERE id=1')).scalar_one()==0
        assert c.execute(text('SELECT updated_at FROM complaints LIMIT 1')).fetchone() is None
        assert c.execute(text('SELECT invoice_number,issued_on FROM invoices WHERE id=1')).one()==('SW-LEGACY-000001','2026-01-01')
        assert c.execute(text('SELECT branch_id FROM invoices WHERE id=1')).scalar_one()==room
    engine.dispose()

def test_legacy_rows_are_not_assigned_arbitrarily_when_multiple_branches_exist(tmp_path):
    path=tmp_path/'ambiguous.sqlite';legacy_database(path,branches=2)
    with pytest.raises(RuntimeError,match='multiple branches exist'):
        command.upgrade(config_for(path),'head')

def test_release_upgrade_preserves_all_existing_columns_and_rows(tmp_path):
    path=tmp_path/'pre-release.sqlite';legacy_database(path)
    cfg=config_for(path);command.upgrade(cfg,'0013_fees_settlements_complaint_assignment')
    engine=create_engine(f'sqlite:///{path}')
    with engine.begin() as c:
        c.execute(text("INSERT INTO payments (id,invoice_id,amount,method,reference,idempotency_key,recorded_by,paid_at) VALUES (1,1,2000,'cash','original-reference','original-payment-key',1,'2026-01-10 10:00:00')"))
        c.execute(text("INSERT INTO outbox (id,branch_id,dedupe_key,recipient,subject,body,channel,delivery_status) VALUES (1,1,'original-receipt','r@example.test','Receipt','Preserved content','email','queued')"))
        tables=[t for t in inspect(c).get_table_names() if t!='alembic_version']
        columns={t:[col['name'] for col in inspect(c).get_columns(t)] for t in tables}
        snapshot={t:c.execute(text(f'SELECT * FROM "{t}"')).all() for t in tables}
    command.upgrade(cfg,'head');command.upgrade(cfg,'head')
    with engine.connect() as c:
        for table in tables:
            fields=','.join(f'"{col}"' for col in columns[table])
            assert c.execute(text(f'SELECT {fields} FROM "{table}"')).all()==snapshot[table],table
        assert c.execute(text('SELECT user_id FROM outbox WHERE id=1')).scalar_one()==1
        assert c.execute(text('SELECT discount_percent,discount_rule_id FROM invoices WHERE id=1')).one()==(0,None)
        assert c.exec_driver_sql('PRAGMA integrity_check').scalar()=='ok'
        assert c.exec_driver_sql('PRAGMA foreign_key_check').all()==[]
    engine.dispose()
