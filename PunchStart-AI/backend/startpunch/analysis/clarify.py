"""Gap analysis before running a report: what is missing, and which questions to ask."""
from __future__ import annotations

import logging

from .. import llm
from .signals import AnalysisInput

logger = logging.getLogger("startpunch.clarify")

_SCHEMA = llm.obj({
    "summary": llm.S("string"),
    "missing": llm.arr(llm.S("string")),
    "questions": llm.arr(llm.obj({
        "id": llm.S("string"),
        "question": llm.S("string"),
        "why": llm.S("string"),
        "field": llm.enum(["problem", "solution", "target_customers", "revenue_model", "team", "funding", "geography",
                           "competitors_known", "differentiation", "traction", "other"]),
    })),
})

_RULES = [
    ("target_customers", "Who exactly is the first customer (role, company type or demographic)?",
     "Scores for market, acquisition and revenue depend on the buyer."),
    ("problem", "What do these customers do today to solve the problem, and what does it cost them?",
     "Problem severity is the highest-weighted rubric dimension."),
    ("revenue_model", "Who pays, and roughly how much (per month, per transaction, per seat)?",
     "Needed for business-model, revenue and unit-economics sections."),
    ("geography", "Which country or region will you launch in first?", "Regulation, pricing and currency depend on it."),
    ("differentiation", "Why would a customer switch from their current alternative to you?",
     "Differentiation is scored against retrieved competitors."),
    ("traction", "What validation do you have so far (interviews, waitlist, pilots, revenue)?",
     "Validation evidence is scored directly."),
]


def rule_based(data: AnalysisInput) -> dict:
    questions = [{"id": f"q{i + 1}", "question": q, "why": why, "field": field}
                 for i, (field, q, why) in enumerate(_RULES) if not getattr(data, field)]
    return {"method": "rules", "summary": "", "missing": [q["field"].replace("_", " ") for q in questions],
            "questions": questions[:5]}


def clarify(data: AnalysisInput) -> dict:
    if not llm.available():
        return rule_based(data)
    prompt = (
        "A founder is about to run a startup analysis. Read their input and identify what is missing for an "
        "evidence-based evaluation. Ask at most 5 short, specific follow-up questions that would most change the "
        "analysis (not generic). Do not ask about anything they already answered.\n"
        "summary: one sentence restating the idea neutrally.\n\nFOUNDER INPUT:\n" + data.as_text()
    )
    try:
        result = llm.generate_json(prompt, schema=_SCHEMA, temperature=0.2, max_output_tokens=1500, profile="fast")
        out = dict(result.data)
        out["questions"] = [q for q in out.get("questions", []) if q.get("question")][:5]
        for i, q in enumerate(out["questions"]):
            q["id"] = f"q{i + 1}"
        out["method"] = result.model
        return out
    except llm.LLMUnavailable as exc:
        logger.warning("clarify fell back to rules: %s", exc)
        return rule_based(data)
