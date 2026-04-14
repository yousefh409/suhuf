#!/usr/bin/env python3
"""Dump all raw scoring signals for offline threshold optimization.

Runs test_mutations once and saves all word-level signals to JSON.
This allows rapid iteration on classify_words thresholds without
re-running the expensive CTC scoring (~10 min).
"""
import sys
import json
import random
import numpy as np
import torch
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

from engine import RecitationEngine, StreamingSession
from server import classify_words
from arabic import (
    FATHA, DAMMA, KASRA, FATHATAN, DAMMATAN, KASRATAN, SUKOON, SHADDA,
    HARAKAT, strip_diacritics,
)
from test_mutations import (
    find_best_sessions, _extract_phrase_segments,
    mutate_i3rab, mutate_tashkeel, mutate_word,
    SAMPLE_RATE,
)

MODEL_PATH = BASE / "models" / "ssl_xls_r_v5"


def extract_signals(wr, word_text):
    """Extract all numeric signals from a word result dict."""
    eff = wr["effective_score"]
    consonants = strip_diacritics(word_text)
    greedy_seg = wr.get("greedy_segment", "")
    alt = wr["best_alt_score"]
    tash = wr.get("best_tashkeel_score", -999.0)
    sukoon_alt = wr.get("best_sukoon_score", -999.0)

    return {
        "word": word_text,
        "eff": round(eff, 4),
        "consonant_match": round(wr.get("greedy_consonant_match", 1.0), 4),
        "frame_count": wr.get("frame_count", 0),
        "word_len": len(consonants),
        "greedy_len": len(greedy_seg),
        # i3rab signals
        "i3rab_delta": round(alt - eff, 4) if alt > -900 else None,
        "i3rab_name": wr.get("best_alt_name"),
        "skip_i3rab": wr.get("skip_i3rab", False),
        # tashkeel signals
        "tash_delta": round(tash - eff, 4) if tash > -900 else None,
        "tash_name": wr.get("best_tashkeel_name"),
        "sukoon_delta": round(sukoon_alt - eff, 4) if sukoon_alt > -900 else None,
        "skip_tashkeel": wr.get("skip_tashkeel", False),
        # per-char
        "pc": round(wr.get("pc_worst_delta", 999.0), 4) if wr.get("pc_worst_delta", 999.0) < 900 else None,
        "pc_expected": wr.get("pc_expected_diac"),
        "pc_heard": wr.get("pc_heard_diac"),
        # sf-gop
        "sf": round(wr.get("sf_worst_delta", 999.0), 4) if wr.get("sf_worst_delta", 999.0) < 900 else None,
        # greedy mismatch
        "gdm": wr.get("greedy_diac_mismatches", 0),
        "gfm": wr.get("greedy_final_mismatch", False),
        # shadda
        "shadda_delta": round(wr.get("best_shadda_score", -999.0) - eff, 4) if wr.get("best_shadda_score", -999.0) > -900 else None,
        # mixgop
        "mg": round(wr.get("mg_worst_margin", 999.0), 4) if wr.get("mg_worst_margin", 999.0) < 900 else None,
        # whisper
        "whisper_match": wr.get("whisper_match", True),
        # expected/sukoon scores
        "expected_score": round(wr.get("expected_score", -999.0), 4),
        "sukoon_score": round(wr.get("sukoon_score", -999.0), 4),
        # phrase-differential
        "pd_i3rab": round(wr.get("pd_i3rab_delta", 0.0), 4),
        "pd_tashkeel": round(wr.get("pd_tashkeel_delta", 0.0), 4),
        # local phrase-differential
        "local_pd_i3rab": round(wr.get("local_pd_i3rab", 0.0), 4),
        "local_pd_tashkeel": round(wr.get("local_pd_tashkeel", 0.0), 4),
        # frame scan
        "fs_worst_delta": round(wr.get("fs_worst_delta", 999.0), 4) if wr.get("fs_worst_delta", 999.0) < 900 else None,
        "fs_expected": wr.get("fs_expected"),
        "fs_heard": wr.get("fs_heard"),
        # rescored
        "rescored_eff": round(wr.get("rescored_eff", -999.0), 4) if wr.get("rescored_eff") is not None else None,
        "rescored_sf": round(wr.get("rescored_sf", 999.0), 4) if wr.get("rescored_sf", 999.0) < 900 else None,
        "rescored_pc": round(wr.get("rescored_pc", 999.0), 4) if wr.get("rescored_pc", 999.0) < 900 else None,
        "rescored_gfm": wr.get("rescored_gfm", False),
        "rescored_i3rab_delta": round(wr.get("rescored_i3rab_delta", 0.0), 4),
        "rescored_tash_delta": round(wr.get("rescored_tash_delta", 0.0), 4),
    }


def main():
    random.seed(42)

    sessions_dir = BASE / "test_data" / "sessions"
    sessions = find_best_sessions(sessions_dir)

    if not sessions:
        print("No sessions found")
        return

    engine = RecitationEngine(str(MODEL_PATH))

    all_records = []  # Each: {signals, label, mutation_type, mutation_desc, phrase_idx, word_idx}

    for pid in sorted(sessions):
        si = sessions[pid]
        phrases = si["meta"]["phrases"]
        audio = si["audio"]
        full_text = " ".join(phrases)
        all_words = full_text.split()

        print(f"\nSession: {pid} ({si['duration']:.1f}s)")

        # Score full text to get alignment
        waveform = torch.from_numpy(audio)
        word_results, greedy, full_score = engine.score_phrase(waveform, full_text,
                                                                  compute_pd=False)

        # Extract per-phrase audio segments
        segments = _extract_phrase_segments(word_results, phrases, audio)

        # Whisper per segment
        whisper_per_phrase = {}
        for pi in sorted(segments.keys()):
            whisper_per_phrase[pi] = engine.whisper_transcribe(segments[pi])

        covered = sorted(segments.keys())
        print(f"  Covered phrases: {len(covered)}/{len(phrases)}")

        # --- CORRECT TEXT (FP check) ---
        for pi in covered:
            phrase = phrases[pi]
            pw = phrase.split()
            seg = segments[pi]
            whisper_words = whisper_per_phrase[pi]

            waveform_seg = torch.from_numpy(seg)
            word_results_phrase, _, _ = engine.score_phrase(waveform_seg, phrase)

            # Add whisper matching
            duration = len(seg) / SAMPLE_RATE
            wmatch = StreamingSession._whisper_word_matches(whisper_words, pw)
            match_ratio = sum(wmatch) / len(wmatch) if wmatch else 1.0
            trust_whisper = duration >= 3.0 and match_ratio >= 0.6
            for wr in word_results_phrase:
                wi = wr["word_idx"]
                if trust_whisper:
                    wr["whisper_match"] = wmatch[wi] if wi < len(wmatch) else True
                else:
                    wr["whisper_match"] = True

            for wr in word_results_phrase:
                wi = wr["word_idx"]
                if wi >= len(pw):
                    continue
                signals = extract_signals(wr, pw[wi])
                all_records.append({
                    "signals": signals,
                    "label": "correct",
                    "mutation_type": None,
                    "mutation_desc": None,
                    "passage_id": pid,
                    "phrase_idx": pi,
                    "word_idx": wi,
                })

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
                _add_mutation_record(engine, seg, mut_text, wi, "i3rab", desc,
                                     all_records, pid, pi, whisper_words)

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
                _add_mutation_record(engine, seg, mut_text, wi, "tashkeel", desc,
                                     all_records, pid, pi, whisper_words)

            # word replacements
            candidates = [i for i, w in enumerate(pw) if len(strip_diacritics(w)) >= 3]
            if candidates:
                test_idxs = random.sample(candidates, min(2, len(candidates)))
                for wi in test_idxs:
                    mut_words_list, desc = mutate_word(pw, wi)
                    mut_text = " ".join(mut_words_list)
                    _add_mutation_record(engine, seg, mut_text, wi, "word", desc,
                                         all_records, pid, pi, whisper_words)

        print(f"  Records so far: {len(all_records)}")

    # Save to JSON
    out_path = BASE / "signal_dump.json"
    with open(out_path, "w") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)

    n_correct = sum(1 for r in all_records if r["label"] == "correct")
    n_mutated = sum(1 for r in all_records if r["label"] != "correct")
    print(f"\nSaved {len(all_records)} records ({n_correct} correct, {n_mutated} mutated) to {out_path}")


def _add_mutation_record(engine, audio_segment, mutated_text, word_idx,
                         mutation_type, desc, records, pid, pi, whisper_words):
    """Score mutated text and add signal record."""
    try:
        waveform = torch.from_numpy(audio_segment)
        word_results, _, _ = engine.score_phrase(waveform, mutated_text)
    except Exception:
        return

    # Add whisper
    mut_words = mutated_text.split()
    duration = len(audio_segment) / SAMPLE_RATE
    wmatch = StreamingSession._whisper_word_matches(whisper_words, mut_words)
    match_ratio = sum(wmatch) / len(wmatch) if wmatch else 1.0
    trust_whisper = duration >= 3.0 and match_ratio >= 0.6
    for wr in word_results:
        wi = wr["word_idx"]
        if trust_whisper:
            wr["whisper_match"] = wmatch[wi] if wi < len(wmatch) else True
        else:
            wr["whisper_match"] = True

    # Find the mutated word's result
    for wr in word_results:
        if wr["word_idx"] == word_idx:
            signals = extract_signals(wr, mut_words[word_idx] if word_idx < len(mut_words) else "")
            records.append({
                "signals": signals,
                "label": "mutated",
                "mutation_type": mutation_type,
                "mutation_desc": desc,
                "passage_id": pid,
                "phrase_idx": pi,
                "word_idx": word_idx,
            })
            break


if __name__ == "__main__":
    main()
