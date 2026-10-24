"""Real HTTP startup and restart against an isolated SQLite file, not PostgreSQL."""
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import time
from urllib.request import urlopen


def test_http_startup_migrations_and_restart_persistence(tmp_path):
    root=Path(__file__).resolve().parents[1]
    database=tmp_path/'runtime.sqlite'
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    env={**os.environ,'DATABASE_URL':f'sqlite:///{database}',
         'JWT_SECRET':secrets.token_urlsafe(40),'ADMIN_PASSWORD':secrets.token_urlsafe(30),
         'ADMIN_EMAIL':'runtime-owner@example.test','ADMIN_PHONE':'','JOBS_ENABLED':'false',
         'APP_ENVIRONMENT':'test','AUTO_MIGRATE':'true','WHATSAPP_ENABLED':'false',
         'WHATSAPP_PROVIDER':'test','RELEASE_ID':'disposable-runtime-test',
         'X_ZOHO_CATALYST_LISTEN_PORT':str(port),'PORT':'1'}
    def start():
        process=subprocess.Popen([sys.executable,'-m','app.serve'],cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            for _ in range(120):
                if process.poll() is not None: raise AssertionError('Disposable API failed during startup')
                try:
                    with urlopen(f'http://127.0.0.1:{port}/api/health',timeout=.25) as result:
                        assert result.headers['Content-Type'].startswith('application/json')
                        assert json.load(result)=={'status':'ok'}
                    return process
                except OSError: time.sleep(.05)
            raise AssertionError('Disposable API startup timed out')
        except BaseException:
            process.terminate();process.wait(timeout=10);raise
    process=start()
    try:
        with urlopen(f'http://127.0.0.1:{port}/api/build') as result:
            assert json.load(result)['release']=='disposable-runtime-test'
        with urlopen(f'http://127.0.0.1:{port}/api/branches') as result: assert json.load(result)==[]
        with sqlite3.connect(database) as db:
            assert db.execute('SELECT version_num FROM alembic_version').fetchone()[0]=='0015_gap_completion'
            before=db.execute('SELECT id,email,password_hash FROM users').fetchall()
            db.execute("UPDATE branches SET description='Disposable persistence marker' WHERE id=1");db.commit()
    finally: process.terminate();process.wait(timeout=10)
    process=start()
    try:
        with sqlite3.connect(database) as db:
            assert db.execute('SELECT id,email,password_hash FROM users').fetchall()==before
            assert db.execute('SELECT description FROM branches WHERE id=1').fetchone()[0]=='Disposable persistence marker'
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
    finally: process.terminate();process.wait(timeout=10)
