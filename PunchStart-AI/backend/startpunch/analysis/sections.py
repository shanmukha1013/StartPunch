"""Report section catalog (34 sections) and the structured output schema."""
from __future__ import annotations

from .. import llm

BASIS = ["fact", "founder_input", "estimate", "assumption", "recommendation"]

# key: (title, group, guidance)
SECTIONS: dict[str, tuple[str, str, str]] = {
    # ---- opportunity
    "problem_analysis": ("Problem Analysis", "market",
        "Who has the problem, how often, what it costs them today, current workarounds. Separate founder claims from inference."),
    "proposed_solution": ("Proposed Solution", "market",
        "What the product does, the core workflow, why it could beat workarounds; note unproven assumptions."),
    "target_audience": ("Target Audience", "market",
        "Primary beachhead segment and secondary segments; segment sizing drivers (count of buyers, budget owner)."),
    "customer_personas": ("Customer Personas", "market",
        "2-3 personas in `groups` (label = persona name + role; items = goals, pains, buying triggers, objections)."),
    "market_research": ("Market Research", "market",
        "What the evidence base shows about this category: which comparable products launched, when, how they position. Cite [S#]."),
    "market_sizing": ("TAM, SAM and SOM", "market",
        "Bottom-up estimate in `metrics` (TAM, SAM, SOM) with basis=estimate and the formula + assumptions in `note`. "
        "No sourced market-size figures are available: never present a size as a fact. List the data needed to firm it up in `missing`."),
    "market_trends": ("Market Trends", "market",
        "Trends supported by the evidence (launch activity, recent launches, shutdowns) with [S#], plus general technology/behaviour "
        "trends clearly marked as assumption."),
    # ---- competition
    "competitor_analysis": ("Competitor Analysis", "competition",
        "Overview of the competitive landscape from the graded evidence; where the white space is."),
    "direct_competitors": ("Direct Competitors", "competition",
        "`table` columns: Company, What they do, Overlap, Source. Use only evidence entities graded direct; if none, say so."),
    "indirect_competitors": ("Indirect Competitors", "competition",
        "`table` columns: Company / alternative, How it substitutes, Weakness to exploit, Source. Include non-product workarounds."),
    "competitor_comparison": ("Competitor Comparison", "competition",
        "`table` comparing this idea vs up to 3 named competitors across 5-6 dimensions (target user, pricing approach, key feature, "
        "distribution, differentiation). Cells about competitors must be grounded in evidence snippets or say 'unknown'."),
    "swot": ("SWOT Analysis", "competition",
        "`groups`: Strengths, Weaknesses, Opportunities, Threats — 3-4 short, idea-specific items each."),
    "pestle": ("PESTLE Analysis", "competition",
        "`groups`: Political, Economic, Social, Technological, Legal, Environmental — 1-3 items each relevant to the founder's geography."),
    # ---- business
    "business_model": ("Business Model", "business",
        "Who pays, for what, how value is captured; fit between customer type and model; alternatives considered."),
    "revenue_streams": ("Revenue Streams", "business",
        "Primary and secondary streams with timing (now / later); `table` columns: Stream, Payer, Timing, Notes."),
    "pricing_strategy": ("Pricing Strategy", "business",
        "`table` of proposed tiers (Tier, Price (estimate), Includes, Target). Explain the value metric. Prices are estimates."),
    "unit_economics": ("Unit Economics", "business",
        "`metrics`: ARPU, gross margin, CAC, payback, LTV — all basis=estimate/assumption with assumptions in `note`."),
    "customer_acquisition": ("Customer Acquisition Strategy", "business",
        "Top 3-4 channels ranked by expected efficiency for this customer type, first 100 customers plan."),
    "go_to_market": ("Go-To-Market Strategy", "business",
        "Beachhead, positioning statement, launch sequence, sales motion, 90-day GTM milestones."),
    "marketing_strategy": ("Marketing Strategy", "business",
        "Messaging pillars, content/community plays, partnerships, metrics to watch."),
    # ---- build
    "product_roadmap": ("Product Development Roadmap", "build",
        "`table` columns: Phase, Timeline, Scope, Exit criteria — from MVP to v1."),
    "technical_architecture": ("Technical Architecture Recommendations", "build",
        "Components, data flows, build-vs-buy decisions, security/privacy needs, scaling risks."),
    "technology_stack": ("Technology Stack Recommendations", "build",
        "`table` columns: Layer, Recommendation, Why, Alternatives. Prefer boring, proven tools sized to the team."),
    "development_cost": ("Estimated Development Cost", "build",
        "`table` columns: Item, Effort, Cost range (estimate), Assumptions. State rates/currency assumptions explicitly."),
    "operational_requirements": ("Operational Requirements", "build",
        "Team roles needed, support, compliance operations, vendors, ongoing costs."),
    "funding_requirements": ("Funding Requirements", "build",
        "Capital needed to reach the next milestone, use of funds, funding options (bootstrapping, grants, angels, pre-seed) — estimates."),
    "financial_projections": ("Financial Projections", "build",
        "3-year `table` (Year, Customers, Revenue, Costs, Net) — every number is an estimate built from stated assumptions listed in `points`."),
    # ---- risk & next steps
    "risk_analysis": ("Risk Analysis", "risk",
        "`table` columns: Risk, Likelihood, Impact, Mitigation. Include market, execution, technical, financial, competitive risks; "
        "use shutdown evidence [S#] where similar products failed."),
    "regulatory_compliance": ("Regulatory and Compliance Considerations", "risk",
        "Relevant regulations for the founder's geography and domain (data protection, sector rules, licensing). "
        "Mark as assumption and recommend legal review; do not invent statute numbers."),
    "validation_experiments": ("Validation Experiments", "risk",
        "`table` columns: Hypothesis, Experiment, Success metric, Threshold, Cost/time — 4-6 cheap experiments ordered by risk."),
    "mvp_scope": ("MVP Scope", "risk",
        "`groups`: Must have, Should have later, Explicitly not now. Keep the MVP buildable in 6-10 weeks."),
    "growth_strategy": ("Growth Strategy", "risk",
        "Growth loops, expansion segments, retention drivers, when to raise or hire."),
    "long_term_roadmap": ("Long-Term Roadmap", "risk",
        "`table` columns: Horizon, Goal, Bets, Signals to watch — 1y / 3y / 5y."),
    # ---- synthesis (generated last)
    "executive_summary": ("Executive Summary", "synthesis",
        "4-6 sentences: what it is, who for, strongest evidence, biggest risks, verdict. Reference the overall score."),
    "final_recommendations": ("Final Recommendations", "synthesis",
        "Verdict in `metrics` (label 'Verdict', value one of: Build now / Validate first / Narrow the idea / Rethink), "
        "then 5-7 prioritized next steps in `points` (basis=recommendation)."),
}

GROUPS: dict[str, list[str]] = {}
for _key, (_title, _group, _guide) in SECTIONS.items():
    GROUPS.setdefault(_group, []).append(_key)

WRITE_GROUPS = ["market", "competition", "business", "build", "risk"]
SECTION_ORDER = ["executive_summary", *[k for g in WRITE_GROUPS for k in GROUPS[g]], "final_recommendations"]


def section_schema(keys: list[str]) -> dict:
    point = llm.obj({
        "text": llm.S("string"),
        "basis": llm.enum(BASIS),
        "sources": llm.arr(llm.S("string")),
    })
    metric = llm.obj({"label": llm.S("string"), "value": llm.S("string"), "basis": llm.enum(BASIS), "note": llm.S("string")})
    group = llm.obj({"label": llm.S("string"), "items": llm.arr(llm.S("string"))})
    table = llm.obj({"columns": llm.arr(llm.S("string")), "rows": llm.arr(llm.arr(llm.S("string")))})
    section = llm.obj({
        "key": llm.enum(keys),
        "summary": llm.S("string"),
        "points": llm.arr(point),
        "metrics": llm.arr(metric),
        "groups": llm.arr(group),
        "table": table,
        "missing": llm.arr(llm.S("string")),
        "confidence": llm.enum(["low", "medium", "high"]),
    })
    return llm.obj({"sections": llm.arr(section)})
