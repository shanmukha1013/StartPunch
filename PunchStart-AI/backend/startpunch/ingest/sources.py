"""Source connectors for the knowledge base.

All data comes from the official, public Hacker News Search API (hn.algolia.com), which
is offered for programmatic use without credentials. Content belongs to its authors; we
store short excerpts with a permanent link back to the original discussion and always
display that link as the citation.

| Stream        | Query                                     | What it represents                              |
|---------------|-------------------------------------------|-------------------------------------------------|
| hn_launch     | "Launch HN" stories                        | Founder-written launches of early-stage startups (mostly YC) |
| hn_show       | "Show HN" stories with >= 100 points       | Product launches that drew community attention   |
| hn_shutdown   | shutdown / post-mortem stories            | Public shutdown announcements and post-mortems    |

Raw responses are cached under ``backend/data/raw`` (git-ignored) so builds are reproducible.
"""
from __future__ import annotations

import gzip
import html
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import httpx

from ..config import BACKEND_DIR, get_settings
from ..utils import utcnow

logger = logging.getLogger("startpunch.ingest")
RAW_DIR = BACKEND_DIR / "data" / "raw"
HN_API = "https://hn.algolia.com/api/v1/search_by_date"

SOURCE_REGISTRY: dict[str, dict[str, Any]] = {
    "hn_launch": {
        "name": "Hacker News — Launch HN",
        "url": "https://news.ycombinator.com/launches",
        "license": "Public HN Search API; excerpts © original authors, always linked to the source thread",
        "description": "Founder-written launch announcements of early-stage startups (mostly Y Combinator companies).",
        "queries": [{"query": '"Launch HN"', "min_points": 0, "title_prefix": "launch hn"}],
    },
    "hn_show": {
        "name": "Hacker News — Show HN (≥ 100 points)",
        "url": "https://news.ycombinator.com/show",
        "license": "Public HN Search API; excerpts © original authors, always linked to the source thread",
        "description": "Product launches that received at least 100 community upvotes. Includes side projects, not only companies.",
        "queries": [{"query": '"Show HN"', "min_points": 100, "title_prefix": "show hn"}],
    },
    "hn_shutdown": {
        "name": "Hacker News — shutdowns & post-mortems",
        "url": "https://news.ycombinator.com/",
        "license": "Public HN Search API; titles/excerpts © original authors, always linked to the source thread",
        "description": "Stories announcing a product or company shutting down, or a founder post-mortem.",
        "queries": [
            {"query": '"shutting down"', "min_points": 30},
            {"query": '"shut down"', "min_points": 60},
            {"query": "post-mortem", "min_points": 20},
            {"query": "postmortem", "min_points": 20},
            {"query": '"why we failed"', "min_points": 10},
            {"query": '"startup failed"', "min_points": 10},
            {"query": '"lessons from"  startup failure', "min_points": 10},
        ],
    },
}


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": get_settings().ingest_user_agent},
        timeout=httpx.Timeout(60.0, connect=15.0),
        follow_redirects=True,
    )


def _cache_path(name: str) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    return RAW_DIR / f"{name}.json.gz"


def _save(name: str, payload: Any) -> None:
    with gzip.open(_cache_path(name), "wt", encoding="utf-8") as handle:
        json.dump(payload, handle)


def _load(name: str) -> Any | None:
    path = _cache_path(name)
    if not path.exists():
        return None
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


_TAG_RE = re.compile(r"<[^>]+>")


def html_to_text(value: str) -> str:
    value = re.sub(r"<p>", "\n\n", value or "", flags=re.I)
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = _TAG_RE.sub("", value)
    value = html.unescape(value)
    return re.sub(r"[ \t]+", " ", value).strip()


def _hit(hit: dict) -> dict:
    return {
        "id": hit["objectID"], "title": hit.get("title") or "", "url": hit.get("url"),
        "story_text": hit.get("story_text") or "", "points": hit.get("points") or 0,
        "num_comments": hit.get("num_comments") or 0, "created_at": hit.get("created_at"),
        "created_at_i": hit.get("created_at_i"),
    }


def _paginate(client: httpx.Client, query: str, min_points: int, title_prefix: str | None) -> dict[str, dict]:
    hits: dict[str, dict] = {}
    before: int | None = None
    for _ in range(60):
        filters = []
        if min_points:
            filters.append(f"points>={min_points}")
        if before:
            filters.append(f"created_at_i<{before}")
        params = {"query": query, "tags": "story", "hitsPerPage": 1000, "restrictSearchableAttributes": "title"}
        if filters:
            params["numericFilters"] = ",".join(filters)
        for attempt in range(4):
            try:
                response = client.get(HN_API, params=params)
                response.raise_for_status()
                batch = response.json().get("hits", [])
                break
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("hn query %r attempt %s failed: %s", query, attempt + 1, exc)
                time.sleep(3 * (attempt + 1))
        else:
            raise RuntimeError(f"HN API unavailable for query {query!r}")
        if not batch:
            break
        for item in batch:
            title = (item.get("title") or "").lower()
            if title_prefix and not title.startswith(title_prefix):
                continue
            hits[item["objectID"]] = _hit(item)
        before = min(item["created_at_i"] for item in batch)
        if len(batch) < 1000:
            break
        time.sleep(0.5)
    return hits


def fetch_stream(stream: str, refresh: bool = False) -> dict:
    cached = None if refresh else _load(stream)
    if cached:
        logger.info("%s: using cache (%s items)", stream, len(cached["hits"]))
        return cached
    spec = SOURCE_REGISTRY[stream]
    hits: dict[str, dict] = {}
    with _client() as client:
        for q in spec["queries"]:
            found = _paginate(client, q["query"], q.get("min_points", 0), q.get("title_prefix"))
            logger.info("%s %r: %s items", stream, q["query"], len(found))
            hits.update(found)
            time.sleep(0.5)
    payload = {"fetched_at": utcnow().isoformat(), "queries": spec["queries"], "hits": list(hits.values())}
    _save(stream, payload)
    return payload
