"""Research stage: retrieval -> LLM relevance grading -> evidence bundle with stable source ids."""
from __future__ import annotations

import logging
from datetime import date, timedelta

from .. import llm
from ..kb import retrieval
from ..kb.store import get_kb

logger = logging.getLogger("startpunch.research")

RELATIONS = ["direct_competitor", "indirect_competitor", "similar_business_model", "adjacent", "unrelated"]
_GRADE_SCHEMA = llm.arr(llm.obj({
    "id": llm.S("string"),
    "relation": llm.enum(RELATIONS),
    "relevance": llm.S("integer"),
    "reason": llm.S("string"),
}))


def _grade(idea_summary: str, candidates: list[dict]) -> dict[str, dict] | None:
    listing = "\n".join(
        f"- id={c['company_id']} | {c['name']} | {c.get('description', '')[:160]} | evidence: {c['evidence'][0]['text'][:260] if c['evidence'] else ''}"
        for c in candidates)
    prompt = (
        f"Startup idea:\n{idea_summary}\n\nCandidates retrieved from a knowledge base of product launches:\n{listing}\n\n"
        "For every candidate decide its relation to the idea:\n"
        "- direct_competitor: solves the same problem for the same customer\n"
        "- indirect_competitor: different approach to the same problem, or same product for another customer\n"
        "- similar_business_model: unrelated problem but a business model/go-to-market worth learning from\n"
        "- adjacent: same broad space but not competing\n"
        "- unrelated: only superficially similar wording\n"
        "relevance: 0-3 (3 = highly relevant). reason: max 15 words, based only on the text shown. "
        "Return one object per candidate with the same ids."
    )
    try:
        result = llm.generate_json(prompt, schema=_GRADE_SCHEMA, temperature=0.0, max_output_tokens=6000, profile="fast")
    except llm.LLMUnavailable as exc:
        logger.warning("relevance grading unavailable: %s", exc)
        return None
    graded = {}
    valid = {c["company_id"] for c in candidates}
    for row in result.data:
        if isinstance(row, dict) and row.get("id") in valid and row.get("relation") in RELATIONS:
            graded[row["id"]] = {"relation": row["relation"], "relevance": max(0, min(3, int(row.get("relevance") or 0))),
                                 "reason": str(row.get("reason", ""))[:200], "model": result.model}
    return graded


def run(data, signals: dict, classification: dict, idea_embedding: list[float] | None) -> dict:
    kb = get_kb()
    sectors = [t["label"] for t in (classification.get("sector") or {}).get("top", [])]
    queries = [signals.get("one_liner") or data.search_text(), data.search_text()] + list(signals.get("search_queries") or [])
    queries = [q for q in dict.fromkeys(q.strip() for q in queries if q and q.strip())][:6]

    vectors = None
    if llm.available() and kb.embeddings is not None:
        try:
            vectors = llm.embed(queries, task="RETRIEVAL_QUERY")
        except llm.LLMUnavailable as exc:
            logger.warning("query embedding failed: %s", exc)

    hits, diagnostics = retrieval.search(queries, query_embeddings=vectors, boost_sectors=sectors,
                                         boost_names=signals.get("competitors_mentioned"), k_companies=30, kb=kb)
    shutdown_hits, _ = retrieval.search(queries, query_embeddings=vectors, boost_sectors=sectors,
                                        filters=retrieval.Filters(statuses=["shutdown_announced"]), k_companies=10, kb=kb)
    seen = {h["company_id"] for h in hits}
    candidates = hits + [h for h in shutdown_hits if h["company_id"] not in seen]

    idea_summary = f"{signals.get('one_liner') or data.idea[:300]}\nCustomer: {signals.get('customer_type')}; {data.target_customers}"
    graded = _grade(idea_summary, candidates) if candidates and llm.available() else None
    diagnostics["llm_graded"] = graded is not None

    competitors = {"direct": [], "indirect": [], "similar_models": [], "adjacent": []}
    shutdowns: list[dict] = []
    sources: list[dict] = []
    dropped = 0
    for hit in candidates:
        grade = (graded or {}).get(hit["company_id"])
        if graded is not None:
            if grade is None or grade["relation"] == "unrelated" or grade["relevance"] < 1:
                dropped += 1
                continue
        else:
            # Without LLM grading keep only the strongest matches and mark them unclassified.
            if hit["score"] < (candidates[0]["score"] * 0.35):
                dropped += 1
                continue
            grade = {"relation": "unclassified", "relevance": None, "reason": "Not graded (AI engine unavailable)."}
        sid = f"S{len(sources) + 1}"
        doc = hit["evidence"][0] if hit["evidence"] else {}
        source = {
            "sid": sid, "company_id": hit["company_id"], "name": hit["name"], "entity_type": hit.get("entity_type"),
            "title": doc.get("title") or hit["name"], "url": doc.get("url"), "date": doc.get("date"),
            "stream": doc.get("source"), "snippet": (doc.get("text") or "")[:600], "status": hit.get("status"),
            "sector": hit.get("sector_label"), "description": hit.get("description"), "batch": hit.get("batch"),
            "relation": grade["relation"], "relevance": grade["relevance"], "reason": grade["reason"],
            "retrieval_score": hit["score"], "signals": hit["signals"],
        }
        sources.append(source)
        if hit.get("status") == "shutdown_announced":
            shutdowns.append(source)
        bucket = {"direct_competitor": "direct", "indirect_competitor": "indirect",
                  "similar_business_model": "similar_models", "adjacent": "adjacent"}.get(grade["relation"])
        if bucket:
            competitors[bucket].append(source)
        elif grade["relation"] == "unclassified":
            competitors["adjacent"].append(source)
        if len(sources) >= 24:
            break
    for bucket in competitors.values():
        bucket.sort(key=lambda s: (-(s["relevance"] or 0), -s["retrieval_score"]))

    # Recent launches in the predicted sector (market activity signal).
    recent: list[dict] = []
    top_sector = (classification.get("sector") or {}).get("top", [{}])
    top_key = top_sector[0].get("label") if top_sector else None
    if top_key:
        cutoff = (date.today() - timedelta(days=730)).isoformat()
        recent_hits, _ = retrieval.search(queries[:2], query_embeddings=vectors[:2] if vectors else None,
                                          filters=retrieval.Filters(sectors=[top_key], since=cutoff), k_companies=8, kb=kb)
        recent = [{"name": h["name"], "date": h["evidence"][0]["date"] if h["evidence"] else h.get("first_launch"),
                   "url": h["evidence"][0]["url"] if h["evidence"] else None, "description": h.get("description")}
                  for h in recent_hits]

    sector_stats = kb.stats.get("sectors", {}).get(top_key) if top_key else None
    manifest = kb.manifest or {}
    return {
        "sources": sources,
        "competitors": competitors,
        "shutdowns": shutdowns,
        "recent_launches": recent,
        "sector_stats": sector_stats,
        "retrieval": {**diagnostics, "queries": queries, "candidates": len(candidates), "dropped_as_unrelated": dropped},
        "knowledge_base": {"snapshot_id": manifest.get("snapshot_id"), "built_at": manifest.get("built_at"),
                           "entities": (manifest.get("counts") or {}).get("entities"),
                           "coverage_note": "Evidence comes only from Hacker News launch, Show HN and shutdown posts. "
                                            "Companies that never posted there are not covered."},
    }
