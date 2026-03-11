"""Arabic text utilities for harakat manipulation and normalization."""

import re
import unicodedata

from .models import HARAKAT, HARAKA_NAMES, HarakaDiff


def strip_harakat(word: str) -> str:
    """Remove all tashkeel/diacritical marks, leaving only base letters."""
    return "".join(c for c in word if c not in HARAKAT)


def get_harakat_map(word: str) -> dict[int, list[str]]:
    """Map each base-letter index to its list of attached harakat."""
    result: dict[int, list[str]] = {}
    base_idx = -1
    for c in word:
        if c in HARAKAT:
            if base_idx >= 0:
                result.setdefault(base_idx, []).append(c)
        else:
            base_idx += 1
    return result


def get_last_letter_harakat(word: str) -> list[str]:
    """Get the harakat on the last base letter of a word (the i3rab position)."""
    hmap = get_harakat_map(word)
    base_len = len(strip_harakat(word))
    if base_len == 0:
        return []
    return hmap.get(base_len - 1, [])


def set_last_letter_harakat(word: str, new_harakat: list[str]) -> str:
    """Replace the harakat on the last base letter with new ones."""
    base = strip_harakat(word)
    if not base:
        return word
    hmap = get_harakat_map(word)
    last_idx = len(base) - 1
    hmap[last_idx] = new_harakat

    # Reconstruct word
    result = []
    for i, letter in enumerate(base):
        result.append(letter)
        for h in hmap.get(i, []):
            result.append(h)
    return "".join(result)


def has_harakat(text: str) -> bool:
    """Check if text contains any diacritical marks."""
    return any(c in HARAKAT for c in text)


def normalize_arabic(text: str) -> str:
    """Normalize Arabic text for comparison."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\u0671", "\u0627")  # Alef wasla -> regular alef
    text = text.replace("\u0627\u0644\u0652", "\u0627\u0644")  # Remove sukun on lam of ال
    text = re.sub(r"[^\u0600-\u06FF\s]", "", text)  # Strip non-Arabic
    return text.strip()


def format_haraka_list(harakat_list: list[str]) -> str:
    """Format a list of harakat codepoints into readable names."""
    if not harakat_list:
        return "(none)"
    return " + ".join(HARAKA_NAMES.get(h, repr(h)) for h in harakat_list)


_SHADDA = "\u0651"


def _normalize_harakat_order(marks: list[str]) -> list[str]:
    """Normalize harakat ordering: shadda always first."""
    if _SHADDA not in marks:
        return marks
    others = [m for m in marks if m != _SHADDA]
    return [_SHADDA] + others


def _shadda_equivalent(expected: list[str], got: list[str]) -> bool:
    """Check if harakat lists are equivalent modulo CTC shadda artifacts.

    Tolerates CTC emitting shadda-only where reference has shadda+vowel
    (the model confirmed gemination but didn't emit the implicit vowel).
    Does NOT tolerate: wrong vowel, or shadda dropped entirely.
    """
    norm_exp = _normalize_harakat_order(expected)
    norm_got = _normalize_harakat_order(got)

    if norm_exp == norm_got:
        return True

    # CTC dropped the vowel after shadda
    if (
        len(norm_got) == 1
        and norm_got[0] == _SHADDA
        and len(norm_exp) >= 1
        and norm_exp[0] == _SHADDA
    ):
        return True

    return False


def compare_harakat(ref_word: str, hyp_word: str) -> list[HarakaDiff]:
    """Compare harakat letter-by-letter, shadda-aware.

    Normalizes shadda+vowel ordering and tolerates CTC dropping
    the vowel after shadda (a known decoder artifact).
    """
    base = strip_harakat(ref_word)
    ref_map = get_harakat_map(ref_word)
    hyp_map = get_harakat_map(hyp_word)
    last_idx = len(base) - 1

    diffs = []
    for i, letter in enumerate(base):
        expected = ref_map.get(i, [])
        got = hyp_map.get(i, [])

        if _normalize_harakat_order(expected) == _normalize_harakat_order(got):
            continue

        if _shadda_equivalent(expected, got):
            continue

        diffs.append(HarakaDiff(
            letter=letter,
            position=i,
            expected=expected,
            got=got,
            is_irab=(i == last_idx),
        ))
    return diffs


def normalize_for_matching(word: str) -> str:
    """Normalize word for fuzzy base-form matching.

    Strips harakat, then removes trailing ta marbuta/ha so that
    ASR variants like 'الدرسة' match the book form 'الدرس'.
    """
    base = strip_harakat(word)
    if base.endswith("\u0629") or base.endswith("\u0647"):  # ة or ه
        base = base[:-1]
    return base


def is_preposition(word: str) -> bool:
    """Check if word is a common Arabic preposition (requires genitive after it)."""
    base = strip_harakat(word)
    prepositions = {"في", "من", "الى", "على", "عن", "الي", "إلى"}
    return base in prepositions


def is_definite(word: str) -> bool:
    """Check if word has the definite article ال."""
    base = strip_harakat(word)
    return base.startswith("ال") and len(base) > 2


def split_sentences(text: str) -> list[str]:
    """Split Arabic text into sentences based on punctuation."""
    # Split on Arabic/Latin sentence-ending punctuation
    parts = re.split(r'[.،؟!,؛\n]+', text)
    return [p.strip() for p in parts if p.strip()]
