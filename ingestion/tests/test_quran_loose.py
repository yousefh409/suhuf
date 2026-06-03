"""Tests for the loose (Uthmani-vs-standard tolerant) quran matcher."""
from ingestion.quran import loose_lookup


def test_loose_resolves_standard_orthography_ayahs():
    # Full ayahs in standard orthography that the strict matcher misses because
    # of Uthmani spelling (dagger alef, standalone hamza, word joining).
    assert loose_lookup("يا أيها الرسل كلوا من الطيبات واعملوا صالحا") == (23, 51)
    assert loose_lookup("يا أيها الذين آمنوا كلوا من طيبات ما رزقناكم") == (2, 172)
    assert loose_lookup("تتجافى جنوبهم عن المضاجع") == (32, 16)


def test_loose_ignores_braces():
    assert loose_lookup("{تتجافى جنوبهم عن المضاجع}") == (32, 16)


def test_loose_returns_none_for_short_or_ambiguous():
    assert loose_lookup("يعملون") is None          # too short
    assert loose_lookup("الحمد لله") is None        # common, not unique
    assert loose_lookup("الذين آمنوا") is None      # common phrase
