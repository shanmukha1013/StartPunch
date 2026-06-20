import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from utils.scoring import calculate_score_fallback


logger = logging.getLogger("punchstart.report")


class MarketSize(BaseModel):
    tam: str
    sam: str
    som: str
    rationale: str


class SWOT(BaseModel):
    strengths: list[str] = Field(min_length=2)
    weaknesses: list[str] = Field(min_length=2)
    opportunities: list[str] = Field(min_length=2)
    threats: list[str] = Field(min_length=2)


class Force(BaseModel):
    force: str
    rating: str
    insight: str


class Risk(BaseModel):
    risk: str
    severity: str
    likelihood: str
    mitigation: str


class RoadmapItem(BaseModel):
    phase: str
    timeline: str
    focus: str
    success_metric: str


class PitchSlide(BaseModel):
    title: str
    content: str


class Competitor(BaseModel):
    name: str
    positioning: str
    advantage: str
    gap_to_exploit: str


class Report(BaseModel):
    executive_summary: str
    startup_score: int = Field(ge=0, le=100)
    investor_readiness_score: int = Field(ge=0, le=100)
    tam_sam_som: MarketSize
    market_analysis: str
    industry_trends: list[str] = Field(min_length=3)
    competitor_landscape: list[Competitor] = Field(min_length=3)
    customer_persona: str
    revenue_strategy: str
    business_model_analysis: str
    swot: SWOT
    porters_five_forces: list[Force] = Field(min_length=5)
    go_to_market_strategy: str
    risk_matrix: list[Risk] = Field(min_length=3)
    funding_recommendation: str
    mvp_roadmap: list[RoadmapItem] = Field(min_length=3)
    growth_strategy: str
    pitch_deck_outline: list[PitchSlide] = Field(min_length=8)
    market_timing_analysis: str
    founder_recommendations: list[str] = Field(min_length=4)
    monetization_strategy: str
    investor_attractiveness_analysis: str

    @field_validator("*", mode="before")
    @classmethod
    def reject_empty_language(cls, value: Any) -> Any:
        blocked = {"", "n/a", "na", "unknown", "not available", "data unavailable"}
        if isinstance(value, str) and value.strip().lower() in blocked:
            raise ValueError("Empty filler language is not allowed")
        if isinstance(value, list) and len(value) == 0:
            raise ValueError("Empty arrays are not allowed")
        return value


def generate_report_json(model_output: str, input_data: dict) -> dict:
    parsed = _parse_json_with_repair(model_output)
    return normalize_report(parsed, input_data)


def normalize_report(candidate: dict[str, Any] | None, input_data: dict) -> dict:
    baseline = _build_deterministic_report(input_data)
    merged = _deep_merge(baseline, candidate or {})
    try:
        report = Report.model_validate(merged)
    except ValidationError as exc:
        logger.warning("Report validation failed; using deterministic report. %s", exc)
        report = Report.model_validate(baseline)

    payload = report.model_dump()
    payload.update(_compatibility_fields(payload))
    return payload


def _parse_json_with_repair(raw: str) -> dict[str, Any]:
    cleaned = (raw or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    for body in (cleaned, _extract_json_object(cleaned), _repair_json(cleaned)):
        if not body:
            continue
        try:
            value = json.loads(body)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            continue

    raise ValueError("Structured analysis could not be normalized")


def _extract_json_object(raw: str) -> str | None:
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return raw[start : end + 1]


def _repair_json(raw: str) -> str:
    body = _extract_json_object(raw) or raw
    body = body.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
    body = re.sub(r",(\s*[}\]])", r"\1", body)
    return body


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    aliases = {
        "investor_readiness": "investor_readiness_score",
        "competitor_analysis": "competitor_landscape",
        "swot_analysis": "swot",
        "funding_analysis": "funding_recommendation",
        "revenue_model": "revenue_strategy",
        "investor_pitch_deck": "pitch_deck_outline",
        "risk_assessment": "risk_matrix",
    }
    for raw_key, raw_value in overlay.items():
        key = aliases.get(raw_key, raw_key)
        if key not in result:
            continue
        if isinstance(result[key], dict) and isinstance(raw_value, dict):
            result[key] = _deep_merge(result[key], raw_value)
        elif _has_content(raw_value):
            result[key] = raw_value
    return result


def _has_content(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in {"", "n/a", "unknown", "not available"}
    if isinstance(value, list):
        return len(value) > 0
    return True


def _build_deterministic_report(data: dict) -> dict:
    name = _clean(data.get("startup_name"), "The startup")
    industry = _clean(data.get("industry"), "technology")
    problem = _clean(data.get("problem"), "a costly workflow gap for a reachable customer segment")
    solution = _clean(data.get("solution"), "a focused software-enabled solution")
    customers = _clean(data.get("target_customers"), "early adopters with urgent budget pressure")
    revenue = _clean(data.get("revenue_model"), "tiered subscription with usage-based expansion")
    stage = _clean(data.get("business_stage"), "validation")
    funding = _clean(data.get("funding_requirement"), "a disciplined pre-seed round")
    score = calculate_score_fallback(data)
    readiness = min(96, max(45, score - 4 + (8 if stage.lower() not in {"ideation", ""} else 0)))

    market_scale = _market_scale(industry)
    wedge = f"{customers} who feel the pain around {problem.lower()}"

    return {
        "executive_summary": (
            f"{name} is positioned as a {industry} company addressing {problem}. "
            f"The proposed solution, {solution}, has credible venture potential if the team proves urgency, repeatable acquisition, "
            f"and willingness to pay among {customers}."
        ),
        "startup_score": score,
        "investor_readiness_score": readiness,
        "tam_sam_som": {
            "tam": market_scale["tam"],
            "sam": market_scale["sam"],
            "som": market_scale["som"],
            "rationale": (
                f"Sizing is modeled from the broader {industry} opportunity, narrowed to reachable Indian digital buyers, "
                f"then constrained to a realistic five-year beachhead share."
            ),
        },
        "market_analysis": (
            f"The {industry} market rewards teams that combine a sharp wedge with fast distribution learning. "
            f"{name} should initially concentrate on {wedge}, because this segment can produce clearer interviews, faster pilots, "
            f"and stronger proof than a broad horizontal launch."
        ),
        "industry_trends": [
            f"Buyers in {industry} increasingly expect intelligent workflows, measurable ROI, and short onboarding cycles.",
            "Investors are favoring capital-efficient startups with evidence of retention, not only top-line user growth.",
            "India's digital adoption creates room for vertical products that localize pricing, support, and compliance.",
        ],
        "competitor_landscape": [
            {
                "name": "Incumbent workflow tools",
                "positioning": "Broad platforms already embedded in customer operations.",
                "advantage": "Existing budgets, procurement trust, and feature depth.",
                "gap_to_exploit": "They are often too generic for the specific pain and slower to localize for Indian customers.",
            },
            {
                "name": "Manual service providers",
                "positioning": "Consultants, agencies, or operators solving the problem by hand.",
                "advantage": "High-touch relationships and customer trust.",
                "gap_to_exploit": "Software can win on speed, consistency, visibility, and lower marginal cost.",
            },
            {
                "name": "Emerging automation-native startups",
                "positioning": "New entrants using intelligent automation as the primary wedge.",
                "advantage": "Fresh UX, rapid experimentation, and focused messaging.",
                "gap_to_exploit": f"{name} can differentiate through sharper customer focus and proprietary workflow data.",
            },
        ],
        "customer_persona": (
            f"The ideal first customer is a pragmatic operator inside {customers}: budget-aware, frustrated by {problem.lower()}, "
            f"and willing to trial a product when it saves time, reduces risk, or improves revenue visibility within 30 days."
        ),
        "revenue_strategy": (
            f"Start with {revenue}, price around a painful workflow outcome, and add expansion revenue through seats, usage, "
            f"premium analytics, or managed onboarding once retention is proven."
        ),
        "business_model_analysis": (
            f"The strongest model is a narrow B2B wedge with founder-led sales at first, followed by repeatable inside sales. "
            f"Gross margins should improve as implementation playbooks and self-serve onboarding mature."
        ),
        "swot": {
            "strengths": [
                f"Clear problem-solution narrative in {industry}.",
                "Structured intelligence can create faster customer feedback loops.",
                "Focused beachhead allows disciplined MVP scope.",
            ],
            "weaknesses": [
                "Market proof depends on direct customer interviews and paid pilots.",
                "Competitive moat is not yet defensible without proprietary data or workflow lock-in.",
                "Early pricing power may be limited until ROI is quantified.",
            ],
            "opportunities": [
                "Create category authority through benchmarks, reports, and founder-led content.",
                "Partner with communities, accelerators, and vertical associations for distribution.",
                "Use customer workflow data to build differentiated recommendations over time.",
            ],
            "threats": [
                "Large platforms could bundle similar functionality.",
                "Long procurement cycles may slow revenue if the initial customer is too enterprise-heavy.",
                "Trust, privacy, or accuracy concerns can block adoption without transparent controls.",
            ],
        },
        "porters_five_forces": [
            {"force": "Competitive rivalry", "rating": "Medium", "insight": f"{industry} has active entrants, so differentiation must be workflow-specific."},
            {"force": "Threat of new entrants", "rating": "High", "insight": "Automation tooling lowers build cost; distribution and data quality matter more than feature parity."},
            {"force": "Buyer power", "rating": "Medium", "insight": "Customers have alternatives, but urgent pain and measurable ROI can reduce price pressure."},
            {"force": "Supplier power", "rating": "Medium", "insight": "Model, cloud, and data vendors create dependency risk that should be abstracted early."},
            {"force": "Threat of substitutes", "rating": "Medium", "insight": "Manual workarounds remain viable until the product proves faster payback."},
        ],
        "go_to_market_strategy": (
            "Run 25 problem interviews, convert the strongest 5 into design partners, publish a benchmark report from the findings, "
            "and launch with founder-led outbound plus community partnerships. The first GTM metric should be qualified pilots booked per week."
        ),
        "risk_matrix": [
            {"risk": "Weak willingness to pay", "severity": "High", "likelihood": "Medium", "mitigation": "Pre-sell pilots before overbuilding and require clear success metrics."},
            {"risk": "Generic positioning", "severity": "Medium", "likelihood": "Medium", "mitigation": "Choose one customer segment and write messaging around a single expensive workflow."},
            {"risk": "Analysis trust", "severity": "Medium", "likelihood": "Medium", "mitigation": "Add citations, confidence notes, review paths, and transparent assumptions."},
        ],
        "funding_recommendation": (
            f"Raise {funding} only after proving at least 3 paid pilots or strong LOIs. Use funds for MVP completion, customer discovery, "
            "data acquisition, and one growth experiment rather than broad hiring."
        ),
        "mvp_roadmap": [
            {"phase": "Discovery sprint", "timeline": "Weeks 1-2", "focus": "Interview users, map workflows, and define the must-win use case.", "success_metric": "25 interviews and 5 qualified design partners."},
            {"phase": "Concierge MVP", "timeline": "Weeks 3-6", "focus": "Deliver the outcome manually with lightweight automation.", "success_metric": "3 pilots with measurable before/after impact."},
            {"phase": "Productized beta", "timeline": "Weeks 7-12", "focus": "Automate the repeatable workflow, add analytics, and tighten onboarding.", "success_metric": "40 percent weekly active usage among pilot accounts."},
        ],
        "growth_strategy": (
            "Scale from founder-led sales into repeatable content, partnerships, and referral loops. Prioritize retention cohorts before paid acquisition, "
            "then expand into adjacent customer segments with the same pain pattern."
        ),
        "pitch_deck_outline": [
            {"title": "Vision", "content": f"{name} turns a costly {industry} pain into a faster, measurable workflow."},
            {"title": "Problem", "content": problem},
            {"title": "Solution", "content": solution},
            {"title": "Market", "content": f"{market_scale['tam']} TAM with a focused {market_scale['som']} beachhead."},
            {"title": "Product", "content": "Show the core workflow, insight loop, and time-to-value."},
            {"title": "Business Model", "content": revenue},
            {"title": "Go To Market", "content": "Design partners, founder-led outbound, community distribution, and proof-led content."},
            {"title": "Ask", "content": f"Raise {funding} tied to pilots, MVP delivery, and retention milestones."},
        ],
        "market_timing_analysis": (
            f"Timing is favorable because intelligent automation has shifted customer expectations, but fundraising markets now demand proof. "
            f"The right move is to validate quickly and convert insight into paid pilots before scaling spend."
        ),
        "founder_recommendations": [
            "Write a one-sentence ICP and reject customers outside it for the first 60 days.",
            "Run paid pilots with explicit ROI metrics instead of free exploratory walkthroughs.",
            "Instrument onboarding, activation, retention, and expansion intent from the first beta.",
            "Build a proprietary dataset from customer workflows to strengthen defensibility.",
        ],
        "monetization_strategy": (
            f"Use entry pricing that reduces adoption friction, then graduate to value-based tiers as {name} proves savings, revenue lift, "
            "or risk reduction. Avoid custom pricing until the sales motion is understood."
        ),
        "investor_attractiveness_analysis": (
            f"{name} becomes investor-attractive when it shows a narrow wedge, fast sales learning, early revenue quality, and a data advantage. "
            "The current idea is fundable as a pre-seed narrative if customer evidence arrives quickly."
        ),
    }


def _market_scale(industry: str) -> dict[str, str]:
    sizes = {
        "fintech": ("INR 75,000 Cr", "INR 18,000 Cr", "INR 900 Cr"),
        "healthtech": ("INR 60,000 Cr", "INR 12,000 Cr", "INR 600 Cr"),
        "edtech": ("INR 45,000 Cr", "INR 9,000 Cr", "INR 450 Cr"),
        "saas": ("INR 90,000 Cr", "INR 22,000 Cr", "INR 1,100 Cr"),
        "ai/ml": ("INR 80,000 Cr", "INR 20,000 Cr", "INR 1,000 Cr"),
        "intelligent automation": ("INR 80,000 Cr", "INR 20,000 Cr", "INR 1,000 Cr"),
        "cleantech": ("INR 70,000 Cr", "INR 15,000 Cr", "INR 750 Cr"),
        "ev": ("INR 1,20,000 Cr", "INR 30,000 Cr", "INR 1,500 Cr"),
    }
    tam, sam, som = sizes.get(industry.strip().lower(), ("INR 50,000 Cr", "INR 10,000 Cr", "INR 500 Cr"))
    return {"tam": tam, "sam": sam, "som": som}


def _clean(value: Any, fallback: str) -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def _compatibility_fields(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "investor_readiness": payload["investor_readiness_score"],
        "swot_analysis": payload["swot"],
        "competitor_analysis": payload["competitor_landscape"],
        "revenue_model": payload["revenue_strategy"],
        "funding_analysis": payload["funding_recommendation"],
        "risk_assessment": payload["risk_matrix"],
        "investor_pitch_deck": payload["pitch_deck_outline"],
    }
