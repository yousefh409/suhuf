"""Deterministic hadith-structure detection.

Anchors on the universal prophetic-speech marker (قال رسول الله / عن النبي / …)
to split a prose hadith block into isnad / matn / takhrij inline spans, with a
confidence per span. Runs after parse, before tashkeel. See spec
docs/superpowers/specs/2026-06-03-deterministic-hadith-structure-design.md.
"""
from __future__ import annotations
import logging
import re

from ingestion.models import ParseResult, Span

logger = logging.getLogger(__name__)

HIGH_CONF = 0.95   # ≥2 signals agree (marker + quote or takhrij)
LOW_CONF = 0.70    # marker only

# Combining marks (harakat, sukun, dagger alef) + tatweel.
_TASHKEEL = re.compile(r"[ً-ْٰـ]")


def _norm(text: str) -> str:
    """Bare Arabic letters for marker matching: strip tashkeel, fold alef/ya/ta
    variants, drop non-letters (punctuation, «», digits, ﷺ)."""
    text = _TASHKEEL.sub("", text)
    text = text.translate(str.maketrans("أإآىة", "ااايه"))
    return "".join(c for c in text if "ء" <= c <= "ي")


# Prophetic-speech markers as normalized word tuples (the isnad→matn boundary).
PROPHETIC_MARKERS: tuple[tuple[str, ...], ...] = (
    ("قال", "رسول", "الله"),
    ("عن", "رسول", "الله"),
    ("ان", "رسول", "الله"),
    ("سمعت", "رسول", "الله"),
    ("قال", "النبي"),
    ("عن", "النبي"),
    ("ان", "النبي"),
    ("سمعت", "النبي"),
)

# Source-attribution keywords (normalized) that open a takhrij tail.
TAKHRIJ_NORM = {"رواه", "اخرجه", "اخرجها", "رواها", "متفق"}


def _find_prophetic_marker(norm_tokens: list[str]) -> int | None:
    """Return the index of the first token of the earliest prophetic marker
    phrase, or None if no marker is present."""
    for i in range(len(norm_tokens)):
        for phrase in PROPHETIC_MARKERS:
            if tuple(norm_tokens[i : i + len(phrase)]) == phrase:
                return i
    return None


def detect_hadith_structure(result: ParseResult) -> dict:
    """Stub — implemented in Task 2."""
    return {}
