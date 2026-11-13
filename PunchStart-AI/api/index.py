"""Vercel Python serverless entry point: exposes the FastAPI app for every /api/* request."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from startpunch.main import app  # noqa: E402,F401
