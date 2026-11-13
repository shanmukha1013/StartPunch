import numpy as np
import pytest

from startpunch.ingest.normalize import _parse_shutdown, _split_name, build_chunks, build_companies, chunk_text, normalize_name
from startpunch.kb import retrieval
from startpunch.kb.bm25 import BM25Index, tokenize
from startpunch.ml.textvec import TfidfInference, softmax
from tests.conftest import make_kb


# ---------------------------------------------------------------- normalization / entity resolution
def test_title_parsing():
    assert _split_name("Acme (YC W21) – AI for invoices") == ("Acme", "AI for invoices")
    assert _split_name("I built a tool that does X") == (None, "I built a tool that does X")
    assert _parse_shutdown("FloydHub Is Shutting Down") == "FloydHub"
    assert _parse_shutdown("Cloudflare outage on November 18 post mortem") is None
    assert normalize_name("Acme Labs, Inc.") == "acme"


def test_entity_resolution_merges_by_domain_and_name():
    streams = {
        "hn_launch": {"fetched_at": "t", "hits": [
            {"id": "1", "title": "Launch HN: Acme (YC W21) – AI for invoices", "url": "https://acme.io",
             "story_text": "We help exporters reconcile invoices with AI. " * 3, "points": 50, "num_comments": 10,
             "created_at": "2021-03-01T00:00:00Z", "created_at_i": 1}]},
        "hn_show": {"fetched_at": "t", "hits": [
            {"id": "2", "title": "Show HN: Acme – invoices on autopilot", "url": "https://acme.io/new",
             "story_text": "", "points": 150, "num_comments": 5, "created_at": "2022-01-01T00:00:00Z", "created_at_i": 2},
            {"id": "3", "title": "Show HN: I made a thing", "url": "https://thing.dev", "story_text": "", "points": 100,
             "num_comments": 1, "created_at": "2022-01-01T00:00:00Z", "created_at_i": 3}]},
        "hn_shutdown": {"fetched_at": "t", "hits": [
            {"id": "4", "title": "Acme is shutting down", "url": "https://medium.com/acme-post", "story_text": "",
             "points": 90, "num_comments": 40, "created_at": "2023-06-01T00:00:00Z", "created_at_i": 4}]},
    }
    companies, report = build_companies(streams, 2026)
    assert len(companies) == 1  # Show HN with no name is skipped; Acme merged across 3 streams
    acme = companies[0]
    assert acme["status"] == "shutdown_announced" and acme["batch"] == "YC W21"
    assert [d["kind"] for d in acme["documents"]] == ["launch", "show", "shutdown"]
    assert report.resolved_by_domain == 1 and report.resolved_by_name == 1
    assert report.rejected["no_identifiable_name"] == 1
    assert len(build_chunks(companies)) == 3


def test_chunking_respects_limit_and_overlaps():
    text = " ".join(f"Sentence number {i} is here." for i in range(80))
    chunks = chunk_text(text, max_chars=200)
    assert all(len(c) <= 200 for c in chunks) and len(chunks) > 5
    assert chunks[0].split(". ")[-1].rstrip(".") in chunks[1]  # one-sentence overlap


# ------------------------------------------------------------------------------ retrieval
def test_bm25_ranks_relevant_first():
    index = BM25Index(["invoice reconciliation for exporters", "math tutoring for students", "delivery routing"])
    assert index.search("reconcile invoices")[0][0] == 0
    assert tokenize("Invoices invoice invoicing") == ["invoic"] * 3
    assert tokenize("tutor tutoring") == ["tutor", "tutor"]


def test_lexical_search_and_filters():
    kb = make_kb()
    hits, diag = retrieval.search(["invoice reconciliation exporters"], mode="lexical", kb=kb)
    assert hits[0]["name"] == "InvoiceBot" and diag["mode"] == "lexical"
    assert hits[0]["evidence"][0]["url"].startswith("https://news.ycombinator.com/")
    only_shutdowns, _ = retrieval.search(["invoice payments"], mode="lexical", kb=kb,
                                         filters=retrieval.Filters(statuses=["shutdown_announced"]))
    assert [h["name"] for h in only_shutdowns] == ["PayDead"]
    edtech, _ = retrieval.search(["ai"], mode="lexical", kb=kb, filters=retrieval.Filters(sectors=["edtech"]))
    assert {h["sector"] for h in edtech} == {"edtech"}


def test_hybrid_fuses_dense_and_lexical():
    kb = make_kb(with_embeddings=True)
    target = kb.embeddings[2]  # TutorAI's vector
    hits, diag = retrieval.search(["invoice reconciliation"], query_embeddings=[target.tolist()], kb=kb)
    names = [h["name"] for h in hits]
    assert diag["mode"] == "hybrid"
    assert names[0] == "InvoiceBot"   # strong in both rankers
    assert "TutorAI" in names[:4]      # only the dense ranker finds it; fusion keeps it


def test_named_competitor_boost():
    kb = make_kb()
    hits, _ = retrieval.search(["bookkeeping"], mode="lexical", boost_names=["Ledgerly"], kb=kb)
    assert hits[0]["name"] == "Ledgerly"


# ------------------------------------------------------------------------------------- ML
def test_tfidf_numpy_matches_sklearn():
    sklearn = pytest.importorskip("sklearn")
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
    from sklearn.linear_model import LogisticRegression

    texts = ["payments api for online stores", "math tutoring with ai", "invoice payments for exporters",
             "ai tutor for students", "card payments and banking", "online courses and quizzes"]
    labels = [0, 1, 0, 1, 0, 1]
    vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
    x = vec.fit_transform(texts)
    clf = LogisticRegression(max_iter=500).fit(x, labels)
    ours = TfidfInference({k: int(v) for k, v in vec.vocabulary_.items()}, vec.idf_.tolist(), sorted(ENGLISH_STOP_WORDS))
    query = "payments for online stores and exporters"
    idx, weights = ours.transform_sparse(query)
    dense = np.zeros(len(vec.vocabulary_))
    dense[idx] = weights
    np.testing.assert_allclose(dense, vec.transform([query]).toarray()[0], atol=1e-6)
    proba = softmax(np.r_[0.0, (clf.coef_[0][idx] @ weights + clf.intercept_[0])])
    np.testing.assert_allclose(proba[1], clf.predict_proba(vec.transform([query]))[0][1], atol=1e-5)


def test_trained_models_load_if_present():
    from startpunch.ml import classifier

    model = classifier.get("industry")
    if model is None:
        pytest.skip("knowledge base not built in this checkout")
    result = model.predict("Stripe-like payments API for online merchants and card processing")
    assert result["top"][0]["probability"] > 0 and result["method"] == "tfidf_lr"
    assert "silver" in model.card["evaluation_note"].lower() or "llm" in model.card["evaluation_note"].lower()
