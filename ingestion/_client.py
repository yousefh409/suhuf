"""Shared Anthropic client + response parsing for the ingestion pipeline."""
from __future__ import annotations
import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anthropic import Anthropic

logger = logging.getLogger(__name__)


def create_client() -> "Anthropic":
    """Create an Anthropic client from environment (reads ANTHROPIC_API_KEY)."""
    from anthropic import Anthropic
    return Anthropic()


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
