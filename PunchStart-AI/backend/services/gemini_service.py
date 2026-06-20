import asyncio
import json
import logging
import os
import warnings
from pathlib import Path
from typing import Any

try:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=FutureWarning, module=r"google\.generativeai.*")
        import google.generativeai as genai
except ModuleNotFoundError:
    genai = None

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None


logger = logging.getLogger("punchstart.gemini")

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
REQUEST_TIMEOUT_SECONDS = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "45"))
MAX_RETRIES = int(os.getenv("GEMINI_MAX_RETRIES", "2"))

_model = None
_selected_model_name: str | None = None


def _load_environment() -> str | None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists() and load_dotenv is not None:
        load_dotenv(dotenv_path=str(env_path), override=False)
    return os.getenv("GEMINI_API_KEY")


def _get_model():
    global _model, _selected_model_name
    if _model is not None:
        return _model

    api_key = _load_environment()
    if genai is None:
        logger.warning("google-generativeai is not installed; deterministic report engine will be used.")
        return None
    if not api_key:
        logger.warning("GEMINI_API_KEY is not configured; deterministic report engine will be used.")
        return None

    genai.configure(api_key=api_key)
    _selected_model_name = _resolve_model_name()
    _model = genai.GenerativeModel(
        _selected_model_name,
        generation_config={
            "temperature": 0.35,
            "top_p": 0.9,
            "response_mime_type": "application/json",
        },
    )
    return _model


def _resolve_model_name() -> str:
    env_model = os.getenv("GEMINI_MODEL")
    if env_model:
        return env_model

    preferred = ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "models/gemini-1.5-flash")
    try:
        models = list(genai.list_models() or [])
    except Exception as exc:
        logger.warning("Could not list generation models; using configured default. %s", exc)
        return DEFAULT_MODEL

    available: list[tuple[str, str]] = []
    for model in models:
        name = getattr(model, "name", "") or getattr(model, "model_name", "")
        methods = getattr(model, "supported_generation_methods", []) or []
        method_text = " ".join(str(method).lower() for method in methods)
        if name and ("generatecontent" in method_text or "generate_content" in method_text):
            available.append((name, name.split("/")[-1]))

    for wanted in preferred:
        for full_name, short_name in available:
            if wanted in {full_name, short_name}:
                logger.info("Selected generation model: %s", full_name)
                return full_name

    if available:
        logger.info("Selected generation model: %s", available[0][0])
        return available[0][0]

    return DEFAULT_MODEL


async def generate_content(prompt: str) -> str:
    """Return model text with retries and timeouts.

    Errors are logged for operators and re-raised without provider-specific wording
    so callers can fall back to a professional report.
    """
    model = _get_model()
    if model is None:
        raise RuntimeError("Analysis engine is not configured")

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(model.generate_content, prompt),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            text = getattr(response, "text", "") or ""
            if not text.strip():
                raise ValueError("Empty model response")
            return text
        except Exception as exc:
            last_error = exc
            logger.warning("Structured generation attempt %s failed: %s", attempt + 1, exc)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(0.8 * (attempt + 1))

    logger.exception("Structured generation exhausted retries", exc_info=last_error)
    raise RuntimeError("Analysis engine could not complete the request") from last_error


async def generate_json(prompt: str) -> dict[str, Any]:
    text = await generate_content(prompt)
    return json.loads(text)


def test_gemini_connection() -> tuple[bool, str]:
    try:
        model = _get_model()
        if model is None:
            return False, "Analysis engine is not configured."
        response = model.generate_content("Return {\"status\":\"ok\"} as JSON.")
        return True, getattr(response, "text", "").strip()
    except Exception:
        logger.exception("Analysis engine connectivity test failed")
        return False, "Analysis engine connectivity test failed."
