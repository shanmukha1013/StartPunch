"""Test fixtures. Tests never call external APIs: the LLM is disabled or replaced by a stub."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["SESSION_SECRET"] = "test-secret-" + "x" * 40
os.environ["GEMINI_API_KEY"] = ""
os.environ["STARTPUNCH_ENV"] = "test"
os.environ["SERVE_FRONTEND"] = "0"
os.environ["ADMIN_EMAILS"] = "admin@example.com"
os.environ["DAILY_REPORT_QUOTA"] = "50"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from startpunch import config, db, ratelimit  # noqa: E402
from startpunch.kb import store  # noqa: E402
from startpunch.kb.bm25 import BM25Index  # noqa: E402

config.get_settings.cache_clear()


def _company(cid, name, description, sector, status="launched", entity_type="startup", date="2024-03-01", text=""):
    return {"id": cid, "name": name, "entity_type": entity_type, "description": description, "sector": sector,
            "sector_label": sector, "sector_source": "llm_label", "business_model": "saas_subscription",
            "status": status, "batch": "YC W24" if entity_type == "startup" else None, "first_launch": date,
            "shutdown_date": date if status == "shutdown_announced" else None, "website": f"https://{cid[3:]}.example",
            "max_points": 120, "documents": [{"kind": "shutdown" if status == "shutdown_announced" else "launch",
                                              "title": f"Launch HN: {name} – {description}", "tagline": description,
                                              "date": date, "url": f"https://news.ycombinator.com/item?id={abs(hash(cid)) % 10**8}",
                                              "points": 120, "comments": 40, "text": text or description}],
            "sources": [{"source": "hn_launch", "url": "https://news.ycombinator.com/item?id=1"}]}


TEST_COMPANIES = [
    _company("hn:invoicebot", "InvoiceBot", "AI invoice reconciliation for small exporters", "fintech",
             text="InvoiceBot reconciles invoices, FX payments and bank statements for exporters with AI."),
    _company("hn:ledgerly", "Ledgerly", "Bookkeeping automation for freelancers", "fintech",
             text="Ledgerly automates bookkeeping and tax estimates for freelancers and consultants."),
    _company("hn:tutorai", "TutorAI", "AI tutor for high-school math", "edtech",
             text="TutorAI gives students step by step math tutoring with an AI model."),
    _company("hn:shipfast", "ShipFast", "Last-mile delivery routing for couriers", "logistics",
             text="ShipFast optimizes last-mile delivery routes for courier companies."),
    _company("hn:paydead", "PayDead", "Payments app for invoices", "fintech", status="shutdown_announced",
             entity_type="company", date="2022-05-01", text="PayDead is shutting down. Invoice payments were hard to monetize."),
]


def make_kb(with_embeddings: bool = False) -> store.KnowledgeBase:
    companies = {c["id"]: c for c in TEST_COMPANIES}
    chunks = []
    for c in TEST_COMPANIES:
        d = c["documents"][0]
        chunks.append({"id": f"ch-{c['id']}", "company_id": c["id"], "kind": d["kind"], "source": f"hn_{d['kind']}",
                       "url": d["url"], "date": d["date"], "title": d["title"], "points": 120, "text": d["text"], "seq": 0})
    docs = [f"{companies[ch['company_id']]['name']} {ch['title']} {ch['text']}" for ch in chunks]
    embeddings = None
    if with_embeddings:
        rng = np.random.default_rng(0)
        embeddings = rng.normal(size=(len(chunks), 8)).astype(np.float32)
        embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
    company_chunks = {}
    for i, ch in enumerate(chunks):
        company_chunks.setdefault(ch["company_id"], []).append(i)
    stats = {"sectors": {"fintech": {"sector": "fintech", "label": "FinTech", "entities": 3, "shutdown_announcements": 1,
                                     "launch_share_trend": {"direction": "rising", "prior_count": 4, "recent_count": 9}}},
             "caveats": ["test"]}
    manifest = {"snapshot_id": "test-snapshot", "built_at": "2026-11-13T00:00:00+00:00", "counts": {"entities": 5},
                "freshness_policy_days": 30, "sources": []}
    return store.KnowledgeBase(manifest, companies, chunks, embeddings, company_chunks, BM25Index(docs), stats)


@pytest.fixture(autouse=True)
def fresh_state(tmp_path):
    db.reset_for_tests(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    ratelimit.reset()
    store.set_kb(make_kb())
    yield
    store.set_kb(None)


@pytest.fixture()
def client():
    from startpunch.main import app

    with TestClient(app) as c:
        c.headers.update({"X-StartPunch-Client": "web"})
        yield c


def signup(client, name="Ada Founder", email=None, password="Founder123"):
    email = email or f"{name.split()[0].lower()}@example.com"
    response = client.post("/api/auth/signup", json={"name": name, "email": email, "password": password})
    assert response.status_code == 201, response.text
    return response.json()["user"]


@pytest.fixture()
def make_client():
    """Factory for independent clients (separate cookie jars = separate users)."""
    from startpunch.main import app

    clients = []

    def factory(name="Member", email=None):
        c = TestClient(app)
        c.headers.update({"X-StartPunch-Client": "web"})
        clients.append(c)
        user = signup(c, name, email)
        return c, user

    yield factory
    for c in clients:
        c.close()
