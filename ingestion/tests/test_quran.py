"""Tests for ingestion.quran — Quran ayah index and matcher."""
import pytest
from ingestion.quran import normalize, lookup, lookup_match, sura_number, citation_to_ref


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


def test_lookup_match_reports_exact():
    # A full ayah resolves as an exact match.
    assert lookup_match("الحمد لله رب العالمين") == (1, 2, "exact")


def test_lookup_match_reports_containment():
    # A sura name ("آل عمران") is not a whole ayah but uniquely appears
    # inside ayah 3:33 — a weaker containment match.
    assert lookup_match("آل عمران") == (3, 33, "containment")


def test_lookup_match_no_match_returns_none():
    assert lookup_match("هذا كلام ليس من القرآن أبدا") is None


# ---------------------------------------------------------------------------
# Sura-name resolution and citation parsing
# ---------------------------------------------------------------------------

def test_sura_number_resolves_names():
    assert sura_number("الأعراف") == 7
    assert sura_number("آل عمران") == 3
    assert sura_number("ص") == 38
    assert sura_number("النحل") == 16


def test_sura_number_tolerates_orthographic_variants():
    # Hamza/alef variants and diacritics must not block the match.
    assert sura_number("الاعراف") == 7
    assert sura_number("الأَعراف") == 7


def test_sura_number_unknown_returns_none():
    assert sura_number("ليست سورة") is None


def test_citation_to_ref_single_ayah():
    assert citation_to_ref("الأنعام: 19") == "6:19"


def test_citation_to_ref_ayah_range():
    # Arabic comma between consecutive ayah numbers → a hyphenated range.
    assert citation_to_ref("القلم: 44، 45") == "68:44-45"


def test_citation_to_ref_arabic_indic_digits():
    assert citation_to_ref("النساء: ١٠٥") == "4:105"


def test_citation_to_ref_unknown_sura_returns_none():
    assert citation_to_ref("سورة مجهولة: 3") is None


def test_index_completeness():
    from ingestion.quran import _ayat_list
    assert len(_ayat_list) == 6236
    suras = {entry[1] for entry in _ayat_list}  # (norm_text, sura, ayah)
    assert len(suras) == 114
