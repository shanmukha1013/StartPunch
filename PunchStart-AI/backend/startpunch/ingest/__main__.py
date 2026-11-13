"""CLI: python -m startpunch.ingest build [--refresh] [--skip-embeddings] | evaluate"""
from __future__ import annotations

import argparse
import json
import logging


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m startpunch.ingest")
    sub = parser.add_subparsers(dest="command", required=True)
    build_p = sub.add_parser("build", help="Fetch sources and build the knowledge-base snapshot")
    build_p.add_argument("--refresh", action="store_true", help="Re-fetch all sources instead of using the raw cache")
    build_p.add_argument("--skip-embeddings", action="store_true")
    sub.add_parser("evaluate", help="Re-run the retrieval evaluation on the current snapshot")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    from .build import build, evaluate_retrieval
    from ..config import KB_DIR

    if args.command == "build":
        manifest = build(refresh=args.refresh, skip_embeddings=args.skip_embeddings)
        print(json.dumps({k: manifest[k] for k in ("snapshot_id", "counts")}, indent=2))
    else:
        evaluation = evaluate_retrieval(KB_DIR)
        manifest_path = KB_DIR / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["retrieval_evaluation"] = evaluation
        manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        print(json.dumps(evaluation, indent=2))


if __name__ == "__main__":
    main()
