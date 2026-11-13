"""Environment-based configuration.

Every secret comes from the environment (or a local, git-ignored ``backend/.env``
during development). Nothing secret is ever shipped to the browser.
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
FRONTEND_DIR = PROJECT_DIR / "frontend"
KB_DIR = BACKEND_DIR / "data" / "kb"
VAR_DIR = BACKEND_DIR / "var"


def _load_dotenv() -> None:
    """Minimal .env loader (KEY=VALUE lines). Real environment variables win."""
    env_path = BACKEND_DIR / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    env: str
    on_vercel: bool
    database_url: str
    database_configured: bool
    session_secret: str
    session_secret_configured: bool
    session_days: int
    cookie_secure: bool
    cors_origins: list[str]
    admin_emails: list[str]
    gemini_api_key: str | None
    gemini_model: str
    gemini_fallback_models: list[str]
    gemini_fast_models: list[str]
    gemini_embed_model: str
    gemini_timeout: float
    max_upload_bytes: int
    serve_frontend: bool
    daily_report_quota: int
    daily_ai_quota: int
    ingest_user_agent: str
    extra: dict = field(default_factory=dict)

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def ai_configured(self) -> bool:
        return bool(self.gemini_api_key)


def _dev_secret() -> str:
    """Stable per-machine secret for local development only."""
    path = VAR_DIR / "dev_session_secret"
    try:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        VAR_DIR.mkdir(parents=True, exist_ok=True)
        value = secrets.token_urlsafe(48)
        path.write_text(value, encoding="utf-8")
        return value
    except OSError:
        return secrets.token_urlsafe(48)


def normalize_database_url(url: str) -> str:
    """Use the pure-Python pg8000 driver for Postgres URLs (works on Vercel and locally)."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+pg8000://" + url[len("postgresql://"):]
    return url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_dotenv()
    on_vercel = bool(os.getenv("VERCEL"))
    env = os.getenv("STARTPUNCH_ENV") or ("production" if on_vercel else "development")

    raw_db = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or ""
    database_configured = bool(raw_db)
    if not raw_db:
        if on_vercel:
            # Serverless filesystems are ephemeral: never silently pretend data persists.
            raw_db = ""
        else:
            VAR_DIR.mkdir(parents=True, exist_ok=True)
            raw_db = f"sqlite:///{(VAR_DIR / 'startpunch.db').as_posix()}"
            database_configured = True

    secret = os.getenv("SESSION_SECRET", "")
    secret_configured = len(secret) >= 32
    if not secret_configured and env != "production":
        secret = _dev_secret()
        secret_configured = True

    return Settings(
        env=env,
        on_vercel=on_vercel,
        database_url=normalize_database_url(raw_db) if raw_db else "",
        database_configured=database_configured,
        session_secret=secret,
        session_secret_configured=secret_configured,
        session_days=int(os.getenv("SESSION_DAYS", "14")),
        cookie_secure=_bool("COOKIE_SECURE", env == "production"),
        cors_origins=_list("CORS_ORIGINS"),
        admin_emails=[email.lower() for email in _list("ADMIN_EMAILS")],
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        gemini_fallback_models=_list("GEMINI_FALLBACK_MODELS") or ["gemini-3.1-flash-lite", "gemini-flash-lite-latest", "gemma-4-26b-a4b-it"],
        gemini_fast_models=_list("GEMINI_FAST_MODELS") or ["gemini-flash-lite-latest", "gemma-4-26b-a4b-it", "gemini-3.1-flash-lite"],
        gemini_embed_model=os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001"),
        gemini_timeout=float(os.getenv("GEMINI_TIMEOUT_SECONDS", "55")),
        max_upload_bytes=int(float(os.getenv("MAX_UPLOAD_MB", "3")) * 1024 * 1024),
        serve_frontend=_bool("SERVE_FRONTEND", not on_vercel),
        daily_report_quota=int(os.getenv("DAILY_REPORT_QUOTA", "8")),
        daily_ai_quota=int(os.getenv("DAILY_AI_QUOTA", "120")),
        ingest_user_agent=os.getenv("INGEST_USER_AGENT", "startup-intel-ingest/1.0 (open-data research client)"),
    )
