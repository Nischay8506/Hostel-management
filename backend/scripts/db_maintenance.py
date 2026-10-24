"""Read-only inventory and explicit backup. Never migrates or restores a database.

Run from backend: python scripts/db_maintenance.py inspect
or: python scripts/db_maintenance.py backup /absolute/private/new-directory
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from app.config import settings


def inventory(engine):
    with engine.connect() as connection:
        tables=inspect(connection).get_table_names()
        quote=engine.dialect.identifier_preparer.quote
        counts={table:connection.scalar(text(f'SELECT COUNT(*) FROM {quote(table)}')) for table in tables}
        result={'engine':engine.dialect.name,'tables':counts,
                'revision':connection.scalar(text('SELECT version_num FROM alembic_version')) if 'alembic_version' in tables else None}
        if engine.dialect.name=='sqlite':
            result.update(integrity=connection.exec_driver_sql('PRAGMA integrity_check').scalar(),foreign_key_violations=len(connection.exec_driver_sql('PRAGMA foreign_key_check').all()))
        return result


def backup(engine,destination):
    destination=Path(destination).expanduser()
    if not destination.is_absolute(): raise ValueError('Use an absolute backup directory outside the repository')
    repository=Path(__file__).resolve().parents[2]
    if destination.resolve().is_relative_to(repository): raise ValueError('Backups must be stored outside the repository')
    destination.mkdir(mode=0o700,parents=False,exist_ok=False)
    os.chmod(destination,0o700)
    if engine.dialect.name=='sqlite':
        # SQLite online backup is consistent even with a running API.
        target=destination/'database.sqlite'
        with engine.connect() as source, sqlite3.connect(target) as copy:
            source.connection.driver_connection.backup(copy)
        copied=create_engine(f'sqlite:///{target}')
        manifest=inventory(copied);copied.dispose()
        if manifest['integrity']!='ok' or manifest['foreign_key_violations']: raise RuntimeError('Backup integrity failed')
    elif engine.dialect.name=='postgresql':
        target=destination/'database.dump'
        url=make_url(settings.database_url)
        # Credentials stay in the subprocess environment, never arguments/logs.
        env=os.environ.copy()
        env.update(PGHOST=url.host or '',PGPORT=str(url.port or 5432),PGDATABASE=url.database or '',PGUSER=url.username or '',PGPASSWORD=url.password or '')
        if 'sslmode' in url.query: env['PGSSLMODE']=url.query['sslmode']
        for source,key in [('sslrootcert','PGSSLROOTCERT'),('sslcert','PGSSLCERT'),('sslkey','PGSSLKEY')]:
            if source in url.query: env[key]=url.query[source]
        with target.open('xb') as output:
            proc=subprocess.run(['pg_dump','--format=custom','--no-owner','--no-acl'],env=env,stdout=output,stderr=subprocess.PIPE)
        if proc.returncode: raise RuntimeError('pg_dump failed; verify client version and database access privately')
        checked=subprocess.run(['pg_restore','--list',str(target)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        if checked.returncode: raise RuntimeError('Backup archive could not be read')
        manifest=inventory(engine)
        manifest['verification']='Archive listing only. Restore to a separate database and compare counts before production migration.'
        manifest['count_consistency']='Inventory collected after dump. Quiesce writes for exact count comparison.'
    else: raise ValueError('Unsupported database engine')
    os.chmod(target,0o600)
    manifest['sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
    manifest['created_at']=datetime.now(timezone.utc).isoformat()
    file=destination/'manifest.json';file.write_text(json.dumps(manifest,indent=2));os.chmod(file,0o600)
    return {'backup':str(target),'manifest':str(file),'sha256':manifest['sha256']}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['inspect','backup']);parser.add_argument('destination',nargs='?');args=parser.parse_args()
    try:
        engine=create_engine(settings.database_url)
        if args.action=='backup' and not args.destination: parser.error('backup requires a new absolute directory')
        print(json.dumps(inventory(engine) if args.action=='inspect' else backup(engine,args.destination),indent=2))
    except Exception as exc:
        print(f'Database maintenance failed ({type(exc).__name__}); check the target configuration privately.',file=sys.stderr)
        raise SystemExit(1)
    finally:
        if 'engine' in locals(): engine.dispose()
