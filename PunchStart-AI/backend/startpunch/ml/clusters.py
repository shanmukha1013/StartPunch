"""Sector-cluster assignment (inference)."""
from __future__ import annotations

import json
from functools import lru_cache

import numpy as np

from .classifier import latest_version_dir


@lru_cache(maxsize=1)
def _load():
    directory = latest_version_dir("clusters")
    if directory is None:
        return None
    card = json.loads((directory / "card.json").read_text(encoding="utf-8"))
    centroids = np.load(directory / "centroids.npy").astype(np.float32)
    return card, centroids


def card() -> dict | None:
    loaded = _load()
    return loaded[0] if loaded else None


def assign(embedding: list[float] | None) -> dict | None:
    loaded = _load()
    if loaded is None or embedding is None:
        return None
    card_, centroids = loaded
    vec = np.asarray(embedding, dtype=np.float32)
    if vec.shape[0] != centroids.shape[1]:
        return None
    sims = centroids @ vec
    best = int(np.argmax(sims))
    cluster = next(c for c in card_["clusters"] if c["id"] == best)
    return {"model": f"clusters@{card_['version']}", "cluster_id": best, "similarity": round(float(sims[best]), 4),
            "size": cluster["size"], "top_terms": cluster["top_terms"], "dominant_sectors": cluster["dominant_sectors"]}
