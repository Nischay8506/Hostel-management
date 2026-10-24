"""Database-backed limits shared by API instances; identifiers are HMAC hashes."""
import hashlib
import hmac
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from .models import RateLimitBucket, now
from .config import settings

def consume(db, purpose, identity, limit, seconds):
    moment=now()
    window=moment.replace(microsecond=0)-timedelta(seconds=int(moment.timestamp()) % seconds)
    digest=hmac.new(settings.jwt_secret.encode(),str(identity).encode(),hashlib.sha256).hexdigest()
    key=f'{purpose}:{digest}'
    insert=pg_insert if db.bind.dialect.name=='postgresql' else sqlite_insert
    statement=insert(RateLimitBucket).values(key=key,window_start=window,attempts=1)
    from sqlalchemy import case
    statement=statement.on_conflict_do_update(index_elements=['key'],set_={
        'window_start':window,
        'attempts':case((RateLimitBucket.window_start==window,RateLimitBucket.attempts+1),else_=1),
    }).returning(RateLimitBucket.attempts)
    attempts=db.execute(statement).scalar_one()
    db.execute(delete(RateLimitBucket).where(RateLimitBucket.window_start<moment-timedelta(days=1)))
    db.commit()  # Persist failed attempts even when the following request is denied.
    if attempts>limit:
        raise HTTPException(429,'Too many attempts. Please try again later.',headers={'Retry-After':str(seconds)})
