"""Offline training + evaluation (requires scikit-learn; see requirements-ml.txt).

Text classifiers (``industry`` and ``business_model``)
------------------------------------------------------
* Inputs: an entity description (TF-IDF model) or its 256-d Gemini embedding (embedding model).
* Labels: "silver" labels assigned by an LLM to a sample of knowledge-base entities
  (see ``ingest/llm_labels.py``). The models distil those labels into a fast classifier
  that needs no API call and is consistent across the corpus.
* Split: stratified 80/20 hold-out, seed 42; classes with < MIN_CLASS_SIZE examples are dropped.
* Metrics: accuracy / macro-F1 / per-class F1 on the hold-out split — i.e. *agreement with the
  LLM labels*, not accuracy against human ground truth. A majority-class baseline is reported.

Clustering
----------
k-means on company embeddings; k chosen by silhouette; clusters described by c-TF-IDF terms.

Artifacts are versioned under ``backend/data/models/<name>/v<N>/`` with a model card.
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from pathlib import Path

import numpy as np

from ..utils import utcnow
from .classifier import MODELS_DIR

logger = logging.getLogger("startpunch.ml.train")
MIN_CLASS_SIZE = 20
SEED = 42


def _next_version(name: str) -> Path:
    base = MODELS_DIR / name
    base.mkdir(parents=True, exist_ok=True)
    existing = [int(p.name[1:]) for p in base.iterdir() if p.is_dir() and p.name[1:].isdigit()]
    path = base / f"v{(max(existing) + 1) if existing else 1}"
    path.mkdir()
    return path


def entity_text(company: dict) -> str:
    """Text used for classification. The entity name is removed so models learn content, not names."""
    parts = [company.get("description") or ""]
    for doc in company.get("documents", [])[:3]:
        parts.append(f"{doc['tagline']} {doc['text'][:700]}")
    text = " ".join(p for p in parts if p)
    name = company.get("name") or ""
    if len(name) > 2:
        text = re.sub(re.escape(name), " ", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def _metrics(y_true, y_pred, classes) -> dict:
    from sklearn.metrics import accuracy_score, classification_report, f1_score

    report = classification_report(y_true, y_pred, output_dict=True, zero_division=0)
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "macro_f1": round(float(f1_score(y_true, y_pred, average="macro")), 4),
        "weighted_f1": round(float(f1_score(y_true, y_pred, average="weighted")), 4),
        "per_class_f1": {classes[int(k)]: round(v["f1-score"], 3) for k, v in report.items() if k.isdigit()},
    }


def train_classifier(name: str, records: list[dict], vectors: dict[str, np.ndarray] | None, snapshot_id: str,
                     task: str, label_source: str, class_descriptions: dict[str, str]) -> tuple[Path, dict]:
    """records: [{id, text, label}]"""
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import f1_score
    from sklearn.model_selection import train_test_split

    counts = Counter(r["label"] for r in records)
    keep = {label for label, n in counts.items() if n >= MIN_CLASS_SIZE}
    records = [r for r in records if r["label"] in keep and len(r["text"]) >= 20]
    classes = sorted(keep)
    texts = [r["text"] for r in records]
    y = np.array([classes.index(r["label"]) for r in records])
    ids = np.array([r["id"] for r in records])
    idx_train, idx_test = train_test_split(np.arange(len(records)), test_size=0.2, random_state=SEED, stratify=y)

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_df=0.5, sublinear_tf=True, stop_words="english",
                                 max_features=30000)
    x_train = vectorizer.fit_transform([texts[i] for i in idx_train])
    x_test = vectorizer.transform([texts[i] for i in idx_test])
    best = None
    for c in (2.0, 5.0, 10.0):  # small, fixed grid; selection uses 3-fold CV on the training split only
        from sklearn.model_selection import cross_val_score
        score = cross_val_score(LogisticRegression(C=c, max_iter=3000, class_weight="balanced"),
                                x_train, y[idx_train], cv=3, scoring="f1_macro").mean()
        if best is None or score > best[1]:
            best = (c, score)
    clf = LogisticRegression(C=best[0], max_iter=3000, class_weight="balanced").fit(x_train, y[idx_train])
    metrics = {"tfidf_lr": {**_metrics(y[idx_test], clf.predict(x_test), classes), "C": best[0],
                            "cv_macro_f1_train": round(float(best[1]), 4)}}
    majority = Counter(y[idx_train]).most_common(1)[0][0]
    metrics["majority_baseline"] = {
        "accuracy": round(float(np.mean(y[idx_test] == majority)), 4),
        "macro_f1": round(float(f1_score(y[idx_test], np.full_like(y[idx_test], majority), average="macro")), 4),
    }
    logger.info("%s tfidf_lr: acc=%s macroF1=%s", name, metrics["tfidf_lr"]["accuracy"], metrics["tfidf_lr"]["macro_f1"])

    emb_clf = None
    if vectors:
        have = np.array([i in vectors for i in ids])
        tr, te = idx_train[have[idx_train]], idx_test[have[idx_test]]
        if len(tr) > 100 and len(te) > 20:
            x_tr = np.stack([vectors[ids[i]] for i in tr])
            x_te = np.stack([vectors[ids[i]] for i in te])
            emb_clf = LogisticRegression(C=4.0, max_iter=4000, class_weight="balanced").fit(x_tr, y[tr])
            metrics["embedding_lr"] = _metrics(y[te], emb_clf.predict(x_te), classes)
            logger.info("%s embedding_lr: acc=%s macroF1=%s", name, metrics["embedding_lr"]["accuracy"], metrics["embedding_lr"]["macro_f1"])

    out = _next_version(name)
    (out / "tfidf.json").write_text(json.dumps({
        "vocabulary": {t: int(i) for t, i in vectorizer.vocabulary_.items()},
        "idf": [round(float(v), 6) for v in vectorizer.idf_],
        "stop_words": sorted(ENGLISH_STOP_WORDS), "ngram_range": [1, 2], "sublinear_tf": True,
    }), encoding="utf-8")
    np.savez_compressed(out / "tfidf_lr.npz", coef=clf.coef_.astype(np.float32), intercept=clf.intercept_.astype(np.float32))
    if emb_clf is not None:
        np.savez_compressed(out / "embedding_lr.npz", coef=emb_clf.coef_.astype(np.float32),
                            intercept=emb_clf.intercept_.astype(np.float32))
    card = {
        "name": name, "version": out.name, "trained_at": utcnow().isoformat(), "kb_snapshot": snapshot_id,
        "task": task,
        "inputs": "Entity description text (tfidf_lr) or a 256-d gemini-embedding-001 vector (embedding_lr).",
        "outputs": "Probability per class; top-3 returned with the model version.",
        "label_source": label_source,
        "training_data": {"examples": len(records), "train": int(len(idx_train)), "test": int(len(idx_test)),
                          "class_counts": {classes[i]: int(n) for i, n in sorted(Counter(y).items())},
                          "dropped_classes": sorted(set(counts) - keep), "min_class_size": MIN_CLASS_SIZE},
        "evaluation_note": "Hold-out metrics measure agreement with LLM-assigned (silver) labels, not human ground truth.",
        "known_limitations": [
            "Silver labels inherit LLM mistakes and ambiguity between neighbouring classes.",
            "Training entities come from Hacker News launches (tech-heavy, US-heavy, 2007-present).",
            "Multi-category products are forced into a single label.",
        ],
        "classes": classes,
        "class_descriptions": {c: class_descriptions.get(c, c) for c in classes},
        "metrics": metrics,
    }
    (out / "card.json").write_text(json.dumps(card, indent=2), encoding="utf-8")
    logger.info("%s model written to %s", name, out)
    return out, card


def train_clusters(company_ids: list[str], vectors: np.ndarray, texts: list[str], sectors: list[str | None],
                   snapshot_id: str, k_values: tuple[int, ...] = (10, 14, 18, 22, 26, 30)) -> tuple[Path, dict, np.ndarray]:
    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import CountVectorizer
    from sklearn.metrics import silhouette_score

    rng = np.random.default_rng(SEED)
    sample = rng.choice(len(vectors), size=min(3000, len(vectors)), replace=False)
    scores: dict[int, float] = {}
    for k in k_values:
        model = KMeans(n_clusters=k, n_init=4, random_state=SEED).fit(vectors[sample])
        scores[k] = float(silhouette_score(vectors[sample], model.labels_, metric="cosine"))
        logger.info("kmeans k=%s silhouette=%.4f", k, scores[k])
    best_k = max(scores, key=scores.get)
    model = KMeans(n_clusters=best_k, n_init=8, random_state=SEED).fit(vectors)
    labels = model.labels_

    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

    # Launch-post boilerplate carries no topical meaning; keep it out of cluster descriptions.
    generic = {"people", "like", "online", "company", "companies", "use", "using", "used", "make", "makes", "way", "help", "helps",
               "new", "just", "need", "want", "built", "build", "building", "time", "work", "works", "app", "apps", "tool", "tools",
               "product", "products", "service", "platform", "free", "easy", "simple", "hn", "hi", "hey", "today", "launch",
               "launching", "startup", "startups", "users", "user", "team", "thanks", "feedback", "love", "yc", "ve", "ll", "don",
               "really", "lot", "lots", "better", "good", "great", "able", "based", "day", "year", "years", "world", "things", "thing"}
    cv = CountVectorizer(stop_words=list(ENGLISH_STOP_WORDS | generic), min_df=3, max_df=0.2, ngram_range=(1, 2),
                         max_features=30000, token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z]+\b")
    counts = cv.fit_transform(texts)
    terms = np.array(cv.get_feature_names_out())
    total = np.asarray(counts.sum(axis=0)).ravel() + 1
    clusters = []
    for c in range(best_k):
        members = np.where(labels == c)[0]
        tf = np.asarray(counts[members].sum(axis=0)).ravel()
        weight = (tf / (tf.sum() or 1)) * np.log(1 + total.sum() / total)
        sector_counts = Counter(sectors[i] for i in members if sectors[i])
        centroid = model.cluster_centers_[c] / (np.linalg.norm(model.cluster_centers_[c]) or 1)
        nearest = members[np.argsort(-(vectors[members] @ centroid))[:6]]
        clusters.append({
            "id": int(c), "size": int(len(members)), "top_terms": [str(t) for t in terms[np.argsort(-weight)[:8]]],
            "dominant_sectors": [{"sector": s, "share": round(n / len(members), 3)} for s, n in sector_counts.most_common(2)],
            "examples": [company_ids[i] for i in nearest],
        })
    out = _next_version("clusters")
    centers = model.cluster_centers_ / np.linalg.norm(model.cluster_centers_, axis=1, keepdims=True)
    np.save(out / "centroids.npy", centers.astype(np.float32))
    card = {
        "name": "market-clusters", "version": out.name, "trained_at": utcnow().isoformat(), "kb_snapshot": snapshot_id,
        "algorithm": "k-means on L2-normalized entity embeddings (gemini-embedding-001, 256-d)",
        "k_selection": {"candidates": list(k_values), "silhouette_cosine_sample": {str(k): round(v, 4) for k, v in scores.items()},
                        "chosen_k": best_k},
        "clusters": clusters,
        "limitations": ["Clusters describe the knowledge base's coverage (HN launches), not the whole market.",
                        "Silhouette scores for text embeddings are typically low because topics overlap; treat clusters as a map."],
    }
    (out / "card.json").write_text(json.dumps(card, indent=2), encoding="utf-8")
    return out, card, labels
