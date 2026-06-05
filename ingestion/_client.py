"""Shared LLM client + response parsing for the ingestion pipeline.

Calls run through OpenRouter's Anthropic-compatible Messages endpoint, so the
Anthropic SDK is reused unchanged — only the base URL, auth, and model slugs
differ. Models are passed as OpenRouter slugs (e.g. ``anthropic/claude-sonnet-4``).
"""
from __future__ import annotations
import json
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anthropic import Anthropic

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api"


def create_client() -> "Anthropic":
    """Create an Anthropic SDK client pointed at OpenRouter (reads OPENROUTER_API_KEY).

    Uses ``auth_token`` so the SDK sends ``Authorization: Bearer <key>``, which is
    what OpenRouter expects. Raises if OPENROUTER_API_KEY is unset.
    """
    from anthropic import Anthropic

    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    return Anthropic(base_url=OPENROUTER_BASE_URL, auth_token=key)


def parse_json_response(text: str) -> dict:
    """Extract JSON from a Claude response, tolerating markdown code fences.
    Returns {} on parse failure (logged as a warning)."""
    text = text.strip()
    if text.startswith("```"):
        lines = [l for l in text.split("\n") if not l.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse JSON response: {e}; first 200 chars: {text[:200]}")
        return {}
