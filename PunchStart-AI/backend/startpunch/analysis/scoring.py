"""Transparent startup evaluation rubric (rule-based).

This is NOT a statistically validated prediction of startup success: there is no outcome data
in the knowledge base that would support one. Each dimension applies an explicit rule to
(a) structured signals extracted from the founder's input and (b) evidence retrieved from the
knowledge base. Every score carries its rationale, evidence, confidence, missing information
and the cheapest next validation step.
"""
from __future__ import annotations

from dataclasses import dataclass

RUBRIC_VERSION = "rubric-1.0"
METHOD_NOTE = ("Rule-based rubric: explicit rules over founder-provided signals and retrieved evidence. "
               "Not a statistically validated predictor of startup success.")

DIMENSIONS: list[tuple[str, str, int]] = [
    ("problem_severity", "Problem severity", 10),
    ("market_opportunity", "Market opportunity", 9),
    ("market_growth", "Market momentum", 7),
    ("competition", "Competitive pressure", 8),
    ("differentiation", "Differentiation", 9),
    ("business_model", "Business model clarity", 8),
    ("revenue_potential", "Revenue potential", 8),
    ("customer_acquisition", "Customer acquisition ease", 8),
    ("technical_feasibility", "Technical feasibility", 7),
    ("execution_complexity", "Execution simplicity", 7),
    ("financial_viability", "Financial viability", 7),
    ("regulatory_risk", "Regulatory exposure (inverse)", 6),
    ("validation_evidence", "Validation evidence", 6),
]


@dataclass
class Dim:
    score: float
    rationale: str
    evidence: list[dict]
    confidence: str
    missing: list[str]
    next_step: str


def _clamp(value: float) -> float:
    return round(max(0.0, min(10.0, value)), 1)


def _ev(text: str, sources: list[str] | None = None) -> dict:
    return {"text": text, "sources": sources or []}


def score(signals: dict, data, evidence: dict) -> dict:
    """``data`` is an AnalysisInput; ``evidence`` is the research-stage evidence bundle."""
    heuristic = signals.get("method") != "llm"
    inferred = "medium" if not heuristic else "low"
    dims: dict[str, Dim] = {}
    direct = evidence.get("competitors", {}).get("direct", [])
    indirect = evidence.get("competitors", {}).get("indirect", [])
    shutdowns = evidence.get("shutdowns", [])
    sector_stats = evidence.get("sector_stats") or {}
    sid = lambda items: [i["sid"] for i in items if i.get("sid")][:6]  # noqa: E731

    # 1. Problem severity
    freq, cost = signals.get("problem_frequency", "unclear"), signals.get("problem_cost", "unclear")
    freq_pts = {"constant": 4.5, "frequent": 3.5, "occasional": 2.0, "rare": 1.0}.get(freq, 2.5)
    cost_pts = {"high": 4.5, "medium": 3.0, "low": 1.5}.get(cost, 2.5)
    quote = signals.get("problem_quote")
    s = freq_pts + cost_pts + (1.0 if quote else 0.0)
    dims["problem_severity"] = Dim(
        _clamp(s), f"Problem described as {freq} with {cost} cost to the customer"
        + (" — supported by the founder's own wording." if quote else " — inferred, not stated explicitly."),
        [_ev(f'Founder: "{quote}"')] if quote else [],
        "high" if quote and freq != "unclear" and cost != "unclear" else inferred,
        [m for m, v in (("how often the problem occurs", freq == "unclear"), ("what the problem costs today", cost == "unclear")) if v],
        "Run 10-15 problem interviews; ask how often it happens and what they spend on it today.")

    # 2. Market opportunity (reach x willingness to pay) — no sourced market size exists
    customer = signals.get("customer_type", "unclear")
    price = signals.get("price_point", "unclear")
    reach = {"b2c": 3.5, "developers": 3.0, "b2b": 3.0, "b2b2c": 3.5, "marketplace": 3.5, "government": 2.0}.get(customer, 2.5)
    wtp = {"enterprise": 4.5, "high": 4.0, "mid": 3.0, "low": 2.0, "free": 1.0}.get(price, 2.5)
    related = len(direct) + len(indirect)
    activity = 1.5 if related >= 5 else 1.0 if related >= 2 else 0.5
    dims["market_opportunity"] = Dim(
        _clamp(reach + wtp + activity),
        f"{customer.upper() if customer != 'unclear' else 'Unclear'} customer with a {price} price point; "
        f"{related} related products found in the knowledge base (category activity, not market size).",
        [_ev(f"{related} related products/companies retrieved", sid(direct + indirect))],
        "low", ["sourced market size for the target geography", "number of reachable buyers and their budget"],
        "Count reachable buyers in one segment (directories, LinkedIn, associations) and test willingness to pay.")

    # 3. Market momentum — launch-share trend of the predicted sector on HN
    trend = (sector_stats.get("launch_share_trend") or {})
    direction = trend.get("direction", "insufficient data")
    s = {"rising": 7.5, "flat": 5.5, "falling": 4.0}.get(direction, 5.0)
    dims["market_growth"] = Dim(
        _clamp(s),
        f"Sector launch share on Hacker News is {direction}"
        + (f" ({trend.get('prior_count')} → {trend.get('recent_count')} launch posts across 2-year windows)." if trend else "."),
        [_ev(f"Sector: {sector_stats.get('label', 'unknown')}; launch-share trend {direction}")] if sector_stats else [],
        "low" if direction == "insufficient data" else "medium",
        ["industry growth data (analyst reports, public filings) for the target market"],
        "Look for recent funding/launch activity and search-volume trends for the core problem keywords.")

    # 4. Competitive pressure (higher = less crowded)
    n_direct = len(direct)
    s = 8.0 if n_direct == 0 else 6.5 if n_direct <= 2 else 5.0 if n_direct <= 5 else 3.5
    rationale = (f"{n_direct} direct competitor(s) found in the knowledge base"
                 + (" — absence can also mean the knowledge base lacks coverage, or that the market is unproven." if n_direct == 0 else "."))
    dims["competition"] = Dim(_clamp(s), rationale, [_ev(", ".join(c["name"] for c in direct[:6]), sid(direct))] if direct else [],
                              "medium" if direct else "low", ["competitors outside Hacker News coverage (search app stores, G2, local markets)"],
                              "List 10 alternatives customers use today (including spreadsheets/agencies) and how they pay.")

    # 5. Differentiation
    diff_quote = signals.get("differentiation_quote") or data.differentiation
    top_sim = max((c.get("relevance", 0) for c in direct), default=0)
    s = (4.0 if diff_quote else 2.0) + (3.0 if n_direct == 0 else 2.0 if top_sim < 3 else 1.0) + (1.5 if signals.get("network_effects") else 0.5)
    dims["differentiation"] = Dim(
        _clamp(s), ("Founder states a differentiation" if diff_quote else "No explicit differentiation provided")
        + (f"; closest direct competitor rated relevance {top_sim}/3." if direct else "; no close direct competitor retrieved."),
        [_ev(f'Founder: "{diff_quote[:200]}"')] if diff_quote else [], "medium" if diff_quote else "low",
        [] if diff_quote else ["a one-sentence reason customers would switch from today's alternative"],
        "Show the positioning to 5 target users next to the top competitor and ask which they'd pick and why.")

    # 6. Business model clarity
    model = signals.get("revenue_model", "unclear")
    s = 3.0 + (3.5 if data.revenue_model else 0) + (2.0 if model != "unclear" else 0)
    mismatch = model == "advertising" and customer == "b2b"
    if mismatch:
        s -= 2.0
    dims["business_model"] = Dim(
        _clamp(s), (f"Revenue model: {model.replace('_', ' ')}" if model != "unclear" else "Revenue model unclear")
        + (" (stated by founder)." if data.revenue_model else " (inferred).") + (" Advertising rarely suits B2B buyers." if mismatch else ""),
        [_ev(f'Founder: "{data.revenue_model}"')] if data.revenue_model else [], "high" if data.revenue_model else inferred,
        [] if data.revenue_model else ["who pays and how (subscription, usage, commission...)"],
        "Put a price on a landing page or in a sales conversation and measure conversion to a paid pilot.")

    # 7. Revenue potential
    s = {"enterprise": 8.5, "high": 7.5, "mid": 6.0, "low": 4.5, "free": 2.5}.get(price, 5.0)
    if customer in {"b2c"} and price in {"low", "free"}:
        s -= 0.5
    dims["revenue_potential"] = Dim(_clamp(s), f"Price point '{price}' for a {customer} buyer drives revenue per customer.",
                                    [], inferred if price != "unclear" else "low",
                                    ["expected price per customer per month/year"] if price == "unclear" else [],
                                    "Ask 10 prospects what they pay for current alternatives; anchor pricing on that.")

    # 8. Customer acquisition ease
    s = {"developers": 6.5, "b2b": 6.0, "b2b2c": 5.0, "b2c": 4.5, "marketplace": 4.0, "government": 3.5}.get(customer, 5.0)
    channels = signals.get("channels_mentioned") or []
    if channels:
        s += 1.0
    dims["customer_acquisition"] = Dim(
        _clamp(s), f"{customer} acquisition is typically {'slower and costlier' if s < 5 else 'moderate'}"
        + (f"; founder named channels: {', '.join(channels[:3])}." if channels else "; no acquisition channel named."),
        [], inferred, [] if channels else ["the first acquisition channel and its expected cost"],
        "Run one channel test (e.g. 50 targeted outreach messages or a $100 ad test) and measure reply/sign-up rate.")

    # 9. Technical feasibility (higher = easier)
    complexity = signals.get("technical_complexity", "medium")
    s = {"low": 8.5, "medium": 6.5, "high": 4.0}.get(complexity, 6.0)
    drivers = signals.get("complexity_drivers") or []
    dims["technical_feasibility"] = Dim(_clamp(s), f"Technical complexity assessed as {complexity}"
                                        + (f" ({', '.join(drivers[:3])})." if drivers else "."),
                                        [], inferred, [], "Build a throwaway prototype of the riskiest technical piece in 1-2 weeks.")

    # 10. Execution simplicity
    ops = signals.get("operational_intensity", "medium")
    capital = signals.get("capital_intensity", "medium")
    s = 10 - {"low": 1.0, "medium": 2.5, "high": 4.0}.get(ops, 2.5) - {"low": 1.0, "medium": 2.0, "high": 3.5}.get(capital, 2.0)
    team = data.team
    if team:
        s += 0.5
    dims["execution_complexity"] = Dim(_clamp(s), f"Operational intensity {ops}, capital intensity {capital}"
                                       + ("; team described." if team else "; team not described."),
                                       [], inferred, [] if team else ["team size and relevant skills"],
                                       "Map the first 90 days of operations and identify the single hardest dependency.")

    # 11. Financial viability
    margin = {"saas_subscription": 2.5, "usage_based": 2.0, "open_core": 2.0, "marketplace": 1.5, "transaction_fees": 1.5,
              "advertising": 1.0, "consumer_freemium": 1.0, "services": 0.5, "ecommerce_d2c": 0.5, "hardware": 0.0}.get(model, 1.0)
    s = 4.0 + margin + {"low": 2.5, "medium": 1.5, "high": 0.0}.get(capital, 1.0) + (1.0 if data.funding else 0.0)
    dims["financial_viability"] = Dim(_clamp(s), f"Gross-margin profile of a {model.replace('_', ' ')} model with {capital} capital needs"
                                      + ("; funding plan stated." if data.funding else "; no funding plan stated."),
                                      [], inferred, [] if data.funding else ["how the first 12-18 months will be funded"],
                                      "Build a one-page 18-month cost model; compare to realistic revenue by month 12.")

    # 12. Regulatory exposure (higher = less exposed)
    regulated = signals.get("regulated_domains") or []
    s = 9.0 - 1.8 * len(regulated)
    dims["regulatory_risk"] = Dim(_clamp(s), ("Regulated areas detected: " + ", ".join(regulated) + ".") if regulated
                                  else "No obviously regulated domain detected.", [], inferred,
                                  ["applicable regulations in the target geography"] if regulated else [],
                                  "Book a 30-minute review with a lawyer familiar with the domain before handling customer data or money.")

    # 13. Validation evidence
    stage_pts = {"idea": 2.0, "prototype": 3.5, "mvp": 5.0, "beta": 6.0, "paying_customers": 8.0, "scaling": 9.0}.get(data.stage, 2.0)
    traction = signals.get("traction_quotes") or []
    s = stage_pts + min(1.5, 0.75 * len(traction))
    dims["validation_evidence"] = Dim(_clamp(s), f"Stage: {data.stage.replace('_', ' ')}; {len(traction)} traction statement(s) provided.",
                                      [_ev(f'Founder: "{t[:160]}"') for t in traction[:3]], "high" if traction else "medium",
                                      [] if traction else ["any customer conversations, waitlist, pilots or revenue"],
                                      "Get 3 customers to commit to something costly: a pre-order, LOI, or paid pilot.")

    total_weight = sum(w for _, _, w in DIMENSIONS)
    overall = round(sum(dims[k].score * w for k, _, w in DIMENSIONS) / total_weight * 10)
    conf_points = {"high": 1.0, "medium": 0.6, "low": 0.25}
    confidence_value = sum(conf_points[dims[k].confidence] * w for k, _, w in DIMENSIONS) / total_weight
    confidence = "high" if confidence_value >= 0.75 else "medium" if confidence_value >= 0.5 else "low"
    return {
        "version": RUBRIC_VERSION,
        "method": METHOD_NOTE,
        "signals_method": signals.get("method"),
        "overall": overall,
        "confidence": confidence,
        "confidence_value": round(confidence_value, 3),
        "dimensions": [
            {"key": key, "label": label, "weight": weight, "score": dims[key].score, "rationale": dims[key].rationale,
             "evidence": dims[key].evidence, "confidence": dims[key].confidence, "missing": dims[key].missing,
             "next_step": dims[key].next_step}
            for key, label, weight in DIMENSIONS
        ],
        "missing_information": sorted({m for d in dims.values() for m in d.missing} | set(signals.get("missing_information") or [])),
        "shutdown_evidence": len(shutdowns),
    }
