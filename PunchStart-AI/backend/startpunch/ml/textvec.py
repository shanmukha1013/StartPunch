"""Numpy re-implementation of scikit-learn's TfidfVectorizer.transform (inference only).

Training happens offline with scikit-learn; the fitted vocabulary/idf/stop-words are exported
to JSON so production inference needs only numpy. ``tests/test_ml.py`` checks parity.
"""
from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np

TOKEN_RE = re.compile(r"(?u)\b\w\w+\b")


class TfidfInference:
    def __init__(self, vocabulary: dict[str, int], idf: list[float], stop_words: list[str],
                 ngram_range: tuple[int, int] = (1, 2), sublinear_tf: bool = True):
        self.vocabulary = vocabulary
        self.idf = np.asarray(idf, dtype=np.float32)
        self.stop_words = frozenset(stop_words)
        self.ngram_range = tuple(ngram_range)
        self.sublinear_tf = sublinear_tf

    @classmethod
    def from_dict(cls, data: dict) -> "TfidfInference":
        return cls(data["vocabulary"], data["idf"], data["stop_words"], tuple(data["ngram_range"]), data["sublinear_tf"])

    def _ngrams(self, text: str) -> list[str]:
        tokens = [t for t in TOKEN_RE.findall(text.lower()) if t not in self.stop_words]
        lo, hi = self.ngram_range
        grams: list[str] = []
        for n in range(lo, hi + 1):
            if n == 1:
                grams.extend(tokens)
            else:
                grams.extend(" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1))
        return grams

    def transform_sparse(self, text: str) -> tuple[np.ndarray, np.ndarray]:
        counts = Counter(g for g in self._ngrams(text) if g in self.vocabulary)
        if not counts:
            return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float32)
        idx = np.fromiter((self.vocabulary[g] for g in counts), dtype=np.int64, count=len(counts))
        tf = np.fromiter(((1.0 + math.log(c)) if self.sublinear_tf else float(c) for c in counts.values()),
                         dtype=np.float32, count=len(counts))
        weights = tf * self.idf[idx]
        norm = float(np.linalg.norm(weights)) or 1.0
        return idx, weights / norm


def softmax(scores: np.ndarray) -> np.ndarray:
    shifted = scores - scores.max()
    exp = np.exp(shifted)
    return exp / exp.sum()
