#!/usr/bin/env python3
"""Diagnostic: analyze local_pd signals from test_mutations run.

Runs the same test flow but prints local_pd values for all records at eff <= -1.5.
"""
import sys
import random
import numpy as np
import torch
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

from engine import RecitationEngine, StreamingSession
from server import classify_words
from arabic import strip_diacritics
from test_mutations import (
    find_best_sessions, _extract_phrase_segments,
    mutate_i3rab, mutate_tashkeel, mutate_word,
    _score_phrase_with_whisper,
    SAMPLE_RATE,
)

MODEL_PATH = BASE / "models" / "ssl_xls_r_v5"


def main():
    random.seed(42)

    sessions_dir = BASE / "test_data" / "sessions"
    sessions = find_best_sessions(sessions_dir)
    if not sessions:
        print("No sessions found")
        return

    engine = RecitationEngine(str(MODEL_PATH))

    # Collect local_pd stats for correct and mutated at eff <= -1.5
    correct_lpd = []  # (word, eff, lpd_i, lpd_t)
    mutated_lpd = []  # (word, eff, lpd_i, lpd_t, mutation_type, desc, detected)

    for pid in sorted(sessions):
        si = sessions[pid]
        phrases = si["meta"]["phrases"]
        audio = si["audio"]
        full_text = " ".join(phrases)

        print(f"\nSession: {pid} ({si['duration']:.1f}s)")

        waveform = torch.from_numpy(audio)
        word_results, greedy, full_score = engine.score_phrase(waveform, full_text, compute_pd=False)
        segments = _extract_phrase_segments(word_results, phrases, audio)

        whisper_per_phrase = {}
        for pi in sorted(segments.keys()):
            whisper_per_phrase[pi] = engine.whisper_transcribe(segments[pi])

        covered = sorted(segments.keys())

        # --- CORRECT TEXT ---
        for pi in covered:
            phrase = phrases[pi]
            pw = phrase.split()
            seg = segments[pi]
            whisper_words = whisper_per_phrase[pi]
            classified = _score_phrase_with_whisper(engine, seg, phrase, whisper_words)

            for cw in classified:
                d = cw["debug"]
                eff = d["eff"]
                if eff <= -1.5:
                    lpd_i = d.get("local_pd_i", 0.0)
                    lpd_t = d.get("local_pd_t", 0.0)
                    correct_lpd.append((cw["word"], eff, lpd_i, lpd_t))

        # --- MUTATED TEXT ---
        for pi in covered:
            phrase = phrases[pi]
            pw = phrase.split()
            seg = segments[pi]
            whisper_words = whisper_per_phrase[pi]

            # i3rab mutations
            for wi, word in enumerate(pw):
                mutated, desc = mutate_i3rab(word)
                if mutated is None:
                    continue
                mut_words = list(pw)
                mut_words[wi] = mutated
                mut_text = " ".join(mut_words)
                classified = _score_phrase_with_whisper(engine, seg, mut_text, whisper_words)

                for cw in classified:
                    if cw["idx"] == wi:
                        d = cw["debug"]
                        eff = d["eff"]
                        if eff <= -1.5:
                            lpd_i = d.get("local_pd_i", 0.0)
                            lpd_t = d.get("local_pd_t", 0.0)
                            detected = cw["status"] != "correct"
                            mutated_lpd.append((cw["word"], eff, lpd_i, lpd_t, "i3rab", desc, detected))

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
                classified = _score_phrase_with_whisper(engine, seg, mut_text, whisper_words)

                for cw in classified:
                    if cw["idx"] == wi:
                        d = cw["debug"]
                        eff = d["eff"]
                        if eff <= -1.5:
                            lpd_i = d.get("local_pd_i", 0.0)
                            lpd_t = d.get("local_pd_t", 0.0)
                            detected = cw["status"] != "correct"
                            mutated_lpd.append((cw["word"], eff, lpd_i, lpd_t, "tashkeel", desc, detected))

            # word mutations
            candidates = [i for i, w in enumerate(pw) if len(strip_diacritics(w)) >= 3]
            if candidates:
                test_idxs = random.sample(candidates, min(2, len(candidates)))
                for wi in test_idxs:
                    mut_words_list, desc = mutate_word(pw, wi)
                    mut_text = " ".join(mut_words_list)
                    classified = _score_phrase_with_whisper(engine, seg, mut_text, whisper_words)

                    for cw in classified:
                        if cw["idx"] == wi:
                            d = cw["debug"]
                            eff = d["eff"]
                            if eff <= -1.5:
                                lpd_i = d.get("local_pd_i", 0.0)
                                lpd_t = d.get("local_pd_t", 0.0)
                                detected = cw["status"] != "correct"
                                mutated_lpd.append((cw["word"], eff, lpd_i, lpd_t, "word", desc, detected))

        print(f"  correct at low eff: {len(correct_lpd)}, mutated at low eff: {len(mutated_lpd)}")

    # --- ANALYSIS ---
    print("\n" + "=" * 80)
    print("LOCAL PD ANALYSIS (eff <= -1.5)")
    print("=" * 80)

    print(f"\nCorrect words: {len(correct_lpd)}")
    print(f"Mutated words: {len(mutated_lpd)}")

    # Distribution of local_pd values
    for label, data in [("CORRECT", correct_lpd), ("MUTATED (all)", mutated_lpd)]:
        if not data:
            continue
        if label == "CORRECT":
            lpd_i_vals = [x[2] for x in data]
            lpd_t_vals = [x[3] for x in data]
        else:
            lpd_i_vals = [x[2] for x in data]
            lpd_t_vals = [x[3] for x in data]

        print(f"\n  {label}:")
        print(f"    local_pd_i: mean={np.mean(lpd_i_vals):.4f} max={max(lpd_i_vals):.4f} "
              f">0.05: {sum(1 for v in lpd_i_vals if v > 0.05)} "
              f">0.10: {sum(1 for v in lpd_i_vals if v > 0.10)} "
              f">0.20: {sum(1 for v in lpd_i_vals if v > 0.20)} "
              f">0.50: {sum(1 for v in lpd_i_vals if v > 0.50)}")
        print(f"    local_pd_t: mean={np.mean(lpd_t_vals):.4f} max={max(lpd_t_vals):.4f} "
              f">0.05: {sum(1 for v in lpd_t_vals if v > 0.05)} "
              f">0.10: {sum(1 for v in lpd_t_vals if v > 0.10)} "
              f">0.20: {sum(1 for v in lpd_t_vals if v > 0.20)} "
              f">0.50: {sum(1 for v in lpd_t_vals if v > 0.50)}")

    # Split mutated by detected/undetected
    uncaught = [x for x in mutated_lpd if not x[6]]
    caught = [x for x in mutated_lpd if x[6]]

    for label, data in [("MUTATED uncaught", uncaught), ("MUTATED caught", caught)]:
        if not data:
            continue
        lpd_i_vals = [x[2] for x in data]
        lpd_t_vals = [x[3] for x in data]
        print(f"\n  {label} ({len(data)}):")
        print(f"    local_pd_i: mean={np.mean(lpd_i_vals):.4f} max={max(lpd_i_vals):.4f} "
              f">0.05: {sum(1 for v in lpd_i_vals if v > 0.05)} "
              f">0.10: {sum(1 for v in lpd_i_vals if v > 0.10)} "
              f">0.20: {sum(1 for v in lpd_i_vals if v > 0.20)}")
        print(f"    local_pd_t: mean={np.mean(lpd_t_vals):.4f} max={max(lpd_t_vals):.4f} "
              f">0.05: {sum(1 for v in lpd_t_vals if v > 0.05)} "
              f">0.10: {sum(1 for v in lpd_t_vals if v > 0.10)} "
              f">0.20: {sum(1 for v in lpd_t_vals if v > 0.20)}")

    # Split uncaught by mutation type
    for mtype in ["i3rab", "tashkeel", "word"]:
        sub = [x for x in uncaught if x[4] == mtype]
        if not sub:
            continue
        print(f"\n  Uncaught {mtype} ({len(sub)}) — top local_pd values:")
        # Sort by max of lpd_i, lpd_t
        sub.sort(key=lambda x: max(x[2], x[3]), reverse=True)
        for x in sub[:15]:
            print(f"    {x[0]:20s} eff={x[1]:.3f} lpd_i={x[2]:.4f} lpd_t={x[3]:.4f}  {x[5]}")

    # Threshold analysis: for each threshold, count FP and catches
    print("\n\nTHRESHOLD ANALYSIS:")
    print("-" * 60)
    for sig_name, sig_idx in [("local_pd_i", 2), ("local_pd_t", 3)]:
        print(f"\n  Signal: {sig_name}")
        for thresh in [0.03, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30, 0.50]:
            fp = sum(1 for x in correct_lpd if x[sig_idx] >= thresh)
            catches_uncaught = sum(1 for x in uncaught if x[sig_idx] >= thresh)
            catches_total = sum(1 for x in mutated_lpd if x[sig_idx] >= thresh)
            print(f"    >= {thresh:.2f}: FP={fp:3d}/{len(correct_lpd)}  "
                  f"uncaught={catches_uncaught:3d}/{len(uncaught)}  "
                  f"total_mut={catches_total:3d}/{len(mutated_lpd)}")

    # Combined thresholds
    print("\n  Combined: local_pd_i >= T1 OR local_pd_t >= T2")
    for t1, t2 in [(0.10, 0.10), (0.15, 0.15), (0.20, 0.20), (0.10, 0.20), (0.20, 0.10)]:
        fp = sum(1 for x in correct_lpd if x[2] >= t1 or x[3] >= t2)
        catches = sum(1 for x in uncaught if x[2] >= t1 or x[3] >= t2)
        print(f"    lpd_i>={t1} OR lpd_t>={t2}: FP={fp:3d}  uncaught_catches={catches:3d}")

    print("\n  Combined: local_pd_i >= T AND local_pd_t >= T")
    for t in [0.03, 0.05, 0.08, 0.10]:
        fp = sum(1 for x in correct_lpd if x[2] >= t and x[3] >= t)
        catches = sum(1 for x in uncaught if x[2] >= t and x[3] >= t)
        print(f"    both >= {t}: FP={fp:3d}  uncaught_catches={catches:3d}")


if __name__ == "__main__":
    main()
