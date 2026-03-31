#!/usr/bin/env python3
"""Evaluation harness: run all test recordings through the scoring engine."""

import sys, json, time
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

from engine import RecitationEngine
from arabic import strip_diacritics

MODEL_PATH = BASE / "models" / "ssl_xls_r_v5"
PASSAGES_FILE = BASE / "passage.json"
MANIFEST_FILE = BASE / "test_data" / "manifest.jsonl"
TEST_DIR = BASE / "test_data"


def load_phrases():
    with open(PASSAGES_FILE) as f:
        data = json.load(f)
    for p in data["passages"]:
        if p["id"] == "ajrumiyyah" and "phrases" in p:
            return p["phrases"]
    return []


def load_manifest():
    entries = []
    with open(MANIFEST_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def classify_recording(notes):
    """Classify a recording based on its notes.
    Returns (is_correct, error_details).
    """
    notes = notes.lower().strip()

    # "correct reading" or "correct ereading" (typo) or "test"
    if notes in ("correct reading", "correct ereading", "test"):
        return True, []

    # Handle "correct reading, ..." notes — parse the detail part
    if notes.startswith("correct reading"):
        detail = notes[len("correct reading"):].strip().lstrip(",").strip()
        if not detail:
            return True, []
        # Acceptable details: sukoon, pause, self-correction
        detail_lower = detail.lower()
        acceptable = ("sukoon" in detail_lower or "pause" in detail_lower
                      or "correct" in detail_lower)
        # Check for actual vowel errors mentioned alongside "correct reading"
        has_vowel_error = any(x in detail_lower for x in
                             ("fatha", "kasra", "dhamma", "damma", "tanween"))
        if acceptable and not has_vowel_error:
            return True, []
        if has_vowel_error:
            return False, [detail]
        return True, []

    # Parse non-"correct reading" notes
    errors = []
    is_sukoon_only = True

    parts = notes.split(".")
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if "sukoon" in part and "no tanween" not in part and not any(
                x in part for x in ("kasra", "fatha", "dhamma", "damma")):
            pass  # sukoon-only clause (includes "sukoon on tanween" = waqf)
        elif "kasra" in part or "fatha" in part or "dhamma" in part or "damma" in part:
            is_sukoon_only = False
            errors.append(part)
        elif "no tanween" in part:
            is_sukoon_only = False
            errors.append(part)
        else:
            is_sukoon_only = False
            errors.append(part)

    if is_sukoon_only:
        return True, []
    return False, errors


def run_evaluation(engine, phrases, manifest, verbose=False):
    """Run all recordings through the engine and collect results."""
    all_results = []

    for idx, entry in enumerate(manifest):
        audio_path = TEST_DIR / entry["file"]
        phrase_idx = entry["phrase_idx"]
        notes = entry["notes"]

        if phrase_idx >= len(phrases):
            continue

        phrase_text = phrases[phrase_idx]
        is_correct, error_details = classify_recording(notes)

        if verbose:
            print(f"\n[{idx:3d}] {entry['file']}")
            print(f"      Notes: {notes}")
            print(f"      Correct: {is_correct}")

        t0 = time.time()
        try:
            waveform = engine.load_audio(str(audio_path))
            word_results, greedy, full_score = engine.score_phrase(waveform, phrase_text)
        except Exception as e:
            print(f"      ERROR: {e}")
            continue
        elapsed = time.time() - t0

        rec_result = {
            "idx": idx,
            "file": entry["file"],
            "phrase_idx": phrase_idx,
            "notes": notes,
            "is_correct": is_correct,
            "error_details": error_details,
            "greedy": greedy,
            "full_score": full_score,
            "word_results": word_results,
            "elapsed": elapsed,
        }
        all_results.append(rec_result)

        if verbose:
            print(f"      Greedy: {greedy}")
            print(f"      Score: {full_score:.4f}  ({elapsed:.1f}s)")
            for wr in word_results:
                i3_delta = wr["effective_score"] - wr["best_alt_score"] if wr["best_alt_score"] > -900 else 999
                tash_score = wr.get("best_tashkeel_score", -999.0)
                tash_delta = wr["effective_score"] - tash_score if tash_score > -900 else 999
                pc = wr.get("pc_worst_delta", 999.0)
                print(f"        {wr['word']:>25s}  eff={wr['effective_score']:+.3f}  "
                      f"i3rab={wr['best_alt_score']:+.3f}({wr['best_alt_name'] or '-':>12s}) d={i3_delta:+.3f}  "
                      f"tash={tash_score:+.3f}({wr.get('best_tashkeel_name') or '-':>20s}) d={tash_delta:+.3f}  "
                      f"pc={pc:+.2f}")

    return all_results


def word_is_flagged(wr, threshold, tashkeel_threshold=None,
                    pc_tier1_delta=-4.5, pc_tier1_eff=-0.7,
                    pc_tier2_delta=-2.5, pc_tier2_eff=-0.3):
    """Check if a word result is flagged as an error.

    Three signals (OR): CTC i3rab, CTC tashkeel, per-char diacritic confidence.
    """
    if tashkeel_threshold is None:
        tashkeel_threshold = threshold
    eff = wr["effective_score"]
    # Signal 0: Wrong word
    consonant_match = wr.get("greedy_consonant_match", 1.0)
    frame_count = wr.get("frame_count", 999)
    word_text = wr.get("word", "")
    word_consonants = strip_diacritics(word_text)
    greedy_seg = wr.get("greedy_segment", "")
    # frame_count > 50 = ~1s for one word = likely misaligned, skip
    if (len(word_consonants) >= 3 and eff > -1.0
            and consonant_match < 0.4 and len(greedy_seg) > 0
            and frame_count <= 50):
        return True, "wrong", greedy_seg, 1.0 - consonant_match
    # Signal -1: Skipped word (very few frames + very poor score + not a short word)
    if frame_count < 3 and eff < -3.5 and len(word_consonants) >= 3:
        return True, "skipped", None, 0
    # i3rab flag
    alt = wr["best_alt_score"]
    if alt > -900 and alt > eff + threshold:
        return True, "i3rab", wr["best_alt_name"], alt - eff
    # tashkeel flag (vowel-swap)
    tash = wr.get("best_tashkeel_score", -999.0)
    if tash > -900 and tash > eff + tashkeel_threshold:
        return True, "tashkeel", wr.get("best_tashkeel_name"), tash - eff
    # tashkeel flag (sukoon — higher threshold due to CTC length bias)
    sukoon_alt = wr.get("best_sukoon_score", -999.0)
    if sukoon_alt > -900 and sukoon_alt > eff + tashkeel_threshold + 0.10:
        return True, "tashkeel", wr.get("best_sukoon_name"), sukoon_alt - eff
    # per-char diacritic confidence (two-tier)
    pc = wr.get("pc_worst_delta", 999.0)
    if (pc < pc_tier1_delta and eff > pc_tier1_eff) or \
       (pc < pc_tier2_delta and eff > pc_tier2_eff):
        return True, "diacritic", f"pc={pc:.2f}", -pc
    # shadda-position diacritic scoring
    shadda = wr.get("best_shadda_score", -999.0)
    if shadda > -900 and shadda > eff + 0.20:
        return True, "tashkeel", wr.get("best_shadda_name", "shadda"), shadda - eff
    # greedy internal diacritic mismatch (tashkeel) — requires CTC or pc confirmation
    gdm = wr.get("greedy_diac_mismatches", 0)
    if gdm >= 1 and eff > -0.5:
        tash = wr.get("best_tashkeel_score", -999.0)
        pc = wr.get("pc_worst_delta", 999.0)
        if (tash > -900 and tash > eff + 0.03) or pc < -2.0:
            return True, "tashkeel", f"greedy_tash", gdm
    # Signal 5b: Confirmed greedy — greedy mismatch + CTC/pc agreement
    gdm = wr.get("greedy_diac_mismatches", 0)
    if gdm >= 1 and -1.5 < eff <= -1.0:
        tash = wr.get("best_tashkeel_score", -999.0)
        pc = wr.get("pc_worst_delta", 999.0)
        if (tash > -900 and tash > eff + 0.03) or pc < -3.0:
            return True, "tashkeel", "confirmed_greedy", gdm
    # greedy final diacritic mismatch (i3rab) + per-char confirmation
    gfm = wr.get("greedy_final_mismatch", False)
    pc = wr.get("pc_worst_delta", 999.0)
    if gfm and pc < -2.0 and eff > -1.0:
        return True, "i3rab", f"greedy_final", 0
    return False, None, None, 0.0


def analyze_results(all_results, threshold=0.08, tashkeel_threshold=0.12):
    """Analyze results and report accuracy metrics."""

    print(f"\n{'='*80}")
    print(f"EVALUATION RESULTS  (i3rab_thresh={threshold}, tashkeel_thresh={tashkeel_threshold})")
    print(f"{'='*80}")
    print(f"Total recordings: {len(all_results)}")

    correct_recs = [r for r in all_results if r["is_correct"]]
    error_recs = [r for r in all_results if not r["is_correct"]]

    print(f"Correct recordings: {len(correct_recs)}")
    print(f"Error recordings: {len(error_recs)}")

    # ── False positives on correct recordings ──
    total_correct_words = 0
    false_positives = 0
    fp_details = []

    for rec in correct_recs:
        for wr in rec["word_results"]:
            total_correct_words += 1
            flagged, err_type, err_name, delta = word_is_flagged(wr, threshold, tashkeel_threshold)
            if flagged:
                false_positives += 1
                fp_details.append({
                    "file": rec["file"],
                    "word": wr["word"],
                    "eff": wr["effective_score"],
                    "type": err_type,
                    "alt_name": err_name,
                    "delta": delta,
                })

    fp_rate = false_positives / total_correct_words * 100 if total_correct_words > 0 else 0

    print(f"\n── False Positives (correct readings flagged as errors) ──")
    print(f"Total correct words: {total_correct_words}")
    print(f"False positives: {false_positives}  ({fp_rate:.1f}%)")
    if fp_details:
        print(f"Details:")
        for fp in fp_details[:20]:
            print(f"  {fp['file']}: {fp['word']}  eff={fp['eff']:+.3f}  "
                  f"[{fp['type']}] {fp['alt_name']}  delta={fp['delta']:+.3f}")

    # ── Score distributions ──
    print(f"\n── Score distributions for correct recordings ──")
    i3rab_deltas = []
    tashkeel_deltas = []
    for rec in correct_recs:
        for wr in rec["word_results"]:
            eff = wr["effective_score"]
            alt = wr["best_alt_score"]
            if alt > -900:
                i3rab_deltas.append(eff - alt)
            tash = wr.get("best_tashkeel_score", -999.0)
            if tash > -900:
                tashkeel_deltas.append(eff - tash)

    import numpy as np
    for label, deltas in [("i3rab", i3rab_deltas), ("tashkeel", tashkeel_deltas)]:
        if deltas:
            deltas.sort()
            d = np.array(deltas)
            print(f"  {label} delta (eff - alt):  min={d.min():.4f}  p5={np.percentile(d,5):.4f}  "
                  f"p25={np.percentile(d,25):.4f}  median={np.median(d):.4f}  "
                  f"p75={np.percentile(d,75):.4f}  max={d.max():.4f}")
            print(f"    Negative deltas (alt > eff): {(d < 0).sum()} / {len(d)}")

    # ── Error detection on error recordings ──
    print(f"\n── Error Detection (recordings with intentional errors) ──")
    for rec in error_recs:
        flagged = []
        for wr in rec["word_results"]:
            is_flagged, err_type, err_name, delta = word_is_flagged(wr, threshold, tashkeel_threshold)
            if is_flagged:
                flagged.append(f"{wr['word']}([{err_type}]{err_name})")

        flag_str = ", ".join(flagged) if flagged else "NONE DETECTED"
        print(f"  [{rec['idx']:3d}] {rec['notes'][:70]}")
        print(f"        Flagged: {flag_str}")

    # ── 2D threshold sweep (i3rab x tashkeel) ──
    print(f"\n── 2D Threshold sweep (i3rab_thresh x tashkeel_thresh) ──")
    i3rab_vals = [0.02, 0.05, 0.08, 0.10, 0.15]
    tash_vals = [0.05, 0.10, 0.15, 0.20, 0.25]

    # Header
    header = "          " + "".join(f"  tash={tv:.2f}" for tv in tash_vals)
    print(header)

    for i3t in i3rab_vals:
        row = f"i3r={i3t:.2f}"
        for tt in tash_vals:
            fp = 0
            for rec in correct_recs:
                for wr in rec["word_results"]:
                    flagged, _, _, _ = word_is_flagged(wr, i3t, tt)
                    if flagged:
                        fp += 1
            detected = 0
            for rec in error_recs:
                any_flagged = False
                for wr in rec["word_results"]:
                    flagged, _, _, _ = word_is_flagged(wr, i3t, tt)
                    if flagged:
                        any_flagged = True
                if any_flagged:
                    detected += 1

            fp_pct = fp / total_correct_words * 100 if total_correct_words > 0 else 0
            det_pct = detected / len(error_recs) * 100 if error_recs else 0
            row += f"  {fp_pct:4.1f}/{det_pct:4.0f}%"
        print(row)

    print("  (Format: FP% / Detection%)")


def main():
    phrases = load_phrases()
    manifest = load_manifest()

    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    threshold = 0.08
    tashkeel_threshold = 0.12
    for arg in sys.argv[1:]:
        if arg.startswith("--threshold="):
            threshold = float(arg.split("=")[1])
        if arg.startswith("--tashkeel-threshold="):
            tashkeel_threshold = float(arg.split("=")[1])

    engine = RecitationEngine(str(MODEL_PATH))

    print(f"Running {len(manifest)} recordings...")
    results = run_evaluation(engine, phrases, manifest, verbose=verbose)
    analyze_results(results, threshold=threshold, tashkeel_threshold=tashkeel_threshold)


if __name__ == "__main__":
    main()
