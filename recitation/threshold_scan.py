#!/usr/bin/env python3
"""Threshold scanner: finds optimal thresholds for multi-signal voting.

Scores both correct text and mutated text for every phrase, collecting all raw
signals. Then searches for individual and combined thresholds that maximize
detection_rate - 5 * false_positive_rate.

Uses the same infrastructure as test_mutations.py.
"""
import sys
import json
import random
import numpy as np
import torch
from pathlib import Path
from collections import defaultdict
from itertools import combinations

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

from engine import RecitationEngine, StreamingSession
from server import classify_words
from arabic import (
    FATHA, DAMMA, KASRA, FATHATAN, DAMMATAN, KASRATAN, SUKOON, SHADDA,
    HARAKAT, strip_diacritics, generate_i3rab_alternatives, generate_tashkeel_alternatives,
)

MODEL_PATH = BASE / "models" / "ssl_xls_r_v5"
FRAME_STRIDE = 320
SAMPLE_RATE = 16000

# Import mutation generators from test_mutations
from test_mutations import (
    mutate_i3rab, mutate_tashkeel, mutate_word,
    find_best_sessions, _extract_phrase_segments,
)


def extract_signals(wr):
    """Extract all raw signals from a word_result dict (engine output).

    Returns a dict of signal_name -> value. Missing/unavailable signals are None.
    """
    eff = wr.get("effective_score", -999.0)

    # i3rab delta: best alternative i3rab score - effective score
    alt = wr.get("best_alt_score", -999.0)
    i3rab_delta = (alt - eff) if alt > -900 else None

    # tashkeel delta
    tash = wr.get("best_tashkeel_score", -999.0)
    tash_delta = (tash - eff) if tash > -900 else None

    # sukoon delta (tashkeel variant)
    sukoon_alt = wr.get("best_sukoon_score", -999.0)
    sukoon_delta = (sukoon_alt - eff) if sukoon_alt > -900 else None

    # shadda delta
    shadda = wr.get("best_shadda_score", -999.0)
    shadda_delta = (shadda - eff) if shadda > -900 else None

    # Per-char worst delta
    pc_worst = wr.get("pc_worst_delta", 999.0)
    pc_worst_delta = pc_worst if pc_worst < 900 else None

    # SF-GOP worst delta
    sf_worst = wr.get("sf_worst_delta", 999.0)
    sf_worst_delta = sf_worst if sf_worst < 900 else None

    # MixGoP margin
    mg = wr.get("mg_worst_margin", 999.0)
    mg_margin = mg if mg < 900 else None

    # Greedy diac mismatches
    gdm = wr.get("greedy_diac_mismatches", 0)
    gfm = wr.get("greedy_final_mismatch", False)

    # Consonant match and frame count
    consonant_match = wr.get("greedy_consonant_match", 1.0)
    frame_count = wr.get("frame_count", 999)

    return {
        "eff": eff,
        "i3rab_delta": i3rab_delta,
        "tash_delta": tash_delta,
        "sukoon_delta": sukoon_delta,
        "shadda_delta": shadda_delta,
        "pc_worst_delta": pc_worst_delta,
        "sf_worst_delta": sf_worst_delta,
        "mg_margin": mg_margin,
        "gdm": gdm,
        "gfm": 1 if gfm else 0,
        "consonant_match": consonant_match,
        "frame_count": frame_count,
    }


def score_phrase_raw(engine, audio_segment, phrase_text):
    """Score a phrase, returning raw word_results (no classification).

    Returns list of per-word dicts with all signals.
    """
    waveform = torch.from_numpy(audio_segment)
    word_results, greedy, full_score = engine.score_phrase(waveform, phrase_text)
    return word_results


def collect_data(engine, sessions):
    """Collect signal data for all correct words and all mutations.

    Returns list of dicts:
      {signals: {...}, label: "correct"|"mutated_i3rab"|"mutated_tashkeel"|"mutated_word",
       word: str, phrase_idx: int, word_idx: int, ...}
    """
    all_data = []

    for pid in sorted(sessions):
        si = sessions[pid]
        phrases = si["meta"]["phrases"]
        audio = si["audio"]
        full_text = " ".join(phrases)
        all_words = full_text.split()

        print(f"\n{'='*60}")
        print(f"SESSION: {si['session_dir'].name} ({si['duration']:.1f}s)")
        print(f"PASSAGE: {pid}")
        print(f"{'='*60}")

        # Step 1: Full text alignment to get CTC boundaries
        print(f"  Scoring full text ({len(all_words)} words)...")
        waveform = torch.from_numpy(audio)
        word_results, greedy, full_score = engine.score_phrase(waveform, full_text)

        # Step 2: Extract per-phrase audio segments
        segments = _extract_phrase_segments(word_results, phrases, audio)
        covered = sorted(segments.keys())
        print(f"  Covered phrases: {len(covered)}/{len(phrases)}")

        # Step 3: Whisper per segment (for completeness, though we focus on CTC signals)
        whisper_per_phrase = {}
        for pi in covered:
            seg = segments[pi]
            whisper_per_phrase[pi] = engine.whisper_transcribe(seg)

        # ── PHASE 1: Correct text ──
        print(f"  Phase 1: Scoring correct text...")
        correct_count = 0

        for pi in covered:
            phrase = phrases[pi]
            pw = phrase.split()
            seg = segments[pi]

            try:
                wrs = score_phrase_raw(engine, seg, phrase)
            except Exception as e:
                print(f"    Error on phrase {pi}: {e}")
                continue

            for wr in wrs:
                wi = wr["word_idx"]
                if wi >= len(pw):
                    continue
                signals = extract_signals(wr)
                all_data.append({
                    "signals": signals,
                    "label": "correct",
                    "word": pw[wi],
                    "passage_id": pid,
                    "phrase_idx": pi,
                    "word_idx": wi,
                })
                correct_count += 1

        print(f"    Collected {correct_count} correct words")

        # ── PHASE 2: Mutations ──
        print(f"  Phase 2: Scoring mutations...")
        mut_counts = {"i3rab": 0, "tashkeel": 0, "word": 0}

        for pi in covered:
            phrase = phrases[pi]
            pw = phrase.split()
            seg = segments[pi]

            # i3rab mutations
            for wi, word in enumerate(pw):
                mutated, desc = mutate_i3rab(word)
                if mutated is None:
                    continue
                mut_words = list(pw)
                mut_words[wi] = mutated
                mut_text = " ".join(mut_words)

                try:
                    wrs = score_phrase_raw(engine, seg, mut_text)
                except Exception:
                    continue

                for wr in wrs:
                    if wr["word_idx"] == wi:
                        signals = extract_signals(wr)
                        all_data.append({
                            "signals": signals,
                            "label": "mutated_i3rab",
                            "word": word,
                            "mutated_to": mutated,
                            "mutation_desc": desc,
                            "passage_id": pid,
                            "phrase_idx": pi,
                            "word_idx": wi,
                        })
                        mut_counts["i3rab"] += 1
                        break

            # tashkeel mutations
            for wi, word in enumerate(pw):
                if len(strip_diacritics(word)) < 3:
                    continue
                mutated, desc = mutate_tashkeel(word)
                if mutated is None:
                    continue
                mut_words = list(pw)
                mut_words[wi] = mutated
                mut_text = " ".join(mut_words)

                try:
                    wrs = score_phrase_raw(engine, seg, mut_text)
                except Exception:
                    continue

                for wr in wrs:
                    if wr["word_idx"] == wi:
                        signals = extract_signals(wr)
                        all_data.append({
                            "signals": signals,
                            "label": "mutated_tashkeel",
                            "word": word,
                            "mutated_to": mutated,
                            "mutation_desc": desc,
                            "passage_id": pid,
                            "phrase_idx": pi,
                            "word_idx": wi,
                        })
                        mut_counts["tashkeel"] += 1
                        break

            # word replacements (2 per phrase)
            candidates = [i for i, w in enumerate(pw) if len(strip_diacritics(w)) >= 3]
            if candidates:
                test_idxs = random.sample(candidates, min(2, len(candidates)))
                for wi in test_idxs:
                    mut_words_list, desc = mutate_word(pw, wi)
                    mut_text = " ".join(mut_words_list)

                    try:
                        wrs = score_phrase_raw(engine, seg, mut_text)
                    except Exception:
                        continue

                    for wr in wrs:
                        if wr["word_idx"] == wi:
                            signals = extract_signals(wr)
                            all_data.append({
                                "signals": signals,
                                "label": "mutated_word",
                                "word": pw[wi],
                                "mutated_to": mut_words_list[wi],
                                "mutation_desc": desc,
                                "passage_id": pid,
                                "phrase_idx": pi,
                                "word_idx": wi,
                            })
                            mut_counts["word"] += 1
                            break

        print(f"    Mutations: i3rab={mut_counts['i3rab']}, "
              f"tashkeel={mut_counts['tashkeel']}, word={mut_counts['word']}")

    return all_data


def print_distribution_table(all_data):
    """Print summary statistics for each signal, split by label."""
    labels = sorted(set(d["label"] for d in all_data))
    signal_names = [
        "eff", "i3rab_delta", "tash_delta", "sukoon_delta", "shadda_delta",
        "pc_worst_delta", "sf_worst_delta", "mg_margin",
        "gdm", "gfm", "consonant_match", "frame_count",
    ]

    print(f"\n{'='*100}")
    print(f"SIGNAL DISTRIBUTIONS")
    print(f"{'='*100}")

    for sig in signal_names:
        print(f"\n  Signal: {sig}")
        print(f"  {'Label':<20s} {'Count':>6s} {'Mean':>8s} {'Std':>8s} "
              f"{'Min':>8s} {'P25':>8s} {'Median':>8s} {'P75':>8s} {'Max':>8s}")
        print(f"  {'-'*86}")

        for label in labels:
            values = [d["signals"][sig] for d in all_data
                      if d["label"] == label and d["signals"][sig] is not None]
            if not values:
                print(f"  {label:<20s} {'0':>6s} {'N/A':>8s}")
                continue

            arr = np.array(values)
            print(f"  {label:<20s} {len(arr):>6d} {arr.mean():>8.3f} {arr.std():>8.3f} "
                  f"{arr.min():>8.3f} {np.percentile(arr, 25):>8.3f} "
                  f"{np.median(arr):>8.3f} {np.percentile(arr, 75):>8.3f} "
                  f"{arr.max():>8.3f}")


def find_optimal_single_thresholds(all_data):
    """For each signal, find the threshold maximizing detection - 5*FP.

    For "delta" signals (i3rab_delta, tash_delta, etc), higher values indicate
    the mutated form scores better -> error. So we flag when signal > threshold.

    For "worst delta" signals (pc_worst_delta, sf_worst_delta), more negative
    values indicate error. So we flag when signal < threshold (i.e., threshold
    is negative).

    For gdm/gfm, we flag when count >= threshold.
    For consonant_match, we flag when match < threshold.
    """
    print(f"\n{'='*100}")
    print(f"OPTIMAL SINGLE-SIGNAL THRESHOLDS")
    print(f"{'='*100}")
    print(f"  Objective: detection_rate - 5 * false_positive_rate")
    print()

    # Define signal configs: (name, direction, candidate_thresholds)
    # direction = "higher_is_error" means flag when signal > threshold
    # direction = "lower_is_error" means flag when signal < threshold
    signal_configs = [
        ("i3rab_delta", "higher_is_error",
         np.arange(0.01, 0.50, 0.01)),
        ("tash_delta", "higher_is_error",
         np.arange(0.01, 0.50, 0.01)),
        ("sukoon_delta", "higher_is_error",
         np.arange(0.01, 0.60, 0.01)),
        ("shadda_delta", "higher_is_error",
         np.arange(0.01, 0.60, 0.01)),
        ("pc_worst_delta", "lower_is_error",
         np.arange(-10.0, 0.0, 0.25)),
        ("sf_worst_delta", "lower_is_error",
         np.arange(-15.0, 0.0, 0.25)),
        ("mg_margin", "lower_is_error",
         np.arange(-10.0, 0.0, 0.25)),
        ("gdm", "higher_is_error",
         [1, 2, 3]),
        ("gfm", "higher_is_error",
         [1]),
        ("consonant_match", "lower_is_error",
         np.arange(0.1, 0.9, 0.05)),
        ("eff", "lower_is_error",
         np.arange(-5.0, 0.0, 0.1)),
    ]

    # Split data
    correct = [d for d in all_data if d["label"] == "correct"]
    mutated_i3rab = [d for d in all_data if d["label"] == "mutated_i3rab"]
    mutated_tash = [d for d in all_data if d["label"] == "mutated_tashkeel"]
    mutated_word = [d for d in all_data if d["label"] == "mutated_word"]
    all_mutated = mutated_i3rab + mutated_tash + mutated_word

    results = {}

    for sig_name, direction, thresholds in signal_configs:
        # Get values (skip None)
        correct_vals = [d["signals"][sig_name] for d in correct
                        if d["signals"][sig_name] is not None]
        mutated_vals_i3rab = [d["signals"][sig_name] for d in mutated_i3rab
                              if d["signals"][sig_name] is not None]
        mutated_vals_tash = [d["signals"][sig_name] for d in mutated_tash
                             if d["signals"][sig_name] is not None]
        mutated_vals_word = [d["signals"][sig_name] for d in mutated_word
                             if d["signals"][sig_name] is not None]
        all_mut_vals = [d["signals"][sig_name] for d in all_mutated
                        if d["signals"][sig_name] is not None]

        if not correct_vals or not all_mut_vals:
            print(f"  {sig_name}: SKIP (no data)")
            continue

        best_score = -999
        best_thresh = None
        best_fp_rate = None
        best_det_rate = None
        best_det_i3rab = None
        best_det_tash = None
        best_det_word = None

        for t in thresholds:
            if direction == "higher_is_error":
                fp = sum(1 for v in correct_vals if v >= t)
                det = sum(1 for v in all_mut_vals if v >= t)
                det_i = sum(1 for v in mutated_vals_i3rab if v >= t)
                det_t = sum(1 for v in mutated_vals_tash if v >= t)
                det_w = sum(1 for v in mutated_vals_word if v >= t)
            else:
                fp = sum(1 for v in correct_vals if v < t)
                det = sum(1 for v in all_mut_vals if v < t)
                det_i = sum(1 for v in mutated_vals_i3rab if v < t)
                det_t = sum(1 for v in mutated_vals_tash if v < t)
                det_w = sum(1 for v in mutated_vals_word if v < t)

            fp_rate = fp / len(correct_vals)
            det_rate = det / len(all_mut_vals)
            score = det_rate - 5.0 * fp_rate

            if score > best_score:
                best_score = score
                best_thresh = t
                best_fp_rate = fp_rate
                best_det_rate = det_rate
                best_det_i3rab = det_i / len(mutated_vals_i3rab) if mutated_vals_i3rab else 0
                best_det_tash = det_t / len(mutated_vals_tash) if mutated_vals_tash else 0
                best_det_word = det_w / len(mutated_vals_word) if mutated_vals_word else 0

        if best_thresh is not None:
            op = ">" if direction == "higher_is_error" else "<"
            print(f"  {sig_name:20s}: threshold={best_thresh:>7.3f} ({op})")
            print(f"    {'Objective':>15s}: {best_score:.3f}")
            print(f"    {'FP rate':>15s}: {best_fp_rate*100:.1f}% "
                  f"({int(best_fp_rate*len(correct_vals))}/{len(correct_vals)})")
            print(f"    {'Overall det':>15s}: {best_det_rate*100:.1f}% "
                  f"({int(best_det_rate*len(all_mut_vals))}/{len(all_mut_vals)})")
            print(f"    {'i3rab det':>15s}: {best_det_i3rab*100:.1f}%")
            print(f"    {'tashkeel det':>15s}: {best_det_tash*100:.1f}%")
            print(f"    {'word det':>15s}: {best_det_word*100:.1f}%")
            print()

            results[sig_name] = {
                "threshold": float(best_thresh),
                "direction": direction,
                "objective": best_score,
                "fp_rate": best_fp_rate,
                "det_rate": best_det_rate,
                "det_i3rab": best_det_i3rab,
                "det_tash": best_det_tash,
                "det_word": best_det_word,
            }

    return results


def find_optimal_voting(all_data, single_results):
    """Try multi-signal voting with different required vote counts.

    For each combination of signals and required vote count,
    compute detection_rate - 5 * false_positive_rate.
    """
    print(f"\n{'='*100}")
    print(f"MULTI-SIGNAL VOTING OPTIMIZATION")
    print(f"{'='*100}")

    correct = [d for d in all_data if d["label"] == "correct"]
    mutated_i3rab = [d for d in all_data if d["label"] == "mutated_i3rab"]
    mutated_tash = [d for d in all_data if d["label"] == "mutated_tashkeel"]
    mutated_word = [d for d in all_data if d["label"] == "mutated_word"]
    all_mutated = mutated_i3rab + mutated_tash + mutated_word

    # Define signal checkers with multiple threshold levels
    signal_defs = []

    # Delta signals: higher means alternative is better -> error
    for sig, thresholds in [
        ("i3rab_delta", [0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25, 0.30]),
        ("tash_delta", [0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25, 0.30]),
        ("sukoon_delta", [0.10, 0.15, 0.20, 0.25, 0.30]),
        ("shadda_delta", [0.10, 0.15, 0.18, 0.20, 0.25]),
    ]:
        for t in thresholds:
            signal_defs.append({
                "name": f"{sig}>{t:.2f}",
                "signal": sig,
                "threshold": t,
                "direction": "higher_is_error",
            })

    # Negative delta signals: more negative means worse -> error
    for sig, thresholds in [
        ("pc_worst_delta", [-1.5, -2.0, -2.5, -3.0, -3.5, -4.0, -4.5, -5.0, -5.5, -6.0]),
        ("sf_worst_delta", [-1.5, -2.0, -2.5, -3.0, -3.5, -4.0, -4.5, -5.0, -5.5, -6.0]),
    ]:
        for t in thresholds:
            signal_defs.append({
                "name": f"{sig}<{t:.1f}",
                "signal": sig,
                "threshold": t,
                "direction": "lower_is_error",
            })

    # Binary/count signals
    signal_defs.append({
        "name": "gdm>=1",
        "signal": "gdm",
        "threshold": 1,
        "direction": "higher_is_error",
    })
    signal_defs.append({
        "name": "gfm>=1",
        "signal": "gfm",
        "threshold": 1,
        "direction": "higher_is_error",
    })

    if not signal_defs:
        print("  No signals available for voting")
        return

    # Pre-compute which data points fire for each signal checker
    def fires(d, sdef):
        v = d["signals"][sdef["signal"]]
        if v is None:
            return False
        if sdef["direction"] == "higher_is_error":
            return v >= sdef["threshold"]
        else:
            return v < sdef["threshold"]

    n_signals = len(signal_defs)
    correct_fires = np.zeros((len(correct), n_signals), dtype=bool)
    mutated_fires = np.zeros((len(all_mutated), n_signals), dtype=bool)

    for si, sdef in enumerate(signal_defs):
        for di, d in enumerate(correct):
            correct_fires[di, si] = fires(d, sdef)
        for di, d in enumerate(all_mutated):
            mutated_fires[di, si] = fires(d, sdef)

    mut_i3rab_mask = np.array([d["label"] == "mutated_i3rab" for d in all_mutated])
    mut_tash_mask = np.array([d["label"] == "mutated_tashkeel" for d in all_mutated])
    mut_word_mask = np.array([d["label"] == "mutated_word" for d in all_mutated])

    # Also pre-compute eff values for eff-gated analysis
    correct_eff = np.array([d["signals"]["eff"] for d in correct])
    mutated_eff = np.array([d["signals"]["eff"] for d in all_mutated])

    print(f"\n  Testing {n_signals} signal checkers across voting thresholds 2 and 3...")
    print(f"  Correct words: {len(correct)}, Mutated words: {len(all_mutated)}")
    print(f"    i3rab: {mut_i3rab_mask.sum()}, tashkeel: {mut_tash_mask.sum()}, word: {mut_word_mask.sum()}")

    # ── Part A: Brute-force per-signal-pair analysis ──
    print(f"\n  {'='*80}")
    print(f"  PART A: Best signal pairs (any 2 signals agreeing = flag)")
    print(f"  {'='*80}")

    pair_results = []
    for i in range(n_signals):
        for j in range(i+1, n_signals):
            # Both fire = flag
            c_both = correct_fires[:, i] & correct_fires[:, j]
            m_both = mutated_fires[:, i] & mutated_fires[:, j]

            fp = c_both.sum()
            det = m_both.sum()
            fp_rate = fp / len(correct)
            det_rate = det / len(all_mutated)
            score = det_rate - 5.0 * fp_rate

            if fp_rate <= 0.02 and det_rate >= 0.20:
                pair_results.append((score, i, j, fp_rate, det_rate))

    pair_results.sort(reverse=True)
    print(f"\n    Top 15 pairs with FP<=2% and detection>=20%:")
    for rank, (sc, i, j, fpr, dr) in enumerate(pair_results[:15]):
        det_i = (mutated_fires[:, i][mut_i3rab_mask] & mutated_fires[:, j][mut_i3rab_mask]).sum() / mut_i3rab_mask.sum()
        det_t = (mutated_fires[:, i][mut_tash_mask] & mutated_fires[:, j][mut_tash_mask]).sum() / mut_tash_mask.sum()
        det_w = (mutated_fires[:, i][mut_word_mask] & mutated_fires[:, j][mut_word_mask]).sum() / mut_word_mask.sum()
        print(f"    #{rank+1}: {signal_defs[i]['name']:25s} + {signal_defs[j]['name']:25s} "
              f"obj={sc:.3f} FP={fpr*100:.1f}% det={dr*100:.1f}% "
              f"i3={det_i*100:.0f}% ta={det_t*100:.0f}% wd={det_w*100:.0f}%")

    # ── Part B: Eff-gated analysis ──
    print(f"\n  {'='*80}")
    print(f"  PART B: Eff-gated signal performance (only words with eff > -2.0)")
    print(f"  {'='*80}")

    eff_gate = -2.0
    c_mask_eff = correct_eff > eff_gate
    m_mask_eff = mutated_eff > eff_gate
    n_c_eff = c_mask_eff.sum()
    n_m_eff = m_mask_eff.sum()
    print(f"    Correct in range: {n_c_eff}, Mutated in range: {n_m_eff}")

    # Best single signals with eff gate
    print(f"\n    Best single signals (eff > {eff_gate}):")
    for si, sdef in enumerate(signal_defs):
        fp = (correct_fires[:, si] & c_mask_eff).sum()
        det = (mutated_fires[:, si] & m_mask_eff).sum()
        fp_rate = fp / n_c_eff if n_c_eff > 0 else 0
        det_rate = det / n_m_eff if n_m_eff > 0 else 0
        score = det_rate - 5.0 * fp_rate
        if score > 0.1 and fp_rate <= 0.05:
            det_i = (mutated_fires[:, si][mut_i3rab_mask & m_mask_eff]).sum()
            det_t = (mutated_fires[:, si][mut_tash_mask & m_mask_eff]).sum()
            n_i_eff = (mut_i3rab_mask & m_mask_eff).sum()
            n_t_eff = (mut_tash_mask & m_mask_eff).sum()
            print(f"      {sdef['name']:30s} obj={score:.3f} FP={fp_rate*100:.1f}% det={det_rate*100:.1f}% "
                  f"i3={det_i}/{n_i_eff} ta={det_t}/{n_t_eff}")

    # Best pairs with eff gate
    print(f"\n    Best pairs (eff > {eff_gate}, FP<=2%):")
    gated_pairs = []
    for i in range(n_signals):
        for j in range(i+1, n_signals):
            c_both = correct_fires[:, i] & correct_fires[:, j] & c_mask_eff
            m_both = mutated_fires[:, i] & mutated_fires[:, j] & m_mask_eff

            fp_rate = c_both.sum() / n_c_eff if n_c_eff > 0 else 0
            det_rate = m_both.sum() / n_m_eff if n_m_eff > 0 else 0
            score = det_rate - 5.0 * fp_rate

            if fp_rate <= 0.02 and det_rate >= 0.15:
                gated_pairs.append((score, i, j, fp_rate, det_rate))

    gated_pairs.sort(reverse=True)
    for rank, (sc, i, j, fpr, dr) in enumerate(gated_pairs[:15]):
        det_i = ((mutated_fires[:, i] & mutated_fires[:, j])[mut_i3rab_mask & m_mask_eff]).sum()
        det_t = ((mutated_fires[:, i] & mutated_fires[:, j])[mut_tash_mask & m_mask_eff]).sum()
        n_i_eff = (mut_i3rab_mask & m_mask_eff).sum()
        n_t_eff = (mut_tash_mask & m_mask_eff).sum()
        print(f"      #{rank+1}: {signal_defs[i]['name']:25s} + {signal_defs[j]['name']:25s} "
              f"obj={sc:.3f} FP={fpr*100:.1f}% det={dr*100:.1f}% "
              f"i3={det_i}/{n_i_eff} ta={det_t}/{n_t_eff}")

    # ── Part C: Full combinatorial voting search ──
    print(f"\n  {'='*80}")
    print(f"  PART C: Full combinatorial voting search")
    print(f"  {'='*80}")

    # Build a curated signal set: pick one threshold level per signal type
    # to keep combos manageable
    curated_indices = {}
    for si, sdef in enumerate(signal_defs):
        sig = sdef["signal"]
        if sig not in curated_indices:
            curated_indices[sig] = []
        curated_indices[sig].append(si)

    # For each signal type, pick the threshold with best single-signal score
    best_per_type = {}
    for sig, indices in curated_indices.items():
        best_sc = -999
        best_idx = indices[0]
        for si in indices:
            fp = correct_fires[:, si].sum()
            det = mutated_fires[:, si].sum()
            fpr = fp / len(correct)
            dr = det / len(all_mutated)
            sc = dr - 5.0 * fpr
            if sc > best_sc:
                best_sc = sc
                best_idx = si
        best_per_type[sig] = best_idx

    # Also keep 2nd-best for diversity
    curated_set = set()
    for sig, indices in curated_indices.items():
        scored = []
        for si in indices:
            fp = correct_fires[:, si].sum()
            det = mutated_fires[:, si].sum()
            fpr = fp / len(correct)
            dr = det / len(all_mutated)
            sc = dr - 5.0 * fpr
            scored.append((sc, si))
        scored.sort(reverse=True)
        for _, si in scored[:2]:
            curated_set.add(si)

    curated_list = sorted(curated_set)
    print(f"\n    Curated signal set ({len(curated_list)} checkers):")
    for si in curated_list:
        print(f"      {signal_defs[si]['name']}")

    best_configs = []

    for vote_threshold in [2, 3]:
        print(f"\n    --- Vote threshold: {vote_threshold} ---")

        combo_best_score = -999
        combo_best = None

        for combo_size in range(vote_threshold, min(len(curated_list)+1, vote_threshold + 5)):
            all_combos = list(combinations(curated_list, combo_size))
            if len(all_combos) > 10000:
                all_combos = random.sample(all_combos, 10000)

            for combo in all_combos:
                combo = list(combo)
                correct_votes = correct_fires[:, combo].sum(axis=1)
                mutated_votes = mutated_fires[:, combo].sum(axis=1)

                fp = (correct_votes >= vote_threshold).sum()
                det = (mutated_votes >= vote_threshold).sum()

                fp_rate = fp / len(correct) if correct else 0
                det_rate = det / len(all_mutated) if all_mutated else 0
                score = det_rate - 5.0 * fp_rate

                if score > combo_best_score:
                    combo_best_score = score
                    combo_best = (combo, vote_threshold, fp_rate, det_rate, score)

        if combo_best:
            combo, vt, fp_r, det_r, sc = combo_best
            sig_names = [signal_defs[i]["name"] for i in combo]

            mutated_votes_best = mutated_fires[:, combo].sum(axis=1)
            det_i3rab = (mutated_votes_best[mut_i3rab_mask] >= vt).sum() / mut_i3rab_mask.sum() if mut_i3rab_mask.sum() > 0 else 0
            det_tash = (mutated_votes_best[mut_tash_mask] >= vt).sum() / mut_tash_mask.sum() if mut_tash_mask.sum() > 0 else 0
            det_word = (mutated_votes_best[mut_word_mask] >= vt).sum() / mut_word_mask.sum() if mut_word_mask.sum() > 0 else 0

            print(f"\n      Best config (vote>={vt}):")
            print(f"        Signals: {sig_names}")
            print(f"        Objective: {sc:.3f}")
            print(f"        FP rate:   {fp_r*100:.1f}% ({int(fp_r*len(correct))}/{len(correct)})")
            print(f"        Detection: {det_r*100:.1f}% ({int(det_r*len(all_mutated))}/{len(all_mutated)})")
            print(f"        i3rab:     {det_i3rab*100:.1f}%")
            print(f"        tashkeel:  {det_tash*100:.1f}%")
            print(f"        word:      {det_word*100:.1f}%")

            print(f"        Threshold details:")
            for i in combo:
                sd = signal_defs[i]
                op = ">=" if sd["direction"] == "higher_is_error" else "<"
                print(f"          {sd['name']:30s}: {sd['signal']} {op} {sd['threshold']:.3f}")

            best_configs.append(combo_best)

    # ── Part D: Eff-gated voting (require eff > -2.0 AND vote >= threshold) ──
    print(f"\n  {'='*80}")
    print(f"  PART D: Eff-gated voting (eff > -2.0 required)")
    print(f"  {'='*80}")

    for vote_threshold in [2, 3]:
        print(f"\n    --- Vote threshold: {vote_threshold}, eff > {eff_gate} ---")

        combo_best_score = -999
        combo_best = None

        for combo_size in range(vote_threshold, min(len(curated_list)+1, vote_threshold + 5)):
            all_combos = list(combinations(curated_list, combo_size))
            if len(all_combos) > 10000:
                all_combos = random.sample(all_combos, 10000)

            for combo in all_combos:
                combo = list(combo)
                correct_votes = correct_fires[:, combo].sum(axis=1)
                mutated_votes = mutated_fires[:, combo].sum(axis=1)

                # Apply eff gate
                fp = ((correct_votes >= vote_threshold) & c_mask_eff).sum()
                det = ((mutated_votes >= vote_threshold) & m_mask_eff).sum()

                fp_rate = fp / n_c_eff if n_c_eff > 0 else 0
                det_rate = det / n_m_eff if n_m_eff > 0 else 0
                score = det_rate - 5.0 * fp_rate

                if score > combo_best_score:
                    combo_best_score = score
                    combo_best = (combo, vote_threshold, fp_rate, det_rate, score)

        if combo_best:
            combo, vt, fp_r, det_r, sc = combo_best
            sig_names = [signal_defs[i]["name"] for i in combo]

            mutated_votes_best = mutated_fires[:, combo].sum(axis=1)
            flagged_m = (mutated_votes_best >= vt) & m_mask_eff
            det_i3rab = flagged_m[mut_i3rab_mask].sum() / (mut_i3rab_mask & m_mask_eff).sum() if (mut_i3rab_mask & m_mask_eff).sum() > 0 else 0
            det_tash = flagged_m[mut_tash_mask].sum() / (mut_tash_mask & m_mask_eff).sum() if (mut_tash_mask & m_mask_eff).sum() > 0 else 0
            det_word = flagged_m[mut_word_mask].sum() / (mut_word_mask & m_mask_eff).sum() if (mut_word_mask & m_mask_eff).sum() > 0 else 0

            print(f"\n      Best config (vote>={vt}, eff>{eff_gate}):")
            print(f"        Signals: {sig_names}")
            print(f"        Objective: {sc:.3f}")
            print(f"        FP rate:   {fp_r*100:.1f}% ({int(fp_r*n_c_eff)}/{n_c_eff})")
            print(f"        Detection: {det_r*100:.1f}% ({int(det_r*n_m_eff)}/{n_m_eff})")
            print(f"        i3rab:     {det_i3rab*100:.1f}%")
            print(f"        tashkeel:  {det_tash*100:.1f}%")
            print(f"        word:      {det_word*100:.1f}%")
            print(f"        (Among eff>{eff_gate} words only)")

            print(f"        Threshold details:")
            for i in combo:
                sd = signal_defs[i]
                op = ">=" if sd["direction"] == "higher_is_error" else "<"
                print(f"          {sd['name']:30s}: {sd['signal']} {op} {sd['threshold']:.3f}")

            best_configs.append(combo_best)

    # ── Summary ──
    if best_configs:
        print(f"\n{'='*100}")
        print(f"OVERALL BEST VOTING CONFIGURATION")
        print(f"{'='*100}")
        best = max(best_configs, key=lambda x: x[4])
        combo, vt, fp_r, det_r, sc = best
        sig_names = [signal_defs[i]["name"] for i in combo]

        mutated_votes_best = mutated_fires[:, combo].sum(axis=1)
        det_i3rab = (mutated_votes_best[mut_i3rab_mask] >= vt).sum() / mut_i3rab_mask.sum() if mut_i3rab_mask.sum() > 0 else 0
        det_tash = (mutated_votes_best[mut_tash_mask] >= vt).sum() / mut_tash_mask.sum() if mut_tash_mask.sum() > 0 else 0
        det_word = (mutated_votes_best[mut_word_mask] >= vt).sum() / mut_word_mask.sum() if mut_word_mask.sum() > 0 else 0

        print(f"\n  Vote threshold: {vt}")
        print(f"  Signals ({len(combo)}):")
        for i in combo:
            sd = signal_defs[i]
            op = ">=" if sd["direction"] == "higher_is_error" else "<"
            print(f"    {sd['name']:30s}: {sd['signal']} {op} {sd['threshold']:.3f}")
        print(f"\n  Objective:  {sc:.3f}")
        print(f"  FP rate:    {fp_r*100:.1f}%")
        print(f"  Detection:  {det_r*100:.1f}%")
        print(f"  i3rab:      {det_i3rab*100:.1f}%")
        print(f"  tashkeel:   {det_tash*100:.1f}%")
        print(f"  word:       {det_word*100:.1f}%")

    return best_configs


def print_eff_stratified_analysis(all_data):
    """Show how signals perform at different eff ranges."""
    print(f"\n{'='*100}")
    print(f"EFF-STRATIFIED ANALYSIS")
    print(f"{'='*100}")

    eff_ranges = [
        ("good (> -0.5)", lambda e: e > -0.5),
        ("moderate (-0.5 to -1.5)", lambda e: -1.5 <= e <= -0.5),
        ("poor (-1.5 to -3.0)", lambda e: -3.0 <= e < -1.5),
        ("very poor (< -3.0)", lambda e: e < -3.0),
    ]

    key_signals = ["i3rab_delta", "tash_delta", "pc_worst_delta", "sf_worst_delta", "gdm", "gfm"]

    for range_name, eff_filter in eff_ranges:
        correct_in_range = [d for d in all_data if d["label"] == "correct"
                            and eff_filter(d["signals"]["eff"])]
        mutated_in_range = [d for d in all_data if d["label"] != "correct"
                            and eff_filter(d["signals"]["eff"])]

        if not correct_in_range and not mutated_in_range:
            continue

        print(f"\n  EFF range: {range_name}")
        print(f"    Correct: {len(correct_in_range)}, Mutated: {len(mutated_in_range)}")

        for sig in key_signals:
            c_vals = [d["signals"][sig] for d in correct_in_range
                      if d["signals"][sig] is not None]
            m_vals = [d["signals"][sig] for d in mutated_in_range
                      if d["signals"][sig] is not None]

            if c_vals and m_vals:
                c_arr = np.array(c_vals)
                m_arr = np.array(m_vals)
                print(f"    {sig:20s}: correct mean={c_arr.mean():.3f} std={c_arr.std():.3f} | "
                      f"mutated mean={m_arr.mean():.3f} std={m_arr.std():.3f} | "
                      f"separation={abs(m_arr.mean()-c_arr.mean())/(c_arr.std()+1e-6):.2f}sigma")


def main():
    random.seed(42)

    sessions_dir = BASE / "test_data" / "sessions"
    sessions = find_best_sessions(sessions_dir)

    if not sessions:
        print("No sessions found")
        return

    engine = RecitationEngine(str(MODEL_PATH))

    # Phase 1: Collect all data
    print("COLLECTING SIGNAL DATA...")
    all_data = collect_data(engine, sessions)

    print(f"\n{'='*100}")
    print(f"DATA SUMMARY")
    print(f"{'='*100}")
    labels = defaultdict(int)
    for d in all_data:
        labels[d["label"]] += 1
    for label, count in sorted(labels.items()):
        print(f"  {label}: {count}")
    print(f"  Total: {len(all_data)}")

    # Phase 2: Distribution table
    print_distribution_table(all_data)

    # Phase 3: EFF-stratified analysis
    print_eff_stratified_analysis(all_data)

    # Phase 4: Optimal single thresholds
    single_results = find_optimal_single_thresholds(all_data)

    # Phase 5: Multi-signal voting
    find_optimal_voting(all_data, single_results)


if __name__ == "__main__":
    main()
