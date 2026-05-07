"""Shared Groq client wrapper for all LLM-powered features.

Centralises:
  - API-key check (returns a clear error if not configured)
  - Model choice (llama-3.3-70b-versatile — fast, capable, JSON-mode capable)
  - Reasonable defaults (temperature, max_tokens, timeout)
  - JSON-mode helper for endpoints that need structured output

The chat operator (`app/chat/`) has its own AsyncGroq client because it's
a stateful conversation. This module is for one-shot completions.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from groq import AsyncGroq

from app.core.settings import get_settings

log = logging.getLogger("llm")

DEFAULT_MODEL = "llama-3.3-70b-versatile"


class LLMNotConfigured(RuntimeError):
    """Raised when GROQ_API_KEY is missing — caller should return a friendly error."""


def _client() -> AsyncGroq:
    settings = get_settings()
    if not settings.groq_api_key:
        raise LLMNotConfigured(
            "GROQ_API_KEY is not set — LLM-powered features are unavailable."
        )
    return AsyncGroq(api_key=settings.groq_api_key)


async def complete(
    *,
    system: str,
    user: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.2,
    max_tokens: int = 2000,
    json_mode: bool = False,
) -> str:
    """Single-turn completion. Returns the assistant text content."""
    client = _client()
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        resp = await client.chat.completions.create(**kwargs)
    except Exception as e:  # noqa: BLE001
        log.warning("groq completion failed: %s", e)
        raise
    return resp.choices[0].message.content or ""


async def complete_json(
    *, system: str, user: str, model: str = DEFAULT_MODEL,
    temperature: float = 0.2, max_tokens: int = 2000,
) -> dict[str, Any]:
    """Same as `complete` but parses the response as JSON. Falls back to
    {"error": "...", "raw": "..."} on parse failure rather than raising."""
    text = await complete(
        system=system, user=user, model=model,
        temperature=temperature, max_tokens=max_tokens, json_mode=True,
    )
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        log.warning("groq JSON parse failed: %s — text=%s", e, text[:200])
        return {"error": f"json parse failed: {e}", "raw": text[:1000]}
