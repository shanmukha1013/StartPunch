"""Knowledge-base build pipeline.

    python -m startpunch.ingest build            # use cached raw data where available
    python -m startpunch.ingest build --refresh  # re-fetch every source

Steps: fetch -> LLM-verify shutdown candidates -> clean/validate -> de-duplicate ->
entity resolution -> chunk -> embed -> silver labels -> train/evaluate classifiers ->
classify the rest -> cluster -> statistics -> retrieval evaluation -> versioned snapshot +
manifest (sources, licenses, freshness, coverage).
"""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from .. import llm
from ..config import KB_DIR
from ..utils import utcnow
from . import llm_labels, sources
from .normalize import build_chunks, build_companies, shutdown_candidates
from .taxonomy import SECTORS, sector_label

logger = logging.getLogger("startpunch.ingest.build")
EMB_CACHE = sources.RAW_DIR / "embeddings_cache.npz"
PREDICT_MIN_PROB = 0.40
SILVER_SAMPLE_OTHERS = 1600
STREAMS = ["hn_launch", "hn_show", "hn_shutdown"]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def _embedding_text(chunk: dict, company: dict) -> str:
    return f"{company['name']}: {chunk['text']}"


def embed_chunks(chunks: list[dict], companies: dict[str, dict]) -> np.ndarray:
    cache: dict[str, np.ndarray] = {}
    if EMB_CACHE.exists():
        data = np.load(EMB_CACHE, allow_pickle=False)
        cache = dict(zip(data["keys"].tolist(), data["vectors"]))
    keys = [hashlib.sha1(_embedding_text(c, companies[c["company_id"]]).encode()).hexdigest() for c in chunks]
    todo = [i for i, key in enumerate(keys) if key not in cache]
    todo.sort(key=lambda i: chunks[i]["seq"])  # first chunk of every document before continuation chunks
    logger.info("embeddings: %s cached, %s to compute", len(chunks) - len(todo), len(todo))
    batch = 100
    try:
        for start in range(0, len(todo), batch):
            idxs = todo[start:start + batch]
            texts = [_embedding_text(chunks[i], companies[chunks[i]["company_id"]])[:1200] for i in idxs]
            vectors = llm.embed(texts, tokens_per_minute=24000)
            for i, vec in zip(idxs, vectors):
                cache[keys[i]] = np.asarray(vec, dtype=np.float16)
            np.savez_compressed(EMB_CACHE, keys=np.array(list(cache.keys())), vectors=np.stack(list(cache.values())))
            logger.info("embeddings: %s/%s", min(start + batch, len(todo)), len(todo))
    except llm.LLMUnavailable as exc:
        logger.error("embedding stopped early (%s); continuing with partial coverage, rerun build later to resume", exc)
    dims = llm.EMBED_DIMS
    matrix = np.zeros((len(chunks), dims), dtype=np.float32)
    for row, key in enumerate(keys):
        if key in cache:
            matrix[row] = cache[key].astype(np.float32)
    return matrix


def company_vectors(chunks: list[dict], matrix: np.ndarray) -> dict[str, np.ndarray]:
    grouped: dict[str, list[int]] = defaultdict(list)
    for i, chunk in enumerate(chunks):
        if np.any(matrix[i]):  # skip chunks that have no embedding yet
            grouped[chunk["company_id"]].append(i)
    out = {}
    for cid, idxs in grouped.items():
        vec = matrix[idxs].mean(axis=0)
        out[cid] = vec / (np.linalg.norm(vec) or 1.0)
    return out


def compute_stats(companies: list[dict], current_year: int) -> dict:
    def launch_years(rows):
        return Counter(int(d["date"][:4]) for c in rows for d in c["documents"] if d["kind"] in {"launch", "show"})

    all_years = launch_years(companies)
    recent, prior = [current_year - 2, current_year - 1], [current_year - 4, current_year - 3]
    total_recent = sum(all_years[y] for y in recent) or 1
    total_prior = sum(all_years[y] for y in prior) or 1
    by_sector: dict[str, list[dict]] = defaultdict(list)
    for company in companies:
        by_sector[company.get("sector") or "unclassified"].append(company)
    sectors = {}
    for key, rows in by_sector.items():
        years = launch_years(rows)
        recent_n, prior_n = sum(years[y] for y in recent), sum(years[y] for y in prior)
        share_recent, share_prior = recent_n / total_recent, prior_n / total_prior
        shutdowns = sorted((c for c in rows if c.get("status") == "shutdown_announced"),
                           key=lambda c: c.get("shutdown_date") or "", reverse=True)
        models = Counter(c.get("business_model") for c in rows if c.get("business_model"))
        sectors[key] = {
            "sector": key, "label": sector_label(key) if key != "unclassified" else "Unclassified",
            "entities": len(rows),
            "by_type": dict(Counter(c["entity_type"] for c in rows)),
            "yc_startups": sum(1 for c in rows if c.get("batch")),
            "launch_posts_by_year": {str(y): years[y] for y in sorted(years)},
            "shutdown_announcements": len(shutdowns),
            "shutdown_examples": [{"id": c["id"], "name": c["name"], "date": c.get("shutdown_date")} for c in shutdowns[:8]],
            "business_models": dict(models.most_common(6)),
            "launch_share_trend": {
                "recent_years": recent, "prior_years": prior, "recent_count": recent_n, "prior_count": prior_n,
                "recent_share": round(share_recent, 4), "prior_share": round(share_prior, 4),
                "direction": ("insufficient data" if recent_n + prior_n < 15 else
                              "rising" if share_recent > share_prior * 1.2 else
                              "falling" if share_recent < share_prior * 0.8 else "flat"),
            },
        }
    return {
        "generated_at": utcnow().isoformat(),
        "sectors": sectors,
        "launch_posts_by_year": {str(y): all_years[y] for y in sorted(all_years)},
        "caveats": [
            "Coverage is limited to products and startups that were posted to Hacker News (Launch HN, Show HN with 100+ points). "
            "It is tech-heavy, English-language and skewed toward US/YC companies.",
            "'Shutdown announced' only means a public shutdown or failure post-mortem was found and verified; "
            "the absence of one does not mean a company is still operating.",
            "Launch-share trends compare a sector's share of all HN launch posts between two 2-year windows. "
            "They reflect what gets launched on HN, not the size of a market.",
            "Sectors are LLM-assigned (silver labels) or predicted by a classifier trained on those labels.",
        ],
    }


def evaluate_retrieval(kb_dir: Path, sample_size: int = 200, seed: int = 7) -> dict:
    """Known-item recall and sector precision for lexical, dense and hybrid retrieval."""
    from ..kb import retrieval, store

    kb = store.load(kb_dir)
    rng = random.Random(seed)
    pool = []
    for company in kb.companies.values():
        if company.get("sector_source") != "llm_label" or not company.get("sector"):
            continue
        texts = [d["text"] for d in company["documents"] if len(d["text"]) > 250]
        if texts:
            pool.append((company, texts[0]))
    sample = rng.sample(pool, min(sample_size, len(pool)))
    queries = []
    for company, text in sample:
        text = re.sub(re.escape(company["name"]), "", text, flags=re.I) if len(company["name"]) > 2 else text
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if len(s) > 20]
        queries.append(" ".join(sentences[1:3]) if len(sentences) > 2 else text[:300])
    vectors = None
    skipped = None
    if kb.embeddings is not None and llm.available():
        try:
            vectors = llm.embed(queries, task="RETRIEVAL_QUERY")
        except llm.LLMUnavailable as exc:
            skipped = f"dense and hybrid evaluation skipped: {str(exc)[:120]}"
            logger.warning(skipped)
    results = {}
    for mode in ("lexical", "dense", "hybrid"):
        if mode != "lexical" and vectors is None:
            continue
        hit10, precision = 0, []
        for i, (company, _) in enumerate(sample):
            hits, _ = retrieval.search([queries[i]], query_embeddings=[vectors[i]] if vectors else None,
                                       mode=mode, k_companies=11, kb=kb)
            ids = [h["company_id"] for h in hits]
            hit10 += company["id"] in ids[:10]
            others = [h for h in hits if h["company_id"] != company["id"] and h.get("sector")][:10]
            if others:
                precision.append(sum(1 for h in others if h["sector"] == company["sector"]) / len(others))
        results[mode] = {"known_item_recall@10": round(hit10 / max(1, len(sample)), 4),
                         "sector_precision@10": round(float(np.mean(precision)), 4) if precision else None}
        logger.info("retrieval eval %s: %s", mode, results[mode])
    return {
        "evaluated_at": utcnow().isoformat(), "queries": len(sample), "seed": seed,
        "protocol": ("Queries are 1-2 sentences from a sampled entity's own launch text with its name removed. "
                     "known_item_recall@10 = the source entity is in the top 10. sector_precision@10 = share of the other "
                     "top-10 results with the same (LLM-assigned) sector. Labels are silver, so precision is approximate."),
        "results": results,
        "skipped": skipped,
        "dense_coverage": None if kb.embeddings is None else
        {"chunks_with_vectors": int(np.count_nonzero(np.any(kb.embeddings, axis=1))), "chunks_total": len(kb.chunks)},
    }


def build(refresh: bool = False, skip_embeddings: bool = False) -> dict:
    now = utcnow()
    streams = {name: sources.fetch_stream(name, refresh=refresh) for name in STREAMS}

    checks = None
    if llm.available():
        checks = llm_labels.verify_shutdowns(shutdown_candidates(streams["hn_shutdown"]))
    companies, report = build_companies(streams, now.year, checks)
    chunks = build_chunks(companies)
    report.chunks = len(chunks)
    by_id = {c["id"]: c for c in companies}
    logger.info("normalized: %s entities, %s chunks", len(companies), len(chunks))
    snapshot_id = now.strftime("%Y%m%d") + "-" + hashlib.sha1("".join(sorted(c["id"] for c in chunks)).encode()).hexdigest()[:8]

    from ..ml import train as ml_train
    from ..ml.classifier import TextClassifier

    # ---- silver labels on a sample (all Launch HN startups + a random sample of the rest)
    rng = random.Random(42)
    startups = [c for c in companies if c["entity_type"] == "startup"]
    others = [c for c in companies if c["entity_type"] != "startup"]
    sample = startups + rng.sample(others, min(SILVER_SAMPLE_OTHERS, len(others)))
    silver = llm_labels.silver_label([{"id": c["id"], "name": c["name"], "text": ml_train.entity_text(c)} for c in sample]) \
        if llm.available() else {}

    matrix = embed_chunks(chunks, by_id) if (not skip_embeddings and llm.available()) else None
    vectors = company_vectors(chunks, matrix) if matrix is not None else None

    models_info = {}
    for name, field, ignore, task, descriptions in (
        ("industry", "sector", "other", "Predict the startup sector (22-sector taxonomy) from a description.", SECTORS),
        ("business_model", "business_model", "unclear", "Predict the primary business model from a description.",
         llm_labels.BUSINESS_MODELS),
    ):
        records = [{"id": cid, "text": ml_train.entity_text(by_id[cid]), "label": row[field]}
                   for cid, row in silver.items() if cid in by_id and row.get(field) and row[field] != ignore]
        if len(records) < 200:
            logger.warning("not enough silver labels to train %s (%s)", name, len(records))
            continue
        model_dir, card = ml_train.train_classifier(
            name, records, vectors, snapshot_id, task,
            f"LLM silver labels ({next(iter(silver.values())).get('model', 'gemini')}) on {len(records)} sampled entities",
            descriptions)
        models_info[name] = {"version": model_dir.name, "metrics": card["metrics"], "dir": model_dir}

    # ---- assign sector / business model / customer to every entity
    counts = Counter()
    for company in companies:
        label = silver.get(company["id"])
        vec = vectors.get(company["id"]) if vectors else None
        for name, field, ignore in (("industry", "sector", "other"), ("business_model", "business_model", "unclear")):
            if label and label.get(field):
                value = label[field] if label[field] != ignore else None
                company[field], company[f"{field}_source"] = value, "llm_label"
                counts[f"{field}:llm_label"] += 1
                continue
            info = models_info.get(name)
            if info is None:
                company[field], company[f"{field}_source"] = None, None
                continue
            result = TextClassifier(info["dir"]).predict(ml_train.entity_text(company), vec)
            top = result["top"][0] if result["top"] else None
            if top and top["probability"] >= PREDICT_MIN_PROB:
                company[field], company[f"{field}_source"] = top["label"], "model_predicted"
                company[f"{field}_probability"] = top["probability"]
                counts[f"{field}:model_predicted"] += 1
            else:
                company[field], company[f"{field}_source"] = None, None
                counts[f"{field}:unclassified"] += 1
        company["customer"] = (label or {}).get("customer") if (label or {}).get("customer") != "unclear" else None
        company["sector_label"] = sector_label(company.get("sector"))
    logger.info("label assignment: %s", dict(counts))

    cluster_card = None
    if vectors:
        ids = [c["id"] for c in companies if c["id"] in vectors]
        _, cluster_card, labels = ml_train.train_clusters(
            ids, np.stack([vectors[i] for i in ids]), [ml_train.entity_text(by_id[i]) or by_id[i]["name"] for i in ids],
            [by_id[i].get("sector") for i in ids], snapshot_id)
        for cid, label in zip(ids, labels):
            by_id[cid]["cluster"] = int(label)

    stats = compute_stats(companies, now.year)

    KB_DIR.mkdir(parents=True, exist_ok=True)
    for company in companies:
        company.pop("norm", None)
    _write_jsonl(KB_DIR / "companies.jsonl.gz", companies)
    _write_jsonl(KB_DIR / "chunks.jsonl.gz", chunks)
    if matrix is not None:
        np.save(KB_DIR / "embeddings.npy", matrix.astype(np.float16))
    (KB_DIR / "stats.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")

    manifest = {
        "snapshot_id": snapshot_id,
        "built_at": now.isoformat(),
        "sources": [
            {"id": name, **{k: v for k, v in sources.SOURCE_REGISTRY[name].items() if k != "queries"},
             "queries": sources.SOURCE_REGISTRY[name]["queries"], "fetched_at": streams[name].get("fetched_at"),
             "items_fetched": len(streams[name]["hits"]),
             "latest_item": max((h.get("created_at") or "" for h in streams[name]["hits"]), default=None)}
            for name in STREAMS
        ],
        "build_report": report.as_dict(),
        "validation": {
            "shutdown_candidates_checked_by_llm": len(checks or {}),
            "shutdown_confirmed": sum(1 for v in (checks or {}).values() if v.get("is_business_failure")),
        },
        "labels": dict(counts),
        "counts": {
            "entities": len(companies), "chunks": len(chunks),
            "by_type": dict(Counter(c["entity_type"] for c in companies)),
            "yc_startups": sum(1 for c in companies if c.get("batch")),
            "shutdown_announced": sum(1 for c in companies if c.get("status") == "shutdown_announced"),
            "by_sector": dict(Counter(c.get("sector") or "unclassified" for c in companies).most_common()),
        },
        "embedding": {"model": "gemini-embedding-001", "dims": llm.EMBED_DIMS, "stored_as": "float16",
                      "chunks_embedded": int(np.count_nonzero(np.any(matrix, axis=1))), "chunks_total": len(chunks)}
                     if matrix is not None else None,
        "models": {name: {"version": info["version"], "metrics": info["metrics"]} for name, info in models_info.items()},
        "clusters": {"version": cluster_card["version"], "k": cluster_card["k_selection"]["chosen_k"]} if cluster_card else None,
        "sector_taxonomy": SECTORS,
        "freshness_policy_days": 30,
    }
    (KB_DIR / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    logger.info("snapshot written: %s", snapshot_id)
    manifest["retrieval_evaluation"] = evaluate_retrieval(KB_DIR)
    (KB_DIR / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest
