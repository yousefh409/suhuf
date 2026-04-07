#!/usr/bin/env python3
"""Analyze which rules catch mutations at eff < -1.5 and what signals remain for uncaught."""
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

    caught_rules = {}
    uncaught_signals = []
    correct_signals = []

    for pid in sorted(sessions):
        si = sessions[pid]
        phrases = si["meta"]["phrases"]
        audio = si["audio"]
        full_text = " ".join(phrases)

        print(f"Session: {pid}")

        waveform = torch.from_numpy(audio)
        word_results, _, _ = engine.score_phrase(waveform, full_text, compute_pd=False)
        segments = _extract_phrase_segments(word_results, phrases, audio)

        whisper_per_phrase = {}
        for pi in sorted(segments.keys()):
            whisper_per_phrase[pi] = engine.whisper_transcribe(segments[pi])

        covered = sorted(segments.keys())

        def extract_signals(d):
            return {
                "td": d.get("tash_delta") or 0,
                "pd_i": d.get("pd_i3rab") or 0,
                "pd_t": d.get("pd_tashkeel") or 0,
                "i3d": d.get("i3rab_delta") or 0,
                "pc": d.get("pc", 999),
                "sf": d.get("sf_gop", 999),
                "cm": d.get("consonant_match", 1),
                "fs": d.get("fs", 999),
                "lpd_i": d.get("local_pd_i", 0),
                "lpd_t": d.get("local_pd_t", 0),
                "fc": d.get("frame_count", 0),
            }

        # Correct text
        for pi in covered:
            phrase = phrases[pi]
            seg = segments[pi]
            classified = _score_phrase_with_whisper(engine, seg, phrase, whisper_per_phrase[pi])
            for cw in classified:
                d = cw["debug"]
                if d["eff"] > -1.5:
                    continue
                sigs = extract_signals(d)
                sigs["word"] = cw["word"]
                sigs["eff"] = d["eff"]
                correct_signals.append(sigs)

        # Mutated text
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
                for cw in classified:
                    if cw["idx"] == wi:
                        d = cw["debug"]
                        if d["eff"] > -1.5:
                            continue
                        if cw["status"] != "correct":
                            rule = cw.get("error_detail", "unknown")
                            caught_rules[rule] = caught_rules.get(rule, 0) + 1
                        else:
                            sigs = extract_signals(d)
                            sigs["word"] = cw["word"]
                            sigs["eff"] = d["eff"]
                            sigs["mtype"] = "i3rab"
                            uncaught_signals.append(sigs)

            for wi, word in enumerate(pw):
                if len(strip_diacritics(word)) < 3:
                    continue
                mutated, desc = mutate_tashkeel(word)
                if mutated is None:
                    continue
                mut_words = list(pw)
                mut_words[wi] = mutated
                classified = _score_phrase_with_whisper(engine, seg, " ".join(mut_words), whisper_words)
                for cw in classified:
                    if cw["idx"] == wi:
                        d = cw["debug"]
                        if d["eff"] > -1.5:
                            continue
                        if cw["status"] != "correct":
                            rule = cw.get("error_detail", "unknown")
                            caught_rules[rule] = caught_rules.get(rule, 0) + 1
                        else:
                            sigs = extract_signals(d)
                            sigs["word"] = cw["word"]
                            sigs["eff"] = d["eff"]
                            sigs["mtype"] = "tashkeel"
                            uncaught_signals.append(sigs)

            candidates = [i for i, w in enumerate(pw) if len(strip_diacritics(w)) >= 3]
            if candidates:
                for wi in random.sample(candidates, min(2, len(candidates))):
                    mut_words_list, desc = mutate_word(pw, wi)
                    classified = _score_phrase_with_whisper(engine, seg, " ".join(mut_words_list), whisper_words)
                    for cw in classified:
                        if cw["idx"] == wi:
                            d = cw["debug"]
                            if d["eff"] > -1.5:
                                continue
                            if cw["status"] != "correct":
                                rule = cw.get("error_detail", "unknown")
                                caught_rules[rule] = caught_rules.get(rule, 0) + 1

    print(f"\nCAUGHT RULES AT eff < -1.5:")
    for rule, count in sorted(caught_rules.items(), key=lambda x: -x[1]):
        print(f"  {rule}: {count}")
    print(f"  TOTAL: {sum(caught_rules.values())}")
    print(f"\nUNCAUGHT (i3rab+tashkeel): {len(uncaught_signals)}")
    print(f"CORRECT at eff < -1.5: {len(correct_signals)}")

    # Signal availability for uncaught
    print("\nUNCAUGHT SIGNAL STATS:")
    for sig in ["td", "pd_i", "pd_t", "i3d", "lpd_i", "lpd_t"]:
        vals = [r[sig] for r in uncaught_signals]
        pos = sum(1 for v in vals if v > 0.01)
        a05 = sum(1 for v in vals if v >= 0.05)
        a10 = sum(1 for v in vals if v >= 0.10)
        a20 = sum(1 for v in vals if v >= 0.20)
        print(f"  {sig:8s}: >0.01={pos:3d}  >=0.05={a05:3d}  >=0.10={a10:3d}  >=0.20={a20:3d}")

    # Same for correct (FP risk)
    print("\nCORRECT SIGNAL STATS (FP risk):")
    for sig in ["td", "pd_i", "pd_t", "i3d", "lpd_i", "lpd_t"]:
        vals = [r[sig] for r in correct_signals]
        pos = sum(1 for v in vals if v > 0.01)
        a05 = sum(1 for v in vals if v >= 0.05)
        a10 = sum(1 for v in vals if v >= 0.10)
        a20 = sum(1 for v in vals if v >= 0.20)
        print(f"  {sig:8s}: >0.01={pos:3d}  >=0.05={a05:3d}  >=0.10={a10:3d}  >=0.20={a20:3d}")

    # 2-of-3 combos
    print("\n2-of-3 COMBOS (uncaught catches / correct FPs):")
    combos = [
        ("td>=0.03 AND pd_i>=0.10", lambda r: r["td"]>=0.03 and r["pd_i"]>=0.10),
        ("td>=0.03 AND pd_t>=0.10", lambda r: r["td"]>=0.03 and r["pd_t"]>=0.10),
        ("pd_i>=0.10 AND pd_t>=0.10", lambda r: r["pd_i"]>=0.10 and r["pd_t"]>=0.10),
        ("td>=0.05 AND pd_i>=0.15", lambda r: r["td"]>=0.05 and r["pd_i"]>=0.15),
        ("td>=0.05 AND pd_t>=0.15", lambda r: r["td"]>=0.05 and r["pd_t"]>=0.15),
        ("td>=0.03 AND (pd_i>=0.10 OR pd_t>=0.10)", lambda r: r["td"]>=0.03 and (r["pd_i"]>=0.10 or r["pd_t"]>=0.10)),
        ("lpd_i>=0.30 AND pd_i>=0.10", lambda r: r["lpd_i"]>=0.30 and r["pd_i"]>=0.10),
        ("lpd_t>=0.30 AND pd_t>=0.10", lambda r: r["lpd_t"]>=0.30 and r["pd_t"]>=0.10),
        ("i3d>=0.05 AND pd_i>=0.10", lambda r: r["i3d"]>=0.05 and r["pd_i"]>=0.10),
        ("i3d>=0.05 AND pd_t>=0.10", lambda r: r["i3d"]>=0.05 and r["pd_t"]>=0.10),
        ("td>=0.03 AND lpd_t>=0.20", lambda r: r["td"]>=0.03 and r["lpd_t"]>=0.20),
        ("pd_i>=0.15 OR pd_t>=0.15", lambda r: r["pd_i"]>=0.15 or r["pd_t"]>=0.15),
        ("pd_i>=0.20 OR pd_t>=0.20", lambda r: r["pd_i"]>=0.20 or r["pd_t"]>=0.20),
        # Relaxed triple: any 2 of (td>=0.03, pd_i>=0.10, pd_t>=0.10)
        ("any 2 of: td>=0.03, pd_i>=0.10, pd_t>=0.10",
         lambda r: sum([r["td"]>=0.03, r["pd_i"]>=0.10, r["pd_t"]>=0.10]) >= 2),
        # With frame scan
        ("fs<-1.0 AND (pd_i>=0.10 OR pd_t>=0.10)",
         lambda r: (r["fs"] or 999) < -1.0 and (r["pd_i"]>=0.10 or r["pd_t"]>=0.10)),
    ]
    for name, cond in combos:
        catches = sum(1 for r in uncaught_signals if cond(r))
        fps = sum(1 for r in correct_signals if cond(r))
        if catches > 0 or fps > 0:
            print(f"  {name}: catches={catches}  FPs={fps}")


if __name__ == "__main__":
    main()
