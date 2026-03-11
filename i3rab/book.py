"""Book loading, diacritization, and i3rab hypothesis generation."""

from dataclasses import dataclass
import unicodedata

from .models import BookWord, BookPhrase, WordHypothesis, HARAKAT, CASE_HARAKAT
from .arabic import (
    strip_harakat,
    has_harakat,
    get_harakat_map,
    get_last_letter_harakat,
    set_last_letter_harakat,
    normalize_arabic,
    split_sentences,
)


# Map final haraka → grammatical case name
HARAKA_TO_CASE = {
    "\u064E": "acc",        # fatha
    "\u064F": "nom",        # damma
    "\u0650": "gen",        # kasra
    "\u064B": "acc_indef",  # fathatan
    "\u064C": "nom_indef",  # dammatan
    "\u064D": "gen_indef",  # kasratan
    "\u0652": "jussive",    # sukun
}


# Letters that don't take i3rab endings (particles, etc.)
NO_IRAB_BASES = {
    "في", "من", "الى", "على", "عن", "الي", "إلى",  # prepositions
    "ان", "أن", "إن", "لن", "لم", "لا", "ما", "هل",  # particles
    "و", "ف", "ب", "ل", "ك",  # single-letter particles
    "هذا", "هذه", "ذلك", "تلك",  # demonstratives (partially declinable)
    "الذي", "التي", "الذين", "اللذان", "اللتان",  # relative pronouns
}

# Ta marbuta ending — takes different case endings
TA_MARBUTA = "\u0629"  # ة


def _generate_fathatan_alef_hypotheses(word: str, base: str) -> list[WordHypothesis]:
    """Generate hypotheses for words ending in fathatan+alef (acc indef).

    For words like جَمِيلًا, the alef is a spelling convention. The case
    ending is on the letter before the alef. The alef is removed for
    non-fathatan endings.
    """
    hypotheses = []
    # NFC-normalise for dedup (avoids shadda+vowel ordering duplicates)
    seen_nfc: set[str] = set()

    def _nfc(s: str) -> str:
        return unicodedata.normalize("NFC", s)

    # Original form is acc_indef (the fathatan IS the case marker)
    word_nfc = _nfc(word)
    hypotheses.append(WordHypothesis(
        diacritized=word_nfc, case="acc_indef", is_correct=True, is_pausal=False,
    ))
    seen_nfc.add(_nfc(word_nfc))

    # Remove trailing alef to get the stem for other endings
    word_no_alef = word[:-1]

    # Get the pre-alef letter's current harakat (to preserve shadda)
    hmap = get_harakat_map(word)
    pre_alef_idx = len(base) - 2
    pre_alef_harakat = hmap.get(pre_alef_idx, [])

    # Generate other case endings on the pre-alef letter, without alef
    for haraka, case_name in [
        ("\u064E", "acc"),        # fatha (definite accusative)
        ("\u064F", "nom"),        # damma
        ("\u0650", "gen"),        # kasra
        ("\u064C", "nom_indef"),  # dammatan
        ("\u064D", "gen_indef"),  # kasratan
        ("\u0652", "jussive"),    # sukun
    ]:
        new_harakat = [h for h in pre_alef_harakat if h == "\u0651"]
        new_harakat.append(haraka)

        variant = _nfc(set_last_letter_harakat(word_no_alef, new_harakat))
        if _nfc(variant) not in seen_nfc:
            seen_nfc.add(_nfc(variant))
            hypotheses.append(WordHypothesis(
                diacritized=variant, case=case_name,
                is_correct=False, is_pausal=False,
            ))

    # Pausal form: strip all harakat from pre-alef letter (keep shadda)
    pausal_harakat = [h for h in pre_alef_harakat if h == "\u0651"]
    pausal = _nfc(set_last_letter_harakat(word_no_alef, pausal_harakat))
    if _nfc(pausal) not in seen_nfc:
        seen_nfc.add(_nfc(pausal))
        hypotheses.append(WordHypothesis(
            diacritized=pausal, case="pausal",
            is_correct=False, is_pausal=True,
        ))

    return hypotheses


def _generate_irab_hypotheses(word: str) -> list[WordHypothesis]:
    """Generate all valid i3rab (case ending) hypotheses for a word.

    Uses rule-based approach: for the last letter, try all standard
    case endings (fatha, damma, kasra, tanween variants, sukun).
    """
    base = strip_harakat(word)

    if not base or len(base) <= 1:
        return [WordHypothesis(diacritized=word, case="original",
                               is_correct=True, is_pausal=False)]

    # Check if this word type takes i3rab
    if base in NO_IRAB_BASES:
        return [WordHypothesis(diacritized=word, case="original",
                               is_correct=True, is_pausal=False)]

    # Special case: fathatan+alef ending (e.g., جَمِيلًا, يَوْمًا)
    # The alef is a spelling convention; i3rab is on the preceding letter.
    last_letter = base[-1]
    if last_letter == "\u0627" and len(base) > 2:  # alef
        hmap = get_harakat_map(word)
        pre_alef_idx = len(base) - 2
        pre_alef_harakat = hmap.get(pre_alef_idx, [])
        if "\u064B" in pre_alef_harakat:  # fathatan on pre-alef letter
            return _generate_fathatan_alef_hypotheses(word, base)

    hypotheses = []
    # Use NFC-normalised forms for dedup to avoid spurious duplicates when the
    # last letter carries a shadda.  Arabic diacritics have distinct combining
    # classes (fatha=30, damma=31, kasra=32, shadda=33), so Unicode NFC
    # canonicalises their order: vowel first, then shadda.  Without this,
    # set_last_letter_harakat() emits shadda-first order and the original word
    # (which may store vowel-first) compares as a different string — producing
    # two "acc" hypotheses for the same surface form (e.g. ثُمَّ appears twice,
    # once is_correct=True and once is_correct=False).
    seen_nfc = set()

    def _nfc(s: str) -> str:
        return unicodedata.normalize("NFC", s)

    # Determine the grammatical case of the original form from its ending haraka
    last_harakat = get_last_letter_harakat(word)
    # Filter out shadda to find the case-indicating haraka
    case_harakat = [h for h in last_harakat if h != "\u0651"]
    if case_harakat and case_harakat[-1] in HARAKA_TO_CASE:
        original_case = HARAKA_TO_CASE[case_harakat[-1]]
    elif not case_harakat:
        original_case = "pausal"
    else:
        original_case = "original"

    # The original (correct) form — NFC-normalise to canonical byte order
    word_nfc = _nfc(word)
    hypotheses.append(WordHypothesis(
        diacritized=word_nfc, case=original_case, is_correct=True, is_pausal=(original_case == "pausal"),
    ))
    seen_nfc.add(_nfc(word_nfc))

    last_letter = base[-1]

    # Determine which case endings to try
    if last_letter == TA_MARBUTA:
        # Ta marbuta: fatha/damma/kasra (definite) or tanween (indefinite)
        endings_to_try = [
            ("\u064E", "acc"),     # fatha
            ("\u064F", "nom"),     # damma
            ("\u0650", "gen"),     # kasra
            ("\u064B", "acc_indef"),  # fathatan
            ("\u064C", "nom_indef"),  # dammatan
            ("\u064D", "gen_indef"),  # kasratan
        ]
    else:
        # Regular ending
        endings_to_try = [
            ("\u064E", "acc"),     # fatha
            ("\u064F", "nom"),     # damma
            ("\u0650", "gen"),     # kasra
            ("\u064B", "acc_indef"),  # fathatan
            ("\u064C", "nom_indef"),  # dammatan
            ("\u064D", "gen_indef"),  # kasratan
            ("\u0652", "jussive"),    # sukun
        ]

    for haraka, case_name in endings_to_try:
        # Check if last letter already has shadda — keep it
        current_harakat = get_last_letter_harakat(word)
        new_harakat = []
        for h in current_harakat:
            if h == "\u0651":  # shadda
                new_harakat.append(h)
        new_harakat.append(haraka)

        variant = _nfc(set_last_letter_harakat(word, new_harakat))
        variant_nfc_key = _nfc(variant)
        if variant_nfc_key not in seen_nfc:
            seen_nfc.add(variant_nfc_key)
            hypotheses.append(WordHypothesis(
                diacritized=variant,
                case=case_name,
                is_correct=False,
                is_pausal=False,
            ))

    # Pausal form: strip final haraka entirely (keep shadda if present)
    pausal_harakat = [h for h in get_last_letter_harakat(word) if h == "\u0651"]
    pausal = _nfc(set_last_letter_harakat(word, pausal_harakat))
    if _nfc(pausal) not in seen_nfc:
        seen_nfc.add(_nfc(pausal))
        hypotheses.append(WordHypothesis(
            diacritized=pausal, case="pausal",
            is_correct=False, is_pausal=True,
        ))

    return hypotheses


def _try_camel_hypotheses(word: str) -> list[WordHypothesis] | None:
    """Try to use CAMeL Tools for morphologically-informed hypotheses."""
    try:
        from camel_tools.morphology.database import MorphologyDB
        from camel_tools.morphology.analyzer import Analyzer
    except ImportError:
        return None

    try:
        db = MorphologyDB.builtin_db()
        analyzer = Analyzer(db)
        base = strip_harakat(word)
        analyses = analyzer.analyze(base)

        if not analyses:
            return None

        hypotheses = []
        seen = set()

        for a in analyses:
            diac = a.get("diac", "")
            if not diac or diac in seen:
                continue
            seen.add(diac)
            case = a.get("cas", "unknown")
            hypotheses.append(WordHypothesis(
                diacritized=diac,
                case=case,
                is_correct=(diac == word),
                is_pausal=False,
            ))

        if hypotheses:
            # Add pausal form
            pausal_harakat = [h for h in get_last_letter_harakat(word) if h == "\u0651"]
            pausal = set_last_letter_harakat(word, pausal_harakat)
            if pausal not in seen:
                hypotheses.append(WordHypothesis(
                    diacritized=pausal, case="pausal",
                    is_correct=False, is_pausal=True,
                ))
            return hypotheses
    except Exception:
        pass
    return None


def _diacritize_text(text: str) -> str:
    """Diacritize undiacritized Arabic text using CATT (if available)."""
    try:
        from catt_tashkeel import CATTEncoderDecoder
        catt = CATTEncoderDecoder()
        sentences = split_sentences(text)
        results = catt.do_tashkeel_batch(sentences, verbose=False)
        return " ".join(results)
    except ImportError:
        print("WARNING: catt-tashkeel not installed. Using text as-is.")
        print("Install with: pip install catt-tashkeel")
        return text
    except Exception as e:
        print(f"WARNING: CATT diacritization failed: {e}. Using text as-is.")
        return text


def _apply_grammar_constraints(words: list[BookWord]) -> list[BookWord]:
    """Prune hypotheses that violate basic Arabic grammar rules.

    Rules applied:
    - After a preposition → the following noun must be genitive
    - Definite nouns (with ال) cannot take tanween (indefinite endings)
    - Words with prefix preposition (بِ/لِ/كَ + base) → genitive only
    """
    for i, word in enumerate(words):
        if len(word.hypotheses) <= 2:
            continue  # Don't prune if too few hypotheses

        # Rule 1: After preposition → genitive only
        if i > 0 and words[i - 1].base in NO_IRAB_BASES:
            prev_base = words[i - 1].base
            # Only prepositions force genitive (not particles like هل, ما)
            prepositions = {
                "في", "من", "الى", "على", "عن", "الي", "إلى",
                "ب", "ل", "ك",
            }
            if prev_base in prepositions:
                filtered = [
                    h for h in word.hypotheses
                    if h.case in ("gen", "gen_indef", "pausal", "original")
                    or h.is_correct
                ]
                if len(filtered) >= 2:
                    word.hypotheses = filtered

        # Rule 2: Definite nouns can't take tanween
        if word.base.startswith("ال") and len(word.base) > 2:
            filtered = [
                h for h in word.hypotheses
                if h.case not in ("nom_indef", "acc_indef", "gen_indef")
                or h.is_correct
            ]
            if len(filtered) >= 2:
                word.hypotheses = filtered

        # Rule 3: Prefix preposition (بِ/لِ/كَ + base) → genitive only
        # When a word starts with a single-letter preposition prefix
        # attached to the base, the base must be in genitive case.
        base = word.base
        diac = word.correct_diac
        _PREFIX_PREPS = {
            "\u0628": "\u0650",  # ب with kasra (بِ)
            "\u0644": "\u0650",  # ل with kasra (لِ)
            "\u0643": "\u064E",  # ك with fatha (كَ)
        }
        if len(base) > 2 and base[0] in _PREFIX_PREPS:
            # Check that the prefix letter carries the expected haraka
            harakat_map = get_harakat_map(diac)
            prefix_harakat = harakat_map.get(0, [])
            expected_h = _PREFIX_PREPS[base[0]]
            if expected_h in prefix_harakat:
                filtered = [
                    h for h in word.hypotheses
                    if h.case in ("gen", "gen_indef", "pausal", "original")
                    or h.is_correct
                ]
                if len(filtered) >= 2:
                    word.hypotheses = filtered

    return words


class Book:
    """A book loaded for i3rab assessment."""

    def __init__(self, phrases: list[BookPhrase], title: str = ""):
        self.phrases = phrases
        self.title = title
        # Flat word list for position tracking
        self.words: list[BookWord] = []
        for phrase in phrases:
            self.words.extend(phrase.words)
        # Undiacritized word list for fuzzy matching
        self.base_words = [w.base for w in self.words]

    @classmethod
    def from_text(cls, text: str, title: str = "", auto_diacritize: bool = True) -> "Book":
        """Load book from text. Auto-diacritizes if text lacks harakat."""
        text = normalize_arabic(text)

        if auto_diacritize and not has_harakat(text):
            print("Text has no diacritics. Running auto-diacritization...")
            text = _diacritize_text(text)

        sentences = split_sentences(text)
        if not sentences:
            sentences = [text]

        phrases = []
        word_idx = 0

        for sent in sentences:
            words_text = sent.split()
            if not words_text:
                continue

            book_words = []
            for i, w in enumerate(words_text):
                # At end of sentence or before punctuation: allow pausal form
                is_phrase_end = (i == len(words_text) - 1)

                # Try CAMeL Tools first, fall back to rule-based
                hypotheses = _try_camel_hypotheses(w)
                if hypotheses is None:
                    hypotheses = _generate_irab_hypotheses(w)

                book_word = BookWord(
                    index=word_idx,
                    base=strip_harakat(w),
                    correct_diac=w,
                    hypotheses=hypotheses,
                    allows_pausal=True,
                )
                book_words.append(book_word)
                word_idx += 1

            # Apply grammar constraints to prune invalid hypotheses
            book_words = _apply_grammar_constraints(book_words)

            phrases.append(BookPhrase(
                words=book_words,
                start_idx=book_words[0].index,
                end_idx=book_words[-1].index + 1,
                text=sent,
            ))

        return cls(phrases, title)

    @classmethod
    def from_file(cls, path: str, title: str = "") -> "Book":
        """Load book from a text file."""
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        if not title:
            import os
            title = os.path.splitext(os.path.basename(path))[0]
        return cls.from_text(text, title)

    @classmethod
    def from_sentence(cls, sentence: str) -> "Book":
        """Create a single-sentence book (for quick testing)."""
        return cls.from_text(sentence, title="Quick Test", auto_diacritize=False)

    def get_phrase_for_position(self, word_idx: int) -> BookPhrase | None:
        """Get the phrase containing a given word index."""
        for phrase in self.phrases:
            if phrase.start_idx <= word_idx < phrase.end_idx:
                return phrase
        return None

    def __len__(self) -> int:
        return len(self.words)

    def __repr__(self) -> str:
        return f"Book(title={self.title!r}, words={len(self.words)}, phrases={len(self.phrases)})"
