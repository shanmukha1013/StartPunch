"""Market intelligence: knowledge-base coverage, freshness, sector stats, clusters, search, model cards."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from .. import ratelimit
from ..ingest.taxonomy import SECTORS, sector_label
from ..kb import retrieval
from ..kb.store import get_kb
from ..ml import classifier, clusters
from ..security import CurrentUser, current_user

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


def _cache(response: Response, seconds: int = 300) -> None:
    response.headers["Cache-Control"] = f"private, max-age={seconds}"


@router.get("/public-overview")
def public_overview(response: Response):
    """Unauthenticated, aggregate-only numbers for the landing page (no member data)."""
    _cache(response, 900)
    response.headers["Cache-Control"] = "public, max-age=900"
    kb = get_kb()
    manifest = kb.manifest or {}
    counts = manifest.get("counts", {})
    return {
        "entities": counts.get("entities", 0),
        "startups": (counts.get("by_type") or {}).get("startup", 0),
        "shutdowns": counts.get("shutdown_announced", 0),
        "sectors": len([k for k in (counts.get("by_sector") or {}) if k != "unclassified"]),
        "built_at": manifest.get("built_at"),
        "sources": [s.get("name") for s in manifest.get("sources", [])],
    }


@router.get("/coverage")
def coverage(response: Response, user: CurrentUser = Depends(current_user)):
    _cache(response)
    kb = get_kb()
    manifest = kb.manifest or {}
    built = manifest.get("built_at")
    age_days = None
    if built:
        age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(built)).days
    policy = manifest.get("freshness_policy_days", 30)
    return {
        "available": kb.available,
        "snapshot_id": manifest.get("snapshot_id"),
        "built_at": built,
        "age_days": age_days,
        "freshness": "unknown" if age_days is None else ("fresh" if age_days <= policy else "stale"),
        "freshness_policy_days": policy,
        "sources": manifest.get("sources", []),
        "counts": manifest.get("counts", {}),
        "build_report": manifest.get("build_report", {}),
        "validation": manifest.get("validation", {}),
        "labels": manifest.get("labels", {}),
        "embedding": manifest.get("embedding"),
        "models": manifest.get("models", {}),
        "clusters": manifest.get("clusters"),
        "retrieval_evaluation": manifest.get("retrieval_evaluation"),
        "caveats": kb.stats.get("caveats", []),
        "launch_posts_by_year": kb.stats.get("launch_posts_by_year", {}),
        "dense_retrieval": kb.embeddings is not None,
    }


@router.get("/sectors")
def sectors(response: Response, user: CurrentUser = Depends(current_user)):
    _cache(response)
    stats = get_kb().stats.get("sectors", {})
    rows = [{k: v for k, v in s.items() if k not in {"shutdown_examples"}} for s in stats.values()]
    rows.sort(key=lambda s: s["entities"], reverse=True)
    return {"sectors": rows, "taxonomy": SECTORS}


@router.get("/sectors/{key}")
def sector_detail(key: str, response: Response, user: CurrentUser = Depends(current_user)):
    _cache(response)
    kb = get_kb()
    stats = kb.stats.get("sectors", {}).get(key)
    if not stats:
        raise HTTPException(404, "Sector not found.")
    members = [c for c in kb.companies.values() if (c.get("sector") or "unclassified") == key]
    top = sorted(members, key=lambda c: c.get("max_points") or 0, reverse=True)[:12]
    recent = sorted((c for c in members if c.get("first_launch")), key=lambda c: c["first_launch"], reverse=True)[:12]
    brief = lambda c: {"id": c["id"], "name": c["name"], "description": c.get("description"), "status": c.get("status"),  # noqa: E731
                       "first_launch": c.get("first_launch"), "batch": c.get("batch"), "max_points": c.get("max_points"),
                       "entity_type": c.get("entity_type"), "sector_source": c.get("sector_source")}
    return {"stats": stats, "most_discussed": [brief(c) for c in top], "recent": [brief(c) for c in recent]}


@router.get("/clusters")
def cluster_map(response: Response, user: CurrentUser = Depends(current_user)):
    _cache(response)
    card = clusters.card()
    if not card:
        return {"available": False}
    kb = get_kb()
    out = []
    for cluster in card["clusters"]:
        out.append({**cluster, "dominant_sectors": [{**d, "label": sector_label(d["sector"])} for d in cluster["dominant_sectors"]],
                    "examples": [{"id": cid, "name": kb.companies.get(cid, {}).get("name", cid)} for cid in cluster["examples"]]})
    out.sort(key=lambda c: c["size"], reverse=True)
    return {"available": True, "version": card["version"], "algorithm": card["algorithm"], "k_selection": card["k_selection"],
            "limitations": card["limitations"], "clusters": out}


@router.get("/models")
def model_cards(response: Response, user: CurrentUser = Depends(current_user)):
    _cache(response)
    cards = {}
    for name in ("industry", "business_model"):
        model = classifier.get(name)
        if model:
            cards[name] = {k: v for k, v in model.card.items() if k != "class_descriptions"}
    cluster_card = clusters.card()
    if cluster_card:
        cards["clusters"] = {k: v for k, v in cluster_card.items() if k != "clusters"}
    return {"models": cards}


@router.get("/search")
def search(q: str = Query(..., min_length=2, max_length=300), sector: str | None = Query(None, max_length=40),
           status: str | None = Query(None, pattern="^(launched|shutdown_announced)$"),
           entity_type: str | None = Query(None, pattern="^(startup|product|company)$"),
           since: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
           mode: str = Query("hybrid", pattern="^(hybrid|lexical|dense)$"), limit: int = Query(20, le=40),
           user: CurrentUser = Depends(current_user)):
    ratelimit.hit("ai", user.id)
    filters = retrieval.Filters(sectors=[sector] if sector else None, statuses=[status] if status else None,
                                entity_types=[entity_type] if entity_type else None, since=since)
    hits, diagnostics = retrieval.search([q], filters=filters, mode=mode, k_companies=limit)
    return {"results": hits, "diagnostics": diagnostics}


@router.get("/companies/{company_id:path}")
def company(company_id: str, user: CurrentUser = Depends(current_user)):
    card = retrieval.company_card(company_id)
    if card is None:
        raise HTTPException(404, "Not in the knowledge base.")
    return card
