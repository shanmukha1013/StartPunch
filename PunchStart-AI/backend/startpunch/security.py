"""Authentication primitives: scrypt password hashing and signed session cookies."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta

import jwt
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select

from . import db
from .config import get_settings
from .utils import utcnow

SESSION_COOKIE = "sp_session"
CSRF_HEADER = "x-startpunch-client"

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N, _SCRYPT_R, _SCRYPT_P,
        base64.b64encode(salt).decode(), base64.b64encode(digest).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


# Constant-time dummy used when the email does not exist (avoids user enumeration by timing).
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def password_problems(password: str) -> str | None:
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if len(password) > 128:
        return "Password must be at most 128 characters."
    if password.lower() == password or password.upper() == password:
        if not any(ch.isdigit() for ch in password):
            return "Use a mix of letters and numbers (or mixed case) for your password."
    return None


def _require_secret() -> str:
    settings = get_settings()
    if not settings.session_secret_configured:
        raise HTTPException(503, "Authentication is not configured: SESSION_SECRET (32+ characters) must be set on the server.")
    return settings.session_secret


def issue_session(response: Response, user_id: str, token_version: int) -> None:
    settings = get_settings()
    now = utcnow()
    payload = {"sub": user_id, "tv": token_version, "iat": int(now.timestamp()),
               "exp": int((now + timedelta(days=settings.session_days)).timestamp())}
    token = jwt.encode(payload, _require_secret(), algorithm="HS256")
    response.set_cookie(
        SESSION_COOKIE, token,
        max_age=settings.session_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="none" if settings.cors_origins and settings.cookie_secure else "lax",
        path="/",
    )


def clear_session(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(SESSION_COOKIE, path="/", secure=settings.cookie_secure, httponly=True,
                           samesite="none" if settings.cors_origins and settings.cookie_secure else "lax")


@dataclass
class CurrentUser:
    id: str
    email: str
    handle: str
    name: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def _decode(request: Request) -> CurrentUser | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
    if not token:
        return None
    try:
        payload = jwt.decode(token, _require_secret(), algorithms=["HS256"], options={"require": ["exp", "sub"]})
    except jwt.PyJWTError:
        return None
    with db.read() as conn:
        row = conn.execute(
            select(db.users.c.id, db.users.c.email, db.users.c.handle, db.users.c.name, db.users.c.role, db.users.c.token_version)
            .where(db.users.c.id == payload["sub"])
        ).first()
    if row is None or row.token_version != payload.get("tv", -1):
        return None
    role = row.role
    if row.email.lower() in get_settings().admin_emails:
        role = "admin"
    return CurrentUser(id=row.id, email=row.email, handle=row.handle, name=row.name, role=role)


def optional_user(request: Request) -> CurrentUser | None:
    cached = getattr(request.state, "user", "unset")
    if cached != "unset":
        return cached
    user = _decode(request)
    request.state.user = user
    return user


def current_user(user: CurrentUser | None = Depends(optional_user)) -> CurrentUser:
    if user is None:
        raise HTTPException(401, "Sign in to continue.")
    return user


def admin_user(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(403, "Moderator access required.")
    return user
