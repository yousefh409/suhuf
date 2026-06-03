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


# Introducers (normalized) that, immediately before a prophetic subject, mark
# the isnad→matn boundary: speech (قال/سمعت), transmission (عن/ان), and action
# verbs (نهى/كان/أمر/…). The subject is matched by _is_prophetic_subject.
PROPHETIC_INTRODUCERS = {
    "قال", "عن", "ان", "سمعت",
    "نهى", "كان", "امر", "مر", "رايت", "بعث", "قضى", "سئل",
}
_BLESSING = "صلى"  # opens "صلى الله عليه وسلم" — handles the الله-omitted "رسول ﷺ" form

# Source-attribution keywords (normalized) that open a takhrij tail.
TAKHRIJ_NORM = {"رواه", "اخرجه", "اخرجها", "رواها", "متفق"}


def _is_prophetic_subject(norm: list[str], j: int) -> bool:
    """True if token j begins a reference to the Prophet: "النبي", or "رسول"
    whose next non-empty token is "الله" or the blessing "صلى" (so a generic
    "رسول فلان" is excluded)."""
    if j >= len(norm):
        return False
    if norm[j] == "النبي":
        return True
    if norm[j] == "رسول":
        k = j + 1
        while k < len(norm) and norm[k] == "":
            k += 1
        return k < len(norm) and norm[k] in ("الله", _BLESSING)
    return False


def _find_prophetic_marker(norm_tokens: list[str]) -> int | None:
    """Return the index of the earliest introducer immediately followed by a
    prophetic subject (the isnad→matn boundary), or None if absent."""
    for i in range(len(norm_tokens)):
        if norm_tokens[i] in PROPHETIC_INTRODUCERS and _is_prophetic_subject(norm_tokens, i + 1):
            return i
    return None


def detect_hadith_structure(result: ParseResult) -> dict:
    """Mutate prose hadith blocks in place, adding isnad/matn/takhrij spans.
    Returns a stats dict."""
    stats = {"hadith": 0, "isnad": 0, "matn": 0, "takhrij": 0,
             "high_conf": 0, "low_conf": 0}
    for page in result.pages:
        for block in page.content_blocks:
            if block.type != "prose":
                continue
            # Skip blocks already structured (e.g. the rare native @MATN@ path).
            if any(s.label in ("isnad", "matn", "takhrij") for s in block.spans):
                continue
            _detect_block(block, stats)
    return stats


def _detect_block(block, stats: dict) -> None:
    toks = block.tokens
    norm = [_norm(t.text) for t in toks]
    b = _find_prophetic_marker(norm)
    if b is None:
        return  # no reliable boundary — leave to the LLM residual
    n = len(toks)

    # takhrij tail = first attribution keyword after the marker.
    takhrij_idx = next((j for j in range(b + 1, n) if norm[j] in TAKHRIJ_NORM), None)

    # quote close = first "»" at/after the marker (only if a "«" opened at/after b).
    quote_close = None
    if any("«" in toks[k].text for k in range(b, n)):
        quote_close = next((k for k in range(b, n) if "»" in toks[k].text), None)

    candidates = [n - 1]
    if takhrij_idx is not None:
        candidates.append(takhrij_idx - 1)
    if quote_close is not None:
        candidates.append(quote_close)
    matn_end = min(candidates)
    if matn_end < b:
        return  # self-check: matn would be empty

    conf = HIGH_CONF if (takhrij_idx is not None or quote_close is not None) else LOW_CONF
    if b > 0:
        block.spans.append(Span(start_token_id=toks[0].id, end_token_id=toks[b - 1].id,
                                label="isnad", confidence=conf))
        stats["isnad"] += 1
    block.spans.append(Span(start_token_id=toks[b].id, end_token_id=toks[matn_end].id,
                            label="matn", confidence=conf))
    stats["matn"] += 1
    if takhrij_idx is not None:
        block.spans.append(Span(start_token_id=toks[takhrij_idx].id, end_token_id=toks[n - 1].id,
                                label="takhrij", confidence=conf))
        stats["takhrij"] += 1
    stats["hadith"] += 1
    stats["high_conf" if conf == HIGH_CONF else "low_conf"] += 1
