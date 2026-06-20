from __future__ import annotations

import csv
from pathlib import Path


def load_training_metadata(data_dir: str | Path = "../data") -> dict[str, int]:
    base = Path(__file__).resolve().parent / data_dir
    summary: dict[str, int] = {}
    for csv_path in base.glob("*.csv"):
        with csv_path.open(newline="", encoding="utf-8") as handle:
            summary[csv_path.stem] = max(0, sum(1 for _ in csv.DictReader(handle)))
    return summary


def main() -> None:
    summary = load_training_metadata()
    for name, rows in sorted(summary.items()):
        print(f"{name}: {rows} benchmark rows")


if __name__ == "__main__":
    main()
