from services.dataset_engine import find_by_field


def funding_benchmark(stage: str) -> dict[str, str]:
    row = find_by_field("funding_data", "stage", stage)
    if not row:
        return {
            "recommended_round": "Pre-seed",
            "use_of_funds": "Customer discovery, MVP delivery, and first paid pilots.",
            "milestone": "3 paid pilots with measurable customer impact.",
        }
    return row
