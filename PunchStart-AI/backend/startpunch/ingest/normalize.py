"""Cleaning, validation, normalization, de-duplication, entity resolution and chunking."""
from __future__ import annotations

import hashlib
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from ..utils import clean_text
from .sources import html_to_text

logger = logging.getLogger("startpunch.ingest")

_LEGAL_SUFFIX = re.compile(
    r"\b(incorporated|inc|corp|corporation|co|company|ltd|limited|llc|plc|gmbh|ag|sa|bv|nv|oy|ab|pty|pte|"
    r"technologies|technology|labs|holdings|group|hq|app|io)\b\.?", re.I)
_SEPARATOR = re.compile(r"\s+(?:[–—]|-{1,2}|\|)\s+|:\s+")
_LAUNCH_TITLE = re.compile(r"^launch hn:\s*(?P<rest>.+)$", re.I)
_SHOW_TITLE = re.compile(r"^show hn:\s*(?P<rest>.+)$", re.I)
_BATCH = re.compile(r"\((?P<batch>(?:yc|y combinator)\s*[^)]*)\)", re.I)
_URL_RE = re.compile(r"https?://[^\s\"'<>)]+", re.I)
_BLOCKED_DOMAINS = {"news.ycombinator.com", "ycombinator.com", "github.com", "youtube.com", "youtu.be", "loom.com",
                    "twitter.com", "x.com", "docs.google.com", "drive.google.com", "en.wikipedia.org", "apps.apple.com",
                    "play.google.com", "medium.com", "calendly.com", "news.google.com", "bit.ly", "imgur.com", "i.imgur.com",
                    "reddit.com", "linkedin.com", "facebook.com", "substack.com", "techcrunch.com", "nytimes.com",
                    "theverge.com", "bloomberg.com", "wsj.com", "reuters.com", "arstechnica.com", "blog.google",
                    "producthunt.com", "vimeo.com", "dropbox.com", "gist.github.com", "web.archive.org", "slideshare.net",
                    "chrome.google.com", "addons.mozilla.org", "itunes.apple.com", "failory.com", "indiehackers.com",
                    "notion.so", "notion.site", "gitlab.com", "bitbucket.org", "codepen.io", "jsfiddle.net", "glitch.me",
                    "herokuapp.com", "vercel.app", "netlify.app", "blogspot.com", "wordpress.com", "tumblr.com", "posterous.com"}
_PRONOUN_START = re.compile(r"^(i|we|my|our|a|an|the|this|how|what|why|open[- ]source|free)\b", re.I)
_SHUTDOWN_PATTERNS = [
    re.compile(r"^(?P<name>[^,:]{2,60}?)\s+(?:is|are|will be)\s+shutting down\b", re.I),
    re.compile(r"^(?P<name>[^,:]{2,60}?)\s+(?:is|are|will be)\s+(?:shut down|closing down|winding down)\b", re.I),
    re.compile(r"^(?:we(?:'re| are)\s+)?shutting down\s+(?P<name>[^,:.]{2,60})", re.I),
    re.compile(r"^(?P<name>[^,:]{2,60}?)\s*(?::|–|—|-)\s*(?:we(?:'re| are)\s+)?shutting down\b", re.I),
    re.compile(r"^(?:a\s+)?(?:post-?mortem|postmortem)\s*(?:of|for|:)\s*(?P<name>[^,.]{2,60})", re.I),
    re.compile(r"^(?P<name>[^,:]{2,60}?)\s*(?:'s)?\s*(?:post-?mortem|postmortem)\b", re.I),
    re.compile(r"^why\s+(?P<name>[^,]{2,60}?)\s+failed\b", re.I),
]
# Post-mortems about outages/security incidents are not startup failures.
_NOT_FAILURE = re.compile(r"outage|incident|vulnerab|security|breach|bug\b|downtime|cve-|compromise|attack|"
                          r"rollout|deploy|database migration|kernel|latency|dns\b|leak", re.I)
_BIG_TECH = re.compile(r"^(google|microsoft|apple|amazon|aws|meta|facebook|mozilla|yahoo|ibm|oracle|intel|adobe)\b", re.I)


def normalize_name(name: str) -> str:
    value = (name or "").lower().replace("&", " and ")
    value = _LEGAL_SUFFIX.sub(" ", value)
    return re.sub(r"[^a-z0-9]+", "", value)


def domain_of(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = (urlsplit(url.strip()).hostname or "").lower()
    except ValueError:
        return None
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _domains(hit: dict) -> list[str]:
    out: list[str] = []
    for url in [hit.get("url"), *_URL_RE.findall(html_to_text(hit.get("story_text") or ""))]:
        dom = domain_of((url or "").rstrip(".,;"))
        if dom and dom not in _BLOCKED_DOMAINS and not dom.endswith(("github.io", "ycombinator.com")) and dom not in out:
            out.append(dom)
    return out


@dataclass
class BuildReport:
    raw_items: Counter = field(default_factory=Counter)
    rejected: Counter = field(default_factory=Counter)
    resolved_by_domain: int = 0
    resolved_by_name: int = 0
    entities_created: Counter = field(default_factory=Counter)
    companies: int = 0
    chunks: int = 0

    def as_dict(self) -> dict:
        return {
            "raw_items": dict(self.raw_items), "rejected": dict(self.rejected),
            "resolved_by_domain": self.resolved_by_domain, "resolved_by_name": self.resolved_by_name,
            "entities_created": dict(self.entities_created), "companies": self.companies, "chunks": self.chunks,
        }


def _split_name(rest: str) -> tuple[str | None, str]:
    """'Acme (YC W21) – AI for invoices' -> ('Acme', 'AI for invoices')."""
    rest = _BATCH.sub("", rest).strip()
    parts = _SEPARATOR.split(rest, maxsplit=1)
    if len(parts) == 2:
        left, right = parts[0].strip(" -–—:"), parts[1].strip()
        if left and len(left.split()) <= 5 and not _PRONOUN_START.match(left) and len(right) >= 8:
            return left, right
    return None, rest


def _looks_like_name(name: str, max_words: int) -> bool:
    words = name.split()
    if not (2 <= len(name) <= 60) or len(words) > max_words or _PRONOUN_START.match(name):
        return False
    # Proper-noun-ish: starts with a capital/digit or is a domain (e.g. "MathB.in").
    return bool(re.match(r"^[A-Z0-9]", name) or re.search(r"\.[a-z]{2,}$", name))


def _parse_shutdown(title: str) -> str | None:
    if _NOT_FAILURE.search(title):
        return None
    for index, pattern in enumerate(_SHUTDOWN_PATTERNS):
        match = pattern.search(title)
        if match:
            name = match.group("name").strip(" '\"-–—:")
            name = re.sub(r"^(?:we(?:'re| are)\s+)?", "", name, flags=re.I)
            max_words = 3 if index >= 4 else 4  # post-mortem/"why X failed" titles are noisier
            if _looks_like_name(name, max_words):
                return name
    return None


class _Resolver:
    def __init__(self) -> None:
        self.companies: dict[str, dict] = {}
        self.by_domain: dict[str, str] = {}
        self.by_norm: dict[str, str] = {}

    def find(self, norm: str, domains: list[str], strict_domain: bool = False) -> tuple[str | None, str | None]:
        for dom in domains[:2]:
            if dom in self.by_domain:
                dom_norm = normalize_name(dom.split(".")[0])
                # Shutdown stories are often hosted on third-party blogs: only trust a domain
                # match when the parsed name agrees with the domain.
                if strict_domain and not (norm and (norm in dom_norm or dom_norm in norm)):
                    continue
                return self.by_domain[dom], "domain"
        if len(norm) >= 4 and norm in self.by_norm:
            return self.by_norm[norm], "name"
        return None, None

    def add(self, company: dict) -> None:
        self.companies[company["id"]] = company
        if company.get("domain"):
            self.by_domain.setdefault(company["domain"], company["id"])
        if len(company["norm"]) >= 4:
            self.by_norm.setdefault(company["norm"], company["id"])


def shutdown_candidates(payload: dict) -> list[dict]:
    """Loose pre-filter of shutdown/post-mortem stories for LLM verification."""
    out = []
    for hit in payload.get("hits", []):
        title = clean_text(hit.get("title"), 300)
        if _NOT_FAILURE.search(title) and not re.search(r"shutting down|shut down", title, re.I):
            continue
        if any(p.search(title) for p in _SHUTDOWN_PATTERNS):
            out.append({"id": hit["id"], "title": title,
                        "text": clean_text(html_to_text(hit.get("story_text") or ""), 400)})
    return out


def build_companies(streams: dict[str, dict], current_year: int,
                    shutdown_checks: dict[str, dict] | None = None) -> tuple[list[dict], BuildReport]:
    report = BuildReport()
    resolver = _Resolver()
    order = ["hn_launch", "hn_show", "hn_shutdown"]  # most reliable identities first

    for stream in order:
        payload = streams.get(stream) or {"hits": []}
        fetched_at = payload.get("fetched_at")
        for hit in sorted(payload["hits"], key=lambda h: h.get("created_at_i") or 0):
            report.raw_items[stream] += 1
            title = clean_text(hit.get("title"), 300)
            text = clean_text(html_to_text(hit.get("story_text") or ""), 4000)
            date = (hit.get("created_at") or "")[:10]
            if not date or int(date[:4]) > current_year:
                report.rejected["invalid_date"] += 1
                continue
            domains = _domains(hit)
            batch = None
            if stream == "hn_shutdown":
                check = (shutdown_checks or {}).get(hit["id"])
                if check is not None:
                    name = check.get("name", "").strip() if check.get("is_business_failure") else None
                    if not name:
                        report.rejected["shutdown_rejected_by_verification"] += 1
                        continue
                    name = _BATCH.sub("", name).strip()
                else:
                    name = _parse_shutdown(title)
                    if not name:
                        report.rejected["shutdown_unparseable_or_not_failure"] += 1
                        continue
                tagline = title
                kind = "shutdown"
            else:
                match = (_LAUNCH_TITLE if stream == "hn_launch" else _SHOW_TITLE).match(title)
                if not match:
                    report.rejected["unparseable_title"] += 1
                    continue
                rest = match.group("rest")
                bmatch = _BATCH.search(rest)
                batch = re.sub(r"(?i)y combinator", "YC", bmatch.group("batch")).upper().strip() if bmatch else None
                name, tagline = _split_name(rest)
                kind = "launch" if stream == "hn_launch" else "show"
                if not name and stream == "hn_launch":
                    name = rest.split("(")[0].strip()[:60]
                if not name:
                    # No explicit product name in the title: skip rather than invent an identity.
                    report.rejected["no_identifiable_name"] += 1
                    continue
            if len(text) < 60 and len(tagline) < 15:
                report.rejected["insufficient_text"] += 1
                continue
            norm = normalize_name(name)
            if len(norm) < 2:
                report.rejected["no_identifiable_name"] += 1
                continue
            document = {
                "hn_id": hit["id"], "kind": kind, "title": title, "tagline": clean_text(tagline, 240), "batch": batch,
                "date": date, "points": int(hit.get("points") or 0), "comments": int(hit.get("num_comments") or 0),
                "url": f"https://news.ycombinator.com/item?id={hit['id']}", "text": text[:1800], "link": hit.get("url"),
            }
            target, how = resolver.find(norm, domains, strict_domain=(kind == "shutdown"))
            if target and kind == "shutdown" and how == "name":
                existing = resolver.companies[target]
                if existing.get("first_seen", "") > date:  # shutdown before the launch we know: different entity
                    target = None
            if target:
                company = resolver.companies[target]
                if any(d["hn_id"] == document["hn_id"] for d in company["documents"]):
                    continue
                report.resolved_by_domain += how == "domain"
                report.resolved_by_name += how == "name"
                company["documents"].append(document)
                company["sources"].append({"source": stream, "url": document["url"], "date": date,
                                           "retrieved_at": fetched_at, "resolution": how})
                if batch and not company.get("batch"):
                    company["batch"] = batch
                if kind == "shutdown":
                    company["status"] = "shutdown_announced"
                    company["shutdown_date"] = date
                continue
            if kind == "shutdown" and _BIG_TECH.match(name):
                entity_type = "product"  # e.g. "Google Reader is shutting down"
            else:
                entity_type = {"launch": "startup", "show": "product", "shutdown": "company"}[kind]
            company = {
                "id": f"hn:{norm[:40]}", "name": name, "norm": norm, "entity_type": entity_type,
                "description": document["tagline"] if kind != "shutdown" else "",
                "website": f"https://{domains[0]}" if domains else None, "domain": domains[0] if domains else None,
                "batch": batch, "status": "shutdown_announced" if kind == "shutdown" else "launched",
                "first_seen": date, "shutdown_date": date if kind == "shutdown" else None,
                "sector": None, "sector_source": None, "documents": [document],
                "sources": [{"source": stream, "url": document["url"], "date": date, "retrieved_at": fetched_at, "resolution": "new",
                             **({"verified_by": shutdown_checks[hit["id"]].get("model")} if kind == "shutdown" and shutdown_checks and hit["id"] in shutdown_checks else {})}],
            }
            if company["id"] in resolver.companies:  # same normalized name, different identity
                company["id"] = f"hn:{norm[:32]}-{hit['id']}"
            resolver.add(company)
            report.entities_created[entity_type] += 1

    companies = list(resolver.companies.values())
    for company in companies:
        company["documents"].sort(key=lambda d: d["date"])
        launches = [d for d in company["documents"] if d["kind"] in {"launch", "show"}]
        company["first_launch"] = launches[0]["date"] if launches else None
        company["max_points"] = max(d["points"] for d in company["documents"])
        if not company["description"]:
            company["description"] = (launches[0]["tagline"] if launches else company["documents"][0]["tagline"])
    report.companies = len(companies)
    return companies, report


# ------------------------------------------------------------------------------- chunking
def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", text.strip())
    return [p.strip() for p in parts if p.strip()]


def chunk_text(text: str, max_chars: int = 900, overlap_sentences: int = 1) -> list[str]:
    """Paragraph-aware chunking: pack whole sentences up to ``max_chars``; overlap by one sentence."""
    text = re.sub(r"\n{3,}", "\n\n", text or "").strip()
    if len(text) <= max_chars:
        return [text] if text else []
    sentences: list[str] = []
    for paragraph in text.split("\n\n"):
        sentences.extend(_split_sentences(paragraph))
    chunks: list[str] = []
    current: list[str] = []
    for sentence in sentences:
        sentence = sentence[:max_chars]
        if current and len(" ".join(current)) + len(sentence) + 1 > max_chars:
            chunks.append(" ".join(current))
            current = current[-overlap_sentences:] if overlap_sentences else []
        current.append(sentence)
    if current:
        chunks.append(" ".join(current))
    return chunks


def build_chunks(companies: list[dict]) -> list[dict]:
    chunks: list[dict] = []
    for company in companies:
        for document in company["documents"]:
            if document["kind"] == "shutdown":
                body = f"{document['title']}. {document['text']}".strip(". ")
            else:
                body = f"{document['tagline']}. {document['text']}".strip(". ")
            for index, text in enumerate(chunk_text(body)[:3]):
                chunks.append({"company_id": company["id"], "kind": document["kind"], "source": f"hn_{document['kind']}",
                               "url": document["url"], "date": document["date"], "title": document["title"],
                               "points": document["points"], "text": text, "seq": index})
    for chunk in chunks:
        chunk["id"] = hashlib.sha1(f"{chunk['company_id']}|{chunk['url']}|{chunk['seq']}|{chunk['text']}".encode()).hexdigest()[:16]
    return chunks
