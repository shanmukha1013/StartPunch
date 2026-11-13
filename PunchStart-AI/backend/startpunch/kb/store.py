"""Loads the versioned knowledge-base snapshot (built by ``python -m startpunch.ingest build``)."""
from __future__ import annotations

import gzip
import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..config import KB_DIR
from .bm25 import BM25Index

logger = logging.getLogger("startpunch.kb")


@dataclass
class KnowledgeBase:
    manifest: dict
    companies: dict[str, dict]
    chunks: list[dict]
    embeddings: np.ndarray | None          # (n_chunks, dims) float32, L2-normalized
    company_chunks: dict[str, list[int]]
    bm25: BM25Index
    stats: dict

    @property
    def available(self) -> bool:
        return bool(self.chunks)

    def chunk_header(self, chunk: dict) -> str:
        company = self.companies.get(chunk["company_id"], {})
        return f"{company.get('name', '')} | {company.get('sector_label', '')}"


_kb: KnowledgeBase | None = None
_lock = threading.Lock()


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load(directory: Path = KB_DIR) -> KnowledgeBase:
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    companies = {c["id"]: c for c in _read_jsonl(directory / "companies.jsonl.gz")}
    chunks = _read_jsonl(directory / "chunks.jsonl.gz")
    embeddings = None
    emb_path = directory / "embeddings.npy"
    if emb_path.exists() and chunks:
        matrix = np.load(emb_path).astype(np.float32)
        if matrix.shape[0] == len(chunks):
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            embeddings = matrix / norms
        else:
            logger.error("Embedding matrix rows (%s) != chunks (%s); dense retrieval disabled", matrix.shape[0], len(chunks))
    company_chunks: dict[str, list[int]] = {}
    for index, chunk in enumerate(chunks):
        company_chunks.setdefault(chunk["company_id"], []).append(index)
    docs = []
    for chunk in chunks:
        company = companies.get(chunk["company_id"], {})
        docs.append(f"{company.get('name', '')} {company.get('name', '')} {chunk.get('title', '')} {chunk['text']}")
    stats_path = directory / "stats.json"
    stats = json.loads(stats_path.read_text(encoding="utf-8")) if stats_path.exists() else {}
    kb = KnowledgeBase(manifest, companies, chunks, embeddings, company_chunks, BM25Index(docs), stats)
    logger.info("Knowledge base loaded: %s companies, %s chunks, dense=%s", len(companies), len(chunks), embeddings is not None)
    return kb


def get_kb() -> KnowledgeBase:
    global _kb
    if _kb is None:
        with _lock:
            if _kb is None:
                _kb = load()
    return _kb


def set_kb(kb: KnowledgeBase | None) -> None:
    """Swap the in-memory knowledge base (tests / rebuilds)."""
    global _kb
    _kb = kb
