from datetime import datetime, timedelta, timezone
import jwt
from pwdlib import PasswordHash
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db
from .models import User
hashing = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)
def token_for(user,mfa_verified=False,channel="whatsapp"):
    claims={'sub':str(user.id),'exp':datetime.now(timezone.utc)+timedelta(hours=8),'ver':user.session_version or 0}
    if mfa_verified: claims['amr']=['pwd',channel+'_otp']
    return jwt.encode(claims,settings.jwt_secret,algorithm='HS256')
def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)):
    try:
        if not credentials: raise ValueError()
        payload = jwt.decode(credentials.credentials,settings.jwt_secret,algorithms=['HS256'])
        if payload.get('amr') not in (['pwd','whatsapp_otp'],['pwd','sms_otp']): raise ValueError()
        user = db.get(User,int(payload['sub']))
        if not user or not user.active or payload.get('ver',0)!=user.session_version: raise ValueError()
        return user
    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise HTTPException(401,'Please sign in again')
def active_user(user: User = Depends(current_user)):
    if user.must_change_password: raise HTTPException(403,'Change your temporary password first')
    return user
def is_owner(user: User):
    return user.role in {'admin','owner','superadmin'}
def is_staff(user: User):
    return is_owner(user) or user.role=='branch_admin'
def staff(user: User = Depends(active_user)):
    if not is_staff(user): raise HTTPException(403,'Administrator access required')
    return user
def admin(user: User = Depends(active_user)):
    if not is_owner(user): raise HTTPException(403,'Owner access required')
    return user
