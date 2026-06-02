#!/usr/bin/env python3
"""Diagnostic: analyze local_pd signals when extended to eff < -1.0.

Checks what local_pd values look like for correct and mutated words
in the -1.5 < eff <= -1.0 range where local_pd was previously not computed.
"""
import sys
import random
import numpy as np
import torch
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

from engine import RecitationEngine
from arabic import strip_diacritics
from test_mutations import (
    find_best_sessions, _extract_phrase_segments,
    mutate_i3rab, mutate_tashkeel, mutate_word,
    _score_phrase_with_whisper,
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

    # Collect local_pd stats for the extended range -1.5 < eff <= -1.0
    correct_lpd = []  # (word, eff, lpd_i, lpd_t, pd_i, pd_t, i3d, sf, pc)
    mutated_lpd = []  # same + (mutation_type, desc, detected)

    for pid in sorted(sessions):
        si = sessions[pid]
        phrases = si["meta"]["phrases"]
        audio = si["audio"]
        full_text = " ".join(phrases)

        print(f"\nSession: {pid}")

        waveform = torch.from_numpy(audio)
        word_results, _, _ = engine.score_phrase(waveform, full_text, compute_pd=False)
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
                if -1.5 < eff <= -1.0:
                    lpd_i = d.get("local_pd_i", 0.0)
                    lpd_t = d.get("local_pd_t", 0.0)
                    pd_i = d.get("pd_i3rab", 0.0)
                    pd_t = d.get("pd_tashkeel", 0.0)
                    i3d = d.get("i3rab_delta", 0.0)
                    sf = d.get("sf", 999.0)
                    pc = d.get("pc", 999.0)
                    correct_lpd.append((cw["word"], eff, lpd_i, lpd_t, pd_i, pd_t, i3d, sf, pc))

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
                        if -1.5 < eff <= -1.0:
                            lpd_i = d.get("local_pd_i", 0.0)
                            lpd_t = d.get("local_pd_t", 0.0)
                            pd_i = d.get("pd_i3rab", 0.0)
                            pd_t = d.get("pd_tashkeel", 0.0)
                            i3d = d.get("i3rab_delta", 0.0)
                            sf_v = d.get("sf", 999.0)
                            pc_v = d.get("pc", 999.0)
                            detected = cw["status"] != "correct"
                            mutated_lpd.append((cw["word"], eff, lpd_i, lpd_t, pd_i, pd_t, i3d, sf_v, pc_v, "i3rab", desc, detected))

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
                        if -1.5 < eff <= -1.0:
                            lpd_i = d.get("local_pd_i", 0.0)
                            lpd_t = d.get("local_pd_t", 0.0)
                            pd_i = d.get("pd_i3rab", 0.0)
                            pd_t = d.get("pd_tashkeel", 0.0)
                            i3d = d.get("i3rab_delta", 0.0)
                            sf_v = d.get("sf", 999.0)
                            pc_v = d.get("pc", 999.0)
                            detected = cw["status"] != "correct"
                            mutated_lpd.append((cw["word"], eff, lpd_i, lpd_t, pd_i, pd_t, i3d, sf_v, pc_v, "tashkeel", desc, detected))

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
                            if -1.5 < eff <= -1.0:
                                lpd_i = d.get("local_pd_i", 0.0)
                                lpd_t = d.get("local_pd_t", 0.0)
                                pd_i = d.get("pd_i3rab", 0.0)
                                pd_t = d.get("pd_tashkeel", 0.0)
                                i3d = d.get("i3rab_delta", 0.0)
                                sf_v = d.get("sf", 999.0)
                                pc_v = d.get("pc", 999.0)
                                detected = cw["status"] != "correct"
                                mutated_lpd.append((cw["word"], eff, lpd_i, lpd_t, pd_i, pd_t, i3d, sf_v, pc_v, "word", desc, detected))

    # --- ANALYSIS ---
    print("\n" + "=" * 80)
    print("LOCAL PD EXTENDED RANGE ANALYSIS (-1.5 < eff <= -1.0)")
    print("=" * 80)

    print(f"\nCorrect words: {len(correct_lpd)}")
    print(f"Mutated words: {len(mutated_lpd)}")

    uncaught = [x for x in mutated_lpd if not x[11]]
    caught = [x for x in mutated_lpd if x[11]]

    print(f"  Already caught: {len(caught)}")
    print(f"  Uncaught: {len(uncaught)}")

    # Distribution of local_pd values for correct vs uncaught
    for label, data in [("CORRECT", correct_lpd), ("UNCAUGHT", uncaught)]:
        if not data:
            continue
        lpd_i_vals = [x[2] for x in data]
        lpd_t_vals = [x[3] for x in data]
        print(f"\n  {label} ({len(data)}):")
        print(f"    local_pd_i: mean={np.mean(lpd_i_vals):.4f} max={max(lpd_i_vals):.4f}")
        print(f"    local_pd_t: mean={np.mean(lpd_t_vals):.4f} max={max(lpd_t_vals):.4f}")

    # Threshold scan for local_pd standalone
    print("\n\nTHRESHOLD SCAN (local_pd standalone):")
    print("-" * 70)
    for sig_name, sig_idx in [("local_pd_i", 2), ("local_pd_t", 3)]:
        print(f"\n  Signal: {sig_name}")
        for thresh in [0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80]:
            fp = sum(1 for x in correct_lpd if x[sig_idx] >= thresh)
            catches_uncaught = sum(1 for x in uncaught if x[sig_idx] >= thresh)
            catches_total = sum(1 for x in mutated_lpd if x[sig_idx] >= thresh)
            print(f"    >= {thresh:.2f}: FP={fp:3d}/{len(correct_lpd)}  "
                  f"uncaught={catches_uncaught:3d}/{len(uncaught)}  "
                  f"total_mut={catches_total:3d}/{len(mutated_lpd)}")

    # Combo with existing signals
    print("\n\nCOMBO ANALYSIS (local_pd + existing signals):")
    print("-" * 70)

    # local_pd_i + i3rab_delta
    print("\n  local_pd_i + i3rab_delta (i3d):")
    for lpd_th in [0.10, 0.15, 0.20, 0.30]:
        for i3d_th in [0.03, 0.05, 0.08, 0.10]:
            fp = sum(1 for x in correct_lpd if x[2] >= lpd_th and x[6] >= i3d_th)
            catches = sum(1 for x in uncaught if x[2] >= lpd_th and x[6] >= i3d_th)
            if catches >= 3 and fp <= 2:
                print(f"    lpd_i>={lpd_th:.2f} + i3d>={i3d_th:.2f}: FP={fp}  catches={catches}")

    # local_pd_t + pd_tashkeel
    print("\n  local_pd_t + pd_tashkeel:")
    for lpd_th in [0.10, 0.15, 0.20, 0.30]:
        for pd_th in [0.05, 0.10, 0.15, 0.20]:
            fp = sum(1 for x in correct_lpd if x[3] >= lpd_th and x[5] >= pd_th)
            catches = sum(1 for x in uncaught if x[3] >= lpd_th and x[5] >= pd_th)
            if catches >= 3 and fp <= 2:
                print(f"    lpd_t>={lpd_th:.2f} + pd_t>={pd_th:.2f}: FP={fp}  catches={catches}")

    # local_pd_i + sf
    print("\n  local_pd_i + sf:")
    for lpd_th in [0.10, 0.15, 0.20, 0.30]:
        for sf_th in [-2.0, -3.0, -4.0]:
            fp = sum(1 for x in correct_lpd if x[2] >= lpd_th and x[7] < sf_th)
            catches = sum(1 for x in uncaught if x[2] >= lpd_th and x[7] < sf_th)
            if catches >= 3 and fp <= 2:
                print(f"    lpd_i>={lpd_th:.2f} + sf<{sf_th}: FP={fp}  catches={catches}")

    # local_pd_t + sf
    print("\n  local_pd_t + sf:")
    for lpd_th in [0.10, 0.15, 0.20, 0.30]:
        for sf_th in [-2.0, -3.0, -4.0]:
            fp = sum(1 for x in correct_lpd if x[3] >= lpd_th and x[7] < sf_th)
            catches = sum(1 for x in uncaught if x[3] >= lpd_th and x[7] < sf_th)
            if catches >= 3 and fp <= 2:
                print(f"    lpd_t>={lpd_th:.2f} + sf<{sf_th}: FP={fp}  catches={catches}")

    # local_pd_i + pc
    print("\n  local_pd_i + pc:")
    for lpd_th in [0.10, 0.15, 0.20, 0.30]:
        for pc_th in [-3.0, -4.0, -5.0]:
            fp = sum(1 for x in correct_lpd if x[2] >= lpd_th and x[8] < pc_th)
            catches = sum(1 for x in uncaught if x[2] >= lpd_th and x[8] < pc_th)
            if catches >= 3 and fp <= 2:
                print(f"    lpd_i>={lpd_th:.2f} + pc<{pc_th}: FP={fp}  catches={catches}")

    # local_pd_t + pc
    print("\n  local_pd_t + pc:")
    for lpd_th in [0.10, 0.15, 0.20, 0.30]:
        for pc_th in [-3.0, -4.0, -5.0]:
            fp = sum(1 for x in correct_lpd if x[3] >= lpd_th and x[8] < pc_th)
            catches = sum(1 for x in uncaught if x[3] >= lpd_th and x[8] < pc_th)
            if catches >= 3 and fp <= 2:
                print(f"    lpd_t>={lpd_th:.2f} + pc<{pc_th}: FP={fp}  catches={catches}")

    # High standalone local_pd
    print("\n  High standalone local_pd (0 FP target):")
    for sig_name, sig_idx in [("local_pd_i", 2), ("local_pd_t", 3)]:
        for thresh in [0.30, 0.40, 0.50, 0.60, 0.70, 0.80]:
            fp = sum(1 for x in correct_lpd if x[sig_idx] >= thresh)
            catches = sum(1 for x in uncaught if x[sig_idx] >= thresh)
            if fp == 0 and catches > 0:
                print(f"    {sig_name}>={thresh:.2f}: FP=0  catches={catches}")

    # Print uncaught details sorted by max local_pd
    print("\n\nUNCAUGHT DETAILS (sorted by max lpd):")
    uncaught.sort(key=lambda x: max(x[2], x[3]), reverse=True)
    for x in uncaught[:30]:
        print(f"  {x[0]:20s} eff={x[1]:.3f} lpd_i={x[2]:.4f} lpd_t={x[3]:.4f} "
              f"pd_i={x[4]:.3f} pd_t={x[5]:.3f} i3d={x[6]:.4f} sf={x[7]:.3f} pc={x[8]:.2f}  "
              f"{x[9]:8s} {x[10]}")

    # Print correct words with highest local_pd (potential FPs)
    print("\n\nCORRECT with highest local_pd (potential FP risk):")
    correct_lpd.sort(key=lambda x: max(x[2], x[3]), reverse=True)
    for x in correct_lpd[:20]:
        print(f"  {x[0]:20s} eff={x[1]:.3f} lpd_i={x[2]:.4f} lpd_t={x[3]:.4f} "
              f"pd_i={x[4]:.3f} pd_t={x[5]:.3f} i3d={x[6]:.4f} sf={x[7]:.3f} pc={x[8]:.2f}")


if __name__ == "__main__":
    main()
