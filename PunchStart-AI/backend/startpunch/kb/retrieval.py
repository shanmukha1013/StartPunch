"""Hybrid retrieval: BM25 + dense embeddings, reciprocal-rank fusion, metadata filters,
company-level aggregation and feature-based reranking.

LLM relevance grading (direct / indirect competitor / unrelated) happens later in the
analysis pipeline on top of these candidates, so irrelevant-but-similar documents can be
dropped explicitly instead of being trusted because their vectors are close.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np

from .. import llm
from .store import KnowledgeBase, get_kb

logger = logging.getLogger("startpunch.retrieval")
RRF_K = 60


@dataclass
class Filters:
    sectors: list[str] | None = None          # restrict to these sector keys
    statuses: list[str] | None = None         # launched / shutdown_announced
    entity_types: list[str] | None = None     # startup / product / company
    since: str | None = None                  # ISO date: documents on/after
    until: str | None = None                  # ISO date: documents on/before
    sources: list[str] | None = None          # hn_launch / hn_show / hn_shutdown
    exclude_company_ids: set[str] = field(default_factory=set)

    def allows(self, company: dict, chunk: dict) -> bool:
        if company["id"] in self.exclude_company_ids:
            return False
        if self.sectors and company.get("sector") not in self.sectors:
            return False
        if self.statuses and company.get("status") not in self.statuses:
            return False
        if self.entity_types and company.get("entity_type") not in self.entity_types:
            return False
        date = chunk.get("date") or ""
        if self.since and date < self.since:
            return False
        if self.until and date > self.until:
            return False
        if self.sources and chunk.get("source") not in self.sources:
            return False
        return True


@dataclass
class CompanyHit:
    company_id: str
    score: float
    dense: float
    lexical: float
    sector_match: bool
    chunk_indices: list[int]

    def to_dict(self, kb: KnowledgeBase) -> dict:
        company = kb.companies[self.company_id]
        return {
            "company_id": self.company_id,
            "name": company["name"],
            "entity_type": company.get("entity_type"),
            "sector": company.get("sector"),
            "sector_label": company.get("sector_label"),
            "sector_source": company.get("sector_source"),
            "business_model": company.get("business_model"),
            "status": company.get("status"),
            "batch": company.get("batch"),
            "first_launch": company.get("first_launch"),
            "shutdown_date": company.get("shutdown_date"),
            "website": company.get("website"),
            "description": company.get("description") or "",
            "max_points": company.get("max_points"),
            "score": round(self.score, 5),
            "signals": {"dense": round(self.dense, 4), "lexical": round(self.lexical, 4), "sector_match": self.sector_match},
            "evidence": [
                {"chunk_id": kb.chunks[i]["id"], "text": kb.chunks[i]["text"], "url": kb.chunks[i]["url"],
                 "source": kb.chunks[i]["source"], "date": kb.chunks[i].get("date"), "kind": kb.chunks[i]["kind"],
                 "title": kb.chunks[i].get("title")}
                for i in self.chunk_indices[:2]
            ],
        }


def _rrf(rankings: Iterable[list[int]]) -> dict[int, float]:
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (RRF_K + rank + 1)
    return fused


def search(
    queries: list[str],
    *,
    query_embeddings: list[list[float]] | None = None,
    filters: Filters | None = None,
    boost_sectors: list[str] | None = None,
    boost_names: list[str] | None = None,
    mode: str = "hybrid",
    k_chunks: int = 80,
    k_companies: int = 25,
    kb: KnowledgeBase | None = None,
) -> tuple[list[dict], dict]:
    """Return (company hits, diagnostics). ``mode``: hybrid | lexical | dense."""
    kb = kb or get_kb()
    diagnostics = {"mode": mode, "kb_chunks": len(kb.chunks), "dense_available": kb.embeddings is not None}
    if not kb.available:
        diagnostics["mode"] = "unavailable"
        return [], diagnostics
    filters = filters or Filters()
    allowed = [i for i, chunk in enumerate(kb.chunks) if filters.allows(kb.companies[chunk["company_id"]], chunk)]
    allowed_set = set(allowed)
    diagnostics["candidates_after_filters"] = len(allowed)
    if not allowed:
        return [], diagnostics

    rankings: list[list[int]] = []
    dense_best: dict[int, float] = {}
    lexical_best: dict[int, float] = {}

    if mode in {"hybrid", "lexical"}:
        for query in queries:
            results = kb.bm25.search(query, top_k=k_chunks, allowed=allowed_set)
            if results:
                top = results[0][1] or 1.0
                for idx, score in results:
                    lexical_best[idx] = max(lexical_best.get(idx, 0.0), score / top)
                rankings.append([idx for idx, _ in results])

    if mode in {"hybrid", "dense"} and kb.embeddings is not None:
        vectors = query_embeddings
        if vectors is None and llm.available():
            try:
                vectors = llm.embed(queries, task="RETRIEVAL_QUERY")
            except llm.LLMUnavailable as exc:
                logger.warning("Query embedding failed, lexical only: %s", exc)
                vectors = None
        if vectors:
            sub = kb.embeddings[allowed]
            for vec in vectors:
                sims = sub @ np.asarray(vec, dtype=np.float32)
                top_local = np.argsort(-sims)[:k_chunks]
                ranking = [allowed[j] for j in top_local]
                for j in top_local:
                    idx = allowed[j]
                    dense_best[idx] = max(dense_best.get(idx, -1.0), float(sims[j]))
                rankings.append(ranking)
        else:
            diagnostics["mode"] = "lexical" if mode == "hybrid" else "unavailable"
    elif mode == "hybrid":
        diagnostics["mode"] = "lexical"

    fused = _rrf(rankings)
    if not fused:
        return [], diagnostics

    # ---- aggregate to company level
    per_company: dict[str, list[tuple[int, float]]] = {}
    for idx, score in fused.items():
        per_company.setdefault(kb.chunks[idx]["company_id"], []).append((idx, score))

    boost_sectors = boost_sectors or []
    names = {n.strip().lower() for n in (boost_names or []) if n and len(n.strip()) > 2}
    hits: list[CompanyHit] = []
    for company_id, items in per_company.items():
        items.sort(key=lambda item: item[1], reverse=True)
        base = items[0][1] + 0.25 * sum(s for _, s in items[1:3])
        company = kb.companies[company_id]
        sector_match = bool(company.get("sector") and company["sector"] in boost_sectors)
        dense = max((dense_best.get(i, 0.0) for i, _ in items), default=0.0)
        lexical = max((lexical_best.get(i, 0.0) for i, _ in items), default=0.0)
        score = base
        if sector_match:
            # Prefer same-sector companies, weighted by position in the predicted sector list.
            score *= 1.0 + 0.25 * (1.0 - boost_sectors.index(company["sector"]) / max(1, len(boost_sectors)))
        if company["name"].lower() in names:
            score *= 3.0  # founder explicitly named this competitor
        hits.append(CompanyHit(company_id, score, dense, lexical, sector_match, [i for i, _ in items]))

    hits.sort(key=lambda hit: hit.score, reverse=True)
    diagnostics["companies_ranked"] = len(hits)
    return [hit.to_dict(kb) for hit in hits[:k_companies]], diagnostics


def company_card(company_id: str, kb: KnowledgeBase | None = None) -> dict | None:
    kb = kb or get_kb()
    company = kb.companies.get(company_id)
    if not company:
        return None
    keys = ("id", "name", "entity_type", "description", "sector", "sector_label", "sector_source", "sector_probability",
            "business_model", "business_model_source", "customer", "status", "batch", "first_launch", "shutdown_date",
            "website", "max_points", "cluster")
    return {
        **{k: company.get(k) for k in keys},
        "sources": company.get("sources", []),
        "documents": [{k: d.get(k) for k in ("kind", "title", "tagline", "batch", "date", "url", "points", "comments", "link")}
                      for d in company.get("documents", [])],
    }
