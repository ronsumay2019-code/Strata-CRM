"""Authentication, provider signing and encrypted agency secrets."""
import hashlib
import os
import secrets
from datetime import timedelta
from argon2 import PasswordHasher
from cryptography.fernet import Fernet
from fastapi import HTTPException, Request
from sqlalchemy import select
from .db import Session, User, SessionLocal, now

hasher = PasswordHasher()


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def secure_cookies():
    return os.getenv("STRATA_ENV", "development") == "production"


def crypt():
    key = os.environ.get("STRATA_ENCRYPTION_KEY")
    if not key:
        raise HTTPException(503, "Encryption key is not configured")
    return Fernet(key.encode())


def get_auth(request: Request):
    token = request.cookies.get("strata_session")
    if not token:
        raise HTTPException(401, "Sign in required")
    with SessionLocal() as db:
        session = db.get(Session, hash_token(token))
        if not session or session.expires_at.replace(tzinfo=None) < now().replace(tzinfo=None):
            raise HTTPException(401, "Session expired")
        user = db.get(User, session.user_id)
        if not user:
            raise HTTPException(401, "User not found")
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-csrf-token") != session.csrf_token:
            raise HTTPException(403, "CSRF token missing or invalid")
        return {"id": user.id, "email": user.email, "is_owner": user.is_owner, "csrf": session.csrf_token}


def new_session(user_id):
    token = secrets.token_urlsafe(48)
    csrf = secrets.token_urlsafe(32)
    with SessionLocal.begin() as db:
        db.add(Session(token_hash=hash_token(token), user_id=user_id, csrf_token=csrf, expires_at=now() + timedelta(days=7)))
    return token, csrf
