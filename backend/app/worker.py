"""Run via a supervised process or `python -m app.worker --once` scheduler."""
import argparse
import logging
import time
from threading import Lock
from sqlalchemy import text
from .config import settings
from .db import engine, SessionLocal
from .models import JobState, now

_local_lock=Lock()
LOCK_ID=439876123

def state(status):
    with SessionLocal() as db:
        item=db.get(JobState,'reminders-and-moveouts')
        if item is None:
            item=JobState(name='reminders-and-moveouts');db.add(item)
        item.status=status
        if status=='running': item.last_started_at=now()
        if status=='ok': item.last_succeeded_at=now()
        db.commit()

def run_once():
    if not _local_lock.acquire(blocking=False): return {'status':'busy'}
    connection=None;acquired=False
    try:
        if engine.dialect.name=='postgresql':
            connection=engine.connect()
            acquired=bool(connection.scalar(text('SELECT pg_try_advisory_lock(:key)'),{'key':LOCK_ID}))
            if not acquired: return {'status':'busy'}
        state('running')
        from .main import job_tick
        job_tick()
        state('ok')
        return {'status':'ok'}
    except Exception:
        try: state('failed')
        except Exception: pass
        logging.getLogger(__name__).error('Job failed; check database connectivity and provider configuration')
        raise RuntimeError('Scheduled processing failed') from None
    finally:
        if connection is not None:
            try:
                if acquired: connection.execute(text('SELECT pg_advisory_unlock(:key)'),{'key':LOCK_ID})
            finally: connection.close()
        _local_lock.release()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');args=parser.parse_args()
    settings.validate_runtime()
    while True:
        try: run_once()
        except RuntimeError:
            if args.once: raise SystemExit(1)
        if args.once: break
        time.sleep(60)
