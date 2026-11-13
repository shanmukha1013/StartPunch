"""Gemini REST client (generation + embeddings).

Uses the public REST API directly via httpx instead of the deprecated, heavy
``google-generativeai`` SDK. The API key is only ever read server-side.
"""
from __future__ import annotations

import json
import logging
import math
import re
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .config import get_settings

logger = logging.getLogger("startpunch.llm")
API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
EMBED_DIMS = 256

_client: httpx.Client | None = None
_client_lock = threading.Lock()


class LLMUnavailable(RuntimeError):
    """Raised when no model could produce a valid response. Callers must degrade honestly."""


class QuotaExhausted(RuntimeError):
    """A model's (daily) quota is exhausted; skip it until ``until`` (epoch seconds)."""

    def __init__(self, message: str, until: float):
        super().__init__(message)
        self.until = until


_exhausted: dict[str, float] = {}  # model -> epoch seconds when it may be retried
_RETRY_IN = re.compile(r"retry in\s+(?:(\d+)h)?\s*(?:(\d+)m)?\s*(?:([\d.]+)s)?", re.I)


def _retry_seconds(message: str) -> float | None:
    match = _RETRY_IN.search(message)
    if not match or not any(match.groups()):
        return None
    hours, minutes, seconds = (float(g) if g else 0.0 for g in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def model_status() -> dict[str, str]:
    now = time.time()
    return {model: f"quota exhausted, retry in {int(until - now)}s" for model, until in _exhausted.items() if until > now}


@dataclass
class LLMResult:
    data: Any
    model: str
    latency_ms: int
    input_tokens: int = 0
    output_tokens: int = 0


def _http() -> httpx.Client:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = httpx.Client(timeout=httpx.Timeout(get_settings().gemini_timeout, connect=10.0))
    return _client


def available() -> bool:
    return get_settings().ai_configured


def _headers() -> dict[str, str]:
    key = get_settings().gemini_api_key
    if not key:
        raise LLMUnavailable("AI engine is not configured (GEMINI_API_KEY missing).")
    return {"x-goog-api-key": key, "Content-Type": "application/json"}


def _post(path: str, body: dict, *, attempts: int = 3, timeout: float | None = None) -> dict:
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            response = _http().post(f"{API_ROOT}/{path}", headers=_headers(), json=body,
                                    timeout=timeout or get_settings().gemini_timeout)
            if response.status_code == 200:
                return response.json()
            message = response.text[:1500]
            if response.status_code == 429:
                wait = _retry_seconds(message)
                lowered = message.lower()
                if "per day" in lowered or "perday" in lowered or (wait and wait > 90):
                    raise QuotaExhausted(message[:300], time.time() + (wait or 3600))
            if response.status_code in {429, 500, 502, 503, 504}:
                last = RuntimeError(f"HTTP {response.status_code}: {message}")
                delay = min(8.0, 1.5 * (2 ** attempt))
                retry_after = response.headers.get("retry-after")
                if retry_after and retry_after.isdigit():
                    delay = min(20.0, float(retry_after))
                hinted = _retry_seconds(message)
                if hinted:
                    delay = min(60.0, max(delay, hinted))
                logger.warning("Gemini %s transient error (attempt %s): %s", path.split(":")[0], attempt + 1, response.status_code)
                time.sleep(delay)
                continue
            raise RuntimeError(f"HTTP {response.status_code}: {message}")
        except QuotaExhausted:
            raise
        except httpx.TimeoutException as exc:
            last = exc
            logger.warning("Gemini request timed out (attempt %s)", attempt + 1)
        except httpx.HTTPError as exc:
            last = exc
            time.sleep(1.0)
    raise RuntimeError(str(last) if last else "request failed")


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json(text: str) -> Any:
    cleaned = _FENCE.sub("", (text or "").strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            body = re.sub(r",(\s*[}\]])", r"\1", cleaned[start:end + 1])
            return json.loads(body)
        raise


def model_chain(profile: str = "quality") -> list[str]:
    """Ordered model list for a task profile. Each model has its own quota on the Gemini API."""
    settings = get_settings()
    if profile == "quality":
        chain = [settings.gemini_model, *settings.gemini_fallback_models]
    else:
        chain = list(settings.gemini_fast_models)
    return list(dict.fromkeys(chain))


def generate_json(
    prompt: str,
    *,
    system: str | None = None,
    schema: dict | None = None,
    temperature: float = 0.3,
    max_output_tokens: int = 8192,
    timeout: float | None = None,
    models: list[str] | None = None,
    profile: str = "quality",
    deadline: float | None = None,
) -> LLMResult:
    """Generate a JSON object. Tries each model in the profile's chain, skipping exhausted ones."""
    candidates = models or model_chain(profile)
    errors: list[str] = []
    for model in candidates:
        if _exhausted.get(model, 0) > time.time():
            errors.append(f"{model}: quota exhausted")
            continue
        call_timeout = timeout
        if deadline is not None:
            remaining = deadline - time.time()
            if remaining < 12:
                errors.append(f"{model}: skipped (deadline)")
                break
            call_timeout = min(timeout or get_settings().gemini_timeout, remaining)
        config: dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
            "responseMimeType": "application/json",
        }
        if schema is not None:
            config["responseSchema"] = schema
        if model.startswith("gemini-2.5"):
            config["thinkingConfig"] = {"thinkingBudget": 0 if "lite" in model else 512}
        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": config,
        }
        if system:
            if model.startswith("gemma"):
                # Gemma models on the Gemini API do not accept system instructions.
                body["contents"][0]["parts"][0]["text"] = f"{system}\n\n{prompt}"
            else:
                body["systemInstruction"] = {"parts": [{"text": system}]}
        started = time.perf_counter()
        try:
            payload = _post(f"models/{model}:generateContent", body, attempts=1 if deadline else 2, timeout=call_timeout)
            candidate = (payload.get("candidates") or [{}])[0]
            parts = candidate.get("content", {}).get("parts", [])
            text = "".join(part.get("text", "") for part in parts if not part.get("thought"))
            if not text.strip():
                raise RuntimeError(f"empty response (finishReason={candidate.get('finishReason')})")
            data = parse_json(text)
            usage = payload.get("usageMetadata", {})
            result = LLMResult(
                data=data, model=model, latency_ms=int((time.perf_counter() - started) * 1000),
                input_tokens=int(usage.get("promptTokenCount", 0)), output_tokens=int(usage.get("candidatesTokenCount", 0)),
            )
            logger.info("LLM ok model=%s latency=%sms in=%s out=%s", model, result.latency_ms, result.input_tokens, result.output_tokens)
            return result
        except LLMUnavailable:
            raise
        except QuotaExhausted as exc:
            _exhausted[model] = exc.until
            errors.append(f"{model}: quota exhausted")
            logger.warning("LLM model %s quota exhausted; skipping for %ss", model, int(exc.until - time.time()))
        except Exception as exc:  # try next model
            errors.append(f"{model}: {str(exc)[:160]}")
            logger.warning("LLM model %s failed: %s", model, str(exc)[:200])
    raise LLMUnavailable("; ".join(errors) or "no model available")


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


_embed_window: list[tuple[float, int]] = []
_embed_lock = threading.Lock()


def _throttle_tokens(tokens: int, budget_per_minute: int) -> None:
    """Sliding-window token budget (free tiers enforce tokens-per-minute)."""
    while True:
        with _embed_lock:
            now = time.time()
            while _embed_window and now - _embed_window[0][0] > 60:
                _embed_window.pop(0)
            used = sum(t for _, t in _embed_window)
            if used + tokens <= budget_per_minute or not _embed_window:
                _embed_window.append((now, tokens))
                return
            wait = 60 - (now - _embed_window[0][0]) + 0.5
        time.sleep(max(0.5, wait))


def embed(texts: list[str], *, task: str = "RETRIEVAL_DOCUMENT", dims: int = EMBED_DIMS, batch_size: int = 100,
          tokens_per_minute: int | None = None) -> list[list[float]]:
    """Embed texts with gemini-embedding (Matryoshka-truncated to ``dims``, L2-normalized)."""
    settings = get_settings()
    model = settings.gemini_embed_model
    if _exhausted.get(model, 0) > time.time():
        raise LLMUnavailable("embedding quota exhausted")
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        chunk = texts[start:start + batch_size]
        if tokens_per_minute:
            _throttle_tokens(sum(len(t) // 4 + 8 for t in chunk), tokens_per_minute)
        body = {"requests": [
            {"model": f"models/{model}", "content": {"parts": [{"text": (text or " ")[:8000]}]},
             "taskType": task, "outputDimensionality": dims}
            for text in chunk
        ]}
        try:
            payload = _post(f"models/{model}:batchEmbedContents", body, attempts=6, timeout=60)
        except QuotaExhausted as exc:
            _exhausted[model] = exc.until
            raise LLMUnavailable(f"embedding quota exhausted: {exc}") from exc
        except RuntimeError as exc:
            raise LLMUnavailable(f"embedding failed: {exc}") from exc
        for item in payload.get("embeddings", []):
            vectors.append(_normalize(item["values"]))
    if len(vectors) != len(texts):
        raise LLMUnavailable("embedding count mismatch")
    return vectors


def embed_query(text: str) -> list[float]:
    return embed([text], task="RETRIEVAL_QUERY")[0]


# ---- schema helpers (Gemini OpenAPI subset) -------------------------------------------------
def S(type_: str, **kw: Any) -> dict:
    out = {"type": type_.upper()}
    out.update(kw)
    return out


def obj(props: dict[str, dict], required: list[str] | None = None) -> dict:
    return {"type": "OBJECT", "properties": props, "required": required if required is not None else list(props),
            "propertyOrdering": list(props)}


def arr(items: dict, **kw: Any) -> dict:
    return {"type": "ARRAY", "items": items, **kw}


def enum(values: list[str]) -> dict:
    return {"type": "STRING", "enum": values}
