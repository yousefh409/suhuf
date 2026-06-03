"""Tests for deterministic hadith-structure detection."""
from pathlib import Path

from ingestion.hadith import _norm, _find_prophetic_marker, detect_hadith_structure
from ingestion.parse import parse_file


def test_norm_strips_tashkeel_and_normalizes_variants():
    assert _norm("قَالَ") == "قال"
    assert _norm("النَّبِيِّ") == "النبي"
    assert _norm("أنّ") == "ان"          # hamza-alef → bare alef
    assert _norm("الله:") == "الله"       # punctuation dropped


def test_find_marker_returns_phrase_start():
    norm = ["عن", "ابي", "هريره", "قال", "قال", "رسول", "الله"]
    # the SECOND "قال" starts "قال رسول الله"
    assert _find_prophetic_marker(norm) == 4


def test_find_marker_none_when_absent():
    assert _find_prophetic_marker(["عن", "ابي", "هريره", "قال", "كذا"]) is None


def test_find_marker_an_nabi_variant():
    norm = ["عن", "انس", "عن", "النبي", "انه", "قال"]
    assert _find_prophetic_marker(norm) == 2   # "عن النبي"
