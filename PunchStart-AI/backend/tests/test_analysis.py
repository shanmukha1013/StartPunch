"""Analysis engine tests. The LLM is replaced by a deterministic stub — production uses the real Gemini API."""
from __future__ import annotations

import pytest

from startpunch import llm
from startpunch.analysis import generate, pipeline, scoring
from startpunch.analysis.sections import GROUPS, SECTION_ORDER
from startpunch.analysis.signals import AnalysisInput, heuristic

IDEA = {"idea": "An AI assistant that reconciles invoices and FX payments for small exporters automatically.",
        "name": "ReconcileAI", "target_customers": "SME exporters with 50+ invoices a month",
        "revenue_model": "Monthly SaaS subscription", "stage": "mvp", "geography": "India",
        "traction": "12 exporters on the waitlist, 3 paid pilots"}


class StubLLM:
    """Returns schema-shaped JSON based on what the prompt asks for."""

    def __init__(self):
        self.calls = []

    def generate_json(self, prompt, *, system=None, schema=None, **kwargs):
        self.calls.append(prompt[:80])
        props = (schema or {}).get("properties", {})
        if "customer_type" in props:  # signal extraction
            data = {"one_liner": "AI invoice reconciliation for exporters", "customer_type": "b2b", "buyer": "finance lead",
                    "problem_frequency": "frequent", "problem_cost": "high", "problem_quote": "reconciles invoices",
                    "differentiation_quote": "", "revenue_model": "saas_subscription", "price_point": "mid",
                    "technical_complexity": "medium", "complexity_drivers": ["bank integrations"],
                    "regulated_domains": ["payments / lending"], "capital_intensity": "low", "operational_intensity": "medium",
                    "network_effects": False, "traction_quotes": ["3 paid pilots", "invented quote not in input"],
                    "channels_mentioned": [], "competitors_mentioned": [], "search_queries": ["invoice reconciliation exporters"],
                    "missing_information": ["pricing"], "geography": "India"}
        elif schema and schema.get("type") == "ARRAY":  # relevance grading
            ids = [line.split("id=")[1].split(" |")[0] for line in prompt.splitlines() if line.startswith("- id=")]
            data = [{"id": i, "relation": "unrelated" if "tutor" in i or "shipfast" in i else "direct_competitor",
                     "relevance": 0 if "tutor" in i or "shipfast" in i else 3, "reason": "stub"} for i in ids]
        elif "sections" in props:
            keys = props["sections"]["items"]["properties"]["key"]["enum"]
            data = {"sections": [{
                "key": k, "summary": f"Summary for {k}.",
                "points": [{"text": "InvoiceBot reconciles invoices for exporters.", "basis": "fact", "sources": ["S1", "S99"]},
                           {"text": "The market is worth $5 billion.", "basis": "fact", "sources": ["S1"]},
                           {"text": "Start with exporters in one city.", "basis": "recommendation", "sources": []}],
                "metrics": [{"label": "TAM", "value": "$2B", "basis": "fact", "note": "made up"}],
                "groups": [], "table": {"columns": ["Hypothesis", "Experiment", "Success metric", "Threshold"],
                                        "rows": [["Exporters will pay", "Paid pilot", "Conversion", "3 of 10"]]},
                "missing": [], "confidence": "medium"} for k in keys]}
        else:
            data = {}
        return llm.LLMResult(data=data, model="stub-model", latency_ms=1)


@pytest.fixture()
def stub(monkeypatch):
    s = StubLLM()
    monkeypatch.setattr(llm, "generate_json", s.generate_json)
    monkeypatch.setattr(llm, "available", lambda: True)

    def no_embed(*a, **k):
        raise llm.LLMUnavailable("no embeddings in tests")

    monkeypatch.setattr(llm, "embed", no_embed)
    monkeypatch.setattr(llm, "embed_query", no_embed)
    return s


def test_rubric_is_bounded_and_explained():
    data = AnalysisInput(**IDEA)
    sig = heuristic(data)
    result = scoring.score(sig, data, {"competitors": {"direct": [], "indirect": []}, "shutdowns": [], "sector_stats": None})
    assert 0 <= result["overall"] <= 100
    assert len(result["dimensions"]) == 13
    assert sum(d["weight"] for d in result["dimensions"]) == 100
    for d in result["dimensions"]:
        assert 0 <= d["score"] <= 10 and d["rationale"] and d["next_step"] and d["confidence"] in {"low", "medium", "high"}
    assert "not a statistically validated" in result["method"].lower()
    assert result["signals_method"] == "heuristic"


def test_rubric_rewards_validation_evidence():
    base = AnalysisInput(idea=IDEA["idea"], stage="idea")
    strong = AnalysisInput(**{**IDEA, "stage": "paying_customers"})
    ev = {"competitors": {"direct": [], "indirect": []}, "shutdowns": [], "sector_stats": None}
    weak_score = next(d for d in scoring.score(heuristic(base), base, ev)["dimensions"] if d["key"] == "validation_evidence")
    strong_score = next(d for d in scoring.score(heuristic(strong), strong, ev)["dimensions"] if d["key"] == "validation_evidence")
    assert strong_score["score"] > weak_score["score"]


def test_citation_validation_removes_and_downgrades():
    evidence = {"sources": [{"sid": "S1", "name": "InvoiceBot", "title": "Launch HN: InvoiceBot",
                             "snippet": "InvoiceBot reconciles invoices for exporters.", "date": "2024-03-01"}]}
    sections = {"market_research": {"points": [
        {"text": "InvoiceBot reconciles invoices for exporters.", "basis": "fact", "sources": ["S1", "S42"]},
        {"text": "The market is $5 billion [S1].", "basis": "fact", "sources": []},
        {"text": "Nobody cited this.", "basis": "fact", "sources": []},
        {"text": "Invented [S7] claim.", "basis": "assumption", "sources": []},
    ], "metrics": [{"label": "TAM", "value": "$2B", "basis": "fact"}], "table": {}}}
    out, report = generate.validate(sections, evidence)
    points = out["market_research"]["points"]
    assert points[0]["sources"] == ["S1"] and points[0]["basis"] == "fact"
    assert points[1]["basis"] == "unverified"  # number not present in the cited snippet
    assert points[2]["basis"] == "unverified"  # fact without any source
    assert "[S7]" not in points[3]["text"]
    assert out["market_research"]["metrics"][0]["basis"] == "estimate"
    assert report["citations_removed"] >= 2 and report["facts_downgraded"] == 2


def _create(client):
    from tests.conftest import signup
    signup(client)
    response = client.post("/api/reports", json=IDEA)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_pipeline_end_to_end_with_stub_llm(client, stub):
    report_id = _create(client)
    statuses = []
    for _ in range(8):
        payload = client.post(f"/api/reports/{report_id}/advance").json()
        statuses.append(payload["stage"])
        if payload["status"] in {"complete", "partial", "failed"}:
            break
    assert payload["status"] == "complete", payload
    assert statuses[:3] == ["research", "write", "synthesize"]
    report = client.get(f"/api/reports/{report_id}").json()
    result = report["result"]
    assert set(SECTION_ORDER) <= set(result["sections"])
    assert len(SECTION_ORDER) == 35  # the requested 34 topics; direct and indirect competitors are separate sections
    # Retrieval + grading: unrelated companies were dropped, direct competitors kept, shutdown evidence surfaced.
    names = {s["name"] for s in result["evidence"]["sources"]}
    assert "InvoiceBot" in names and "TutorAI" not in names and "ShipFast" not in names
    assert any(s["name"] == "PayDead" for s in result["evidence"]["shutdowns"])
    # Signals: quotes not present in the founder's text were discarded.
    assert result["signals"]["traction_quotes"] == ["3 paid pilots"]
    # Validation: fabricated source ids removed, unsupported numbers downgraded, metric facts relabelled.
    point0, point1 = result["sections"]["market_research"]["points"][:2]
    assert point0["sources"] == ["S1"]
    assert point1["basis"] == "unverified"
    assert result["sections"]["market_sizing"]["metrics"][0]["basis"] == "estimate"
    assert result["validation"]["citations_removed"] > 0
    assert result["engine"]["kb_snapshot"] == "test-snapshot"
    # Validation tracker seeded from the experiments table.
    items = client.get(f"/api/reports/{report_id}/validation").json()["items"]
    assert items and items[0]["title"] == "Exporters will pay"
    # Exports
    md = client.get(f"/api/reports/{report_id}/export?format=md")
    assert md.status_code == 200 and "## Sources" in md.text and "[S1] InvoiceBot" in md.text
    assert client.get(f"/api/reports/{report_id}/export?format=json").json()["title"]


def test_pipeline_without_ai_is_honest(client):
    """No API key: the report must not contain fabricated analysis."""
    report_id = _create(client)
    for _ in range(8):
        payload = client.post(f"/api/reports/{report_id}/advance").json()
        if payload["status"] in {"complete", "partial", "failed"}:
            break
    assert payload["status"] == "partial"
    result = client.get(f"/api/reports/{report_id}").json()["result"]
    assert result["signals"]["method"] == "heuristic"
    assert result["scores"]["overall"] > 0  # rubric still works (transparent heuristics)
    assert all(result["sections"][k].get("unavailable") for k in SECTION_ORDER)
    assert "not configured" in result["sections"]["executive_summary"]["summary"]
    assert result["evidence"]["retrieval"]["mode"] == "lexical"
    assert all(s["relation"] == "unclassified" for s in result["evidence"]["sources"])


def test_report_isolation_between_users(make_client, stub):
    a, _ = make_client("Ada", "ada@example.com")
    b, _ = make_client("Ben", "ben@example.com")
    report_id = a.post("/api/reports", json=IDEA).json()["id"]
    assert b.get(f"/api/reports/{report_id}").status_code == 404
    assert b.post(f"/api/reports/{report_id}/advance").status_code == 404
    assert b.get(f"/api/reports/{report_id}/export").status_code == 404


def test_assistant_filters_invented_citations(client, stub, monkeypatch):
    report_id = _create(client)
    pipeline.run_to_completion(report_id)

    def fake_answer(prompt, **kwargs):
        return llm.LLMResult(data={"answer": "Your closest competitor is InvoiceBot [S1]; also see [S77].",
                                   "citations": ["S1", "S77"], "answer_type": "grounded", "follow_ups": ["How do I differ?"]},
                             model="stub-model", latency_ms=1)

    monkeypatch.setattr(llm, "generate_json", fake_answer)
    reply = client.post(f"/api/reports/{report_id}/chat", json={"message": "Who are my biggest competitors?"}).json()
    assert "[S77]" not in reply["content"]
    assert [s["sid"] for s in reply["meta"]["sources"]] == ["S1"]
    assert reply["meta"]["citations_removed"] == 1
    history = client.get(f"/api/reports/{report_id}/chat").json()["messages"]
    assert [m["role"] for m in history] == ["user", "assistant"]


def test_clarify_rule_fallback(client):
    from tests.conftest import signup
    signup(client)
    response = client.post("/api/analysis/clarify", json={"idea": "A marketplace connecting home cooks with office workers for lunch."})
    body = response.json()
    assert body["method"] == "rules"
    assert any(q["field"] == "target_customers" for q in body["questions"])


def test_publish_report_shares_only_chosen_fields(make_client, stub):
    a, ua = make_client("Ada", "ada@example.com")
    b, _ = make_client("Ben", "ben@example.com")
    report_id = a.post("/api/reports", json=IDEA).json()["id"]
    pipeline.run_to_completion(report_id)
    published = a.post(f"/api/reports/{report_id}/publish", json={"name": "ReconcileAI", "tagline": "Reconciliation for exporters",
                                                                   "share_score": False, "feedback_question": "Would you pay?"}).json()
    page = b.get(f"/api/startups/{published['startup_id']}").json()
    assert "score" not in page["public_summary"]
    assert page["has_report"] is None  # never reveals private report linkage to others
    assert "traction" not in str(page)  # founder inputs stay private
    assert page["updates"][0]["title"].startswith("Feedback wanted")


def test_compare_and_watchlist(client, stub):
    first = _create(client)
    second = client.post("/api/reports", json={**IDEA, "name": "Other", "stage": "idea"}).json()["id"]
    pipeline.run_to_completion(first)
    pipeline.run_to_completion(second)
    compared = client.get(f"/api/reports-compare?ids={first},{second}").json()["reports"]
    assert len(compared) == 2 and set(compared[0]["dimensions"]) == {d[0] for d in scoring.DIMENSIONS}
    assert client.post("/api/watchlist", json={"company_id": "hn:invoicebot", "report_id": first}).status_code == 201
    items = client.get("/api/watchlist").json()["items"]
    assert items[0]["company"]["name"] == "InvoiceBot"
    assert client.post("/api/watchlist", json={"company_id": "hn:doesnotexist"}).status_code == 404


def test_legacy_import_is_marked(client):
    from tests.conftest import signup
    signup(client)
    response = client.post("/api/reports/import-legacy", json={"reports": [
        {"startup_name": "Old Idea", "industry": "Fintech", "startup_score": 82, "data": {"executive_summary": "Old text"}}]})
    assert response.json()["imported"] == 1
    reports = client.get("/api/reports").json()["reports"]
    assert reports[0]["legacy"] is True and reports[0]["score"] == 82
    assert client.post(f"/api/reports/{reports[0]['id']}/chat", json={"message": "hi"}).status_code == 409
