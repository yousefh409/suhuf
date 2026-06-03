"""Quran ayah index and phrase matcher.

Public API
----------
normalize(text) -> str
    Clean Arabic text for comparison: strip diacritics, normalize alef/ya/taa-marbuta,
    remove brackets/tatweel, collapse whitespace.

lookup(quote) -> tuple[int, int] | None
    Resolve a Quranic phrase to (sura, ayah).
    Exact match wins; unique containment is the fallback.
    Returns None if no match or ambiguous.

_ayat_list is exposed for testing: list of (normalized_text, sura, ayah).
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

# Harakat / tashkeel range (does NOT include U+0670 or U+06E1 — handled separately)
_DIACRITICS = re.compile(r"[\u064B-\u065F]")
_PUNCTUATION = re.compile(r"[^\u0600-\u06FF\s]")  # keep Arabic block + spaces
_WHITESPACE = re.compile(r"\s+")

# Alef variants → plain alef; ya/taa-marbuta normalization
_ALEF_VARIANTS = str.maketrans("\u0623\u0625\u0622", "\u0627\u0627\u0627")  # أإآ → ا
_YA_TA = str.maketrans("\u0649\u0629", "\u064A\u0647")                      # ى→ي  ة→ه
_REMOVE = str.maketrans("", "", "\uFD3E\uFD3F\u0640")                       # ﴾﴿ + tatweel


def normalize(text: str) -> str:
    """Return a stripped, diacritic-free, variant-normalized Arabic string.

    Handles both standard Arabic and Uthmani script (as used in risan/quran-json):
    - U+0671 alef wasla (ٱ) → ا
    - U+06E1 Uthmani sukun (ۡ) → removed
    - U+0670 superscript alef (ٰ) → ا  (marks long-vowel alef in Uthmani spelling)

    Stripping scope: all characters outside the Arabic Unicode block (U+0600–U+06FF)
    and outside ASCII/Unicode whitespace are removed. This means Latin letters,
    digits, and punctuation are stripped entirely, not transliterated.
    """
    text = unicodedata.normalize("NFC", text)
    # Uthmani-specific: alef wasla → alef, Uthmani sukun → removed
    text = text.replace("\u0671", "\u0627").replace("\u06E1", "")
    # Superscript alef represents a long-vowel alef in Uthmani; keep as alef
    text = text.replace("\u0670", "\u0627")
    text = text.translate(_REMOVE)
    text = _DIACRITICS.sub("", text)
    text = text.translate(_ALEF_VARIANTS)
    text = text.translate(_YA_TA)
    text = _PUNCTUATION.sub("", text)
    text = _WHITESPACE.sub(" ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Index (built once at import time)
# ---------------------------------------------------------------------------

_DATA_FILE = Path(__file__).parent / "data" / "quran.json"

if not _DATA_FILE.exists():
    raise FileNotFoundError(f"Quran data file not found: {_DATA_FILE}")

with _DATA_FILE.open(encoding="utf-8") as _f:
    _raw = json.load(_f)

# _ayat_list: ordered list of (normalized_text, sura, ayah)
_ayat_list: list[tuple[str, int, int]] = [
    (normalize(entry[2]), entry[0], entry[1])
    for entry in _raw["ayat"]
]

# exact-match index: normalized_text -> list of (sura, ayah)
_exact: dict[str, list[tuple[int, int]]] = {}
for _norm, _s, _a in _ayat_list:
    _exact.setdefault(_norm, []).append((_s, _a))


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------

def lookup_match(quote: str) -> tuple[int, int, str] | None:
    """Resolve *quote* to (sura, ayah, kind), or None if not found / ambiguous.

    ``kind`` is "exact" when the normalized phrase equals a whole ayah, or
    "containment" when it uniquely appears *inside* exactly one ayah. Callers
    use the kind to weight the result: an exact match is the whole verse and
    trustworthy; a containment match is weaker (a fragment, or — for a citation
    marker like "[آل عمران: ١٨٧]" — just the sura name, which can coincide with
    an unrelated ayah).

    Priority:
    1. Exact match on normalized text — must be unique.
    2. Unique containment: exactly one ayah whose text contains the phrase.
    """
    norm = normalize(quote)
    if not norm:
        return None

    # 1. Exact match
    hits = _exact.get(norm)
    if hits and len(hits) == 1:
        return (hits[0][0], hits[0][1], "exact")

    # 2. Containment scan
    matches = [(s, a) for (t, s, a) in _ayat_list if norm in t]
    if len(matches) == 1:
        return (matches[0][0], matches[0][1], "containment")

    return None


def lookup(quote: str) -> tuple[int, int] | None:
    """Resolve *quote* to (sura, ayah), or None if not found / ambiguous.

    Thin wrapper over :func:`lookup_match` that drops the match kind.
    """
    hit = lookup_match(quote)
    return (hit[0], hit[1]) if hit is not None else None
