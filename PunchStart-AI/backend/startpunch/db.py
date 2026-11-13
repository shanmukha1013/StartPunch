"""Database schema and engine (SQLAlchemy Core).

SQLite is used for local development; Postgres (via the pure-Python pg8000 driver)
in production. The schema only uses portable column types.
"""
from __future__ import annotations

import logging
import ssl
import threading
from contextlib import contextmanager
from typing import Iterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    insert,
    select,
)
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.pool import NullPool

from .config import get_settings

logger = logging.getLogger("startpunch.db")
metadata = MetaData()

ID = lambda: String(24)  # noqa: E731 - short random string ids (not enumerable)


def _ts(name: str, nullable: bool = False) -> Column:
    return Column(name, DateTime(timezone=True), nullable=nullable)


users = Table(
    "users", metadata,
    Column("id", ID(), primary_key=True),
    Column("email", String(254), nullable=False, unique=True),
    Column("password_hash", String(255), nullable=False),
    Column("handle", String(32), nullable=False, unique=True),
    Column("name", String(80), nullable=False),
    Column("headline", String(140), nullable=False, default=""),
    Column("bio", Text, nullable=False, default=""),
    Column("location", String(80), nullable=False, default=""),
    Column("avatar_media_id", ID(), nullable=True),
    Column("cover_media_id", ID(), nullable=True),
    Column("skills", JSON, nullable=False, default=list),
    Column("interests", JSON, nullable=False, default=list),
    Column("industries", JSON, nullable=False, default=list),
    Column("looking_for", JSON, nullable=False, default=list),
    Column("open_to", JSON, nullable=False, default=list),
    Column("links", JSON, nullable=False, default=dict),
    Column("achievements", JSON, nullable=False, default=list),
    Column("role", String(16), nullable=False, default="member"),
    Column("profile_visibility", String(16), nullable=False, default="public"),
    Column("message_policy", String(16), nullable=False, default="connections"),
    Column("token_version", Integer, nullable=False, default=0),
    Column("follower_count", Integer, nullable=False, default=0),
    Column("following_count", Integer, nullable=False, default=0),
    _ts("created_at"),
    _ts("updated_at"),
)

media = Table(
    "media", metadata,
    Column("id", ID(), primary_key=True),
    Column("owner_id", ID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("content_type", String(40), nullable=False),
    Column("size", Integer, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("data", LargeBinary, nullable=False),
    _ts("created_at"),
)

# ---------------------------------------------------------------- intelligence
reports = Table(
    "reports", metadata,
    Column("id", ID(), primary_key=True),
    Column("user_id", ID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("title", String(120), nullable=False),
    Column("status", String(16), nullable=False, default="queued"),
    Column("stage", String(32), nullable=False, default="understand"),
    Column("progress", Integer, nullable=False, default=0),
    Column("input", JSON, nullable=False),
    Column("state", JSON, nullable=False, default=dict),
    Column("result", JSON, nullable=True),
    Column("error", Text, nullable=True),
    Column("engine_version", String(32), nullable=False, default=""),
    Column("legacy", Boolean, nullable=False, default=False),
    Column("lock_until", DateTime(timezone=True), nullable=True),
    _ts("created_at"),
    _ts("updated_at"),
    _ts("completed_at", nullable=True),
)
Index("ix_reports_user_created", reports.c.user_id, reports.c.created_at)

report_messages = Table(
    "report_messages", metadata,
    Column("id", ID(), primary_key=True),
    Column("report_id", ID(), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False),
    Column("user_id", ID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("role", String(12), nullable=False),
    Column("content", Text, nullable=False),
    Column("meta", JSON, nullable=False, default=dict),
    _ts("created_at"),
)
Index("ix_report_messages_report", report_messages.c.report_id, report_messages.c.created_at)

validation_items = Table(
    "validation_items", metadata,
    Column("id", ID(), primary_key=True),
    Column("report_id", ID(), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False),
    Column("user_id", ID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("title", String(200), nullable=False),
    Column("hypothesis", Text, nullable=False, default=""),
    Column("method", Text, nullable=False, default=""),
    Column("success_metric", Text, nullable=False, default=""),
    Column("status", String(16), nullable=False, default="todo"),
    Column("notes", Text, nullable=False, default=""),
    _ts("created_at"),
    _ts("updated_at"),
)

watchlist = Table(
    "watchlist", metadata,
    Column("id", ID(), primary_key=True),
    Column("user_id", ID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("company_id", String(64), nullable=False),
    Column("name", String(160), nullable=False),
    Column("report_id", ID(), nullable=True),
    Column("note", Text, nullable=False, default=""),
    _ts("created_at"),
    UniqueConstraint("user_id", "company_id", name="uq_watch_user_company"),
)

ai_usage = Table(
    "ai_usage", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", ID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("kind", String(32), nullable=False),
    _ts("created_at"),
)
Index("ix_ai_usage_user_created", ai_usage.c.user_id, ai_usage.c.created_at)

# ---------------------------------------------------------------- social graph
follows = Table(
    "follows", metadata,
    Column("follower_id", ID(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("followee_id", ID(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    _ts("created_at"),
)
Index("ix_follows_followee", follows.c.followee_id)

blocks = Table(
    "blocks", metadata,
    Column("blocker_id", ID(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("blocked_id", ID(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    _ts("created_at"),
)

connections = Table(
    "connections", metadata,
    Column("id", ID(), primary_key=True),
    Column("requester_id", ID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("addressee_id", ID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("status", String(12), nullable=False, default="pending"),
    Column("message", String(300), nullable=False, default=""),
    _ts("created_at"),
    _ts("responded_at", nullable=True),
    UniqueConstraint("requester_id", "addressee_id", name="uq_connection_pair"),
)

communities = Table(
    "communities", metadata,
    Column("id", ID(), primary_key=True),
    Column("slug", String(48), nullable=False, unique=True),
    Column("name", String(80), nullable=False),
    Column("description", Text, nullable=False, default=""),
    Column("tags", JSON, nullable=False, default=list),
    Column("member_count", Integer, nullable=False, default=0),
    Column("post_count", Integer, nullable=False, default=0),
    Column("created_by", ID(), nullable=True),
    _ts("created_at"),
)

community_members = Table(
    "community_members", metadata,
    Column("community_id", ID(), ForeignKey("communities.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", ID(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role", String(12), nullable=False, default="member"),
    _ts("joined_at"),
)
Index("ix_community_members_user", community_members.c.user_id)

startups = Table(
    "startups", metadata,
    Column("id", ID(), primary_key=True),
    Column("owner_id", ID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("name", String(100), nullable=False),
    Column("tagline", String(160), nullable=False, default=""),
    Column("description", Text, nullable=False, default=""),
    Column("problem", Text, nullable=False, default=""),
    Column("solution", Text, nullable=False, default=""),
    Column("industry", String(60), nullable=False, default=""),
    Column("stage", String(40), nullable=False, default=""),
    Column("website", String(300), nullable=False, default=""),
    Column("looking_for", JSON, nullable=False, default=list),
    Column("tags", JSON, nullable=False, default=list),
    Column("visibility", String(12), nullable=False, default="private"),
    Column("allow_ai_analysis", Boolean, nullable=False, default=False),
    Column("report_id", ID(), nullable=True),
    Column("public_summary", JSON, nullable=False, default=dict),
    Column("follower_count", Integer, nullable=False, default=0),
    _ts("created_at"),
    _ts("updated_at"),
)
Index("ix_startups_owner", startups.c.owner_id)

startup_follows = Table(
    "startup_follows", metadata,
    Column("startup_id", ID(), ForeignKey("startups.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", ID(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    _ts("created_at"),
)

collab_requests = Table(
    "collab_requests", metadata,
    Column("id", ID(), primary_key=True),
    Column("startup_id", ID(), ForeignKey("startups.id", ondelete="CASCADE"), nullable=False),
    Column("user_id", ID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("role", String(60), nullable=False, default=""),
    Column("message", Text, nullable=False, default=""),
    Column("status", String(12), nullable=False, default="pending"),
    _ts("created_at"),
    _ts("responded_at", nullable=True),
    UniqueConstraint("startup_id", "user_id", name="uq_collab_once"),
)

posts = Table(
    "posts", metadata,
    Column("id", ID(), primary_key=True),
    Column("author_id", ID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("kind", String(16), nullable=False, default="post"),
    Column("title", String(200), nullable=False, default=""),
    Column("body", Text, nullable=False, default=""),
    Column("media_ids", JSON, nullable=False, default=list),
    Column("link_url", String(500), nullable=False, default=""),
    Column("video_url", String(500), nullable=False, default=""),
    Column("tags", JSON, nullable=False, default=list),
    Column("community_id", ID(), ForeignKey("communities.id", ondelete="SET NULL"), nullable=True),
    Column("startup_id", ID(), ForeignKey("startups.id", ondelete="SET NULL"), nullable=True),
    Column("repost_of_id", ID(), ForeignKey("posts.id", ondelete="SET NULL"), nullable=True),
    Column("visibility", String(12), nullable=False, default="public"),
    Column("hidden", Boolean, nullable=False, default=False),
    Column("like_count", Integer, nullable=False, default=0),
    Column("comment_count", Integer, nullable=False, default=0),
    Column("repost_count", Integer, nullable=False, default=0),
    Column("bookmark_count", Integer, nullable=False, default=0),
    Column("ai_summary", JSON, nullable=True),
    _ts("created_at"),
    _ts("updated_at"),
)
Index("ix_posts_created", posts.c.created_at)
Index("ix_posts_author", posts.c.author_id, posts.c.created_at)
Index("ix_posts_community", posts.c.community_id, posts.c.created_at)

comments = Table(
    "comments", metadata,
    Column("id", ID(), primary_key=True),
    Column("post_id", ID(), ForeignKey("posts.id", ondelete="CASCADE"), nullable=False),
    Column("author_id", ID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("parent_id", ID(), ForeignKey("comments.id", ondelete="CASCADE"), nullable=True),
    Column("body", Text, nullable=False),
    Column("hidden", Boolean, nullable=False, default=False),
    _ts("created_at"),
)
Index("ix_comments_post", comments.c.post_id, comments.c.created_at)

post_likes = Table(
    "post_likes", metadata,
    Column("post_id", ID(), ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", ID(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    _ts("created_at"),
)

bookmarks = Table(
    "bookmarks", metadata,
    Column("post_id", ID(), ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", ID(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    _ts("created_at"),
)

notifications = Table(
    "notifications", metadata,
    Column("id", ID(), primary_key=True),
    Column("user_id", ID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("actor_id", ID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
    Column("type", String(32), nullable=False),
    Column("entity_type", String(24), nullable=False, default=""),
    Column("entity_id", String(64), nullable=False, default=""),
    Column("text", String(300), nullable=False, default=""),
    _ts("read_at", nullable=True),
    _ts("created_at"),
)
Index("ix_notifications_user", notifications.c.user_id, notifications.c.created_at)

conversations = Table(
    "conversations", metadata,
    Column("id", ID(), primary_key=True),
    Column("pair_key", String(60), nullable=False, unique=True),
    _ts("created_at"),
    _ts("updated_at"),
)

conversation_members = Table(
    "conversation_members", metadata,
    Column("conversation_id", ID(), ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", ID(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    _ts("last_read_at", nullable=True),
)
Index("ix_conversation_members_user", conversation_members.c.user_id)

messages = Table(
    "messages", metadata,
    Column("id", ID(), primary_key=True),
    Column("conversation_id", ID(), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
    Column("sender_id", ID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("body", Text, nullable=False),
    _ts("created_at"),
)
Index("ix_messages_conversation", messages.c.conversation_id, messages.c.created_at)

moderation_reports = Table(
    "moderation_reports", metadata,
    Column("id", ID(), primary_key=True),
    Column("reporter_id", ID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("entity_type", String(16), nullable=False),
    Column("entity_id", String(64), nullable=False),
    Column("reason", String(32), nullable=False),
    Column("details", Text, nullable=False, default=""),
    Column("status", String(12), nullable=False, default="open"),
    Column("resolved_by", ID(), nullable=True),
    _ts("created_at"),
    _ts("resolved_at", nullable=True),
)

schema_meta = Table(
    "schema_meta", metadata,
    Column("key", String(40), primary_key=True),
    Column("value", String(200), nullable=False),
)

SCHEMA_VERSION = "2"

# Structural communities (topic containers, not fake content or members).
DEFAULT_COMMUNITIES = [
    ("ai-ml", "AI & Machine Learning", "Building products with models, agents, data and ML infrastructure.", ["ai", "machine learning", "llm", "data"]),
    ("saas", "SaaS Startups", "B2B software, pricing, churn, product-led growth and sales.", ["saas", "b2b", "software"]),
    ("fintech", "FinTech", "Payments, lending, banking infrastructure, insurance and compliance.", ["fintech", "payments", "banking"]),
    ("edtech", "EdTech", "Learning products, outcomes, institutions and creators.", ["edtech", "education", "learning"]),
    ("healthtech", "HealthTech", "Care delivery, clinical workflows, wellness and regulation.", ["healthtech", "health", "medical"]),
    ("ecommerce", "E-commerce", "D2C brands, marketplaces, retail tech and logistics.", ["ecommerce", "retail", "d2c", "marketplace"]),
    ("web3", "Web3", "Crypto, blockchain infrastructure and decentralized apps.", ["web3", "crypto", "blockchain"]),
    ("content-creation", "Content Creation", "Creators, media businesses, audiences and monetization.", ["creator", "content", "media"]),
    ("product", "Product Development", "Discovery, design, MVPs, roadmaps and shipping.", ["product", "design", "mvp", "ux"]),
    ("marketing", "Marketing", "Positioning, growth loops, acquisition channels and brand.", ["marketing", "growth", "seo", "brand"]),
    ("fundraising", "Fundraising", "Pitching, investors, rounds, terms and runway.", ["fundraising", "investors", "venture", "pitch"]),
    ("entrepreneurship", "Entrepreneurship", "Founder life, co-founders, hiring, focus and decisions.", ["founders", "startup", "entrepreneurship"]),
]

_engine: Engine | None = None
_engine_lock = threading.Lock()
_initialized = False


class DatabaseNotConfigured(RuntimeError):
    pass


def _pg_connect_args(url: str) -> tuple[str, dict]:
    """pg8000 does not understand libpq's sslmode/channel_binding query params."""
    parts = urlsplit(url)
    params = dict(parse_qsl(parts.query))
    sslmode = params.pop("sslmode", None)
    params.pop("channel_binding", None)
    connect_args: dict = {}
    host = parts.hostname or ""
    if sslmode in {"require", "verify-ca", "verify-full"} or (sslmode is None and host not in {"localhost", "127.0.0.1"}):
        connect_args["ssl_context"] = ssl.create_default_context()
    clean = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), parts.fragment))
    return clean, connect_args


def get_engine() -> Engine:
    global _engine
    if _engine is not None:
        return _engine
    with _engine_lock:
        if _engine is not None:
            return _engine
        settings = get_settings()
        if not settings.database_url:
            raise DatabaseNotConfigured(
                "DATABASE_URL is not configured. Set a Postgres connection string in the deployment environment."
            )
        url = settings.database_url
        kwargs: dict = {"future": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        else:
            url, connect_args = _pg_connect_args(url)
            kwargs["connect_args"] = connect_args
            kwargs["pool_pre_ping"] = True
            if settings.on_vercel:
                kwargs["poolclass"] = NullPool
            else:
                kwargs["pool_size"] = 5
                kwargs["max_overflow"] = 5
        engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):
            @event.listens_for(engine, "connect")
            def _sqlite_pragmas(dbapi_connection, _record):  # pragma: no cover - trivial
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.close()
        _engine = engine
        return engine


def init_db() -> None:
    """Create tables (idempotent) and seed structural communities."""
    global _initialized
    if _initialized:
        return
    engine = get_engine()
    metadata.create_all(engine)
    from .utils import new_id, utcnow  # local import to avoid cycle

    with engine.begin() as conn:
        existing = {row.slug for row in conn.execute(select(communities.c.slug))}
        for slug, name, description, tags in DEFAULT_COMMUNITIES:
            if slug not in existing:
                conn.execute(insert(communities).values(
                    id=new_id(), slug=slug, name=name, description=description, tags=tags,
                    member_count=0, post_count=0, created_by=None, created_at=utcnow(),
                ))
        version = conn.execute(select(schema_meta.c.value).where(schema_meta.c.key == "schema_version")).scalar()
        if version is None:
            conn.execute(insert(schema_meta).values(key="schema_version", value=SCHEMA_VERSION))
    _initialized = True
    logger.info("Database ready (%s)", engine.dialect.name)


def reset_for_tests(url: str) -> None:
    """Point the module at a fresh database (tests only)."""
    global _engine, _initialized
    if _engine is not None:
        _engine.dispose()
    _engine = create_engine(url, future=True, connect_args={"check_same_thread": False})

    @event.listens_for(_engine, "connect")
    def _fk(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    _initialized = False
    init_db()


@contextmanager
def transaction() -> Iterator[Connection]:
    init_db()
    with get_engine().begin() as conn:
        yield conn


@contextmanager
def read() -> Iterator[Connection]:
    init_db()
    with get_engine().connect() as conn:
        yield conn
