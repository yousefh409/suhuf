#!/usr/bin/env python3
"""Detailed analysis of tashkeel detection misses.

For each test case, collects full signal vectors and categorizes
misses to find remaining improvement opportunities.

Usage:
    python analyze_misses.py [--passage=ajrumiyyah]
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
DIAC_NAMES = {FATHA: 'fatha', DAMMA: 'damma', KASRA: 'kasra'}
LONG_VOWELS = frozenset('\u0627\u064a\u0648\u0649')  # alif, ya, waw, alif maqsura


def strip_diacritics(text):
    return ''.join(c for c in text if c not in HARAKAT)


def find_internal_diacritics(word):
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
    chars = list(word)
    chars[idx] = replacement
    return ''.join(chars)


def pick_swap(original_diac):
    swaps = {FATHA: KASRA, KASRA: DAMMA, DAMMA: FATHA}
    return swaps[original_diac]


async def tts_generate(text, voice=TTS_VOICE):
    key = hashlib.sha256(f"{voice}:{text}".encode()).hexdigest()[:16]
    raw_path = CACHE_DIR / f"{key}.raw"
    if raw_path.exists():
        return raw_path
    mp3_path = CACHE_DIR / f"{key}.mp3"
    comm = edge_tts.Communicate(text, voice)
    await comm.save(str(mp3_path))
    subprocess.run([
        "ffmpeg", "-y", "-i", str(mp3_path),
        "-f", "f32le", "-acodec", "pcm_f32le",
        "-ac", "1", "-ar", "16000", "-v", "quiet", str(raw_path),
    ], capture_output=True)
    mp3_path.unlink(missing_ok=True)
    return raw_path


def load_pcm(path):
    audio = np.fromfile(str(path), dtype=np.float32)
    return torch.from_numpy(audio.copy())


def categorize_swap(word, idx, orig_diac, cons_char):
    """Categorize a swap test case.

    Returns: 'short_word', 'shadda_position', 'before_long_vowel', 'testable'
    """
    chars = list(word)
    consonants_only = strip_diacritics(word)

    # Short word (≤2 consonants)
    if len(consonants_only) <= 2:
        return 'short_word'

    # Check if the consonant has shadda
    # Look at diacritics around the consonant
    cons_pos = None
    for ci in range(idx - 1, -1, -1):
        if chars[ci] not in HARAKAT:
            cons_pos = ci
            break
    if cons_pos is not None:
        # Check cluster after consonant for shadda
        j = cons_pos + 1
        while j < len(chars) and chars[j] in HARAKAT:
            if chars[j] == SHADDA:
                return 'shadda_position'
            j += 1

    # Check if the next non-diacritic char is a long vowel
    next_char = None
    for ci in range(idx + 1, len(chars)):
        if chars[ci] not in HARAKAT:
            next_char = chars[ci]
            break
    if next_char in LONG_VOWELS:
        return 'before_long_vowel'

    return 'testable'


def classify_word(wr, threshold=0.08, tashkeel_threshold=0.12):
    eff = wr["effective_score"]
    alt = wr["best_alt_score"]
    if alt > -900 and alt > eff + threshold:
        return True, "S1_i3rab"
    tash = wr.get("best_tashkeel_score", -999.0)
    if tash > -900 and tash > eff + tashkeel_threshold:
        return True, "S2_tashkeel"
    pc = wr.get("pc_worst_delta", 999.0)
    if (pc < -4.5 and eff > -0.7) or (pc < -2.5 and eff > -0.3):
        return True, "S3_perchar"
    shadda = wr.get("best_shadda_score", -999.0)
    if shadda > -900 and shadda > eff + 0.25:
        return True, "S4_shadda"
    gdm = wr.get("greedy_diac_mismatches", 0)
    if gdm >= 1 and eff > -0.5:
        return True, "S5_greedy"
    if gdm >= 1 and -1.5 < eff <= -1.0:
        tash2 = wr.get("best_tashkeel_score", -999.0)
        pc2 = wr.get("pc_worst_delta", 999.0)
        if (tash2 > -900 and tash2 > eff + 0.03) or pc2 < -3.0:
            return True, "S5b_confirmed"
    gfm = wr.get("greedy_final_mismatch", False)
    pc = wr.get("pc_worst_delta", 999.0)
    if gfm and pc < -2.0 and eff > -1.0:
        return True, "S6_greedy_final"
    return False, "none"


async def main():
    target_passage = None
    for arg in sys.argv[1:]:
        if arg.startswith("--passage="):
            target_passage = arg.split("=", 1)[1]

    with open(BASE / "passage.json") as f:
        data = json.load(f)

    passages = data["passages"]
    if target_passage:
        passages = [p for p in passages if p["id"] == target_passage]

    from engine import RecitationEngine
    engine = RecitationEngine(str(MODEL_PATH))

    # Collect all test cases with full signal data
    all_cases = []

    for passage in passages:
        pid = passage["id"]
        phrases = passage["phrases"]
        full_text = " ".join(phrases)

        print(f"\nProcessing: {pid} ({len(phrases)} phrases)")

        for pi, phrase in enumerate(phrases):
            words = phrase.split()
            if len(words) > 15:
                continue

            for wi, word in enumerate(words):
                internals = find_internal_diacritics(word)
                if not internals:
                    continue

                non_first = [d for d in internals if not d[3]]
                target = non_first[0] if non_first else internals[0]
                idx, orig_diac, cons, is_first = target
                new_diac = pick_swap(orig_diac)
                modified_word = swap_diacritic(word, idx, orig_diac, new_diac)

                # Categorize
                category = categorize_swap(word, idx, orig_diac, cons)

                # Build modified phrase and score
                mod_words = list(words)
                mod_words[wi] = modified_word
                modified_phrase = " ".join(mod_words)

                wav = await tts_generate(modified_phrase)
                waveform = load_pcm(wav)
                word_results, greedy, matched_idx, full_score = \
                    engine.locate_and_score(waveform, full_text, phrases)

                # Find target word result
                global_offset = sum(len(phrases[i].split()) for i in range(pi))
                target_global = global_offset + wi

                wr = None
                if word_results:
                    for r in word_results:
                        if r["word_idx"] == target_global:
                            wr = r
                            break

                flagged, signal = classify_word(wr) if wr else (False, "no_result")

                case = {
                    "passage": pid,
                    "phrase_idx": pi,
                    "word_idx": wi,
                    "word": word,
                    "modified": modified_word,
                    "category": category,
                    "detected": flagged,
                    "signal": signal,
                    "swap": f"{DIAC_NAMES.get(orig_diac,'?')}→{DIAC_NAMES.get(new_diac,'?')}",
                    "cons": cons,
                }
                if wr:
                    case.update({
                        "eff": wr["effective_score"],
                        "tash": wr.get("best_tashkeel_score", -999.0),
                        "tash_delta": (wr.get("best_tashkeel_score", -999.0) - wr["effective_score"])
                                      if wr.get("best_tashkeel_score", -999.0) > -900 else None,
                        "pc": wr.get("pc_worst_delta", 999.0),
                        "gdm": wr.get("greedy_diac_mismatches", 0),
                        "shadda_score": wr.get("best_shadda_score", -999.0),
                        "shadda_delta": (wr.get("best_shadda_score", -999.0) - wr["effective_score"])
                                        if wr.get("best_shadda_score", -999.0) > -900 else None,
                        "skip_tashkeel": wr.get("skip_tashkeel", False),
                        "greedy_seg": wr.get("greedy_segment", ""),
                    })

                all_cases.append(case)
                sys.stdout.write("." if flagged else "x")
                sys.stdout.flush()

        print()

    # === Analysis ===
    detected = [c for c in all_cases if c["detected"]]
    missed = [c for c in all_cases if not c["detected"]]

    print(f"\n{'='*70}")
    print(f"OVERALL: {len(detected)}/{len(all_cases)} = "
          f"{len(detected)/len(all_cases)*100:.1f}%")
    print(f"{'='*70}")

    # By category
    categories = ['short_word', 'shadda_position', 'before_long_vowel', 'testable']
    print(f"\n── By Category ──")
    for cat in categories:
        total = [c for c in all_cases if c["category"] == cat]
        det = [c for c in total if c["detected"]]
        miss = [c for c in total if not c["detected"]]
        pct = len(det) / len(total) * 100 if total else 0
        print(f"  {cat:20s}: {len(det):3d}/{len(total):3d} = {pct:5.1f}%  "
              f"(missed: {len(miss)})")

    # Effective rate (testable only)
    testable = [c for c in all_cases if c["category"] == 'testable']
    testable_det = [c for c in testable if c["detected"]]
    if testable:
        pct = len(testable_det) / len(testable) * 100
        print(f"\n  EFFECTIVE (testable only): {len(testable_det)}/{len(testable)} = {pct:.1f}%")

    # === Missed cases detail ===
    print(f"\n── Missed Cases Detail ──")
    for cat in categories:
        cat_missed = [c for c in missed if c["category"] == cat]
        if not cat_missed:
            continue
        print(f"\n  [{cat}] ({len(cat_missed)} missed):")
        for c in cat_missed[:15]:  # Show first 15
            eff = c.get("eff", "?")
            tash_d = c.get("tash_delta")
            pc = c.get("pc", "?")
            gdm = c.get("gdm", 0)
            shadda_d = c.get("shadda_delta")
            skip = c.get("skip_tashkeel", False)
            eff_str = f"eff={eff:+.2f}" if isinstance(eff, float) else f"eff={eff}"
            tash_str = f"tash_d={tash_d:+.3f}" if tash_d is not None else "tash_d=N/A"
            pc_str = f"pc={pc:+.2f}" if isinstance(pc, float) and pc < 900 else "pc=N/A"
            shadda_str = f"shd_d={shadda_d:+.3f}" if shadda_d is not None else "shd_d=N/A"
            print(f"    {c['word']:>20s}→{c['modified']:<20s}  {c['swap']:15s}  "
                  f"{eff_str}  {tash_str}  {pc_str}  gdm={gdm}  "
                  f"skip={skip}  {shadda_str}")
        if len(cat_missed) > 15:
            print(f"    ... ({len(cat_missed) - 15} more)")

    # === Signal availability analysis for misses ===
    print(f"\n── Signal availability in misses ──")
    for cat in categories:
        cat_missed = [c for c in missed if c["category"] == cat]
        if not cat_missed:
            continue

        has_tash = [c for c in cat_missed if c.get("tash_delta") is not None]
        has_pc = [c for c in cat_missed if isinstance(c.get("pc"), float) and c["pc"] < 900]
        has_gdm = [c for c in cat_missed if c.get("gdm", 0) >= 1]
        has_shadda = [c for c in cat_missed if c.get("shadda_delta") is not None]

        # How many could be rescued with relaxed thresholds?
        rescued_tash_005 = [c for c in cat_missed
                            if c.get("tash_delta") is not None
                            and c["tash_delta"] > 0.05]
        rescued_pc_35 = [c for c in cat_missed
                         if isinstance(c.get("pc"), float) and c["pc"] < -3.5
                         and isinstance(c.get("eff"), float) and c["eff"] > -1.0]
        rescued_pc_20 = [c for c in cat_missed
                         if isinstance(c.get("pc"), float) and c["pc"] < -2.0
                         and isinstance(c.get("eff"), float) and c["eff"] > -1.0]
        rescued_gdm_loose = [c for c in cat_missed
                             if c.get("gdm", 0) >= 1
                             and isinstance(c.get("eff"), float) and c["eff"] > -1.5]
        rescued_shadda_015 = [c for c in cat_missed
                              if c.get("shadda_delta") is not None
                              and c["shadda_delta"] > 0.15]

        print(f"\n  [{cat}] ({len(cat_missed)} missed):")
        print(f"    Has tash alternatives: {len(has_tash)} "
              f"(rescued @0.05: {len(rescued_tash_005)})")
        print(f"    Has pc signal: {len(has_pc)} "
              f"(rescued @-3.5/eff>-1.0: {len(rescued_pc_35)}, "
              f"@-2.0/eff>-1.0: {len(rescued_pc_20)})")
        print(f"    Has greedy mismatch: {len(has_gdm)} "
              f"(rescued @eff>-1.5: {len(rescued_gdm_loose)})")
        print(f"    Has shadda alt: {len(has_shadda)} "
              f"(rescued @0.15: {len(rescued_shadda_015)})")

        # Distribution of tash_delta for misses
        if has_tash:
            tash_deltas = sorted([c["tash_delta"] for c in has_tash])
            print(f"    Tash delta dist: min={tash_deltas[0]:.3f}  "
                  f"median={tash_deltas[len(tash_deltas)//2]:.3f}  "
                  f"max={tash_deltas[-1]:.3f}")

        # Distribution of pc for misses
        if has_pc:
            pc_vals = sorted([c["pc"] for c in has_pc])
            print(f"    PC delta dist:   min={pc_vals[0]:.2f}  "
                  f"median={pc_vals[len(pc_vals)//2]:.2f}  "
                  f"max={pc_vals[-1]:.2f}")

        # Eff distribution
        effs = [c["eff"] for c in cat_missed if isinstance(c.get("eff"), float)]
        if effs:
            effs.sort()
            print(f"    Eff dist:        min={effs[0]:.2f}  "
                  f"median={effs[len(effs)//2]:.2f}  "
                  f"max={effs[-1]:.2f}")


if __name__ == "__main__":
    asyncio.run(main())
