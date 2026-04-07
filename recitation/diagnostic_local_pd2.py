#!/usr/bin/env python3
"""Deeper combo analysis: local_pd combined with existing signals at eff <= -1.5."""
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
    SAMPLE_RATE,
)

MODEL_PATH = BASE / "models" / "ssl_xls_r_v5"


def score_and_extract(engine, seg, text, whisper_words):
    """Score phrase and return raw word_results with local_pd signals."""
    pw = text.split()
    waveform = torch.from_numpy(seg)
    word_results, _, _ = engine.score_phrase(waveform, text)

    # Add whisper
    duration = len(seg) / SAMPLE_RATE
    wmatch = StreamingSession._whisper_word_matches(whisper_words, pw)
    match_ratio = sum(wmatch) / len(wmatch) if wmatch else 1.0
    trust_whisper = duration >= 3.0 and match_ratio >= 0.6
    for wr in word_results:
        wi = wr["word_idx"]
        if trust_whisper:
            wr["whisper_match"] = wmatch[wi] if wi < len(wmatch) else True
        else:
            wr["whisper_match"] = True

    return word_results


def extract_full_signals(wr, word_text):
    """Extract ALL signals from a word result."""
    eff = wr["effective_score"]
    alt = wr["best_alt_score"]
    tash = wr.get("best_tashkeel_score", -999.0)
    sukoon = wr.get("best_sukoon_score", -999.0)

    return {
        "eff": eff,
        "i3d": (alt - eff) if alt > -900 else 0.0,
        "td": (tash - eff) if tash > -900 else 0.0,
        "sukd": (sukoon - eff) if sukoon > -900 else 0.0,
        "pc": wr.get("pc_worst_delta", 999.0),
        "sf": wr.get("sf_worst_delta", 999.0),
        "cm": wr.get("greedy_consonant_match", 1.0),
        "fc": wr.get("frame_count", 0),
        "pd_i": wr.get("pd_i3rab_delta", 0.0),
        "pd_t": wr.get("pd_tashkeel_delta", 0.0),
        "lpd_i": wr.get("local_pd_i3rab", 0.0),
        "lpd_t": wr.get("local_pd_tashkeel", 0.0),
        "gfm": wr.get("greedy_final_mismatch", False),
        "gdm": wr.get("greedy_diac_mismatches", 0),
        "whisper_match": wr.get("whisper_match", True),
    }


def main():
    random.seed(42)

    sessions_dir = BASE / "test_data" / "sessions"
    sessions = find_best_sessions(sessions_dir)
    if not sessions:
        print("No sessions found")
        return

    engine = RecitationEngine(str(MODEL_PATH))

    correct_records = []  # signals dict
    uncaught_records = []  # (signals, mutation_type, desc)
    caught_records = []

    for pid in sorted(sessions):
        si = sessions[pid]
        phrases = si["meta"]["phrases"]
        audio = si["audio"]
        full_text = " ".join(phrases)

        print(f"\nSession: {pid} ({si['duration']:.1f}s)")

        waveform = torch.from_numpy(audio)
        word_results, _, _ = engine.score_phrase(waveform, full_text, compute_pd=False)
        segments = _extract_phrase_segments(word_results, phrases, audio)

        whisper_per_phrase = {}
        for pi in sorted(segments.keys()):
            whisper_per_phrase[pi] = engine.whisper_transcribe(segments[pi])

        covered = sorted(segments.keys())

        # --- CORRECT TEXT at eff <= -1.5 ---
        for pi in covered:
            phrase = phrases[pi]
            pw = phrase.split()
            seg = segments[pi]
            word_results_phrase = score_and_extract(engine, seg, phrase, whisper_per_phrase[pi])
            classified = classify_words(word_results_phrase, pw)

            for i, wr in enumerate(word_results_phrase):
                wi = wr["word_idx"]
                if wi >= len(pw):
                    continue
                eff = wr["effective_score"]
                if eff > -1.5:
                    continue
                signals = extract_full_signals(wr, pw[wi])
                signals["word"] = pw[wi]
                # Check if this correct word was already flagged as FP
                cw = classified[i] if i < len(classified) else None
                if cw and cw["status"] != "correct":
                    signals["already_fp"] = True
                else:
                    signals["already_fp"] = False
                correct_records.append(signals)

        # --- MUTATED TEXT at eff <= -1.5 ---
        for pi in covered:
            phrase = phrases[pi]
            pw = phrase.split()
            seg = segments[pi]

            def _process_mutation(mut_text, wi, mtype, desc):
                word_results_mut = score_and_extract(engine, seg, mut_text, whisper_per_phrase[pi])
                classified = classify_words(word_results_mut, mut_text.split())
                for j, wr in enumerate(word_results_mut):
                    if wr["word_idx"] == wi:
                        eff = wr["effective_score"]
                        if eff > -1.5:
                            return
                        signals = extract_full_signals(wr, mut_text.split()[wi])
                        signals["word"] = mut_text.split()[wi]
                        cw = classified[j] if j < len(classified) else None
                        detected = cw and cw["status"] != "correct"
                        if detected:
                            caught_records.append((signals, mtype, desc))
                        else:
                            uncaught_records.append((signals, mtype, desc))
                        return

            for wi, word in enumerate(pw):
                mutated, desc = mutate_i3rab(word)
                if mutated is None:
                    continue
                mut_words = list(pw)
                mut_words[wi] = mutated
                _process_mutation(" ".join(mut_words), wi, "i3rab", desc)

            for wi, word in enumerate(pw):
                if len(strip_diacritics(word)) < 3:
                    continue
                mutated, desc = mutate_tashkeel(word)
                if mutated is None:
                    continue
                mut_words = list(pw)
                mut_words[wi] = mutated
                _process_mutation(" ".join(mut_words), wi, "tashkeel", desc)

            candidates = [i for i, w in enumerate(pw) if len(strip_diacritics(w)) >= 3]
            if candidates:
                test_idxs = random.sample(candidates, min(2, len(candidates)))
                for wi in test_idxs:
                    mut_words_list, desc = mutate_word(pw, wi)
                    _process_mutation(" ".join(mut_words_list), wi, "word", desc)

    # Filter out already-FP correct records (they're already flagged)
    clean_correct = [r for r in correct_records if not r["already_fp"]]
    already_fp = [r for r in correct_records if r["already_fp"]]

    print(f"\n{'='*80}")
    print(f"COMBO ANALYSIS (eff <= -1.5)")
    print(f"{'='*80}")
    print(f"Clean correct: {len(clean_correct)} (already FP: {len(already_fp)})")
    print(f"Uncaught mutated: {len(uncaught_records)}")
    print(f"Already caught: {len(caught_records)}")

    # --- SYSTEMATIC 2-SIGNAL COMBO SEARCH ---
    print(f"\n--- 2-Signal combos: lpd + existing signal ---")
    print(f"Looking for FP <= 2, catches >= 5")

    rules_2sig = []
    # local_pd_i + various signals
    for lpd_thresh in [0.20, 0.30, 0.40, 0.50, 0.60, 0.80]:
        for sig_name, key, comp, thresholds in [
            ("td", "td", ">=", [0.03, 0.05, 0.08, 0.10]),
            ("pd_i", "pd_i", ">=", [0.10, 0.15, 0.20, 0.30]),
            ("pd_t", "pd_t", ">=", [0.10, 0.15, 0.20, 0.30]),
            ("sf", "sf", "<", [-2.0, -3.0, -4.0]),
            ("pc", "pc", "<", [-2.0, -3.0, -4.0]),
            ("cm", "cm", "<=", [0.20, 0.30, 0.40]),
        ]:
            for t2 in thresholds:
                if comp == ">=":
                    fp = sum(1 for r in clean_correct if r["lpd_i"] >= lpd_thresh and r[key] >= t2)
                    catches = sum(1 for s, mt, d in uncaught_records if s["lpd_i"] >= lpd_thresh and s[key] >= t2)
                else:
                    fp = sum(1 for r in clean_correct if r["lpd_i"] >= lpd_thresh and r[key] < t2)
                    catches = sum(1 for s, mt, d in uncaught_records if s["lpd_i"] >= lpd_thresh and s[key] < t2)
                if fp <= 2 and catches >= 5:
                    rules_2sig.append((f"lpd_i>={lpd_thresh} + {sig_name}{comp}{t2}", fp, catches))

    # local_pd_t + various signals
    for lpd_thresh in [0.20, 0.30, 0.40, 0.50, 0.60, 0.80]:
        for sig_name, key, comp, thresholds in [
            ("td", "td", ">=", [0.03, 0.05, 0.08, 0.10]),
            ("pd_i", "pd_i", ">=", [0.10, 0.15, 0.20, 0.30]),
            ("pd_t", "pd_t", ">=", [0.10, 0.15, 0.20, 0.30]),
            ("sf", "sf", "<", [-2.0, -3.0, -4.0]),
            ("cm", "cm", "<=", [0.20, 0.30, 0.40]),
        ]:
            for t2 in thresholds:
                if comp == ">=":
                    fp = sum(1 for r in clean_correct if r["lpd_t"] >= lpd_thresh and r[key] >= t2)
                    catches = sum(1 for s, mt, d in uncaught_records if s["lpd_t"] >= lpd_thresh and s[key] >= t2)
                else:
                    fp = sum(1 for r in clean_correct if r["lpd_t"] >= lpd_thresh and r[key] < t2)
                    catches = sum(1 for s, mt, d in uncaught_records if s["lpd_t"] >= lpd_thresh and s[key] < t2)
                if fp <= 2 and catches >= 5:
                    rules_2sig.append((f"lpd_t>={lpd_thresh} + {sig_name}{comp}{t2}", fp, catches))

    # max(lpd_i, lpd_t) threshold
    for lpd_thresh in [0.30, 0.40, 0.50, 0.60, 0.80]:
        for sig_name, key, comp, thresholds in [
            ("td", "td", ">=", [0.03, 0.05, 0.08, 0.10]),
            ("pd_i", "pd_i", ">=", [0.10, 0.15, 0.20]),
        ]:
            for t2 in thresholds:
                fp = sum(1 for r in clean_correct
                         if max(r["lpd_i"], r["lpd_t"]) >= lpd_thresh and r[key] >= t2)
                catches = sum(1 for s, mt, d in uncaught_records
                              if max(s["lpd_i"], s["lpd_t"]) >= lpd_thresh and s[key] >= t2)
                if fp <= 2 and catches >= 5:
                    rules_2sig.append((f"max(lpd)>={lpd_thresh} + {sig_name}>={t2}", fp, catches))

    # Sort by catches descending, then FP ascending
    rules_2sig.sort(key=lambda x: (-x[2], x[1]))
    seen = set()
    for desc, fp, catches in rules_2sig:
        if desc not in seen:
            seen.add(desc)
            print(f"  {desc:50s} FP={fp}  catches={catches}")

    # --- 3-SIGNAL COMBOS ---
    print(f"\n--- 3-Signal combos: lpd + 2 existing signals ---")
    rules_3sig = []

    for lpd_name, lpd_key in [("lpd_i", "lpd_i"), ("lpd_t", "lpd_t")]:
        for lpd_thresh in [0.20, 0.30, 0.40, 0.50]:
            for s1_name, s1_key, s1_comp, s1_thresholds in [
                ("td", "td", ">=", [0.03, 0.05]),
                ("pd_i", "pd_i", ">=", [0.10, 0.20]),
                ("pd_t", "pd_t", ">=", [0.10, 0.20]),
            ]:
                for s2_name, s2_key, s2_comp, s2_thresholds in [
                    ("pd_i", "pd_i", ">=", [0.10, 0.20]),
                    ("pd_t", "pd_t", ">=", [0.10, 0.20]),
                    ("sf", "sf", "<", [-2.0, -3.0]),
                    ("cm", "cm", "<=", [0.25, 0.40]),
                ]:
                    if s1_key == s2_key:
                        continue
                    for t1 in s1_thresholds:
                        for t2 in s2_thresholds:
                            def check(r):
                                if r[lpd_key] < lpd_thresh:
                                    return False
                                v1 = r[s1_key]
                                if s1_comp == ">=" and v1 < t1:
                                    return False
                                if s1_comp == "<" and v1 >= t1:
                                    return False
                                v2 = r[s2_key]
                                if s2_comp == ">=" and v2 < t2:
                                    return False
                                if s2_comp == "<" and v2 >= t2:
                                    return False
                                return True

                            fp = sum(1 for r in clean_correct if check(r))
                            catches = sum(1 for s, mt, d in uncaught_records if check(s))
                            if fp <= 1 and catches >= 5:
                                desc = f"{lpd_name}>={lpd_thresh} + {s1_name}{s1_comp}{t1} + {s2_name}{s2_comp}{t2}"
                                rules_3sig.append((desc, fp, catches))

    rules_3sig.sort(key=lambda x: (-x[2], x[1]))
    seen = set()
    for desc, fp, catches in rules_3sig[:30]:
        if desc not in seen:
            seen.add(desc)
            print(f"  {desc:65s} FP={fp}  catches={catches}")

    # --- TYPE BREAKDOWN for best rules ---
    print(f"\n--- Type breakdown for best 2-sig rules ---")
    if rules_2sig:
        # Take top 5 by catches
        printed = set()
        for desc, fp, catches in rules_2sig:
            if desc in printed:
                continue
            printed.add(desc)
            if len(printed) > 8:
                break

            # Parse rule to get types of catches
            i3rab_catches = 0
            tash_catches = 0
            word_catches = 0
            for s, mt, d in uncaught_records:
                # Re-evaluate rule manually
                parts = desc.split(" + ")
                pass_rule = True
                for part in parts:
                    if ">=" in part:
                        key, val = part.split(">=")
                        key = key.strip()
                        val = float(val)
                        sig_key = key
                        if key == "max(lpd)":
                            if max(s["lpd_i"], s["lpd_t"]) < val:
                                pass_rule = False
                                break
                        else:
                            if s.get(sig_key, 0) < val:
                                pass_rule = False
                                break
                    elif "<=" in part:
                        key, val = part.split("<=")
                        if s.get(key.strip(), 999) > float(val):
                            pass_rule = False
                            break
                    elif "<" in part:
                        key, val = part.split("<")
                        if s.get(key.strip(), 999) >= float(val):
                            pass_rule = False
                            break
                if pass_rule:
                    if mt == "i3rab": i3rab_catches += 1
                    elif mt == "tashkeel": tash_catches += 1
                    else: word_catches += 1

            print(f"  {desc:50s} FP={fp} total={catches}  i3={i3rab_catches} tash={tash_catches} word={word_catches}")

    # --- STANDALONE HIGH-THRESHOLD LOCAL PD ---
    print(f"\n--- High-threshold local_pd standalone ---")
    for thresh in [0.50, 0.60, 0.70, 0.80, 1.00]:
        fp_i = sum(1 for r in clean_correct if r["lpd_i"] >= thresh)
        catch_i = sum(1 for s, mt, d in uncaught_records if s["lpd_i"] >= thresh)
        fp_t = sum(1 for r in clean_correct if r["lpd_t"] >= thresh)
        catch_t = sum(1 for s, mt, d in uncaught_records if s["lpd_t"] >= thresh)
        fp_max = sum(1 for r in clean_correct if max(r["lpd_i"], r["lpd_t"]) >= thresh)
        catch_max = sum(1 for s, mt, d in uncaught_records if max(s["lpd_i"], s["lpd_t"]) >= thresh)
        print(f"  lpd_i>={thresh}: FP={fp_i} catches={catch_i}  |  "
              f"lpd_t>={thresh}: FP={fp_t} catches={catch_t}  |  "
              f"max(lpd)>={thresh}: FP={fp_max} catches={catch_max}")


if __name__ == "__main__":
    main()
