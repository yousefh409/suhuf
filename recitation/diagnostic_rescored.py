#!/usr/bin/env python3
"""Diagnostic: analyze rescored signals (pc, sf, i3d, tash_d) at eff < -1.5.

The windowed rescore re-aligns words in a local 3-word window, potentially
giving better frame positions for diacritic signals. This script checks
if the rescored signals discriminate better than the original signals.
"""
import sys
import random
import numpy as np
import torch
from pathlib import Path

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

    correct_data = []  # list of dicts
    mutated_data = []  # list of dicts

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

        def collect_signals(classified, target_wi=None, is_correct=True, mtype=None, desc=None):
            for cw in classified:
                if target_wi is not None and cw["idx"] != target_wi:
                    continue
                d = cw["debug"]
                eff = d["eff"]
                if eff > -1.5:
                    continue

                rec = {
                    "word": cw["word"],
                    "eff": eff,
                    "status": cw["status"],
                    "detected": cw["status"] != "correct",
                    "mtype": mtype,
                    "desc": desc,
                    # Original signals
                    "i3d": d.get("i3rab_delta", 0.0) or 0.0,
                    "tash_d": d.get("tash_delta", 0.0) or 0.0,
                    "sf": d.get("sf", 999.0),
                    "pc": d.get("pc", 999.0),
                    "cm": d.get("cm", 1.0),
                    # Rescored signals
                    "rs_eff": d.get("rescored_eff"),
                    "rs_i3d": d.get("rescored_i3d"),
                    "rs_tash_d": d.get("rescored_tash_d"),
                    "rs_sf": d.get("rescored_sf"),
                    "rs_pc": d.get("rescored_pc"),
                    "rs_gfm": d.get("rescored_gfm"),
                    # Local PD
                    "lpd_i": d.get("local_pd_i", 0.0),
                    "lpd_t": d.get("local_pd_t", 0.0),
                    # PD
                    "pd_i": d.get("pd_i3rab", 0.0),
                    "pd_t": d.get("pd_tashkeel", 0.0),
                }
                if is_correct:
                    correct_data.append(rec)
                else:
                    mutated_data.append(rec)

        # --- CORRECT TEXT ---
        for pi in covered:
            phrase = phrases[pi]
            seg = segments[pi]
            whisper_words = whisper_per_phrase[pi]
            classified = _score_phrase_with_whisper(engine, seg, phrase, whisper_words)
            collect_signals(classified)

        # --- MUTATED TEXT ---
        for pi in covered:
            phrase = phrases[pi]
            pw = phrase.split()
            seg = segments[pi]
            whisper_words = whisper_per_phrase[pi]

            for wi, word in enumerate(pw):
                mutated, desc = mutate_i3rab(word)
                if mutated is None:
                    continue
                mut_words = list(pw)
                mut_words[wi] = mutated
                classified = _score_phrase_with_whisper(engine, seg, " ".join(mut_words), whisper_words)
                collect_signals(classified, wi, False, "i3rab", desc)

            for wi, word in enumerate(pw):
                if len(strip_diacritics(word)) < 3:
                    continue
                mutated, desc = mutate_tashkeel(word)
                if mutated is None:
                    continue
                mut_words = list(pw)
                mut_words[wi] = mutated
                classified = _score_phrase_with_whisper(engine, seg, " ".join(mut_words), whisper_words)
                collect_signals(classified, wi, False, "tashkeel", desc)

            candidates = [i for i, w in enumerate(pw) if len(strip_diacritics(w)) >= 3]
            if candidates:
                test_idxs = random.sample(candidates, min(2, len(candidates)))
                for wi in test_idxs:
                    mut_words_list, desc = mutate_word(pw, wi)
                    classified = _score_phrase_with_whisper(engine, seg, " ".join(mut_words_list), whisper_words)
                    collect_signals(classified, wi, False, "word", desc)

    # --- ANALYSIS ---
    print("\n" + "=" * 80)
    print("RESCORED SIGNAL ANALYSIS (eff < -1.5)")
    print("=" * 80)

    # How many have rescored signals?
    correct_rs = [r for r in correct_data if r["rs_eff"] is not None]
    mutated_rs = [r for r in mutated_data if r["rs_eff"] is not None]
    uncaught = [r for r in mutated_data if not r["detected"]]
    uncaught_rs = [r for r in uncaught if r["rs_eff"] is not None]

    print(f"\nTotal correct at eff<-1.5: {len(correct_data)}, with rescore: {len(correct_rs)}")
    print(f"Total mutated at eff<-1.5: {len(mutated_data)}, with rescore: {len(mutated_rs)}")
    print(f"Uncaught at eff<-1.5: {len(uncaught)}, with rescore: {len(uncaught_rs)}")

    # Rescored eff distribution
    if correct_rs:
        rs_effs = [r["rs_eff"] for r in correct_rs]
        print(f"\nCorrect rescored eff: mean={np.mean(rs_effs):.3f} min={min(rs_effs):.3f} max={max(rs_effs):.3f}")
    if uncaught_rs:
        rs_effs = [r["rs_eff"] for r in uncaught_rs]
        print(f"Uncaught rescored eff: mean={np.mean(rs_effs):.3f} min={min(rs_effs):.3f} max={max(rs_effs):.3f}")

    # Compare rescored vs original signals
    for sig_name, orig_key, rs_key in [
        ("i3rab_delta", "i3d", "rs_i3d"),
        ("tash_delta", "tash_d", "rs_tash_d"),
        ("sf", "sf", "rs_sf"),
        ("pc", "pc", "rs_pc"),
    ]:
        print(f"\n--- Signal: {sig_name} ---")
        for label, data in [("Correct", correct_rs), ("Uncaught", uncaught_rs)]:
            if not data:
                continue
            orig_vals = [r[orig_key] for r in data if r[orig_key] is not None and r[orig_key] != 999.0]
            rs_vals = [r[rs_key] for r in data if r[rs_key] is not None and r[rs_key] != 999.0]
            if orig_vals:
                print(f"  {label} original: mean={np.mean(orig_vals):.4f} max={max(orig_vals):.4f} min={min(orig_vals):.4f}")
            if rs_vals:
                print(f"  {label} rescored: mean={np.mean(rs_vals):.4f} max={max(rs_vals):.4f} min={min(rs_vals):.4f}")

    # Threshold scan on rescored signals
    print("\n\nTHRESHOLD SCAN ON RESCORED SIGNALS:")
    print("-" * 70)

    for sig_name, key, direction in [
        ("rescored_i3d", "rs_i3d", "high"),  # high = mutated
        ("rescored_tash_d", "rs_tash_d", "high"),
        ("rescored_sf", "rs_sf", "low"),  # low = mutated
        ("rescored_pc", "rs_pc", "low"),
    ]:
        print(f"\n  Signal: {sig_name}")
        for thresh in [0.03, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30, 0.50]:
            if direction == "high":
                fp = sum(1 for r in correct_rs if r[key] is not None and r[key] >= thresh)
                catches = sum(1 for r in uncaught_rs if r[key] is not None and r[key] >= thresh)
            else:
                fp = sum(1 for r in correct_rs if r[key] is not None and r[key] != 999.0 and r[key] < -thresh)
                catches = sum(1 for r in uncaught_rs if r[key] is not None and r[key] != 999.0 and r[key] < -thresh)
            print(f"    {'>='+str(thresh) if direction=='high' else '<-'+str(thresh):>8s}: "
                  f"FP={fp:3d}/{len(correct_rs)}  uncaught={catches:3d}/{len(uncaught_rs)}")

    # Rescored eff threshold — can we catch more by also flagging at higher rescored eff?
    print("\n\nRESCORED EFF GATING (rs_eff > threshold):")
    for rs_eff_thresh in [-1.0, -0.8, -0.5, -0.3, 0.0]:
        correct_above = [r for r in correct_rs if r["rs_eff"] is not None and r["rs_eff"] > rs_eff_thresh]
        uncaught_above = [r for r in uncaught_rs if r["rs_eff"] is not None and r["rs_eff"] > rs_eff_thresh]
        print(f"\n  rs_eff > {rs_eff_thresh}: correct={len(correct_above)}, uncaught={len(uncaught_above)}")

        # For those above threshold, check rescored signals
        for sig_name, key, direction in [
            ("rs_i3d", "rs_i3d", "high"),
            ("rs_tash_d", "rs_tash_d", "high"),
            ("rs_sf", "rs_sf", "low"),
            ("rs_pc", "rs_pc", "low"),
        ]:
            for thresh in [0.05, 0.10, 0.20]:
                if direction == "high":
                    fp = sum(1 for r in correct_above if r[key] is not None and r[key] >= thresh)
                    catches = sum(1 for r in uncaught_above if r[key] is not None and r[key] >= thresh)
                else:
                    fp = sum(1 for r in correct_above if r[key] is not None and r[key] != 999.0 and r[key] < -thresh)
                    catches = sum(1 for r in uncaught_above if r[key] is not None and r[key] != 999.0 and r[key] < -thresh)
                if catches > 0:
                    print(f"    {sig_name} {'>='+str(thresh) if direction=='high' else '<-'+str(thresh):>8s}: "
                          f"FP={fp:3d} catches={catches:3d}")

    # Print all rescored uncaught records
    print("\n\nALL RESCORED UNCAUGHT RECORDS:")
    for r in sorted(uncaught_rs, key=lambda x: x["rs_eff"] or -999, reverse=True):
        print(f"  {r['word']:20s} eff={r['eff']:.3f} rs_eff={r['rs_eff']:.3f} "
              f"rs_i3d={r['rs_i3d'] or 0:.4f} rs_tash={r['rs_tash_d'] or 0:.4f} "
              f"rs_sf={r['rs_sf'] or 999:.3f} rs_pc={r['rs_pc'] or 999:.2f}  "
              f"{r['mtype']:8s} {r['desc']}")

    # Print all rescored correct records
    print("\n\nALL RESCORED CORRECT RECORDS:")
    for r in sorted(correct_rs, key=lambda x: x["rs_eff"] or -999, reverse=True):
        print(f"  {r['word']:20s} eff={r['eff']:.3f} rs_eff={r['rs_eff']:.3f} "
              f"rs_i3d={r['rs_i3d'] or 0:.4f} rs_tash={r['rs_tash_d'] or 0:.4f} "
              f"rs_sf={r['rs_sf'] or 999:.3f} rs_pc={r['rs_pc'] or 999:.2f}")


if __name__ == "__main__":
    main()
