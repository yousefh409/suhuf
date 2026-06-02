#!/usr/bin/env python3
"""Measure tashkeel detection accuracy using TTS full-passage readings.

For each passage × phrase, generates TTS audio for the correct text, then
for each word with swappable internal diacritics, generates a modified version
with ONE word changed. Scores directly through the engine and checks if the
modified word would be flagged.

Also tests full-phrase correct readings for FP measurement.

Usage:
    python measure_tashkeel.py [--verbose] [--passage PASSAGE_ID]
"""

import asyncio
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import edge_tts
import numpy as np
import torch

BASE = Path(__file__).parent
CACHE_DIR = BASE / ".tts_cache"
CACHE_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(BASE))

TTS_VOICE = "ar-SA-HamedNeural"
MODEL_PATH = BASE / "models" / "ssl_xls_r_v5"

FATHA = '\u064e'
DAMMA = '\u064f'
KASRA = '\u0650'
FATHATAN = '\u064b'
DAMMATAN = '\u064c'
KASRATAN = '\u064d'
SUKOON = '\u0652'
SHADDA = '\u0651'
HARAKAT = frozenset({FATHA, DAMMA, KASRA, FATHATAN, DAMMATAN, KASRATAN, SUKOON, SHADDA})

SHORT_VOWELS = {FATHA, DAMMA, KASRA}
LONG_VOWELS = frozenset('\u0627\u064a\u0648\u0649')  # alif, ya, waw, alif maqsura


def strip_diacritics(text):
    return ''.join(c for c in text if c not in HARAKAT)


def categorize_swap(word, idx):
    """Categorize a swap test case.

    Returns: 'short_word', 'shadda_position', 'before_long_vowel', 'testable'
    """
    chars = list(word)
    consonants_only = strip_diacritics(word)

    if len(consonants_only) <= 2:
        return 'short_word'

    # Check if consonant before the vowel has shadda
    cons_pos = None
    for ci in range(idx - 1, -1, -1):
        if chars[ci] not in HARAKAT:
            cons_pos = ci
            break
    if cons_pos is not None:
        j = cons_pos + 1
        while j < len(chars) and chars[j] in HARAKAT:
            if chars[j] == SHADDA:
                return 'shadda_position'
            j += 1

    # Check if next non-diacritic char is a long vowel
    for ci in range(idx + 1, len(chars)):
        if chars[ci] not in HARAKAT:
            if chars[ci] in LONG_VOWELS:
                return 'before_long_vowel'
            break

    return 'testable'


def find_internal_diacritics(word):
    """Find swappable internal diacritics in a word.

    Returns list of (index, char, consonant_before, is_first_cons) for
    internal short vowels that can be swapped for testing.
    Skips the final diacritic (that's i3rab).
    """
    chars = list(word)
    consonants = [i for i, c in enumerate(chars) if c not in HARAKAT]
    if len(consonants) < 2:
        return []

    results = []
    last_cons_idx = consonants[-1]

    for i, ch in enumerate(chars):
        if ch not in SHORT_VOWELS:
            continue
        cons_idx = None
        for ci in range(i - 1, -1, -1):
            if chars[ci] not in HARAKAT:
                cons_idx = ci
                break
        if cons_idx is None:
            continue
        if cons_idx == last_cons_idx:
            continue
        is_first = (cons_idx == consonants[0])
        results.append((i, ch, chars[cons_idx], is_first))

    return results


def swap_diacritic(word, idx, original, replacement):
    """Replace diacritic at position idx."""
    chars = list(word)
    assert chars[idx] == original, f"Expected {repr(original)} at {idx}, got {repr(chars[idx])}"
    chars[idx] = replacement
    return ''.join(chars)


def pick_swap(original_diac):
    """Pick a different short vowel to swap to."""
    swaps = {
        FATHA: KASRA,   # fatha → kasra
        KASRA: DAMMA,   # kasra → damma
        DAMMA: FATHA,   # damma → fatha
    }
    return swaps[original_diac]


async def tts_generate(text: str, voice: str = TTS_VOICE) -> Path:
    """Generate TTS audio, cache by text hash."""
    key = hashlib.sha256(f"{voice}:{text}".encode()).hexdigest()[:16]
    raw_path = CACHE_DIR / f"{key}.raw"
    if raw_path.exists():
        return raw_path

    mp3_path = CACHE_DIR / f"{key}.mp3"
    comm = edge_tts.Communicate(text, voice)
    await comm.save(str(mp3_path))

    result = subprocess.run([
        "ffmpeg", "-y", "-i", str(mp3_path),
        "-f", "f32le", "-acodec", "pcm_f32le",
        "-ac", "1", "-ar", "16000",
        "-v", "quiet", str(raw_path),
    ], capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg error: {result.stderr.decode()}")
    mp3_path.unlink(missing_ok=True)
    return raw_path


def load_pcm(path):
    """Load raw PCM float32 file as torch tensor."""
    audio = np.fromfile(str(path), dtype=np.float32)
    return torch.from_numpy(audio.copy())


def classify_word(wr, threshold=0.08, tashkeel_threshold=0.12):
    """Check if a word result is flagged as an error (batch thresholds).

    Same logic as server.py classify_words with streaming=False.
    Returns (flagged, error_type, error_detail).
    """
    eff = wr["effective_score"]

    # Signal 1: CTC i3rab
    alt = wr["best_alt_score"]
    if alt > -900 and alt > eff + threshold:
        return True, "i3rab", wr["best_alt_name"]

    # Signal 2: CTC tashkeel
    tash = wr.get("best_tashkeel_score", -999.0)
    if tash > -900 and tash > eff + tashkeel_threshold:
        return True, "tashkeel", wr.get("best_tashkeel_name")

    # Signal 3: Per-char diacritic confidence (two-tier)
    pc = wr.get("pc_worst_delta", 999.0)
    if (pc < -4.5 and eff > -0.7) or (pc < -2.5 and eff > -0.3):
        return True, "diacritic", f"pc={pc:.2f}"

    # Signal 4: Shadda scoring
    shadda = wr.get("best_shadda_score", -999.0)
    if shadda > -900 and shadda > eff + 0.20:
        return True, "tashkeel", wr.get("best_shadda_name", "shadda")

    # Signal 5: Greedy internal diacritic mismatch
    gdm = wr.get("greedy_diac_mismatches", 0)
    if gdm >= 1 and eff > -0.5:
        return True, "tashkeel", f"greedy_{wr.get('greedy_diac_expected', '?')}_{wr.get('greedy_diac_heard', '?')}"

    # Signal 5b: Confirmed greedy — greedy mismatch + CTC/pc agreement
    gdm = wr.get("greedy_diac_mismatches", 0)
    if gdm >= 1 and -1.5 < eff <= -1.0:
        tash = wr.get("best_tashkeel_score", -999.0)
        pc = wr.get("pc_worst_delta", 999.0)
        if (tash > -900 and tash > eff + 0.03) or pc < -3.0:
            return True, "tashkeel", f"confirmed_greedy_{wr.get('greedy_diac_expected', '?')}_{wr.get('greedy_diac_heard', '?')}"

    # Signal 6: Greedy final diacritic mismatch + per-char confirmation
    gfm = wr.get("greedy_final_mismatch", False)
    pc = wr.get("pc_worst_delta", 999.0)
    if gfm and pc < -2.0 and eff > -1.0:
        return True, "i3rab", "greedy_final"

    return False, None, None


async def measure_passage(passage_id, phrases, engine, verbose=False):
    """Measure tashkeel detection for a passage using direct engine scoring."""

    full_text = " ".join(phrases)
    all_words = full_text.split()

    total_swaps = 0
    detected = 0
    missed = []

    # Category tracking
    cat_total = {'short_word': 0, 'shadda_position': 0, 'before_long_vowel': 0, 'testable': 0}
    cat_detected = {'short_word': 0, 'shadda_position': 0, 'before_long_vowel': 0, 'testable': 0}

    # Also track FP on correct readings
    total_correct_words = 0
    total_fp = 0
    fp_words = []

    for pi, phrase in enumerate(phrases):
        words = phrase.split()
        if len(words) > 15:
            if verbose:
                print(f"  [{passage_id}][{pi}] Skipping long phrase ({len(words)} words)")
            continue

        # 1. Test correct reading for FP
        wav = await tts_generate(phrase)
        waveform = load_pcm(wav)
        word_results, greedy, matched_idx, full_score = \
            engine.locate_and_score(waveform, full_text, phrases)

        if word_results:
            for wr in word_results:
                wi = wr["word_idx"]
                flagged, err_type, _ = classify_word(wr)
                total_correct_words += 1
                if flagged:
                    total_fp += 1
                    w = all_words[wi] if wi < len(all_words) else "?"
                    fp_words.append(f"{passage_id}[{pi}]:{w}({err_type})")

        # 2. Test each swappable internal diacritic
        for wi, word in enumerate(words):
            internals = find_internal_diacritics(word)
            if not internals:
                continue

            # Prefer non-first-consonant swaps (more meaningful)
            non_first = [d for d in internals if not d[3]]
            target = non_first[0] if non_first else internals[0]
            idx, orig_diac, cons, is_first = target
            new_diac = pick_swap(orig_diac)
            modified_word = swap_diacritic(word, idx, orig_diac, new_diac)
            category = categorize_swap(word, idx)
            cat_total[category] += 1

            # Build modified phrase
            mod_words = list(words)
            mod_words[wi] = modified_word
            modified_phrase = " ".join(mod_words)

            wav = await tts_generate(modified_phrase)
            waveform = load_pcm(wav)
            word_results, greedy, matched_idx, full_score = \
                engine.locate_and_score(waveform, full_text, phrases)

            total_swaps += 1

            # Find the target word in results (by global word index)
            # Compute global index of the target word
            global_offset = sum(len(phrases[i].split()) for i in range(pi))
            target_global = global_offset + wi

            target_flagged = False
            if word_results:
                for wr in word_results:
                    if wr["word_idx"] == target_global:
                        flagged, err_type, _ = classify_word(wr)
                        if flagged:
                            target_flagged = True
                        break

            if target_flagged:
                detected += 1
                cat_detected[category] += 1
                if verbose:
                    print(f"  ✓ [{passage_id}][{pi}] w{wi} {word} → {modified_word} [{category}]")
            else:
                missed.append({
                    "passage": passage_id,
                    "phrase_idx": pi,
                    "word_idx": wi,
                    "word": word,
                    "modified": modified_word,
                    "swap": f"{cons}: {repr(orig_diac)}→{repr(new_diac)}",
                })
                if verbose:
                    print(f"  ✗ [{passage_id}][{pi}] w{wi} {word} → {modified_word} (MISSED)")

    return {
        "total_swaps": total_swaps,
        "detected": detected,
        "missed": missed,
        "total_correct_words": total_correct_words,
        "total_fp": total_fp,
        "fp_words": fp_words,
        "cat_total": dict(cat_total),
        "cat_detected": dict(cat_detected),
    }


async def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    target_passage = None
    for arg in sys.argv[1:]:
        if arg.startswith("--passage="):
            target_passage = arg.split("=", 1)[1]

    with open(BASE / "passage.json") as f:
        data = json.load(f)

    passages = data["passages"]
    if target_passage:
        passages = [p for p in passages if p["id"] == target_passage]

    # Load engine once
    from engine import RecitationEngine
    engine = RecitationEngine(str(MODEL_PATH))

    grand_total_swaps = 0
    grand_detected = 0
    grand_missed = []
    grand_correct_words = 0
    grand_fp = 0
    grand_fp_words = []
    grand_cat_total = {'short_word': 0, 'shadda_position': 0, 'before_long_vowel': 0, 'testable': 0}
    grand_cat_detected = {'short_word': 0, 'shadda_position': 0, 'before_long_vowel': 0, 'testable': 0}

    for passage in passages:
        pid = passage["id"]
        phr = passage["phrases"]
        print(f"\n{'='*60}")
        print(f"Passage: {pid} ({len(phr)} phrases)")
        print(f"{'='*60}")

        result = await measure_passage(pid, phr, engine, verbose)

        pct = result["detected"] / result["total_swaps"] * 100 if result["total_swaps"] > 0 else 0
        fp_pct = result["total_fp"] / result["total_correct_words"] * 100 if result["total_correct_words"] > 0 else 0

        print(f"  Tashkeel: {result['detected']}/{result['total_swaps']} = {pct:.0f}%")
        print(f"  FP: {result['total_fp']}/{result['total_correct_words']} = {fp_pct:.1f}%")

        if result["missed"]:
            print(f"  Missed:")
            for m in result["missed"]:
                print(f"    [{m['phrase_idx']}] w{m['word_idx']} {m['word']} → {m['modified']} ({m['swap']})")

        grand_total_swaps += result["total_swaps"]
        grand_detected += result["detected"]
        grand_missed.extend(result["missed"])
        grand_correct_words += result["total_correct_words"]
        grand_fp += result["total_fp"]
        grand_fp_words.extend(result["fp_words"])
        for cat in grand_cat_total:
            grand_cat_total[cat] += result["cat_total"].get(cat, 0)
            grand_cat_detected[cat] += result["cat_detected"].get(cat, 0)

    print(f"\n{'='*60}")
    print(f"OVERALL")
    print(f"{'='*60}")
    pct = grand_detected / grand_total_swaps * 100 if grand_total_swaps > 0 else 0
    fp_pct = grand_fp / grand_correct_words * 100 if grand_correct_words > 0 else 0
    print(f"  Tashkeel detection: {grand_detected}/{grand_total_swaps} = {pct:.0f}%")
    print(f"  FP on correct:     {grand_fp}/{grand_correct_words} = {fp_pct:.1f}%")

    # Category breakdown
    print(f"\n  By category:")
    for cat in ['testable', 'shadda_position', 'before_long_vowel', 'short_word']:
        t = grand_cat_total[cat]
        d = grand_cat_detected[cat]
        p = d / t * 100 if t > 0 else 0
        label = cat.replace('_', ' ')
        print(f"    {label:20s}: {d:3d}/{t:3d} = {p:5.1f}%")

    t_test = grand_cat_total['testable']
    d_test = grand_cat_detected['testable']
    if t_test > 0:
        print(f"\n  EFFECTIVE (testable): {d_test}/{t_test} = {d_test/t_test*100:.1f}%")
        print(f"  (Excludes: short words, shadda positions, before-long-vowel — TTS cannot test these)")

    if grand_fp_words:
        print(f"\n  FP words: {grand_fp_words}")

    if verbose:
        print(f"\n  Missed ({len(grand_missed)}):")
        for m in grand_missed:
            print(f"    [{m['passage']}][{m['phrase_idx']}] w{m['word_idx']} {m['word']} → {m['modified']}")


if __name__ == "__main__":
    asyncio.run(main())
