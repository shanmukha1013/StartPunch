"""LLM-assisted data validation and silver labelling (build time only).

* ``verify_shutdowns`` — confirms that a candidate story really announces a product/company
  shutdown or is a founder post-mortem of a failed business, and extracts the name.
* ``silver_label`` — assigns sector / business model / customer type to a sample of entities.
  These labels train the lightweight classifiers (distillation). Model cards state clearly that
  evaluation measures agreement with the LLM labels, not human ground truth.
Results are cached in ``backend/data/raw`` so rebuilds don't repeat calls.
"""
from __future__ import annotations

import gzip
import json
import logging
from concurrent.futures import ThreadPoolExecutor

from .. import llm
from .sources import RAW_DIR
from .taxonomy import SECTORS

logger = logging.getLogger("startpunch.ingest.llm")

BUSINESS_MODELS = {
    "saas_subscription": "Recurring software subscription (B2B or prosumer)",
    "usage_based": "Usage/consumption-based pricing (API calls, compute, volume)",
    "marketplace": "Two-sided marketplace taking a commission",
    "transaction_fees": "Fees on payments/financial transactions",
    "advertising": "Free product monetized with ads",
    "ecommerce_d2c": "Selling physical goods directly to consumers",
    "hardware": "Selling hardware devices (possibly with software)",
    "services": "Services / agency / done-for-you work",
    "open_core": "Open-source product with paid hosting/enterprise tier",
    "consumer_freemium": "Consumer app with freemium upgrades or in-app purchases",
}
CUSTOMERS = ["b2b", "b2c", "developers", "b2b2c", "government", "mixed"]


def _cache(name: str) -> dict:
    path = RAW_DIR / f"{name}.json.gz"
    if path.exists():
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    return {}


def _store(name: str, data: dict) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with gzip.open(RAW_DIR / f"{name}.json.gz", "wt", encoding="utf-8") as handle:
        json.dump(data, handle)


def _run_batches(items: list[dict], batch_size: int, worker, workers: int = 2) -> list[dict]:
    batches = [items[i:i + batch_size] for i in range(0, len(items), batch_size)]
    out: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(worker, batches):
            out.extend(result)
    return out


# ------------------------------------------------------------------------ shutdown checks
_SHUTDOWN_SCHEMA = llm.arr(llm.obj({
    "id": llm.S("string"),
    "is_business_failure": llm.S("boolean"),
    "name": llm.S("string"),
    "reason": llm.S("string"),
}))


def verify_shutdowns(candidates: list[dict]) -> dict[str, dict]:
    """candidates: [{id, title, text}] -> {id: {is_business_failure, name, reason, model}}"""
    cache = _cache("llm_shutdown_checks")
    todo = [c for c in candidates if c["id"] not in cache]
    logger.info("shutdown verification: %s cached, %s to check", len(candidates) - len(todo), len(todo))

    def worker(batch: list[dict]) -> list[dict]:
        listing = "\n".join(f'- id={c["id"]} | title: {c["title"]} | text: {c["text"][:300]}' for c in batch)
        prompt = (
            "You are validating a dataset of startup/product failures built from Hacker News stories.\n"
            "For each story decide if it announces that a specific company, startup, product or service is shutting down, "
            "or is a founder's post-mortem explaining why their business/product failed.\n"
            "Answer false for: infrastructure outage or incident reports, security post-mortems, debugging write-ups, "
            "conference or game-jam retrospectives, news about governments or networks being shut down, and general essays.\n"
            "If true, give the exact company/product name as written (no batch tags like '(YC W10)'). If false, name=''.\n"
            "reason: at most 12 words. Return a JSON array with one object per story, same ids.\n\n" + listing
        )
        try:
            result = llm.generate_json(prompt, schema=_SHUTDOWN_SCHEMA, temperature=0.0, max_output_tokens=8000, profile="fast")
            return [{**r, "model": result.model} for r in result.data if isinstance(r, dict) and r.get("id")]
        except llm.LLMUnavailable as exc:
            logger.warning("shutdown verification batch failed: %s", exc)
            return []

    for row in _run_batches(todo, 40, worker):
        cache[row["id"]] = row
    _store("llm_shutdown_checks", cache)
    return cache


# ---------------------------------------------------------------------------- silver labels
_LABEL_SCHEMA = llm.arr(llm.obj({
    "id": llm.S("string"),
    "sector": llm.enum([*SECTORS, "other"]),
    "business_model": llm.enum([*BUSINESS_MODELS, "unclear"]),
    "customer": llm.enum([*CUSTOMERS, "unclear"]),
}))


def silver_label(items: list[dict]) -> dict[str, dict]:
    """items: [{id, name, text}] -> {id: {sector, business_model, customer, model}}"""
    cache = _cache("llm_silver_labels")
    todo = [item for item in items if item["id"] not in cache]
    logger.info("silver labels: %s cached, %s to label", len(items) - len(todo), len(todo))
    sector_lines = "\n".join(f"  {k}: {v}" for k, v in SECTORS.items())
    model_lines = "\n".join(f"  {k}: {v}" for k, v in BUSINESS_MODELS.items())

    def worker(batch: list[dict]) -> list[dict]:
        listing = "\n".join(f'- id={i["id"]} | {i["name"]}: {i["text"][:320]}' for i in batch)
        prompt = (
            "Classify each startup/product described below.\n"
            f"sector (pick the single best; 'other' if none fits):\n{sector_lines}\n"
            f"business_model (most likely primary model; 'unclear' if the text gives no signal):\n{model_lines}\n"
            f"customer: one of {', '.join(CUSTOMERS)} or 'unclear'.\n"
            "Judge only from the text. Return a JSON array, one object per item, same ids.\n\n" + listing
        )
        try:
            result = llm.generate_json(prompt, schema=_LABEL_SCHEMA, temperature=0.0, max_output_tokens=8000, profile="fast")
            return [{**r, "model": result.model} for r in result.data if isinstance(r, dict) and r.get("id")]
        except llm.LLMUnavailable as exc:
            logger.warning("silver label batch failed: %s", exc)
            return []

    done = 0
    for row in _run_batches(todo, 60, worker):
        cache[row["id"]] = row
        done += 1
        if done % 600 == 0:
            _store("llm_silver_labels", cache)
    _store("llm_silver_labels", cache)
    return cache
