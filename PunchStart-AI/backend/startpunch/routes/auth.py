"""Accounts: signup, login, logout, password, data export, account deletion."""
from __future__ import annotations

import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, insert, or_, select, update

from .. import db, ratelimit
from ..config import get_settings
from ..security import (CurrentUser, _DUMMY_HASH, clear_session, current_user, hash_password, issue_session,
                        optional_user, password_problems, verify_password)
from ..serializers import user_full
from ..utils import clean_text, iso, new_id, slugify, utcnow

router = APIRouter(tags=["auth"])
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
HANDLE_RE = re.compile(r"^[a-z0-9_]{3,30}$")


class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)
    handle: str = Field(default="", max_length=30)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_RE.match(value):
            raise ValueError("Enter a valid email address.")
        return value


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class PasswordIn(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(max_length=128)


class DeleteIn(BaseModel):
    password: str = Field(max_length=128)


def _unique_handle(conn, wanted: str, name: str) -> str:
    base = slugify(wanted or name, 24) or "founder"
    if len(base) < 3:
        base = f"{base}founder"
    candidate = base
    for _ in range(20):
        exists = conn.execute(select(db.users.c.id).where(db.users.c.handle == candidate)).first()
        if not exists:
            return candidate
        candidate = f"{base}{secrets.randbelow(9000) + 1000}"
    return f"{base}{new_id(6)}"


@router.post("/auth/signup", status_code=201)
def signup(payload: SignupIn, request: Request, response: Response):
    ratelimit.hit("auth", ratelimit.client_ip(request))
    problem = password_problems(payload.password)
    if problem:
        raise HTTPException(422, problem)
    handle = payload.handle.strip().lower()
    if handle and not HANDLE_RE.match(handle):
        raise HTTPException(422, "Handles use 3-30 lowercase letters, numbers or underscores.")
    now = utcnow()
    with db.transaction() as conn:
        if conn.execute(select(db.users.c.id).where(func.lower(db.users.c.email) == payload.email)).first():
            raise HTTPException(409, "An account with this email already exists. Sign in instead.")
        if handle and conn.execute(select(db.users.c.id).where(db.users.c.handle == handle)).first():
            raise HTTPException(409, "That handle is taken.")
        user_id = new_id()
        role = "admin" if payload.email in get_settings().admin_emails else "member"
        conn.execute(insert(db.users).values(
            id=user_id, email=payload.email, password_hash=hash_password(payload.password),
            handle=handle or _unique_handle(conn, "", payload.name), name=clean_text(payload.name, 80),
            headline="", bio="", location="", skills=[], interests=[], industries=[], looking_for=[], open_to=[],
            links={}, achievements=[], role=role, profile_visibility="public", message_policy="connections",
            token_version=0, follower_count=0, following_count=0, created_at=now, updated_at=now))
        row = conn.execute(select(db.users).where(db.users.c.id == user_id)).first()
    issue_session(response, user_id, 0)
    return {"user": user_full(row, include_private=True)}


@router.post("/auth/login")
def login(payload: LoginIn, request: Request, response: Response):
    ratelimit.hit("auth", ratelimit.client_ip(request))
    email = payload.email.strip().lower()
    with db.read() as conn:
        row = conn.execute(select(db.users).where(func.lower(db.users.c.email) == email)).first()
    if row is None:
        verify_password(payload.password, _DUMMY_HASH)  # equalize timing
        raise HTTPException(401, "Email or password is incorrect.")
    if not verify_password(payload.password, row.password_hash):
        raise HTTPException(401, "Email or password is incorrect.")
    issue_session(response, row.id, row.token_version)
    return {"user": user_full(row, include_private=True)}


@router.post("/auth/logout")
def logout(response: Response):
    clear_session(response)
    return {"ok": True}


@router.get("/auth/session")
def session_status(user: CurrentUser | None = Depends(optional_user)):
    """Always 200: lets public pages check sign-in state without a 401 in the console."""
    return {"authenticated": user is not None, "handle": user.handle if user else None}


@router.get("/auth/me")
def me(user: CurrentUser = Depends(current_user)):
    with db.read() as conn:
        row = conn.execute(select(db.users).where(db.users.c.id == user.id)).first()
        unread = conn.execute(select(func.count()).select_from(db.notifications)
                              .where(db.notifications.c.user_id == user.id, db.notifications.c.read_at.is_(None))).scalar_one()
    data = user_full(row, include_private=True)
    data["role"] = user.role
    return {"user": data, "unread_notifications": unread, "ai_configured": get_settings().ai_configured}


@router.post("/auth/password")
def change_password(payload: PasswordIn, response: Response, user: CurrentUser = Depends(current_user)):
    problem = password_problems(payload.new_password)
    if problem:
        raise HTTPException(422, problem)
    with db.transaction() as conn:
        row = conn.execute(select(db.users).where(db.users.c.id == user.id)).first()
        if not verify_password(payload.current_password, row.password_hash):
            raise HTTPException(403, "Current password is incorrect.")
        conn.execute(update(db.users).where(db.users.c.id == user.id).values(
            password_hash=hash_password(payload.new_password), token_version=row.token_version + 1, updated_at=utcnow()))
    issue_session(response, user.id, row.token_version + 1)  # other sessions are signed out
    return {"ok": True}


@router.post("/auth/logout-all")
def logout_all(response: Response, user: CurrentUser = Depends(current_user)):
    with db.transaction() as conn:
        conn.execute(update(db.users).where(db.users.c.id == user.id).values(token_version=db.users.c.token_version + 1))
    clear_session(response)
    return {"ok": True}


@router.get("/auth/export")
def export_data(user: CurrentUser = Depends(current_user)):
    """Everything we store about the user, as JSON (data portability)."""
    def rows(table, column):
        return [dict(r._mapping) for r in conn.execute(select(table).where(column == user.id))]

    with db.read() as conn:
        profile = dict(conn.execute(select(db.users).where(db.users.c.id == user.id)).first()._mapping)
        profile.pop("password_hash", None)
        data = {
            "profile": profile,
            "reports": rows(db.reports, db.reports.c.user_id),
            "assistant_messages": rows(db.report_messages, db.report_messages.c.user_id),
            "validation_items": rows(db.validation_items, db.validation_items.c.user_id),
            "watchlist": rows(db.watchlist, db.watchlist.c.user_id),
            "posts": rows(db.posts, db.posts.c.author_id),
            "comments": rows(db.comments, db.comments.c.author_id),
            "startups": rows(db.startups, db.startups.c.owner_id),
            "following": rows(db.follows, db.follows.c.follower_id),
            "connections": [dict(r._mapping) for r in conn.execute(select(db.connections).where(
                or_(db.connections.c.requester_id == user.id, db.connections.c.addressee_id == user.id)))],
            "messages_sent": rows(db.messages, db.messages.c.sender_id),
        }

    def _jsonable(value):
        if isinstance(value, dict):
            return {k: _jsonable(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_jsonable(v) for v in value]
        if hasattr(value, "isoformat"):
            return iso(value)
        return value

    return _jsonable(data)


@router.delete("/auth/account")
def delete_account(payload: DeleteIn, response: Response, user: CurrentUser = Depends(current_user)):
    with db.transaction() as conn:
        row = conn.execute(select(db.users).where(db.users.c.id == user.id)).first()
        if not verify_password(payload.password, row.password_hash):
            raise HTTPException(403, "Password is incorrect.")
        from ..social import cleanup_user

        cleanup_user(conn, user.id)
        # Keep denormalized counters correct for people this user followed / was followed by.
        followees = [r.followee_id for r in conn.execute(select(db.follows.c.followee_id).where(db.follows.c.follower_id == user.id))]
        followers = [r.follower_id for r in conn.execute(select(db.follows.c.follower_id).where(db.follows.c.followee_id == user.id))]
        if followees:
            conn.execute(update(db.users).where(db.users.c.id.in_(followees)).values(follower_count=db.users.c.follower_count - 1))
        if followers:
            conn.execute(update(db.users).where(db.users.c.id.in_(followers)).values(following_count=db.users.c.following_count - 1))
        conn.execute(delete(db.users).where(db.users.c.id == user.id))
    clear_session(response)
    return {"ok": True}
