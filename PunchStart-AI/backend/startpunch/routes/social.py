"""Founder social network API."""
from __future__ import annotations

import hashlib
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, delete, desc, func, insert, or_, select, update

from .. import db, llm, ratelimit
from ..analysis import pipeline
from ..analysis.signals import AnalysisInput
from ..config import get_settings
from ..security import CurrentUser, admin_user, current_user
from ..serializers import media_url, user_brief, user_full, users_by_id
from ..social import (POST_KINDS, REPORT_REASONS, are_connected, as_dt, blocked_ids, bump, can_view_post, community_ids,
                      connection_between, following_ids, get_post_or_404, notify, rank_for_you, recommend_communities,
                      recommend_people, safe_url, serialize_posts)
from ..utils import clean_list, clean_text, extract_hashtags, iso, new_id, utcnow

router = APIRouter(tags=["social"])
IMAGE_SIGNATURES = {b"\x89PNG\r\n\x1a\n": "image/png", b"\xff\xd8\xff": "image/jpeg", b"GIF87a": "image/gif",
                    b"GIF89a": "image/gif"}


def _me(conn, user_id: str):
    return conn.execute(select(db.users).where(db.users.c.id == user_id)).first()


def _user_by_handle(conn, handle: str):
    row = conn.execute(select(db.users).where(db.users.c.handle == handle.lower())).first()
    if row is None:
        raise HTTPException(404, "Member not found.")
    return row


# =============================================================================== media
@router.post("/media", status_code=201)
async def upload_media(request: Request, user: CurrentUser = Depends(current_user)):
    """Raw-body image upload (Content-Type: image/png|jpeg|gif|webp). Type is verified from the file signature."""
    ratelimit.hit("upload", user.id)
    limit = get_settings().max_upload_bytes
    declared = int(request.headers.get("content-length") or 0)
    if declared > limit:
        raise HTTPException(413, f"Images must be smaller than {limit // (1024 * 1024)} MB.")
    data = await request.body()
    if not data or len(data) > limit:
        raise HTTPException(413 if data else 422, f"Images must be smaller than {limit // (1024 * 1024)} MB.")
    content_type = next((t for sig, t in IMAGE_SIGNATURES.items() if data.startswith(sig)), None)
    if content_type is None and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        content_type = "image/webp"
    if content_type is None:
        raise HTTPException(415, "Only PNG, JPEG, GIF or WebP images are supported.")
    media_id = new_id()
    with db.transaction() as conn:
        conn.execute(insert(db.media).values(id=media_id, owner_id=user.id, content_type=content_type, size=len(data),
                                             sha256=hashlib.sha256(data).hexdigest(), data=data, created_at=utcnow()))
    return {"id": media_id, "url": media_url(media_id), "content_type": content_type, "size": len(data)}


@router.get("/media/{media_id}")
def get_media(media_id: str, user: CurrentUser = Depends(current_user)):
    with db.read() as conn:
        row = conn.execute(select(db.media.c.content_type, db.media.c.data).where(db.media.c.id == media_id)).first()
    if row is None:
        raise HTTPException(404, "Not found.")
    return Response(content=bytes(row.data), media_type=row.content_type,
                    headers={"Cache-Control": "private, max-age=31536000, immutable", "Content-Security-Policy": "default-src 'none'"})


# ============================================================================ profiles
class ProfileIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    handle: str | None = Field(default=None, pattern=r"^[a-z0-9_]{3,30}$")
    headline: str | None = Field(default=None, max_length=140)
    bio: str | None = Field(default=None, max_length=2000)
    location: str | None = Field(default=None, max_length=80)
    skills: list[str] | None = Field(default=None, max_length=25)
    interests: list[str] | None = Field(default=None, max_length=25)
    industries: list[str] | None = Field(default=None, max_length=15)
    looking_for: list[str] | None = Field(default=None, max_length=10)
    open_to: list[str] | None = Field(default=None, max_length=10)
    links: dict[str, str] | None = None
    achievements: list[dict] | None = Field(default=None, max_length=20)
    avatar_media_id: str | None = Field(default=None, max_length=24)
    cover_media_id: str | None = Field(default=None, max_length=24)
    profile_visibility: str | None = Field(default=None, pattern="^(public|connections)$")
    message_policy: str | None = Field(default=None, pattern="^(everyone|connections)$")


@router.patch("/me/profile")
def update_profile(payload: ProfileIn, user: CurrentUser = Depends(current_user)):
    values: dict = {}
    data = payload.model_dump(exclude_none=True)
    for key in ("name", "headline", "bio", "location"):
        if key in data:
            values[key] = clean_text(data[key], {"name": 80, "headline": 140, "bio": 2000, "location": 80}[key])
    for key in ("skills", "interests", "industries", "looking_for", "open_to"):
        if key in data:
            values[key] = clean_list(data[key], max_items=25)
    if "links" in data:
        allowed = {"website", "linkedin", "github", "x", "youtube", "portfolio"}
        values["links"] = {k: safe_url(v) for k, v in data["links"].items() if k in allowed and v}
    if "achievements" in data:
        values["achievements"] = [{"title": clean_text(a.get("title"), 140), "year": clean_text(a.get("year"), 8)}
                                  for a in data["achievements"] if a.get("title")]
    for key in ("profile_visibility", "message_policy"):
        if key in data:
            values[key] = data[key]
    with db.transaction() as conn:
        for key in ("avatar_media_id", "cover_media_id"):
            if key in data:
                owner = conn.execute(select(db.media.c.owner_id).where(db.media.c.id == data[key])).scalar()
                if owner != user.id:
                    raise HTTPException(422, "Upload the image first.")
                values[key] = data[key]
        if "handle" in data and data["handle"] != user.handle:
            if conn.execute(select(db.users.c.id).where(db.users.c.handle == data["handle"])).first():
                raise HTTPException(409, "That handle is taken.")
            values["handle"] = data["handle"]
        if values:
            conn.execute(update(db.users).where(db.users.c.id == user.id).values(**values, updated_at=utcnow()))
        row = _me(conn, user.id)
    return {"user": user_full(row, include_private=True)}


@router.get("/users/{handle}")
def get_profile(handle: str, user: CurrentUser = Depends(current_user)):
    with db.read() as conn:
        row = _user_by_handle(conn, handle)
        if row.id in blocked_ids(conn, user.id):
            raise HTTPException(404, "Member not found.")
        connection = connection_between(conn, user.id, row.id)
        connected = bool(connection and connection.status == "accepted")
        is_self = row.id == user.id
        data = user_full(row, include_private=is_self)
        restricted = row.profile_visibility == "connections" and not connected and not is_self
        if restricted:
            data = {**user_brief(row), "restricted": True, "follower_count": row.follower_count,
                    "following_count": row.following_count, "cover_url": media_url(row.cover_media_id)}
        data["relationship"] = {
            "is_self": is_self,
            "following": bool(conn.execute(select(db.follows).where(db.follows.c.follower_id == user.id,
                                                                    db.follows.c.followee_id == row.id)).first()),
            "follows_you": bool(conn.execute(select(db.follows).where(db.follows.c.follower_id == row.id,
                                                                      db.follows.c.followee_id == user.id)).first()),
            "connection": {"id": connection.id, "status": connection.status,
                           "direction": "outgoing" if connection.requester_id == user.id else "incoming"} if connection else None,
            "blocked": bool(conn.execute(select(db.blocks).where(db.blocks.c.blocker_id == user.id,
                                                                 db.blocks.c.blocked_id == row.id)).first()),
            "can_message": is_self or row.message_policy == "everyone" or connected,
        }
        startups = conn.execute(select(db.startups).where(db.startups.c.owner_id == row.id,
                                                          or_(db.startups.c.visibility == "public", db.startups.c.owner_id == user.id))
                                .order_by(desc(db.startups.c.updated_at))).fetchall()
        data["startups"] = [] if restricted else [_startup_brief(s) for s in startups]
        data["post_count"] = conn.execute(select(func.count()).select_from(db.posts)
                                          .where(db.posts.c.author_id == row.id, db.posts.c.hidden.is_(False))).scalar_one()
    return data


@router.get("/users/{handle}/posts")
def user_posts(handle: str, offset: int = Query(0, ge=0), user: CurrentUser = Depends(current_user)):
    with db.read() as conn:
        row = _user_by_handle(conn, handle)
        if row.id in blocked_ids(conn, user.id):
            raise HTTPException(404, "Member not found.")
        if row.profile_visibility == "connections" and row.id != user.id and not are_connected(conn, user.id, row.id):
            return {"posts": [], "restricted": True}
        rows = conn.execute(select(db.posts).where(db.posts.c.author_id == row.id).order_by(desc(db.posts.c.created_at))
                            .offset(offset).limit(20)).fetchall()
        following = following_ids(conn, user.id)
        visible = [r for r in rows if can_view_post(r, user.id, following, set(), user.is_admin)]
        return {"posts": serialize_posts(conn, visible, user.id), "next_offset": offset + 20 if len(rows) == 20 else None}


@router.get("/users/{handle}/{relation}")
def user_relations(handle: str, relation: str, user: CurrentUser = Depends(current_user)):
    if relation not in {"followers", "following"}:
        raise HTTPException(404, "Not found.")
    with db.read() as conn:
        row = _user_by_handle(conn, handle)
        if relation == "followers":
            ids = [r.follower_id for r in conn.execute(select(db.follows.c.follower_id).where(db.follows.c.followee_id == row.id)
                                                       .order_by(desc(db.follows.c.created_at)).limit(200))]
        else:
            ids = [r.followee_id for r in conn.execute(select(db.follows.c.followee_id).where(db.follows.c.follower_id == row.id)
                                                       .order_by(desc(db.follows.c.created_at)).limit(200))]
        blocked = blocked_ids(conn, user.id)
        people = users_by_id(conn, [i for i in ids if i not in blocked])
    return {"users": [people[i] for i in ids if i in people]}


@router.post("/users/{handle}/follow")
def follow(handle: str, user: CurrentUser = Depends(current_user)):
    ratelimit.hit("write", user.id)
    with db.transaction() as conn:
        target = _user_by_handle(conn, handle)
        if target.id == user.id:
            raise HTTPException(422, "You can't follow yourself.")
        if target.id in blocked_ids(conn, user.id):
            raise HTTPException(403, "You can't follow this member.")
        if conn.execute(select(db.follows).where(db.follows.c.follower_id == user.id, db.follows.c.followee_id == target.id)).first():
            return {"following": True}
        conn.execute(insert(db.follows).values(follower_id=user.id, followee_id=target.id, created_at=utcnow()))
        bump(conn, db.users, db.users.c.id, target.id, "follower_count", 1)
        bump(conn, db.users, db.users.c.id, user.id, "following_count", 1)
        notify(conn, target.id, user.id, "follow", "user", user.handle, f"{user.name} started following you")
    return {"following": True}


@router.delete("/users/{handle}/follow")
def unfollow(handle: str, user: CurrentUser = Depends(current_user)):
    with db.transaction() as conn:
        target = _user_by_handle(conn, handle)
        result = conn.execute(delete(db.follows).where(db.follows.c.follower_id == user.id, db.follows.c.followee_id == target.id))
        if result.rowcount:
            bump(conn, db.users, db.users.c.id, target.id, "follower_count", -1)
            bump(conn, db.users, db.users.c.id, user.id, "following_count", -1)
    return {"following": False}


@router.post("/users/{handle}/block")
def block(handle: str, user: CurrentUser = Depends(current_user)):
    with db.transaction() as conn:
        target = _user_by_handle(conn, handle)
        if target.id == user.id:
            raise HTTPException(422, "You can't block yourself.")
        if not conn.execute(select(db.blocks).where(db.blocks.c.blocker_id == user.id, db.blocks.c.blocked_id == target.id)).first():
            conn.execute(insert(db.blocks).values(blocker_id=user.id, blocked_id=target.id, created_at=utcnow()))
        for a, b in ((user.id, target.id), (target.id, user.id)):
            if conn.execute(delete(db.follows).where(db.follows.c.follower_id == a, db.follows.c.followee_id == b)).rowcount:
                bump(conn, db.users, db.users.c.id, b, "follower_count", -1)
                bump(conn, db.users, db.users.c.id, a, "following_count", -1)
        conn.execute(delete(db.connections).where(or_(
            and_(db.connections.c.requester_id == user.id, db.connections.c.addressee_id == target.id),
            and_(db.connections.c.requester_id == target.id, db.connections.c.addressee_id == user.id))))
    return {"blocked": True}


@router.delete("/users/{handle}/block")
def unblock(handle: str, user: CurrentUser = Depends(current_user)):
    with db.transaction() as conn:
        target = _user_by_handle(conn, handle)
        conn.execute(delete(db.blocks).where(db.blocks.c.blocker_id == user.id, db.blocks.c.blocked_id == target.id))
    return {"blocked": False}


@router.get("/people")
def people(q: str = Query("", max_length=80), skill: str = Query("", max_length=40),
           looking_for: str = Query("", max_length=40), user: CurrentUser = Depends(current_user)):
    with db.read() as conn:
        stmt = select(db.users).where(db.users.c.id != user.id)
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(or_(func.lower(db.users.c.name).like(like), func.lower(db.users.c.handle).like(like),
                                  func.lower(db.users.c.headline).like(like)))
        rows = conn.execute(stmt.order_by(desc(db.users.c.follower_count)).limit(300)).fetchall()
        blocked = blocked_ids(conn, user.id)
    out = []
    for r in rows:
        if r.id in blocked:
            continue
        if skill and skill.lower() not in " ".join(r.skills or []).lower():
            continue
        if looking_for and looking_for.lower() not in " ".join((r.open_to or []) + (r.skills or [])).lower():
            continue
        out.append({**user_brief(r), "skills": (r.skills or [])[:6], "looking_for": (r.looking_for or [])[:4],
                    "open_to": (r.open_to or [])[:4], "follower_count": r.follower_count})
    return {"users": out[:60]}


@router.get("/people/suggestions")
def people_suggestions(user: CurrentUser = Depends(current_user)):
    with db.read() as conn:
        me = _me(conn, user.id)
        people_recs = recommend_people(conn, me)
        community_recs = recommend_communities(conn, me)
    profile_complete = bool((me.interests or me.industries) and (me.skills or me.looking_for))
    return {"people": people_recs, "communities": community_recs, "profile_complete": profile_complete,
            "method": "Content-based matching on interests, skills and what members are looking for, plus your follow graph "
                      "and shared communities. No engagement is simulated."}


# =============================================================================== posts
class PostIn(BaseModel):
    kind: str = Field(default="post", max_length=16)
    title: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=10000)
    media_ids: list[str] = Field(default_factory=list, max_length=4)
    link_url: str = Field(default="", max_length=500)
    video_url: str = Field(default="", max_length=500)
    community: str | None = Field(default=None, max_length=48)
    startup_id: str | None = Field(default=None, max_length=24)
    visibility: str = Field(default="public", pattern="^(public|followers)$")


class PostPatch(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=10000)


@router.post("/posts", status_code=201)
def create_post(payload: PostIn, user: CurrentUser = Depends(current_user)):
    ratelimit.hit("write", user.id)
    kind = payload.kind if payload.kind in POST_KINDS else "post"
    title, body = clean_text(payload.title, 200), clean_text(payload.body, 10000)
    if not (title or body or payload.media_ids):
        raise HTTPException(422, "Write something or attach an image.")
    now = utcnow()
    with db.transaction() as conn:
        community_id = None
        if payload.community:
            community = conn.execute(select(db.communities).where(db.communities.c.slug == payload.community)).first()
            if community is None:
                raise HTTPException(404, "Community not found.")
            if community.id not in community_ids(conn, user.id):
                raise HTTPException(403, "Join the community to post in it.")
            community_id = community.id
        if payload.startup_id:
            owner = conn.execute(select(db.startups.c.owner_id).where(db.startups.c.id == payload.startup_id)).scalar()
            if owner != user.id:
                raise HTTPException(403, "You can only post updates for your own startups.")
        for media_id in payload.media_ids:
            if conn.execute(select(db.media.c.owner_id).where(db.media.c.id == media_id)).scalar() != user.id:
                raise HTTPException(422, "Attach images you uploaded.")
        post_id = new_id()
        conn.execute(insert(db.posts).values(
            id=post_id, author_id=user.id, kind=kind, title=title, body=body, media_ids=payload.media_ids,
            link_url=safe_url(payload.link_url), video_url=safe_url(payload.video_url, video=True),
            tags=extract_hashtags(f"{title} {body}"), community_id=community_id, startup_id=payload.startup_id,
            repost_of_id=None, visibility=payload.visibility, hidden=False, like_count=0, comment_count=0, repost_count=0,
            bookmark_count=0, ai_summary=None, created_at=now, updated_at=now))
        if community_id:
            bump(conn, db.communities, db.communities.c.id, community_id, "post_count", 1)
        row = conn.execute(select(db.posts).where(db.posts.c.id == post_id)).first()
        return serialize_posts(conn, [row], user.id)[0]


@router.get("/posts/{post_id}")
def get_post(post_id: str, user: CurrentUser = Depends(current_user)):
    with db.read() as conn:
        row = get_post_or_404(conn, post_id, user.id, user.is_admin)
        return serialize_posts(conn, [row], user.id)[0]


@router.patch("/posts/{post_id}")
def edit_post(post_id: str, payload: PostPatch, user: CurrentUser = Depends(current_user)):
    with db.transaction() as conn:
        row = conn.execute(select(db.posts).where(db.posts.c.id == post_id)).first()
        if row is None or row.author_id != user.id:
            raise HTTPException(404, "Post not found.")
        title = clean_text(payload.title, 200) if payload.title is not None else row.title
        body = clean_text(payload.body, 10000) if payload.body is not None else row.body
        conn.execute(update(db.posts).where(db.posts.c.id == post_id).values(
            title=title, body=body, tags=extract_hashtags(f"{title} {body}"), updated_at=utcnow(), ai_summary=None))
        row = conn.execute(select(db.posts).where(db.posts.c.id == post_id)).first()
        return serialize_posts(conn, [row], user.id)[0]


@router.delete("/posts/{post_id}")
def delete_post(post_id: str, user: CurrentUser = Depends(current_user)):
    with db.transaction() as conn:
        row = conn.execute(select(db.posts).where(db.posts.c.id == post_id)).first()
        if row is None or (row.author_id != user.id and not user.is_admin):
            raise HTTPException(404, "Post not found.")
        if row.repost_of_id:
            bump(conn, db.posts, db.posts.c.id, row.repost_of_id, "repost_count", -1)
        if row.community_id:
            bump(conn, db.communities, db.communities.c.id, row.community_id, "post_count", -1)
        conn.execute(delete(db.posts).where(db.posts.c.id == post_id))
    return {"ok": True}


@router.post("/posts/{post_id}/like")
def like(post_id: str, user: CurrentUser = Depends(current_user)):
    ratelimit.hit("write", user.id)
    with db.transaction() as conn:
        row = get_post_or_404(conn, post_id, user.id)
        if conn.execute(select(db.post_likes).where(db.post_likes.c.post_id == post_id, db.post_likes.c.user_id == user.id)).first():
            return {"liked": True}
        conn.execute(insert(db.post_likes).values(post_id=post_id, user_id=user.id, created_at=utcnow()))
        bump(conn, db.posts, db.posts.c.id, post_id, "like_count", 1)
        notify(conn, row.author_id, user.id, "like", "post", post_id, f"{user.name} liked your post")
    return {"liked": True}


@router.delete("/posts/{post_id}/like")
def unlike(post_id: str, user: CurrentUser = Depends(current_user)):
    with db.transaction() as conn:
        if conn.execute(delete(db.post_likes).where(db.post_likes.c.post_id == post_id, db.post_likes.c.user_id == user.id)).rowcount:
            bump(conn, db.posts, db.posts.c.id, post_id, "like_count", -1)
    return {"liked": False}


@router.post("/posts/{post_id}/bookmark")
def bookmark(post_id: str, user: CurrentUser = Depends(current_user)):
    with db.transaction() as conn:
        get_post_or_404(conn, post_id, user.id)
        if not conn.execute(select(db.bookmarks).where(db.bookmarks.c.post_id == post_id, db.bookmarks.c.user_id == user.id)).first():
            conn.execute(insert(db.bookmarks).values(post_id=post_id, user_id=user.id, created_at=utcnow()))
            bump(conn, db.posts, db.posts.c.id, post_id, "bookmark_count", 1)
    return {"bookmarked": True}


@router.delete("/posts/{post_id}/bookmark")
def unbookmark(post_id: str, user: CurrentUser = Depends(current_user)):
    with db.transaction() as conn:
        if conn.execute(delete(db.bookmarks).where(db.bookmarks.c.post_id == post_id, db.bookmarks.c.user_id == user.id)).rowcount:
            bump(conn, db.posts, db.posts.c.id, post_id, "bookmark_count", -1)
    return {"bookmarked": False}


class RepostIn(BaseModel):
    comment: str = Field(default="", max_length=2000)


@router.post("/posts/{post_id}/repost", status_code=201)
def repost(post_id: str, payload: RepostIn, user: CurrentUser = Depends(current_user)):
    ratelimit.hit("write", user.id)
    with db.transaction() as conn:
        original = get_post_or_404(conn, post_id, user.id)
        if original.repost_of_id:  # repost the original, not a repost
            original = get_post_or_404(conn, original.repost_of_id, user.id)
        if original.visibility != "public":
            raise HTTPException(403, "Only public posts can be reposted.")
        existing = conn.execute(select(db.posts.c.id).where(db.posts.c.author_id == user.id,
                                                            db.posts.c.repost_of_id == original.id)).first()
        if existing and not payload.comment:
            raise HTTPException(409, "You already reposted this.")
        now = utcnow()
        new_post = new_id()
        conn.execute(insert(db.posts).values(
            id=new_post, author_id=user.id, kind="post", title="", body=clean_text(payload.comment, 2000), media_ids=[],
            link_url="", video_url="", tags=extract_hashtags(payload.comment), community_id=None, startup_id=None,
            repost_of_id=original.id, visibility="public", hidden=False, like_count=0, comment_count=0, repost_count=0,
            bookmark_count=0, ai_summary=None, created_at=now, updated_at=now))
        bump(conn, db.posts, db.posts.c.id, original.id, "repost_count", 1)
        notify(conn, original.author_id, user.id, "repost", "post", original.id, f"{user.name} reposted your post")
        row = conn.execute(select(db.posts).where(db.posts.c.id == new_post)).first()
        return serialize_posts(conn, [row], user.id)[0]


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    parent_id: str | None = Field(default=None, max_length=24)


@router.get("/posts/{post_id}/comments")
def list_comments(post_id: str, user: CurrentUser = Depends(current_user)):
    with db.read() as conn:
        get_post_or_404(conn, post_id, user.id, user.is_admin)
        blocked = blocked_ids(conn, user.id)
        rows = conn.execute(select(db.comments).where(db.comments.c.post_id == post_id).order_by(db.comments.c.created_at)
                            .limit(500)).fetchall()
        authors = users_by_id(conn, [r.author_id for r in rows])
    return {"comments": [
        {"id": r.id, "parent_id": r.parent_id, "body": "" if r.hidden else r.body, "hidden": r.hidden,
         "author": authors.get(r.author_id), "created_at": iso(r.created_at), "is_author": r.author_id == user.id}
        for r in rows if r.author_id not in blocked and (not r.hidden or user.is_admin or r.author_id == user.id)]}


@router.post("/posts/{post_id}/comments", status_code=201)
def add_comment(post_id: str, payload: CommentIn, user: CurrentUser = Depends(current_user)):
    ratelimit.hit("write", user.id)
    body = clean_text(payload.body, 4000)
    if not body:
        raise HTTPException(422, "Comment is empty.")
    with db.transaction() as conn:
        post = get_post_or_404(conn, post_id, user.id)
        parent = None
        if payload.parent_id:
            parent = conn.execute(select(db.comments).where(db.comments.c.id == payload.parent_id,
                                                            db.comments.c.post_id == post_id)).first()
            if parent is None:
                raise HTTPException(404, "Reply target not found.")
        comment_id = new_id()
        conn.execute(insert(db.comments).values(id=comment_id, post_id=post_id, author_id=user.id,
                                                parent_id=parent.id if parent else None, body=body, hidden=False,
                                                created_at=utcnow()))
        bump(conn, db.posts, db.posts.c.id, post_id, "comment_count", 1)
        if parent and parent.author_id != user.id:
            notify(conn, parent.author_id, user.id, "reply", "post", post_id, f"{user.name} replied to your comment")
        notify(conn, post.author_id, user.id, "comment", "post", post_id, f"{user.name} commented on your post")
    return {"id": comment_id, "parent_id": parent.id if parent else None, "body": body,
            "author": {"id": user.id, "handle": user.handle, "name": user.name}, "created_at": iso(utcnow()), "is_author": True}


@router.delete("/comments/{comment_id}")
def delete_comment(comment_id: str, user: CurrentUser = Depends(current_user)):
    with db.transaction() as conn:
        row = conn.execute(select(db.comments).where(db.comments.c.id == comment_id)).first()
        if row is None or (row.author_id != user.id and not user.is_admin):
            raise HTTPException(404, "Comment not found.")
        removed = 1 + conn.execute(select(func.count()).select_from(db.comments).where(db.comments.c.parent_id == comment_id)).scalar_one()
        conn.execute(delete(db.comments).where(db.comments.c.id == comment_id))
        bump(conn, db.posts, db.posts.c.id, row.post_id, "comment_count", -removed)
    return {"ok": True}


# ---------------------------------------------------------------------------- feeds
@router.get("/feed")
def feed(tab: str = Query("for_you", pattern="^(for_you|following|latest)$"), offset: int = Query(0, ge=0, le=500),
         user: CurrentUser = Depends(current_user)):
    page = 20
    with db.read() as conn:
        me = _me(conn, user.id)
        blocked = blocked_ids(conn, user.id)
        following = following_ids(conn, user.id)
        my_comms = community_ids(conn, user.id)
        base = select(db.posts).where(db.posts.c.hidden.is_(False))
        if blocked:
            base = base.where(db.posts.c.author_id.not_in(list(blocked)))
        if tab == "following":
            scope = [user.id, *following]
            stmt = base.where(or_(db.posts.c.author_id.in_(scope),
                                  db.posts.c.community_id.in_(list(my_comms)) if my_comms else False))
            rows = conn.execute(stmt.order_by(desc(db.posts.c.created_at)).offset(offset).limit(page)).fetchall()
        elif tab == "latest":
            rows = conn.execute(base.where(db.posts.c.visibility == "public").order_by(desc(db.posts.c.created_at))
                                .offset(offset).limit(page)).fetchall()
        else:
            since = utcnow() - timedelta(days=21)
            candidates = conn.execute(base.where(db.posts.c.created_at >= since).order_by(desc(db.posts.c.created_at))
                                      .limit(400)).fetchall()
            ranked = rank_for_you(candidates, me, following, my_comms)
            if len(ranked) < offset + page:  # backfill with older posts when the network is quiet
                older = conn.execute(base.where(db.posts.c.created_at < since).order_by(desc(db.posts.c.created_at))
                                     .limit(offset + page - len(ranked))).fetchall()
                ranked += older
            rows = ranked[offset:offset + page]
        rows = [r for r in rows if can_view_post(r, user.id, following, blocked)]
        posts = serialize_posts(conn, rows, user.id)
    return {"posts": posts, "next_offset": offset + page if len(posts) >= page - 2 else None, "tab": tab,
            "ranking": "recency × engagement × affinity (follows, communities, interests)" if tab == "for_you" else "chronological"}


@router.get("/bookmarks")
def my_bookmarks(user: CurrentUser = Depends(current_user)):
    with db.read() as conn:
        ids = [r.post_id for r in conn.execute(select(db.bookmarks.c.post_id).where(db.bookmarks.c.user_id == user.id)
                                               .order_by(desc(db.bookmarks.c.created_at)).limit(100))]
        rows = conn.execute(select(db.posts).where(db.posts.c.id.in_(ids))).fetchall() if ids else []
        order = {pid: i for i, pid in enumerate(ids)}
        following, blocked = following_ids(conn, user.id), blocked_ids(conn, user.id)
        rows = sorted((r for r in rows if can_view_post(r, user.id, following, blocked)), key=lambda r: order[r.id])
        return {"posts": serialize_posts(conn, rows, user.id)}


@router.get("/trending")
def trending(user: CurrentUser = Depends(current_user)):
    since = utcnow() - timedelta(days=7)
    with db.read() as conn:
        blocked = blocked_ids(conn, user.id)
        rows = conn.execute(select(db.posts).where(db.posts.c.created_at >= since, db.posts.c.hidden.is_(False),
                                                   db.posts.c.visibility == "public")).fetchall()
        rows = [r for r in rows if r.author_id not in blocked]
        tag_counts: dict[str, int] = {}
        for r in rows:
            for tag in r.tags or []:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        engaged = sorted((r for r in rows if r.like_count + r.comment_count + r.repost_count > 0),
                         key=lambda r: (r.like_count + 2 * r.comment_count + 3 * r.repost_count), reverse=True)[:8]
        startups = conn.execute(select(db.startups).where(db.startups.c.visibility == "public", db.startups.c.follower_count > 0)
                                .order_by(desc(db.startups.c.follower_count)).limit(6)).fetchall()
        return {"posts": serialize_posts(conn, engaged, user.id),
                "tags": [{"tag": t, "posts": n} for t, n in sorted(tag_counts.items(), key=lambda i: i[1], reverse=True)[:12]],
                "startups": [_startup_brief(s) for s in startups], "window_days": 7,
                "method": "Counts of real posts, likes, comments and reposts in the last 7 days."}


# ========================================================================= communities
@router.get("/communities")
def list_communities(user: CurrentUser = Depends(current_user)):
    with db.read() as conn:
        mine = community_ids(conn, user.id)
        rows = conn.execute(select(db.communities).order_by(desc(db.communities.c.member_count), db.communities.c.name)).fetchall()
        suggestions = recommend_communities(conn, _me(conn, user.id))
    return {"communities": [{"slug": r.slug, "name": r.name, "description": r.description, "tags": r.tags,
                             "member_count": r.member_count, "post_count": r.post_count, "joined": r.id in mine} for r in rows],
            "suggested": suggestions}


def _community(conn, slug: str):
    row = conn.execute(select(db.communities).where(db.communities.c.slug == slug)).first()
    if row is None:
        raise HTTPException(404, "Community not found.")
    return row


@router.get("/communities/{slug}")
def community_detail(slug: str, offset: int = Query(0, ge=0), user: CurrentUser = Depends(current_user)):
    with db.read() as conn:
        c = _community(conn, slug)
        blocked = blocked_ids(conn, user.id)
        following = following_ids(conn, user.id)
        rows = conn.execute(select(db.posts).where(db.posts.c.community_id == c.id).order_by(desc(db.posts.c.created_at))
                            .offset(offset).limit(20)).fetchall()
        rows = [r for r in rows if can_view_post(r, user.id, following, blocked, user.is_admin)]
        member_ids = [r.user_id for r in conn.execute(select(db.community_members.c.user_id)
                                                      .where(db.community_members.c.community_id == c.id)
                                                      .order_by(desc(db.community_members.c.joined_at)).limit(12))]
        members = users_by_id(conn, [m for m in member_ids if m not in blocked])
        return {"community": {"slug": c.slug, "name": c.name, "description": c.description, "tags": c.tags,
                              "member_count": c.member_count, "post_count": c.post_count,
                              "joined": c.id in community_ids(conn, user.id)},
                "posts": serialize_posts(conn, rows, user.id), "recent_members": [members[m] for m in member_ids if m in members],
                "next_offset": offset + 20 if len(rows) == 20 else None}


@router.post("/communities/{slug}/join")
def join(slug: str, user: CurrentUser = Depends(current_user)):
    with db.transaction() as conn:
        c = _community(conn, slug)
        if not conn.execute(select(db.community_members).where(db.community_members.c.community_id == c.id,
                                                               db.community_members.c.user_id == user.id)).first():
            conn.execute(insert(db.community_members).values(community_id=c.id, user_id=user.id, role="member", joined_at=utcnow()))
            bump(conn, db.communities, db.communities.c.id, c.id, "member_count", 1)
    return {"joined": True}


@router.delete("/communities/{slug}/join")
def leave(slug: str, user: CurrentUser = Depends(current_user)):
    with db.transaction() as conn:
        c = _community(conn, slug)
        if conn.execute(delete(db.community_members).where(db.community_members.c.community_id == c.id,
                                                           db.community_members.c.user_id == user.id)).rowcount:
            bump(conn, db.communities, db.communities.c.id, c.id, "member_count", -1)
    return {"joined": False}


# ============================================================================ startups
class StartupIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    tagline: str = Field(default="", max_length=160)
    description: str = Field(default="", max_length=5000)
    problem: str = Field(default="", max_length=2000)
    solution: str = Field(default="", max_length=2000)
    industry: str = Field(default="", max_length=60)
    stage: str = Field(default="", max_length=40)
    website: str = Field(default="", max_length=300)
    looking_for: list[str] = Field(default_factory=list, max_length=10)
    tags: list[str] = Field(default_factory=list, max_length=10)
    visibility: str = Field(default="private", pattern="^(private|public)$")
    allow_ai_analysis: bool = False


class StartupPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    tagline: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=5000)
    problem: str | None = Field(default=None, max_length=2000)
    solution: str | None = Field(default=None, max_length=2000)
    industry: str | None = Field(default=None, max_length=60)
    stage: str | None = Field(default=None, max_length=40)
    website: str | None = Field(default=None, max_length=300)
    looking_for: list[str] | None = Field(default=None, max_length=10)
    tags: list[str] | None = Field(default=None, max_length=10)
    visibility: str | None = Field(default=None, pattern="^(private|public)$")
    allow_ai_analysis: bool | None = None


def _startup_brief(s) -> dict:
    return {"id": s.id, "name": s.name, "tagline": s.tagline, "industry": s.industry, "stage": s.stage,
            "looking_for": s.looking_for or [], "visibility": s.visibility, "follower_count": s.follower_count,
            "allow_ai_analysis": s.allow_ai_analysis}


def _startup_for(conn, startup_id: str, viewer_id: str):
    row = conn.execute(select(db.startups).where(db.startups.c.id == startup_id)).first()
    if row is None or (row.visibility != "public" and row.owner_id != viewer_id):
        raise HTTPException(404, "Startup not found.")
    if row.owner_id in blocked_ids(conn, viewer_id):
        raise HTTPException(404, "Startup not found.")
    return row


def _clean_startup(values: dict) -> dict:
    out = {}
    for key, value in values.items():
        if key in {"looking_for", "tags"}:
            out[key] = clean_list(value, max_items=10)
        elif key == "website":
            out[key] = safe_url(value)
        elif isinstance(value, str):
            out[key] = clean_text(value)
        else:
            out[key] = value
    return out


@router.post("/startups", status_code=201)
def create_startup(payload: StartupIn, user: CurrentUser = Depends(current_user)):
    ratelimit.hit("write", user.id)
    now = utcnow()
    startup_id = new_id()
    with db.transaction() as conn:
        conn.execute(insert(db.startups).values(id=startup_id, owner_id=user.id, report_id=None, public_summary={},
                                                follower_count=0, created_at=now, updated_at=now,
                                                **_clean_startup(payload.model_dump())))
    return {"id": startup_id}


@router.get("/startups")
def list_startups(q: str = Query("", max_length=80), looking_for: str = Query("", max_length=40),
                  mine: bool = False, user: CurrentUser = Depends(current_user)):
    with db.read() as conn:
        stmt = select(db.startups)
        stmt = stmt.where(db.startups.c.owner_id == user.id) if mine else stmt.where(db.startups.c.visibility == "public")
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(or_(func.lower(db.startups.c.name).like(like), func.lower(db.startups.c.tagline).like(like),
                                  func.lower(db.startups.c.industry).like(like), func.lower(db.startups.c.description).like(like)))
        rows = conn.execute(stmt.order_by(desc(db.startups.c.updated_at)).limit(200)).fetchall()
        blocked = blocked_ids(conn, user.id)
        owners = users_by_id(conn, [r.owner_id for r in rows])
    out = []
    for r in rows:
        if r.owner_id in blocked:
            continue
        if looking_for and looking_for.lower() not in " ".join(r.looking_for or []).lower():
            continue
        out.append({**_startup_brief(r), "owner": owners.get(r.owner_id), "updated_at": iso(r.updated_at)})
    return {"startups": out}


@router.get("/startups/{startup_id}")
def get_startup(startup_id: str, user: CurrentUser = Depends(current_user)):
    with db.read() as conn:
        s = _startup_for(conn, startup_id, user.id)
        owner = users_by_id(conn, [s.owner_id]).get(s.owner_id)
        following = bool(conn.execute(select(db.startup_follows).where(db.startup_follows.c.startup_id == s.id,
                                                                       db.startup_follows.c.user_id == user.id)).first())
        my_request = conn.execute(select(db.collab_requests).where(db.collab_requests.c.startup_id == s.id,
                                                                   db.collab_requests.c.user_id == user.id)).first()
        rows = conn.execute(select(db.posts).where(db.posts.c.startup_id == s.id).order_by(desc(db.posts.c.created_at)).limit(20)).fetchall()
        f_ids, blocked = following_ids(conn, user.id), blocked_ids(conn, user.id)
        updates = serialize_posts(conn, [r for r in rows if can_view_post(r, user.id, f_ids, blocked)], user.id)
        pending = 0
        if s.owner_id == user.id:
            pending = conn.execute(select(func.count()).select_from(db.collab_requests).where(
                db.collab_requests.c.startup_id == s.id, db.collab_requests.c.status == "pending")).scalar_one()
    return {
        **_startup_brief(s), "description": s.description, "problem": s.problem, "solution": s.solution, "website": s.website,
        "tags": s.tags or [], "public_summary": s.public_summary or {}, "owner": owner, "is_owner": s.owner_id == user.id,
        "following": following, "my_request": {"status": my_request.status, "role": my_request.role} if my_request else None,
        "updates": updates, "pending_requests": pending, "has_report": bool(s.report_id) if s.owner_id == user.id else None,
        "created_at": iso(s.created_at), "updated_at": iso(s.updated_at),
    }


@router.patch("/startups/{startup_id}")
def update_startup(startup_id: str, payload: StartupPatch, user: CurrentUser = Depends(current_user)):
    values = _clean_startup(payload.model_dump(exclude_none=True))
    with db.transaction() as conn:
        row = conn.execute(select(db.startups.c.owner_id).where(db.startups.c.id == startup_id)).first()
        if row is None or row.owner_id != user.id:
            raise HTTPException(404, "Startup not found.")
        if values:
            conn.execute(update(db.startups).where(db.startups.c.id == startup_id).values(**values, updated_at=utcnow()))
    return {"ok": True}


@router.delete("/startups/{startup_id}")
def delete_startup(startup_id: str, user: CurrentUser = Depends(current_user)):
    with db.transaction() as conn:
        if not conn.execute(delete(db.startups).where(db.startups.c.id == startup_id, db.startups.c.owner_id == user.id)).rowcount:
            raise HTTPException(404, "Startup not found.")
    return {"ok": True}


@router.post("/startups/{startup_id}/follow")
def follow_startup(startup_id: str, user: CurrentUser = Depends(current_user)):
    with db.transaction() as conn:
        s = _startup_for(conn, startup_id, user.id)
        if not conn.execute(select(db.startup_follows).where(db.startup_follows.c.startup_id == s.id,
                                                             db.startup_follows.c.user_id == user.id)).first():
            conn.execute(insert(db.startup_follows).values(startup_id=s.id, user_id=user.id, created_at=utcnow()))
            bump(conn, db.startups, db.startups.c.id, s.id, "follower_count", 1)
            notify(conn, s.owner_id, user.id, "startup_follow", "startup", s.id, f"{user.name} is following {s.name}")
    return {"following": True}


@router.delete("/startups/{startup_id}/follow")
def unfollow_startup(startup_id: str, user: CurrentUser = Depends(current_user)):
    with db.transaction() as conn:
        if conn.execute(delete(db.startup_follows).where(db.startup_follows.c.startup_id == startup_id,
                                                         db.startup_follows.c.user_id == user.id)).rowcount:
            bump(conn, db.startups, db.startups.c.id, startup_id, "follower_count", -1)
    return {"following": False}


class CollabIn(BaseModel):
    role: str = Field(min_length=1, max_length=60)
    message: str = Field(default="", max_length=1500)


@router.post("/startups/{startup_id}/collaborate", status_code=201)
def request_collaboration(startup_id: str, payload: CollabIn, user: CurrentUser = Depends(current_user)):
    ratelimit.hit("write", user.id)
    with db.transaction() as conn:
        s = _startup_for(conn, startup_id, user.id)
        if s.owner_id == user.id:
            raise HTTPException(422, "This is your startup.")
        if conn.execute(select(db.collab_requests).where(db.collab_requests.c.startup_id == s.id,
                                                         db.collab_requests.c.user_id == user.id)).first():
            raise HTTPException(409, "You already sent a request for this startup.")
        conn.execute(insert(db.collab_requests).values(id=new_id(), startup_id=s.id, user_id=user.id,
                                                       role=clean_text(payload.role, 60), message=clean_text(payload.message, 1500),
                                                       status="pending", created_at=utcnow(), responded_at=None))
        notify(conn, s.owner_id, user.id, "collab_request", "startup", s.id,
               f"{user.name} wants to join {s.name} as {clean_text(payload.role, 60)}")
    return {"status": "pending"}


@router.get("/startups/{startup_id}/collab-requests")
def collab_requests(startup_id: str, user: CurrentUser = Depends(current_user)):
    with db.read() as conn:
        s = conn.execute(select(db.startups).where(db.startups.c.id == startup_id)).first()
        if s is None or s.owner_id != user.id:
            raise HTTPException(404, "Startup not found.")
        rows = conn.execute(select(db.collab_requests).where(db.collab_requests.c.startup_id == startup_id)
                            .order_by(desc(db.collab_requests.c.created_at))).fetchall()
        people_ = users_by_id(conn, [r.user_id for r in rows])
    return {"requests": [{"id": r.id, "user": people_.get(r.user_id), "role": r.role, "message": r.message, "status": r.status,
                          "created_at": iso(r.created_at)} for r in rows]}


class RespondIn(BaseModel):
    accept: bool


@router.post("/collab-requests/{request_id}/respond")
def respond_collab(request_id: str, payload: RespondIn, user: CurrentUser = Depends(current_user)):
    with db.transaction() as conn:
        r = conn.execute(select(db.collab_requests).where(db.collab_requests.c.id == request_id)).first()
        s = conn.execute(select(db.startups).where(db.startups.c.id == r.startup_id)).first() if r else None
        if r is None or s is None or s.owner_id != user.id:
            raise HTTPException(404, "Request not found.")
        status = "accepted" if payload.accept else "declined"
        conn.execute(update(db.collab_requests).where(db.collab_requests.c.id == request_id).values(status=status, responded_at=utcnow()))
        if payload.accept:
            notify(conn, r.user_id, user.id, "collab_accepted", "startup", s.id,
                   f"{user.name} accepted your request to join {s.name} — send them a message")
    return {"status": status}


class PublishIn(BaseModel):
    startup_id: str | None = Field(default=None, max_length=24)
    name: str = Field(min_length=1, max_length=100)
    tagline: str = Field(default="", max_length=160)
    share_score: bool = False
    share_summary: bool = True
    share_scores_breakdown: bool = False
    looking_for: list[str] = Field(default_factory=list, max_length=10)
    allow_ai_analysis: bool = False
    feedback_question: str = Field(default="", max_length=500)


@router.post("/reports/{report_id}/publish")
def publish_report(report_id: str, payload: PublishIn, user: CurrentUser = Depends(current_user)):
    """Publish a founder-chosen public summary of a report. The full report, inputs and evidence stay private."""
    with db.transaction() as conn:
        report = conn.execute(select(db.reports).where(db.reports.c.id == report_id)).first()
        if report is None or report.user_id != user.id or not report.result or report.legacy:
            raise HTTPException(404, "Report not found or not finished.")
        result = report.result
        summary: dict = {"published_at": iso(utcnow())}
        if payload.share_summary:
            summary["one_liner"] = (result.get("signals") or {}).get("one_liner", "")
        if payload.share_score:
            summary["score"] = result["scores"]["overall"]
            summary["score_note"] = "Rule-based StartPunch rubric score (not a prediction of success)."
        if payload.share_scores_breakdown:
            summary["dimensions"] = [{"label": d["label"], "score": d["score"]} for d in result["scores"]["dimensions"]]
        sector = ((result.get("classification", {}).get("sector") or {}).get("top") or [{}])[0].get("label", "")
        now = utcnow()
        values = dict(name=clean_text(payload.name, 100), tagline=clean_text(payload.tagline, 160),
                      description=summary.get("one_liner", ""), industry=sector, stage=(report.input or {}).get("stage", ""),
                      looking_for=clean_list(payload.looking_for), visibility="public", allow_ai_analysis=payload.allow_ai_analysis,
                      report_id=report_id, public_summary=summary, updated_at=now)
        if payload.startup_id:
            owner = conn.execute(select(db.startups.c.owner_id).where(db.startups.c.id == payload.startup_id)).scalar()
            if owner != user.id:
                raise HTTPException(404, "Startup not found.")
            conn.execute(update(db.startups).where(db.startups.c.id == payload.startup_id).values(**values))
            startup_id = payload.startup_id
        else:
            startup_id = new_id()
            conn.execute(insert(db.startups).values(id=startup_id, owner_id=user.id, problem="", solution="", website="",
                                                    tags=[], follower_count=0, created_at=now, **values))
        if payload.feedback_question:
            conn.execute(insert(db.posts).values(
                id=new_id(), author_id=user.id, kind="idea", title=f"Feedback wanted: {values['name']}",
                body=clean_text(payload.feedback_question, 500), media_ids=[], link_url="", video_url="",
                tags=extract_hashtags(payload.feedback_question), community_id=None, startup_id=startup_id, repost_of_id=None,
                visibility="public", hidden=False, like_count=0, comment_count=0, repost_count=0, bookmark_count=0,
                ai_summary=None, created_at=now, updated_at=now))
    return {"startup_id": startup_id}


@router.post("/startups/{startup_id}/analyze", status_code=201)
def analyze_public_startup(startup_id: str, user: CurrentUser = Depends(current_user)):
    """Run StartPunch analysis on a public startup — only if its founder allowed it, using only public fields."""
    with db.read() as conn:
        s = _startup_for(conn, startup_id, user.id)
    if s.owner_id != user.id and not s.allow_ai_analysis:
        raise HTTPException(403, "The founder has not enabled AI analysis for this startup.")
    idea = " ".join(t for t in [s.tagline, s.description, (s.public_summary or {}).get("one_liner", "")] if t)
    if len(idea) < 30:
        raise HTTPException(422, "This startup's public description is too short to analyze.")
    payload = AnalysisInput(idea=idea[:5000], name=s.name, problem=s.problem, solution=s.solution, stage=s.stage or "idea")
    ratelimit.hit("ai", user.id)
    ratelimit.consume_ai_quota(user.id, "report")
    now = utcnow()
    report_id = new_id()
    with db.transaction() as conn:
        conn.execute(insert(db.reports).values(
            id=report_id, user_id=user.id, title=f"{s.name} (public profile)"[:120], status="queued", stage="understand",
            progress=pipeline.PROGRESS["understand"], input=payload.model_dump(), state={}, result=None, error=None,
            engine_version=pipeline.ENGINE_VERSION, legacy=False, lock_until=None, created_at=now, updated_at=now))
    return {"id": report_id}


# =========================================================================== network
class ConnectIn(BaseModel):
    handle: str = Field(min_length=3, max_length=30)
    message: str = Field(default="", max_length=300)


@router.post("/connections", status_code=201)
def request_connection(payload: ConnectIn, user: CurrentUser = Depends(current_user)):
    ratelimit.hit("write", user.id)
    with db.transaction() as conn:
        target = _user_by_handle(conn, payload.handle)
        if target.id == user.id or target.id in blocked_ids(conn, user.id):
            raise HTTPException(422, "You can't connect with this member.")
        existing = connection_between(conn, user.id, target.id)
        if existing:
            if existing.status == "pending" and existing.addressee_id == user.id:  # they asked first: accept
                conn.execute(update(db.connections).where(db.connections.c.id == existing.id).values(status="accepted", responded_at=utcnow()))
                notify(conn, target.id, user.id, "connection_accepted", "user", user.handle, f"{user.name} accepted your connection request")
                return {"id": existing.id, "status": "accepted"}
            if existing.status == "declined" and existing.requester_id == user.id:
                raise HTTPException(409, "Your previous request was declined.")
            return {"id": existing.id, "status": existing.status}
        connection_id = new_id()
        conn.execute(insert(db.connections).values(id=connection_id, requester_id=user.id, addressee_id=target.id, status="pending",
                                                   message=clean_text(payload.message, 300), created_at=utcnow(), responded_at=None))
        notify(conn, target.id, user.id, "connection_request", "user", user.handle, f"{user.name} wants to connect")
    return {"id": connection_id, "status": "pending"}


@router.get("/connections")
def my_connections(user: CurrentUser = Depends(current_user)):
    with db.read() as conn:
        rows = conn.execute(select(db.connections).where(or_(db.connections.c.requester_id == user.id,
                                                             db.connections.c.addressee_id == user.id))
                            .order_by(desc(db.connections.c.created_at))).fetchall()
        others = users_by_id(conn, [r.addressee_id if r.requester_id == user.id else r.requester_id for r in rows])
    out = {"connections": [], "incoming": [], "outgoing": []}
    for r in rows:
        other = others.get(r.addressee_id if r.requester_id == user.id else r.requester_id)
        if other is None:
            continue
        item = {"id": r.id, "user": other, "message": r.message, "status": r.status, "created_at": iso(r.created_at)}
        if r.status == "accepted":
            out["connections"].append(item)
        elif r.status == "pending":
            out["incoming" if r.addressee_id == user.id else "outgoing"].append(item)
    return out


@router.post("/connections/{connection_id}/respond")
def respond_connection(connection_id: str, payload: RespondIn, user: CurrentUser = Depends(current_user)):
    with db.transaction() as conn:
        r = conn.execute(select(db.connections).where(db.connections.c.id == connection_id)).first()
        if r is None or r.addressee_id != user.id or r.status != "pending":
            raise HTTPException(404, "Request not found.")
        status = "accepted" if payload.accept else "declined"
        conn.execute(update(db.connections).where(db.connections.c.id == connection_id).values(status=status, responded_at=utcnow()))
        if payload.accept:
            notify(conn, r.requester_id, user.id, "connection_accepted", "user", user.handle, f"{user.name} accepted your connection request")
    return {"status": status}


@router.delete("/connections/{connection_id}")
def remove_connection(connection_id: str, user: CurrentUser = Depends(current_user)):
    with db.transaction() as conn:
        conn.execute(delete(db.connections).where(db.connections.c.id == connection_id, or_(
            db.connections.c.requester_id == user.id, db.connections.c.addressee_id == user.id)))
    return {"ok": True}


# =========================================================================== messages
class ConversationIn(BaseModel):
    handle: str = Field(min_length=3, max_length=30)


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


def _member_of(conn, conversation_id: str, user_id: str) -> None:
    if not conn.execute(select(db.conversation_members).where(db.conversation_members.c.conversation_id == conversation_id,
                                                              db.conversation_members.c.user_id == user_id)).first():
        raise HTTPException(404, "Conversation not found.")


def _other_member(conn, conversation_id: str, user_id: str) -> str | None:
    return conn.execute(select(db.conversation_members.c.user_id).where(db.conversation_members.c.conversation_id == conversation_id,
                                                                        db.conversation_members.c.user_id != user_id)).scalar()


@router.post("/conversations")
def open_conversation(payload: ConversationIn, user: CurrentUser = Depends(current_user)):
    with db.transaction() as conn:
        target = _user_by_handle(conn, payload.handle)
        if target.id == user.id or target.id in blocked_ids(conn, user.id):
            raise HTTPException(422, "You can't message this member.")
        if target.message_policy != "everyone" and not are_connected(conn, user.id, target.id):
            accepted_collab = conn.execute(select(db.collab_requests.c.id).join(db.startups, db.startups.c.id == db.collab_requests.c.startup_id)
                                           .where(db.collab_requests.c.status == "accepted", or_(
                                               and_(db.collab_requests.c.user_id == user.id, db.startups.c.owner_id == target.id),
                                               and_(db.collab_requests.c.user_id == target.id, db.startups.c.owner_id == user.id)))).first()
            if not accepted_collab:
                raise HTTPException(403, "This member only accepts messages from connections. Send a connection request first.")
        pair = ":".join(sorted([user.id, target.id]))
        existing = conn.execute(select(db.conversations.c.id).where(db.conversations.c.pair_key == pair)).scalar()
        if existing:
            return {"id": existing}
        conversation_id = new_id()
        now = utcnow()
        conn.execute(insert(db.conversations).values(id=conversation_id, pair_key=pair, created_at=now, updated_at=now))
        for member in (user.id, target.id):
            conn.execute(insert(db.conversation_members).values(conversation_id=conversation_id, user_id=member, last_read_at=None))
    return {"id": conversation_id}


@router.get("/conversations")
def conversations(user: CurrentUser = Depends(current_user)):
    with db.read() as conn:
        memberships = conn.execute(select(db.conversation_members).where(db.conversation_members.c.user_id == user.id)).fetchall()
        out = []
        blocked = blocked_ids(conn, user.id)
        for m in memberships:
            other = _other_member(conn, m.conversation_id, user.id)
            if other in blocked:
                continue
            last = conn.execute(select(db.messages).where(db.messages.c.conversation_id == m.conversation_id)
                                .order_by(desc(db.messages.c.created_at)).limit(1)).first()
            unread_q = select(func.count()).select_from(db.messages).where(db.messages.c.conversation_id == m.conversation_id,
                                                                           db.messages.c.sender_id != user.id)
            if m.last_read_at:
                unread_q = unread_q.where(db.messages.c.created_at > m.last_read_at)
            out.append({"id": m.conversation_id, "with": users_by_id(conn, [other]).get(other),
                        "last_message": {"body": last.body[:140], "created_at": iso(last.created_at),
                                         "from_me": last.sender_id == user.id} if last else None,
                        "unread": conn.execute(unread_q).scalar_one(), "_sort": as_dt(last.created_at if last else None)})
    out.sort(key=lambda c: c.pop("_sort"), reverse=True)
    return {"conversations": out}


@router.get("/conversations/{conversation_id}/messages")
def conversation_messages(conversation_id: str, after: str | None = Query(None, max_length=40), user: CurrentUser = Depends(current_user)):
    with db.transaction() as conn:
        _member_of(conn, conversation_id, user.id)
        stmt = select(db.messages).where(db.messages.c.conversation_id == conversation_id)
        rows = conn.execute(stmt.order_by(desc(db.messages.c.created_at)).limit(200)).fetchall()[::-1]
        if after:
            rows = [r for r in rows if (iso(r.created_at) or "") > after]
        conn.execute(update(db.conversation_members).where(db.conversation_members.c.conversation_id == conversation_id,
                                                           db.conversation_members.c.user_id == user.id).values(last_read_at=utcnow()))
        other = _other_member(conn, conversation_id, user.id)
        return {"with": users_by_id(conn, [other]).get(other),
                "messages": [{"id": r.id, "body": r.body, "from_me": r.sender_id == user.id, "created_at": iso(r.created_at)} for r in rows]}


@router.post("/conversations/{conversation_id}/messages", status_code=201)
def send_message(conversation_id: str, payload: MessageIn, user: CurrentUser = Depends(current_user)):
    ratelimit.hit("write", user.id)
    body = clean_text(payload.body, 4000)
    if not body:
        raise HTTPException(422, "Message is empty.")
    with db.transaction() as conn:
        _member_of(conn, conversation_id, user.id)
        other = _other_member(conn, conversation_id, user.id)
        if other in blocked_ids(conn, user.id):
            raise HTTPException(403, "You can't message this member.")
        now = utcnow()
        message_id = new_id()
        conn.execute(insert(db.messages).values(id=message_id, conversation_id=conversation_id, sender_id=user.id, body=body, created_at=now))
        conn.execute(update(db.conversations).where(db.conversations.c.id == conversation_id).values(updated_at=now))
        conn.execute(update(db.conversation_members).where(db.conversation_members.c.conversation_id == conversation_id,
                                                           db.conversation_members.c.user_id == user.id).values(last_read_at=now))
        recent = conn.execute(select(func.count()).select_from(db.notifications).where(
            db.notifications.c.user_id == other, db.notifications.c.type == "message",
            db.notifications.c.entity_id == conversation_id, db.notifications.c.read_at.is_(None))).scalar_one()
        if not recent:  # one unread notification per conversation, not one per message
            notify(conn, other, user.id, "message", "conversation", conversation_id, f"New message from {user.name}")
    return {"id": message_id, "body": body, "from_me": True, "created_at": iso(now)}


# ====================================================================== notifications
@router.get("/notifications")
def list_notifications(user: CurrentUser = Depends(current_user)):
    with db.read() as conn:
        rows = conn.execute(select(db.notifications).where(db.notifications.c.user_id == user.id)
                            .order_by(desc(db.notifications.c.created_at)).limit(60)).fetchall()
        actors = users_by_id(conn, [r.actor_id for r in rows])
    return {"notifications": [{"id": r.id, "type": r.type, "text": r.text, "entity_type": r.entity_type, "entity_id": r.entity_id,
                               "actor": actors.get(r.actor_id), "read": r.read_at is not None, "created_at": iso(r.created_at)}
                              for r in rows]}


@router.get("/notifications/unread-count")
def unread_count(user: CurrentUser = Depends(current_user)):
    with db.read() as conn:
        notes = conn.execute(select(func.count()).select_from(db.notifications).where(
            db.notifications.c.user_id == user.id, db.notifications.c.read_at.is_(None))).scalar_one()
    return {"notifications": notes}


class ReadIn(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=200)


@router.post("/notifications/read")
def mark_read(payload: ReadIn, user: CurrentUser = Depends(current_user)):
    with db.transaction() as conn:
        stmt = update(db.notifications).where(db.notifications.c.user_id == user.id, db.notifications.c.read_at.is_(None))
        if payload.ids:
            stmt = stmt.where(db.notifications.c.id.in_(payload.ids))
        conn.execute(stmt.values(read_at=utcnow()))
    return {"ok": True}


# ========================================================================= moderation
class ReportContentIn(BaseModel):
    entity_type: str = Field(pattern="^(post|comment|user|startup)$")
    entity_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(max_length=32)
    details: str = Field(default="", max_length=1000)


@router.post("/moderation/reports", status_code=201)
def report_content(payload: ReportContentIn, user: CurrentUser = Depends(current_user)):
    ratelimit.hit("write", user.id)
    if payload.reason not in REPORT_REASONS:
        raise HTTPException(422, "Choose a reason.")
    with db.transaction() as conn:
        conn.execute(insert(db.moderation_reports).values(id=new_id(), reporter_id=user.id, entity_type=payload.entity_type,
                                                          entity_id=payload.entity_id, reason=payload.reason,
                                                          details=clean_text(payload.details, 1000), status="open",
                                                          resolved_by=None, created_at=utcnow(), resolved_at=None))
    return {"ok": True, "message": "Thanks — a moderator will review this."}


@router.get("/moderation/reports")
def moderation_queue(status: str = Query("open", pattern="^(open|actioned|dismissed)$"), user: CurrentUser = Depends(admin_user)):
    with db.read() as conn:
        rows = conn.execute(select(db.moderation_reports).where(db.moderation_reports.c.status == status)
                            .order_by(desc(db.moderation_reports.c.created_at)).limit(100)).fetchall()
        reporters = users_by_id(conn, [r.reporter_id for r in rows])
        items = []
        for r in rows:
            preview = ""
            if r.entity_type == "post":
                p = conn.execute(select(db.posts.c.title, db.posts.c.body).where(db.posts.c.id == r.entity_id)).first()
                preview = f"{p.title} {p.body}".strip()[:300] if p else "(deleted)"
            elif r.entity_type == "comment":
                c = conn.execute(select(db.comments.c.body).where(db.comments.c.id == r.entity_id)).first()
                preview = c.body[:300] if c else "(deleted)"
            items.append({"id": r.id, "entity_type": r.entity_type, "entity_id": r.entity_id, "reason": r.reason,
                          "details": r.details, "preview": preview, "reporter": reporters.get(r.reporter_id),
                          "created_at": iso(r.created_at)})
    return {"reports": items}


class ResolveIn(BaseModel):
    action: str = Field(pattern="^(hide|dismiss)$")


@router.post("/moderation/reports/{report_id}/resolve")
def resolve(report_id: str, payload: ResolveIn, user: CurrentUser = Depends(admin_user)):
    with db.transaction() as conn:
        r = conn.execute(select(db.moderation_reports).where(db.moderation_reports.c.id == report_id)).first()
        if r is None:
            raise HTTPException(404, "Not found.")
        if payload.action == "hide":
            if r.entity_type == "post":
                conn.execute(update(db.posts).where(db.posts.c.id == r.entity_id).values(hidden=True))
            elif r.entity_type == "comment":
                conn.execute(update(db.comments).where(db.comments.c.id == r.entity_id).values(hidden=True))
            elif r.entity_type == "startup":
                conn.execute(update(db.startups).where(db.startups.c.id == r.entity_id).values(visibility="private"))
        conn.execute(update(db.moderation_reports).where(or_(
            db.moderation_reports.c.id == report_id,
            and_(db.moderation_reports.c.entity_id == r.entity_id, db.moderation_reports.c.status == "open"))).values(
            status="actioned" if payload.action == "hide" else "dismissed", resolved_by=user.id, resolved_at=utcnow()))
    return {"ok": True}


# ============================================================================= search
@router.get("/search")
def search_all(q: str = Query(..., min_length=2, max_length=80), user: CurrentUser = Depends(current_user)):
    like = f"%{q.lower()}%"
    with db.read() as conn:
        blocked = blocked_ids(conn, user.id)
        following = following_ids(conn, user.id)
        users = [r for r in conn.execute(select(db.users).where(or_(
            func.lower(db.users.c.name).like(like), func.lower(db.users.c.handle).like(like),
            func.lower(db.users.c.headline).like(like))).limit(10)).fetchall() if r.id not in blocked]
        post_rows = conn.execute(select(db.posts).where(db.posts.c.hidden.is_(False), or_(
            func.lower(db.posts.c.title).like(like), func.lower(db.posts.c.body).like(like)))
            .order_by(desc(db.posts.c.created_at)).limit(20)).fetchall()
        post_rows = [r for r in post_rows if can_view_post(r, user.id, following, blocked)]
        startups = conn.execute(select(db.startups).where(db.startups.c.visibility == "public", or_(
            func.lower(db.startups.c.name).like(like), func.lower(db.startups.c.tagline).like(like)))).fetchall()
        comms = conn.execute(select(db.communities).where(or_(func.lower(db.communities.c.name).like(like),
                                                              func.lower(db.communities.c.description).like(like)))).fetchall()
        return {"users": [user_brief(r) for r in users], "posts": serialize_posts(conn, post_rows, user.id),
                "startups": [_startup_brief(s) for s in startups if s.owner_id not in blocked][:10],
                "communities": [{"slug": c.slug, "name": c.name, "member_count": c.member_count} for c in comms]}


# ======================================================================== AI helpers
class ImproveIn(BaseModel):
    title: str = Field(default="", max_length=200)
    body: str = Field(min_length=20, max_length=5000)


_IMPROVE_SCHEMA = llm.obj({
    "clarity_score": llm.S("integer"),
    "strengths": llm.arr(llm.S("string")),
    "missing": llm.arr(llm.S("string")),
    "questions_readers_will_ask": llm.arr(llm.S("string")),
    "suggested_title": llm.S("string"),
    "suggested_body": llm.S("string"),
    "confidentiality_warnings": llm.arr(llm.S("string")),
})


@router.post("/ai/improve-idea")
def improve_idea(payload: ImproveIn, user: CurrentUser = Depends(current_user)):
    """Help a founder improve a public idea post before publishing (nothing is posted automatically)."""
    if not llm.available():
        raise HTTPException(503, "The AI engine is not configured on this server.")
    ratelimit.hit("ai", user.id)
    ratelimit.consume_ai_quota(user.id, "social_ai")
    prompt = ("A founder wants to publish this startup idea on a professional founder network to get feedback and "
              "collaborators. Give concise, specific feedback. clarity_score 1-10. suggested_body: an improved version in "
              "the founder's voice, max 180 words, no hype, no invented facts or numbers. confidentiality_warnings: anything "
              "they may not want to share publicly (customer names, revenue, unreleased IP).\n\n"
              f"TITLE: {payload.title}\nPOST:\n{payload.body}")
    try:
        result = llm.generate_json(prompt, schema=_IMPROVE_SCHEMA, temperature=0.4, max_output_tokens=1500, profile="fast")
    except llm.LLMUnavailable:
        raise HTTPException(503, "The AI engine is temporarily unavailable. Please try again later.")
    return {**result.data, "model": result.model}


_SUMMARY_SCHEMA = llm.obj({
    "summary": llm.S("string"),
    "key_points": llm.arr(llm.S("string")),
    "open_questions": llm.arr(llm.S("string")),
    "sentiment": llm.enum(["supportive", "mixed", "critical", "neutral"]),
})


@router.post("/posts/{post_id}/summarize")
def summarize_discussion(post_id: str, user: CurrentUser = Depends(current_user)):
    with db.read() as conn:
        post = get_post_or_404(conn, post_id, user.id)
        if post.ai_summary and post.ai_summary.get("comment_count") == post.comment_count:
            return post.ai_summary
        if post.comment_count < 3:
            raise HTTPException(422, "Summaries are available once a discussion has at least 3 comments.")
        rows = conn.execute(select(db.comments).where(db.comments.c.post_id == post_id, db.comments.c.hidden.is_(False))
                            .order_by(db.comments.c.created_at).limit(150)).fetchall()
        authors = users_by_id(conn, [r.author_id for r in rows])
    if not llm.available():
        raise HTTPException(503, "The AI engine is not configured on this server.")
    ratelimit.hit("ai", user.id)
    ratelimit.consume_ai_quota(user.id, "social_ai")
    thread = "\n".join(f"- {authors.get(r.author_id, {}).get('name', 'member')}: {r.body[:500]}" for r in rows)
    prompt = (f"Summarize this founder-network discussion faithfully. Only use what participants wrote.\n\nPOST: {post.title}\n"
              f"{post.body[:2000]}\n\nCOMMENTS:\n{thread}")
    try:
        result = llm.generate_json(prompt, schema=_SUMMARY_SCHEMA, temperature=0.2, max_output_tokens=1200, profile="fast")
    except llm.LLMUnavailable:
        raise HTTPException(503, "The AI engine is temporarily unavailable. Please try again later.")
    summary = {**result.data, "model": result.model, "comment_count": post.comment_count, "generated_at": iso(utcnow())}
    with db.transaction() as conn:
        conn.execute(update(db.posts).where(db.posts.c.id == post_id).values(ai_summary=summary))
    return summary
