"""Arabic text utilities for the recitation system."""

# Arabic diacritics (Unicode)
FATHA = '\u064E'           # َ
DAMMA = '\u064F'           # ُ
KASRA = '\u0650'           # ِ
FATHATAN = '\u064B'        # ً
DAMMATAN = '\u064C'        # ٌ
KASRATAN = '\u064D'        # ٍ
SUKOON = '\u0652'          # ْ
SHADDA = '\u0651'          # ّ
SUPERSCRIPT_ALIF = '\u0670'  # ٰ

HARAKAT = frozenset({FATHA, DAMMA, KASRA, FATHATAN, DAMMATAN, KASRATAN, SUKOON, SHADDA, SUPERSCRIPT_ALIF})
SHORT_VOWELS = frozenset({FATHA, DAMMA, KASRA})
TANWEEN = frozenset({FATHATAN, DAMMATAN, KASRATAN})


def strip_diacritics(text):
    """Remove all diacritics from Arabic text."""
    return ''.join(c for c in text if c not in HARAKAT)


def get_final_diacritic(word):
    """Get the diacritic(s) on the last consonant of a word.
    Returns (diacritics_string, last_consonant_index).
    """
    chars = list(word)
    last_cons = -1
    for i in range(len(chars) - 1, -1, -1):
        if chars[i] not in HARAKAT:
            last_cons = i
            break
    if last_cons == -1:
        return '', -1
    diacritics = ''
    for i in range(last_cons + 1, len(chars)):
        if chars[i] in HARAKAT:
            diacritics += chars[i]
    return diacritics, last_cons


def replace_final_diacritic(word, new_mark):
    """Replace the i3rab mark on the last consonant.
    Keeps shadda if present, replaces the vowel/case mark.
    """
    chars = list(word)
    last_cons = -1
    for i in range(len(chars) - 1, -1, -1):
        if chars[i] not in HARAKAT:
            last_cons = i
            break
    if last_cons == -1:
        return word
    # Keep everything up to and including last consonant
    result = chars[:last_cons + 1]
    # Keep shadda if it was there
    has_shadda = any(chars[i] == SHADDA for i in range(last_cons + 1, len(chars)))
    if has_shadda:
        result.append(SHADDA)
    # Add new mark
    if new_mark:
        result.append(new_mark)
    return ''.join(result)


def make_sukoon_variant(word):
    """Create the waqf (pausal) form with sukoon on last letter."""
    return replace_final_diacritic(word, SUKOON)


def generate_i3rab_alternatives(word):
    """Generate all plausible i3rab alternatives for a word.
    Returns dict {description: modified_word}.
    """
    alts = {}
    for mark, name in [
        (DAMMA, 'raf3'), (FATHA, 'nasb'), (KASRA, 'jarr'),
        (DAMMATAN, 'raf3_tanween'), (FATHATAN, 'nasb_tanween'),
        (KASRATAN, 'jarr_tanween'), (SUKOON, 'sukoon'),
    ]:
        variant = replace_final_diacritic(word, mark)
        if variant != word:
            alts[name] = variant
    return alts


def generate_tashkeel_alternatives(word):
    """Generate alternatives with each internal short vowel swapped.

    For each internal vowel position (not the final diacritic / i3rab),
    produce variants replacing that vowel with each of the other two
    short vowels.  Returns dict {description: modified_word}.

    Example: وَفِعْلٌ has internal fatha on و and kasra on ف.
    We generate variants like وَفَعْلٌ (kasra→fatha on ف),
    وَفُعْلٌ (kasra→damma on ف), etc.
    """
    chars = list(word)

    # Find last consonant index (to exclude final diacritics)
    last_cons = -1
    for i in range(len(chars) - 1, -1, -1):
        if chars[i] not in HARAKAT:
            last_cons = i
            break
    if last_cons == -1:
        return {}

    # Collect internal short-vowel and sukoon positions
    TASHKEEL_MARKS = SHORT_VOWELS | frozenset({SUKOON})
    vowel_positions = []
    for i, c in enumerate(chars):
        if c in TASHKEEL_MARKS and i < last_cons:
            vowel_positions.append(i)

    VOWEL_NAMES = {FATHA: 'fatha', DAMMA: 'damma', KASRA: 'kasra',
                   SUKOON: 'sukoon'}
    alts = {}
    for pos in vowel_positions:
        original = chars[pos]
        # Find the consonant this vowel belongs to (preceding non-diacritic)
        cons_idx = pos - 1
        while cons_idx >= 0 and chars[cons_idx] in HARAKAT:
            cons_idx -= 1
        cons_char = chars[cons_idx] if cons_idx >= 0 else '?'

        # Skip vowels on shadda'd consonants — the gemination makes
        # vowel quality acoustically ambiguous and causes false positives
        # in CTC hypothesis scoring. Per-char analysis still covers these.
        cluster_end = cons_idx + 1
        while cluster_end < len(chars) and chars[cluster_end] in HARAKAT:
            cluster_end += 1
        has_shadda = any(chars[j] == SHADDA
                        for j in range(cons_idx + 1, cluster_end))
        if has_shadda:
            continue

        for replacement in TASHKEEL_MARKS:
            if replacement == original:
                continue
            new_chars = chars.copy()
            new_chars[pos] = replacement
            name = f"tashkeel_{VOWEL_NAMES[replacement]}_on_{cons_char}"
            # Tag sukoon-related swaps (either direction) for separate thresholding
            if original == SUKOON or replacement == SUKOON:
                name += "_sukoon"
            # Deduplicate if same consonant letter appears multiple times
            if name in alts:
                name = f"{name}_{pos}"
            alts[name] = ''.join(new_chars)

    return alts
