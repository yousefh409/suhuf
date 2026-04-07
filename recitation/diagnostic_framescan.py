#!/usr/bin/env python3
"""Diagnostic: test frame_scan_diacritics signal at eff < -1.5.

Frame scan is alignment-independent — it scans a wide region of frames
for diacritic evidence instead of relying on forced-aligned char spans.
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
        return

    engine = RecitationEngine(str(MODEL_PATH))

    correct_data = []
    mutated_data = []

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

        def collect(classified, target_wi=None, is_correct=True, mtype=None, desc=None):
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
                    "detected": cw["status"] != "correct",
                    "mtype": mtype,
                    "desc": desc,
                    "fs": d.get("fs", 999.0),
                    "pc": d.get("pc", 999.0),
                    "sf": d.get("sf_gop", 999.0),
                    "i3d": d.get("i3rab_delta", 0.0) or 0.0,
                    "cm": d.get("cm", 1.0),
                    "fs_expected": d.get("fs_expected"),
                    "fs_heard": d.get("fs_heard"),
                }
                if is_correct:
                    correct_data.append(rec)
                else:
                    mutated_data.append(rec)

        for pi in covered:
            phrase = phrases[pi]
            seg = segments[pi]
            classified = _score_phrase_with_whisper(engine, seg, phrase, whisper_per_phrase[pi])
            collect(classified)

        for pi in covered:
            phrase = phrases[pi]
            pw = phrase.split()
            seg = segments[pi]

            for wi, word in enumerate(pw):
                mutated, desc = mutate_i3rab(word)
                if mutated is None:
                    continue
                mut_words = list(pw)
                mut_words[wi] = mutated
                classified = _score_phrase_with_whisper(engine, seg, " ".join(mut_words), whisper_per_phrase[pi])
                collect(classified, wi, False, "i3rab", desc)

            for wi, word in enumerate(pw):
                if len(strip_diacritics(word)) < 3:
                    continue
                mutated, desc = mutate_tashkeel(word)
                if mutated is None:
                    continue
                mut_words = list(pw)
                mut_words[wi] = mutated
                classified = _score_phrase_with_whisper(engine, seg, " ".join(mut_words), whisper_per_phrase[pi])
                collect(classified, wi, False, "tashkeel", desc)

            candidates = [i for i, w in enumerate(pw) if len(strip_diacritics(w)) >= 3]
            if candidates:
                for wi in random.sample(candidates, min(2, len(candidates))):
                    mut_words_list, desc = mutate_word(pw, wi)
                    classified = _score_phrase_with_whisper(engine, seg, " ".join(mut_words_list), whisper_per_phrase[pi])
                    collect(classified, wi, False, "word", desc)

    print("\n" + "=" * 80)
    print("FRAME SCAN DIAGNOSTIC (eff < -1.5)")
    print("=" * 80)

    uncaught = [r for r in mutated_data if not r["detected"]]
    caught = [r for r in mutated_data if r["detected"]]

    print(f"\nCorrect: {len(correct_data)}, Mutated: {len(mutated_data)} "
          f"(caught={len(caught)}, uncaught={len(uncaught)})")

    # Distribution
    for label, data in [("CORRECT", correct_data), ("UNCAUGHT", uncaught), ("CAUGHT", caught)]:
        if not data:
            continue
        fs_vals = [r["fs"] for r in data if r["fs"] != 999.0]
        pc_vals = [r["pc"] for r in data if r["pc"] != 999.0]
        if fs_vals:
            print(f"\n  {label} frame_scan ({len(fs_vals)}/{len(data)} with values):")
            print(f"    mean={np.mean(fs_vals):.3f} min={min(fs_vals):.3f} max={max(fs_vals):.3f}")
        if pc_vals:
            print(f"  {label} pc ({len(pc_vals)}/{len(data)} with values):")
            print(f"    mean={np.mean(pc_vals):.3f} min={min(pc_vals):.3f} max={max(pc_vals):.3f}")

    # Threshold scan: frame_scan vs pc
    print("\n\nTHRESHOLD COMPARISON: frame_scan vs pc")
    print("-" * 70)
    for sig_name, key in [("frame_scan", "fs"), ("pc", "pc")]:
        print(f"\n  {sig_name}:")
        for thresh in [-1.0, -2.0, -3.0, -4.0, -5.0, -6.0, -8.0, -10.0]:
            fp = sum(1 for r in correct_data if r[key] != 999.0 and r[key] < thresh)
            catches = sum(1 for r in uncaught if r[key] != 999.0 and r[key] < thresh)
            total = sum(1 for r in mutated_data if r[key] != 999.0 and r[key] < thresh)
            if fp + catches > 0:
                print(f"    < {thresh:6.1f}: FP={fp:3d}/{len(correct_data)}  "
                      f"uncaught={catches:3d}/{len(uncaught)}  total_mut={total:3d}")

    # Combo: frame_scan + other signals
    print("\n\nCOMBO: frame_scan + existing signals")
    print("-" * 70)

    # fs + i3d
    print("\n  frame_scan + i3rab_delta:")
    for fs_th in [-2.0, -3.0, -4.0, -5.0]:
        for i3d_th in [0.03, 0.05, 0.10]:
            fp = sum(1 for r in correct_data if r["fs"] < fs_th and r["i3d"] >= i3d_th)
            catches = sum(1 for r in uncaught if r["fs"] < fs_th and r["i3d"] >= i3d_th)
            if catches >= 3 and fp <= 2:
                print(f"    fs<{fs_th} + i3d>={i3d_th}: FP={fp}  catches={catches}")

    # fs + cm
    print("\n  frame_scan + cm:")
    for fs_th in [-2.0, -3.0, -4.0, -5.0]:
        for cm_th in [0.3, 0.4, 0.5]:
            fp = sum(1 for r in correct_data if r["fs"] < fs_th and r["cm"] <= cm_th)
            catches = sum(1 for r in uncaught if r["fs"] < fs_th and r["cm"] <= cm_th)
            if catches >= 3 and fp <= 2:
                print(f"    fs<{fs_th} + cm<={cm_th}: FP={fp}  catches={catches}")

    # fs + sf
    print("\n  frame_scan + sf:")
    for fs_th in [-2.0, -3.0, -4.0]:
        for sf_th in [-2.0, -3.0, -4.0]:
            fp = sum(1 for r in correct_data if r["fs"] < fs_th and r["sf"] < sf_th)
            catches = sum(1 for r in uncaught if r["fs"] < fs_th and r["sf"] < sf_th)
            if catches >= 3 and fp <= 2:
                print(f"    fs<{fs_th} + sf<{sf_th}: FP={fp}  catches={catches}")

    # Print details of uncaught sorted by frame_scan
    print("\n\nUNCAUGHT sorted by frame_scan (lowest first):")
    uncaught_fs = [r for r in uncaught if r["fs"] != 999.0]
    uncaught_fs.sort(key=lambda r: r["fs"])
    for r in uncaught_fs[:30]:
        print(f"  {r['word']:20s} eff={r['eff']:.3f} fs={r['fs']:.3f} pc={r['pc']:.2f} "
              f"sf={r['sf']:.3f} i3d={r['i3d']:.4f} cm={r['cm']:.2f}  "
              f"{r['mtype']:8s} {r['desc']}")

    # Correct with most negative frame_scan (FP risk)
    print("\n\nCORRECT with most negative frame_scan:")
    correct_fs = [r for r in correct_data if r["fs"] != 999.0]
    correct_fs.sort(key=lambda r: r["fs"])
    for r in correct_fs[:20]:
        print(f"  {r['word']:20s} eff={r['eff']:.3f} fs={r['fs']:.3f} pc={r['pc']:.2f} "
              f"sf={r['sf']:.3f} i3d={r['i3d']:.4f} cm={r['cm']:.2f}")


if __name__ == "__main__":
    main()
