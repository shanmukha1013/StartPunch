"""Founder input model and signal extraction.

Signals are structured judgements about the idea (customer type, problem frequency, technical
complexity...). They come from the LLM *with verbatim quotes from the founder's text* where
possible; quotes are checked against the input. If the LLM is unavailable a transparent
keyword heuristic is used and every signal is marked ``method: heuristic``.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .. import llm
from ..ingest.llm_labels import BUSINESS_MODELS
from ..utils import clean_text

logger = logging.getLogger("startpunch.signals")

STAGES = ["idea", "prototype", "mvp", "beta", "paying_customers", "scaling"]


class Clarification(BaseModel):
    question: str = Field(max_length=300)
    answer: str = Field(max_length=1500)


class AnalysisInput(BaseModel):
    idea: str = Field(min_length=30, max_length=5000)
    name: str = Field(default="", max_length=100)
    problem: str = Field(default="", max_length=2000)
    solution: str = Field(default="", max_length=2000)
    target_customers: str = Field(default="", max_length=1000)
    revenue_model: str = Field(default="", max_length=500)
    stage: str = Field(default="idea", max_length=40)
    team: str = Field(default="", max_length=1000)
    funding: str = Field(default="", max_length=500)
    geography: str = Field(default="", max_length=120)
    competitors_known: str = Field(default="", max_length=1000)
    differentiation: str = Field(default="", max_length=1500)
    traction: str = Field(default="", max_length=1500)
    clarifications: list[Clarification] = Field(default_factory=list, max_length=8)

    @field_validator("*", mode="before")
    @classmethod
    def _clean(cls, value: Any) -> Any:
        return clean_text(value) if isinstance(value, str) else value

    @field_validator("stage")
    @classmethod
    def _stage(cls, value: str) -> str:
        value = (value or "idea").lower().replace(" ", "_")
        return value if value in STAGES else "idea"

    def as_text(self) -> str:
        fields = [("Idea", self.idea), ("Name", self.name), ("Problem", self.problem), ("Solution", self.solution),
                  ("Target customers", self.target_customers), ("Revenue model", self.revenue_model),
                  ("Stage", self.stage.replace("_", " ")), ("Team", self.team), ("Funding", self.funding),
                  ("Geography", self.geography), ("Known competitors", self.competitors_known),
                  ("Differentiation", self.differentiation), ("Traction", self.traction)]
        lines = [f"{label}: {value}" for label, value in fields if value]
        lines += [f"Q: {c.question}\nA: {c.answer}" for c in self.clarifications if c.answer]
        return "\n".join(lines)

    def search_text(self) -> str:
        return " ".join(t for t in [self.idea, self.problem, self.solution, self.target_customers] if t)[:2000]

    def display_name(self) -> str:
        return self.name or (self.idea[:60].rsplit(" ", 1)[0] + "…" if len(self.idea) > 60 else self.idea)


LEVEL = ["low", "medium", "high"]
FREQ = ["rare", "occasional", "frequent", "constant", "unclear"]
CUSTOMER = ["b2b", "b2c", "b2b2c", "developers", "government", "marketplace", "unclear"]
PRICE = ["free", "low", "mid", "high", "enterprise", "unclear"]

_SCHEMA = llm.obj({
    "one_liner": llm.S("string"),
    "customer_type": llm.enum(CUSTOMER),
    "buyer": llm.S("string"),
    "problem_frequency": llm.enum(FREQ),
    "problem_cost": llm.enum([*LEVEL, "unclear"]),
    "problem_quote": llm.S("string"),
    "differentiation_quote": llm.S("string"),
    "revenue_model": llm.enum([*BUSINESS_MODELS, "unclear"]),
    "price_point": llm.enum(PRICE),
    "technical_complexity": llm.enum(LEVEL),
    "complexity_drivers": llm.arr(llm.S("string")),
    "regulated_domains": llm.arr(llm.S("string")),
    "capital_intensity": llm.enum(LEVEL),
    "operational_intensity": llm.enum(LEVEL),
    "network_effects": llm.S("boolean"),
    "traction_quotes": llm.arr(llm.S("string")),
    "channels_mentioned": llm.arr(llm.S("string")),
    "competitors_mentioned": llm.arr(llm.S("string")),
    "search_queries": llm.arr(llm.S("string")),
    "missing_information": llm.arr(llm.S("string")),
    "geography": llm.S("string"),
})

_SYSTEM = (
    "You extract structured, conservative signals from a founder's startup description for an evidence-based "
    "analysis engine. Never invent facts. For *_quote fields copy an exact phrase from the founder's text, or "
    "return an empty string if the text does not say it. Use 'unclear' when the text gives no signal."
)


def _quote_ok(quote: str, source: str) -> bool:
    norm = lambda s: re.sub(r"\W+", " ", s.lower()).strip()  # noqa: E731
    return bool(quote) and norm(quote) in norm(source)


def extract(data: AnalysisInput) -> dict:
    text = data.as_text()
    prompt = (
        f"Founder's description:\n<<<\n{text}\n>>>\n\n"
        "Fill the schema. search_queries: 4 short queries describing what similar products/companies would be "
        "called or do (no brand names unless the founder named them). competitors_mentioned: only names the founder wrote. "
        "missing_information: the most decision-relevant facts the founder has not provided (max 6). "
        "regulated_domains: e.g. health data, payments/lending, children, insurance, employment, education records, "
        "aviation/drones, food safety, crypto — only if relevant. geography: the founder's target market, or '' if not stated."
    )
    try:
        result = llm.generate_json(prompt, system=_SYSTEM, schema=_SCHEMA, temperature=0.1, max_output_tokens=2500, profile="fast")
        signals = dict(result.data)
        signals["method"] = "llm"
        signals["model"] = result.model
        for key in ("problem_quote", "differentiation_quote"):
            if signals.get(key) and not _quote_ok(signals[key], text):
                signals[key] = ""  # discard quotes that are not verbatim
        signals["traction_quotes"] = [q for q in signals.get("traction_quotes", []) if _quote_ok(q, text)][:5]
        signals["search_queries"] = [clean_text(q, 160) for q in signals.get("search_queries", []) if q][:5]
        signals["competitors_mentioned"] = [c for c in signals.get("competitors_mentioned", [])
                                            if c and c.lower() in text.lower()][:8]
        return signals
    except llm.LLMUnavailable as exc:
        logger.warning("signal extraction fell back to heuristics: %s", exc)
        return heuristic(data)


_REGULATED = {
    "health data": r"\b(patient|clinic|hospital|medical|health|therap|diagnos|prescription)",
    "payments / lending": r"\b(payment|lend|loan|credit|bank|wallet|remittance|insurance|invest)",
    "children": r"\b(kids?|children|child|minor|student|school)",
    "employment": r"\b(hiring|recruit|payroll|employee|candidate)",
    "personal data": r"\b(personal data|location data|biometric|face recognition|tracking)",
    "crypto": r"\b(crypto|token|blockchain|defi|nft)",
    "aviation / drones": r"\b(drone|aviation|aircraft)",
    "food safety": r"\b(food|meal|restaurant|grocery)",
}


def heuristic(data: AnalysisInput) -> dict:
    text = data.as_text()
    lower = text.lower()
    customer = "unclear"
    if re.search(r"\b(business|companies|teams|smb|enterprise|b2b|clinic|agenc|retailer|restaurant)", lower):
        customer = "b2b"
    elif re.search(r"\b(consumer|people|users|students|parents|individuals|b2c)", lower):
        customer = "b2c"
    if re.search(r"\b(developer|engineer|api|sdk)", lower):
        customer = "developers"
    if re.search(r"\b(marketplace|connect(s|ing)? .* with|two-sided)", lower):
        customer = "marketplace"
    complexity = "high" if re.search(r"\b(hardware|device|robot|satellite|biotech|drug|chip|vehicle)", lower) else (
        "medium" if re.search(r"\b(ai|machine learning|model|real-time|integration|platform)", lower) else "low")
    regulated = [label for label, pattern in _REGULATED.items() if re.search(pattern, lower)]
    model = "unclear"
    for key, pattern in (("saas_subscription", r"subscription|saas|per seat|monthly"), ("marketplace", r"commission|marketplace"),
                         ("transaction_fees", r"transaction fee|per transaction"), ("advertising", r"\bads?\b|advertis"),
                         ("usage_based", r"usage|per api call|pay as you go"), ("hardware", r"hardware|device")):
        if re.search(pattern, (data.revenue_model + " " + lower)):
            model = key
            break
    queries = [data.idea[:160]]
    if data.problem:
        queries.append(data.problem[:160])
    if data.solution:
        queries.append(data.solution[:160])
    return {
        "method": "heuristic", "model": "keyword-rules",
        "one_liner": data.idea[:180], "customer_type": customer, "buyer": data.target_customers[:120],
        "problem_frequency": "unclear", "problem_cost": "unclear", "problem_quote": "",
        "differentiation_quote": data.differentiation[:200], "revenue_model": model, "price_point": "unclear",
        "technical_complexity": complexity, "complexity_drivers": [], "regulated_domains": regulated,
        "capital_intensity": "high" if complexity == "high" else "medium" if complexity == "medium" else "low",
        "operational_intensity": "high" if customer == "marketplace" else "medium",
        "network_effects": customer == "marketplace", "traction_quotes": [data.traction[:200]] if data.traction else [],
        "channels_mentioned": [], "competitors_mentioned": [c.strip() for c in re.split(r"[,;\n]", data.competitors_known) if c.strip()][:8],
        "search_queries": queries, "missing_information": [
            label for label, value in (("target customers", data.target_customers), ("revenue model", data.revenue_model),
                                       ("geography", data.geography), ("traction or validation evidence", data.traction),
                                       ("differentiation", data.differentiation)) if not value],
        "geography": data.geography,
    }
