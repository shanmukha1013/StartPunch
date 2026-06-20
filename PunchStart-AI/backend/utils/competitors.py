from services.dataset_engine import load_dataset


def competitor_benchmarks(industry: str) -> list[dict[str, str]]:
    rows = [
        row for row in load_dataset("competitor_data")
        if row.get("industry", "").lower() == industry.lower()
    ]
    return rows or load_dataset("competitor_data")[:3]
