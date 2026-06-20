import csv
from functools import lru_cache
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@lru_cache(maxsize=8)
def load_dataset(name: str) -> list[dict[str, str]]:
    path = DATA_DIR / f"{name}.csv"
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def find_by_field(dataset: str, field: str, value: str) -> dict[str, str] | None:
    target = value.strip().lower()
    for row in load_dataset(dataset):
        if row.get(field, "").strip().lower() == target:
            return row
    return None
