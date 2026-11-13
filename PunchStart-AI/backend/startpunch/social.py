"""Social-network domain helpers: visibility, notifications, serialization, ranking, recommendations."""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import and_, func, insert, or_, select, update
from sqlalchemy.engine import Connection

from . import db
from .serializers import media_url, users_by_id
from .utils import as_aware, iso, new_id, utcnow

POST_KINDS = {"post", "idea", "update", "milestone", "article", "question", "news"}
REPORT_REASONS = {"spam", "harassment", "hate", "misinformation", "inappropriate", "impersonation", "other"}
VIDEO_HOSTS = {"youtube.com", "www.youtube.com", "youtu.be", "vimeo.com", "www.vimeo.com", "loom.com", "www.loom.com"}


def safe_url(value: str | None, video: bool = False) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise HTTPException(422, "Links must start with http:// or https://")
    if video and (parts.hostname or "").lower() not in VIDEO_HOSTS:
        raise HTTPException(422, "Video links must be YouTube, Vimeo or Loom URLs.")
    return value[:500]


# ------------------------------------------------------------------------------ graph
def blocked_ids(conn: Connection, user_id: str) -> set[str]:
    rows = conn.execute(select(db.blocks.c.blocker_id, db.blocks.c.blocked_id)
                        .where(or_(db.blocks.c.blocker_id == user_id, db.blocks.c.blocked_id == user_id)))
    return {r.blocked_id if r.blocker_id == user_id else r.blocker_id for r in rows}


def following_ids(conn: Connection, user_id: str) -> set[str]:
    return {r.followee_id for r in conn.execute(select(db.follows.c.followee_id).where(db.follows.c.follower_id == user_id))}


def community_ids(conn: Connection, user_id: str) -> set[str]:
    return {r.community_id for r in conn.execute(select(db.community_members.c.community_id)
                                                  .where(db.community_members.c.user_id == user_id))}


def connection_between(conn: Connection, a: str, b: str):
    return conn.execute(select(db.connections).where(or_(
        and_(db.connections.c.requester_id == a, db.connections.c.addressee_id == b),
        and_(db.connections.c.requester_id == b, db.connections.c.addressee_id == a)))).first()


def are_connected(conn: Connection, a: str, b: str) -> bool:
    row = connection_between(conn, a, b)
    return bool(row and row.status == "accepted")


def notify(conn: Connection, user_id: str, actor_id: str | None, type_: str, entity_type: str, entity_id: str, text: str) -> None:
    if not user_id or user_id == actor_id:
        return
    conn.execute(insert(db.notifications).values(id=new_id(), user_id=user_id, actor_id=actor_id, type=type_,
                                                 entity_type=entity_type, entity_id=entity_id, text=text[:300],
                                                 read_at=None, created_at=utcnow()))


# ------------------------------------------------------------------------------ posts
def can_view_post(row, viewer_id: str, following: set[str], blocked: set[str], is_admin: bool = False) -> bool:
    if row.author_id in blocked:
        return False
    if row.hidden and row.author_id != viewer_id and not is_admin:
        return False
    if row.visibility == "followers" and row.author_id != viewer_id and row.author_id not in following:
        return False
    return True


def serialize_posts(conn: Connection, rows: list, viewer_id: str, *, nested: bool = True) -> list[dict]:
    if not rows:
        return []
    post_ids = [r.id for r in rows]
    authors = users_by_id(conn, [r.author_id for r in rows])
    liked = {r.post_id for r in conn.execute(select(db.post_likes.c.post_id).where(
        db.post_likes.c.user_id == viewer_id, db.post_likes.c.post_id.in_(post_ids)))}
    saved = {r.post_id for r in conn.execute(select(db.bookmarks.c.post_id).where(
        db.bookmarks.c.user_id == viewer_id, db.bookmarks.c.post_id.in_(post_ids)))}
    reposted = {r.repost_of_id for r in conn.execute(select(db.posts.c.repost_of_id).where(
        db.posts.c.author_id == viewer_id, db.posts.c.repost_of_id.in_(post_ids)))}
    community_rows = {r.id: r for r in conn.execute(select(db.communities.c.id, db.communities.c.slug, db.communities.c.name)
                                                     .where(db.communities.c.id.in_([r.community_id for r in rows if r.community_id])))}
    startup_rows = {r.id: r for r in conn.execute(select(db.startups.c.id, db.startups.c.name, db.startups.c.visibility,
                                                          db.startups.c.owner_id)
                                                   .where(db.startups.c.id.in_([r.startup_id for r in rows if r.startup_id])))}
    originals: dict[str, dict] = {}
    if nested:
        ids = [r.repost_of_id for r in rows if r.repost_of_id]
        if ids:
            original_rows = conn.execute(select(db.posts).where(db.posts.c.id.in_(ids))).fetchall()
            blocked = blocked_ids(conn, viewer_id)
            following = following_ids(conn, viewer_id)
            visible = [o for o in original_rows if can_view_post(o, viewer_id, following, blocked)]
            originals = {o["id"]: o for o in serialize_posts(conn, visible, viewer_id, nested=False)}
    out = []
    for r in rows:
        startup = startup_rows.get(r.startup_id)
        if startup and startup.visibility != "public" and startup.owner_id != viewer_id:
            startup = None
        community = community_rows.get(r.community_id)
        out.append({
            "id": r.id, "kind": r.kind, "title": r.title, "body": r.body, "tags": r.tags or [],
            "media": [{"id": m, "url": media_url(m)} for m in (r.media_ids or [])],
            "link_url": r.link_url or "", "video_url": r.video_url or "", "visibility": r.visibility, "hidden": r.hidden,
            "author": authors.get(r.author_id), "community": {"slug": community.slug, "name": community.name} if community else None,
            "startup": {"id": startup.id, "name": startup.name} if startup else None,
            "repost_of": originals.get(r.repost_of_id) if r.repost_of_id else None,
            "repost_unavailable": bool(r.repost_of_id) and r.repost_of_id not in originals,
            "counts": {"likes": r.like_count, "comments": r.comment_count, "reposts": r.repost_count},
            "viewer": {"liked": r.id in liked, "bookmarked": r.id in saved, "reposted": r.id in reposted,
                       "is_author": r.author_id == viewer_id},
            "created_at": iso(r.created_at), "edited": bool(r.updated_at and r.created_at and r.updated_at > r.created_at),
            "ai_summary": r.ai_summary,
        })
    return out


def get_post_or_404(conn: Connection, post_id: str, viewer_id: str, is_admin: bool = False):
    row = conn.execute(select(db.posts).where(db.posts.c.id == post_id)).first()
    if row is None or not can_view_post(row, viewer_id, following_ids(conn, viewer_id), blocked_ids(conn, viewer_id), is_admin):
        raise HTTPException(404, "Post not found.")
    return row


def bump(conn: Connection, table, key_col, key, column: str, delta: int) -> None:
    conn.execute(update(table).where(key_col == key).values(**{column: func.max(getattr(table.c, column) + delta, 0)})
                 if conn.dialect.name == "sqlite" else
                 update(table).where(key_col == key).values(**{column: func.greatest(getattr(table.c, column) + delta, 0)}))


# ---------------------------------------------------------------------------- ranking
def _hours_since(value: datetime | None) -> float:
    value = as_aware(value) or utcnow()
    return max(0.0, (utcnow() - value).total_seconds() / 3600)


def rank_for_you(rows: list, viewer, following: set[str], my_communities: set[str]) -> list:
    """Score = recency decay x engagement x affinity. Every factor is a real signal; no synthetic popularity."""
    interests = {t.lower() for t in (viewer.interests or []) + (viewer.industries or [])}
    scored = []
    for r in rows:
        recency = 0.5 ** (_hours_since(r.created_at) / 36.0)
        engagement = 1.0 + math.log1p(r.like_count + 2 * r.comment_count + 3 * r.repost_count)
        affinity = 1.0
        if r.author_id in following:
            affinity += 1.5
        if r.community_id and r.community_id in my_communities:
            affinity += 1.0
        tags = {t.lower() for t in (r.tags or [])}
        text = f"{r.title} {r.body}".lower()
        overlap = len(tags & interests) + sum(1 for i in interests if len(i) > 3 and i in text)
        affinity += 0.6 * min(3, overlap)
        if r.kind in {"idea", "milestone", "question"}:
            affinity += 0.2
        scored.append((recency * engagement * affinity, r))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [r for _, r in scored]


def _tokens(values) -> set[str]:
    out = set()
    for value in values or []:
        value = str(value).lower().strip()
        if value:
            out.add(value)
            out.update(w for w in re.split(r"[^a-z0-9+#]+", value) if len(w) > 2)
    return out


def recommend_people(conn: Connection, me, limit: int = 12) -> list[dict]:
    blocked = blocked_ids(conn, me.id)
    following = following_ids(conn, me.id)
    my_comms = community_ids(conn, me.id)
    connected = {r.requester_id if r.addressee_id == me.id else r.addressee_id for r in conn.execute(
        select(db.connections).where(or_(db.connections.c.requester_id == me.id, db.connections.c.addressee_id == me.id),
                                     db.connections.c.status == "accepted"))}
    my_topics = _tokens((me.interests or []) + (me.industries or []))
    my_needs = _tokens(me.looking_for)
    my_offer = _tokens((me.skills or []) + (me.open_to or []))
    candidates = conn.execute(select(db.users).where(db.users.c.id != me.id).order_by(db.users.c.created_at.desc()).limit(2000)).fetchall()
    followed_by_followees: dict[str, int] = {}
    if following:
        for r in conn.execute(select(db.follows.c.followee_id).where(db.follows.c.follower_id.in_(list(following)))):
            followed_by_followees[r.followee_id] = followed_by_followees.get(r.followee_id, 0) + 1
    member_rows = conn.execute(select(db.community_members.c.user_id, db.community_members.c.community_id)
                               .where(db.community_members.c.community_id.in_(list(my_comms)))).fetchall() if my_comms else []
    shared_comms: dict[str, int] = {}
    for r in member_rows:
        shared_comms[r.user_id] = shared_comms.get(r.user_id, 0) + 1
    out = []
    for u in candidates:
        if u.id in blocked or u.id in following or u.id in connected:
            continue
        reasons, score = [], 0.0
        topics = my_topics & _tokens((u.interests or []) + (u.industries or []))
        if topics:
            score += 2.0 * min(4, len(topics))
            reasons.append("Shared interests: " + ", ".join(sorted(topics)[:3]))
        they_offer = my_needs & _tokens((u.skills or []) + (u.open_to or []))
        if they_offer:
            score += 2.5 * min(3, len(they_offer))
            reasons.append("Has what you're looking for: " + ", ".join(sorted(they_offer)[:3]))
        they_need = _tokens(u.looking_for) & my_offer
        if they_need:
            score += 1.5 * min(3, len(they_need))
            reasons.append("Looking for your skills: " + ", ".join(sorted(they_need)[:3]))
        mutual = followed_by_followees.get(u.id, 0)
        if mutual:
            score += 0.8 * min(5, mutual)
            reasons.append(f"Followed by {mutual} people you follow")
        comms = shared_comms.get(u.id, 0)
        if comms:
            score += 0.6 * min(4, comms)
            reasons.append(f"{comms} shared communit{'y' if comms == 1 else 'ies'}")
        if score > 0:
            out.append({"user": {"id": u.id, "handle": u.handle, "name": u.name, "headline": u.headline,
                                 "avatar_url": media_url(u.avatar_media_id), "skills": (u.skills or [])[:5],
                                 "looking_for": (u.looking_for or [])[:4]},
                        "score": round(score, 2), "reasons": reasons})
    out.sort(key=lambda item: item["score"], reverse=True)
    return out[:limit]


def recommend_communities(conn: Connection, me, limit: int = 6) -> list[dict]:
    mine = community_ids(conn, me.id)
    topics = _tokens((me.interests or []) + (me.industries or []) + (me.skills or []))
    following = following_ids(conn, me.id)
    joined_by_followees: dict[str, int] = {}
    if following:
        for r in conn.execute(select(db.community_members.c.community_id)
                              .where(db.community_members.c.user_id.in_(list(following)))):
            joined_by_followees[r.community_id] = joined_by_followees.get(r.community_id, 0) + 1
    out = []
    for c in conn.execute(select(db.communities)).fetchall():
        if c.id in mine:
            continue
        overlap = topics & _tokens((c.tags or []) + [c.name])
        friends = joined_by_followees.get(c.id, 0)
        score = 2.0 * len(overlap) + 1.0 * friends
        reasons = []
        if overlap:
            reasons.append("Matches your interests: " + ", ".join(sorted(overlap)[:3]))
        if friends:
            reasons.append(f"{friends} people you follow are members")
        out.append({"slug": c.slug, "name": c.name, "description": c.description, "member_count": c.member_count,
                    "score": score, "reasons": reasons})
    out.sort(key=lambda item: (item["score"], item["member_count"]), reverse=True)
    return out[:limit]


def cleanup_user(conn: Connection, user_id: str) -> None:
    """Keep denormalized counters consistent before a user's rows are cascaded away."""
    for r in conn.execute(select(db.post_likes.c.post_id).where(db.post_likes.c.user_id == user_id)).fetchall():
        bump(conn, db.posts, db.posts.c.id, r.post_id, "like_count", -1)
    for r in conn.execute(select(db.comments.c.post_id).where(db.comments.c.author_id == user_id)).fetchall():
        bump(conn, db.posts, db.posts.c.id, r.post_id, "comment_count", -1)
    for r in conn.execute(select(db.posts.c.repost_of_id).where(db.posts.c.author_id == user_id,
                                                                db.posts.c.repost_of_id.is_not(None))).fetchall():
        bump(conn, db.posts, db.posts.c.id, r.repost_of_id, "repost_count", -1)
    for r in conn.execute(select(db.community_members.c.community_id).where(db.community_members.c.user_id == user_id)).fetchall():
        bump(conn, db.communities, db.communities.c.id, r.community_id, "member_count", -1)
    for r in conn.execute(select(db.startup_follows.c.startup_id).where(db.startup_follows.c.user_id == user_id)).fetchall():
        bump(conn, db.startups, db.startups.c.id, r.startup_id, "follower_count", -1)


def as_dt(value) -> datetime:
    return as_aware(value) or datetime.min.replace(tzinfo=timezone.utc)
