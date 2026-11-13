"""Text classifiers — numpy-only inference.

Models (trained offline by ``ml/train.py``):
* ``industry``        — startup sector (22-sector taxonomy)
* ``business_model``  — primary business model
Each has a TF-IDF + logistic-regression variant (no API call needed) and, when available, an
embedding + logistic-regression variant (used when a Gemini embedding of the text exists).
Model cards (``card.json``) hold hold-out metrics; predictions are always reported as
"predicted" together with the model version.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

import numpy as np

from ..config import BACKEND_DIR
from .textvec import TfidfInference, softmax

logger = logging.getLogger("startpunch.ml")
MODELS_DIR = BACKEND_DIR / "data" / "models"


def latest_version_dir(name: str) -> Path | None:
    base = MODELS_DIR / name
    if not base.exists():
        return None
    versions = [p for p in base.iterdir() if p.is_dir() and p.name[1:].isdigit()]
    return max(versions, key=lambda p: int(p.name[1:])) if versions else None


class TextClassifier:
    def __init__(self, directory: Path):
        self.directory = directory
        self.card = json.loads((directory / "card.json").read_text(encoding="utf-8"))
        self.name = self.card["name"]
        self.classes: list[str] = self.card["classes"]
        self.version = f"{self.name}@{directory.name}"
        self.tfidf = TfidfInference.from_dict(json.loads((directory / "tfidf.json").read_text(encoding="utf-8")))
        lr = np.load(directory / "tfidf_lr.npz")
        self.tfidf_coef = lr["coef"].astype(np.float32)
        self.tfidf_intercept = lr["intercept"].astype(np.float32)
        self.emb_coef = self.emb_intercept = None
        if (directory / "embedding_lr.npz").exists():
            emb = np.load(directory / "embedding_lr.npz")
            self.emb_coef = emb["coef"].astype(np.float32)
            self.emb_intercept = emb["intercept"].astype(np.float32)

    def proba_tfidf(self, text: str) -> np.ndarray | None:
        idx, weights = self.tfidf.transform_sparse(text)
        if idx.size == 0:
            return None
        return softmax(self.tfidf_coef[:, idx] @ weights + self.tfidf_intercept)

    def proba_embedding(self, embedding) -> np.ndarray | None:
        if self.emb_coef is None or embedding is None:
            return None
        vec = np.asarray(embedding, dtype=np.float32)
        if vec.shape[0] != self.emb_coef.shape[1]:
            return None
        return softmax(self.emb_coef @ vec + self.emb_intercept)

    def predict(self, text: str, embedding=None, top_k: int = 3) -> dict:
        proba, method = self.proba_embedding(embedding), "embedding_lr"
        if proba is None:
            proba, method = self.proba_tfidf(text), "tfidf_lr"
        if proba is None:
            return {"model": self.version, "method": None, "top": [], "heldout": None}
        order = np.argsort(-proba)[:top_k]
        held = self.card.get("metrics", {}).get(method, {})
        return {
            "model": f"{self.version}/{method}",
            "method": method,
            "heldout": {"accuracy": held.get("accuracy"), "macro_f1": held.get("macro_f1"),
                        "note": self.card.get("evaluation_note")},
            "top": [{"label": self.classes[i], "description": self.card.get("class_descriptions", {}).get(self.classes[i]),
                     "probability": round(float(proba[i]), 4)} for i in order],
        }


@lru_cache(maxsize=4)
def get(name: str) -> TextClassifier | None:
    directory = latest_version_dir(name)
    if directory is None:
        logger.warning("No %s model found.", name)
        return None
    try:
        return TextClassifier(directory)
    except (OSError, KeyError, ValueError) as exc:
        logger.error("Could not load %s model: %s", name, exc)
        return None


def predict(name: str, text: str, embedding=None) -> dict | None:
    model = get(name)
    return model.predict(text, embedding) if model else None
