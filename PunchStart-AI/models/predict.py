from __future__ import annotations

from preprocess import normalize_startup_record


INDUSTRY_BASELINE = {
    "Intelligent Automation": 88,
    "AI/ML": 88,
    "SaaS": 86,
    "Fintech": 84,
    "Healthtech": 82,
    "EV": 82,
    "CleanTech": 80,
    "Edtech": 76,
    "AgriTech": 74,
    "Logistics": 72,
    "E-commerce": 70,
    "Foodtech": 68,
    "PropTech": 68,
}


def predict_startup_score(record: dict) -> int:
    data = normalize_startup_record(record)
    score = int(INDUSTRY_BASELINE.get(data["industry"], 66) * 0.42)
    score += min(20, data["problem_length"] // 12)
    score += min(18, data["solution_length"] // 14)
    score += 10 if data["has_revenue_model"] else 0
    score += min(6, data["team_size"] * 2)
    score += 8 if data["has_funding_plan"] else 0
    return max(35, min(100, score))


def predict_investor_readiness(record: dict) -> int:
    score = predict_startup_score(record)
    stage = str(record.get("business_stage", "")).lower()
    if stage in {"beta launch", "early traction", "scaling"}:
        score += 6
    if not record.get("funding_requirement"):
        score -= 5
    return max(30, min(100, score))
