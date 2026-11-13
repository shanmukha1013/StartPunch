"""Row -> JSON helpers shared by routes."""
from __future__ import annotations

from typing import Iterable

from sqlalchemy import select
from sqlalchemy.engine import Connection

from . import db
from .utils import iso


def media_url(media_id: str | None) -> str | None:
    return f"/api/media/{media_id}" if media_id else None


def user_brief(row) -> dict:
    return {"id": row.id, "handle": row.handle, "name": row.name, "headline": row.headline or "",
            "avatar_url": media_url(row.avatar_media_id)}


def users_by_id(conn: Connection, ids: Iterable[str]) -> dict[str, dict]:
    ids = list({i for i in ids if i})
    if not ids:
        return {}
    rows = conn.execute(select(db.users.c.id, db.users.c.handle, db.users.c.name, db.users.c.headline,
                               db.users.c.avatar_media_id).where(db.users.c.id.in_(ids)))
    return {row.id: user_brief(row) for row in rows}


def user_full(row, *, include_private: bool = False) -> dict:
    data = {
        **user_brief(row),
        "bio": row.bio or "", "location": row.location or "", "cover_url": media_url(row.cover_media_id),
        "skills": row.skills or [], "interests": row.interests or [], "industries": row.industries or [],
        "looking_for": row.looking_for or [], "open_to": row.open_to or [], "links": row.links or {},
        "achievements": row.achievements or [], "follower_count": row.follower_count, "following_count": row.following_count,
        "joined_at": iso(row.created_at), "profile_visibility": row.profile_visibility,
    }
    if include_private:
        data.update(email=row.email, role=row.role, message_policy=row.message_policy)
    return data
