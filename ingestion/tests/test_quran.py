"""Tests for ingestion.quran — Quran ayah index and matcher."""
import pytest
from ingestion.quran import normalize, lookup


def test_normalize_strips_diacritics_and_brackets():
    # Ornate bracket + diacritics
    assert normalize("﴿الْحَمْدُ﴾") == "الحمد"
    # Plain diacritics
    assert normalize("رَبِّ الْعَالَمِينَ") == "رب العالمين"


def test_normalize_alef_and_ya_variants():
    # أ إ آ → ا
    assert normalize("أإآ") == "اا ا".replace(" ", "")
    # More precisely: each alef variant becomes ا
    assert normalize("أ") == "ا"
    assert normalize("إ") == "ا"
    assert normalize("آ") == "ا"
    # ى → ي
    assert normalize("على") == "علي"
    # ة → ه
    assert normalize("رحمة") == "رحمه"


def test_lookup_exact_fatiha():
    # Exact match must win over substring matches in 6:45, 37:182, etc.
    result = lookup("الحمد لله رب العالمين")
    assert result == (1, 2)


def test_lookup_with_diacritics_and_brackets():
    # Should normalize before matching
    result = lookup("﴿الْحَمْدُ لِلَّهِ رَبِّ الْعَالَمِينَ﴾")
    assert result == (1, 2)


def test_lookup_no_match_returns_none():
    result = lookup("هذا كلام ليس من القرآن أبدا")
    assert result is None


def test_lookup_ambiguous_returns_none():
    # "الله" appears in very many ayat — not a unique match
    result = lookup("الله")
    assert result is None


def test_index_completeness():
    from ingestion.quran import _ayat_list
    assert len(_ayat_list) == 6236
    suras = {entry[1] for entry in _ayat_list}  # (norm_text, sura, ayah)
    assert len(suras) == 114
