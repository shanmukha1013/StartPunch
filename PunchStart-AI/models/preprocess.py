from __future__ import annotations

from typing import Any


TEXT_FIELDS = (
    "startup_name",
    "industry",
    "problem",
    "solution",
    "target_customers",
    "revenue_model",
    "funding_requirement",
    "business_stage",
)


def normalize_startup_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized = {field: str(record.get(field, "")).strip() for field in TEXT_FIELDS}
    try:
        normalized["team_size"] = max(0, int(record.get("team_size") or 0))
    except (TypeError, ValueError):
        normalized["team_size"] = 0
    normalized["problem_length"] = len(normalized["problem"])
    normalized["solution_length"] = len(normalized["solution"])
    normalized["has_revenue_model"] = bool(normalized["revenue_model"])
    normalized["has_funding_plan"] = bool(normalized["funding_requirement"])
    return normalized


def batch_normalize(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [normalize_startup_record(record) for record in records]
