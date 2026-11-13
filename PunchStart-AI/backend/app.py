"""Compatibility entry point: `uvicorn app:app` (run from backend/) serves the StartPunch API + frontend."""
from startpunch.main import app  # noqa: F401
