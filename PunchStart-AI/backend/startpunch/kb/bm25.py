"""Okapi BM25 over knowledge-base chunks (pure Python, built at load time)."""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#.-]*[a-z0-9+#]|[a-z0-9]")
STOP = frozenset("""
a an and are as at be been but by can could did do does for from had has have he her his how i if in into is it its
just more most my no not of on or our out over she so some such than that the their them then there these they this
those to too under up us very was we were what when where which while who why will with would you your also about
after all any based both each new one only other own same two via within without company founded startup startups
inc ltd llc platform service services solution solutions product products using use used help helps
""".split())


_SUFFIXES = ("izations", "ization", "ations", "ation", "ments", "ment", "ings", "ing", "ness", "ities", "ity",
             "ers", "er", "ed", "ly", "ive", "ize", "ise", "ance", "ence", "able", "al", "e")


def _stem(token: str) -> str:
    """Light, consistent suffix stripping (invoice/invoices/invoicing -> invoic)."""
    if token.isdigit() or len(token) <= 3:
        return token
    if token.endswith("ies") and len(token) > 4:
        token = token[:-3] + "y"
    elif token.endswith("sses"):
        token = token[:-2]
    elif token.endswith("s") and not token.endswith(("ss", "us", "is")) and len(token) > 4:
        token = token[:-1]
    for suffix in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            token = token[: -len(suffix)]
            break
    return token[:-1] if token.endswith("i") and len(token) > 5 else token


def tokenize(text: str) -> list[str]:
    return [_stem(t) for t in _TOKEN.findall((text or "").lower()) if t not in STOP and len(t) > 1]


class BM25Index:
    def __init__(self, documents: list[str], k1: float = 1.4, b: float = 0.72):
        self.k1, self.b = k1, b
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self.lengths: list[int] = []
        for doc_id, text in enumerate(documents):
            counts = Counter(tokenize(text))
            self.lengths.append(sum(counts.values()))
            for term, tf in counts.items():
                self.postings[term].append((doc_id, tf))
        self.n = len(documents)
        self.avgdl = (sum(self.lengths) / self.n) if self.n else 1.0
        self.idf = {term: math.log(1 + (self.n - len(p) + 0.5) / (len(p) + 0.5)) for term, p in self.postings.items()}

    def search(self, query: str, top_k: int = 100, allowed: set[int] | None = None) -> list[tuple[int, float]]:
        scores: dict[int, float] = defaultdict(float)
        for term in set(tokenize(query)):
            idf = self.idf.get(term)
            if idf is None:
                continue
            for doc_id, tf in self.postings[term]:
                if allowed is not None and doc_id not in allowed:
                    continue
                dl = self.lengths[doc_id]
                scores[doc_id] += idf * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        return sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
