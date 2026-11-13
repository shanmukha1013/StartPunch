from __future__ import annotations

import re
import secrets
import unicodedata
from datetime import datetime, timezone
from typing import Any, Iterable

_ID_ALPHABET = "abcdefghijkmnopqrstuvwxyz23456789"


def new_id(length: int = 14) -> str:
    return "".join(secrets.choice(_ID_ALPHABET) for _ in range(length))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:  # SQLite returns naive datetimes
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def clean_text(value: Any, max_len: int | None = None) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]", "", text)
    text = text.strip()
    if max_len is not None:
        text = text[:max_len]
    return text


def clean_list(values: Iterable[Any] | None, max_items: int = 20, max_len: int = 40) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        item = clean_text(value, max_len)
        key = item.lower()
        if item and key not in seen:
            seen.add(key)
            out.append(item)
        if len(out) >= max_items:
            break
    return out


HASHTAG_RE = re.compile(r"(?<![\w#])#([A-Za-z][A-Za-z0-9_]{1,30})")


def extract_hashtags(text: str) -> list[str]:
    return clean_list((tag.lower() for tag in HASHTAG_RE.findall(text or "")), max_items=10, max_len=31)


def slugify(value: str, max_len: int = 32) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^a-zA-Z0-9]+", "", value).lower()
    return value[:max_len]


def truncate(text: str, n: int) -> str:
    text = text or ""
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"
