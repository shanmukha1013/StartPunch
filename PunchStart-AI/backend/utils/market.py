from services.dataset_engine import find_by_field


def market_benchmark(industry: str) -> dict[str, str]:
    row = find_by_field("market_data", "industry", industry)
    if not row:
        return {
            "tam_inr_cr": "50000",
            "sam_inr_cr": "10000",
            "som_inr_cr": "500",
            "growth_signal": "Focused digital products can build a defensible wedge when they prove measurable ROI.",
        }
    return row
