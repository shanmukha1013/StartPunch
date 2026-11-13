"""Rate limiting.

* Burst limits: in-memory sliding windows per client key (per process; on serverless each
  instance keeps its own window, so these are a first line of defence only).
* Expensive AI work: durable per-user daily quotas counted in the database (``ai_usage``),
  which hold across instances.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from datetime import timedelta

from fastapi import HTTPException, Request
from sqlalchemy import func, insert, select

from . import db
from .config import get_settings
from .utils import utcnow

_windows: dict[str, deque[float]] = defaultdict(deque)
_lock = threading.Lock()

LIMITS = {
    "auth": (10, 60),          # 10 attempts per minute per IP
    "write": (40, 60),         # posts/comments/likes per minute per user
    "ai": (12, 60),            # AI calls per minute per user
    "upload": (12, 300),
    "default": (240, 60),
}


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def hit(bucket: str, key: str) -> None:
    limit, window = LIMITS.get(bucket, LIMITS["default"])
    now = time.monotonic()
    full_key = f"{bucket}:{key}"
    with _lock:
        q = _windows[full_key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            retry = int(window - (now - q[0])) + 1
            raise HTTPException(429, f"Too many requests. Try again in {retry} seconds.", headers={"Retry-After": str(retry)})
        q.append(now)
        if len(_windows) > 50_000:  # bound memory
            for stale in list(_windows)[:10_000]:
                _windows.pop(stale, None)


def reset() -> None:
    with _lock:
        _windows.clear()


def consume_ai_quota(user_id: str, kind: str) -> None:
    """Durable daily quota for model-backed operations."""
    settings = get_settings()
    quota = settings.daily_report_quota if kind == "report" else settings.daily_ai_quota
    since = utcnow() - timedelta(days=1)
    with db.transaction() as conn:
        used = conn.execute(
            select(func.count()).select_from(db.ai_usage)
            .where(db.ai_usage.c.user_id == user_id, db.ai_usage.c.kind == kind, db.ai_usage.c.created_at >= since)
        ).scalar_one()
        if used >= quota:
            raise HTTPException(429, f"Daily limit reached for this AI feature ({quota} per 24 hours).")
        conn.execute(insert(db.ai_usage).values(user_id=user_id, kind=kind, created_at=utcnow()))
