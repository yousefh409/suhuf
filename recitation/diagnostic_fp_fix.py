#!/usr/bin/env python3
"""Check impact of tightening rules to fix specific FPs."""
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
        return

    engine = RecitationEngine(str(MODEL_PATH))

    # Collect all word results for mutation phase with full signals
    # Focus on the specific rules causing FPs

    # Rule checks:
    # 1. i3rab Tier 5: i3d>=0.03 + sf<-3.0, FP at eff=-1.453
    #    Fix: restrict to eff > -1.0. What mutations does this lose?
    # 2. tashkeel pc Tier 2 at -1.5<eff<=-1.0: pc<-4.0, FP at eff=-1.052 pc=-5.8
    #    Fix: revert to pc<-6.0. What mutations does this lose?
    # 3. whisper: eff<-1.5, FP at eff=-1.534
    #    Fix: tighten to eff<-1.6. What mutations does this lose?

    tier5_catches = []  # catches from i3rab Tier 5 at -1.5 < eff <= -1.0
    pc_tier2_catches = []  # catches from pc tier at -1.5<eff<=-1.0 with -6<pc<=-4
    whisper_catches_border = []  # catches from whisper at -1.6<eff<=-1.5

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

        for pi in covered:
            phrase = phrases[pi]
            pw = phrase.split()
            seg = segments[pi]

            def check_mutations(mut_text, wi, mtype, desc):
                waveform_seg = torch.from_numpy(seg)
                word_results_mut, _, _ = engine.score_phrase(waveform_seg, mut_text)

                # Add whisper
                mut_words = mut_text.split()
                duration = len(seg) / SAMPLE_RATE
                wmatch = StreamingSession._whisper_word_matches(whisper_per_phrase[pi], mut_words)
                match_ratio = sum(wmatch) / len(wmatch) if wmatch else 1.0
                trust_whisper = duration >= 3.0 and match_ratio >= 0.6
                for wr in word_results_mut:
                    w_idx = wr["word_idx"]
                    if trust_whisper:
                        wr["whisper_match"] = wmatch[w_idx] if w_idx < len(wmatch) else True
                    else:
                        wr["whisper_match"] = True

                for wr in word_results_mut:
                    if wr["word_idx"] != wi:
                        continue
                    eff = wr["effective_score"]
                    alt = wr["best_alt_score"]
                    tash = wr.get("best_tashkeel_score", -999.0)
                    i3d = (alt - eff) if alt > -900 else 0.0
                    td = (tash - eff) if tash > -900 else 0.0
                    sf = wr.get("sf_worst_delta", 999.0)
                    pc = wr.get("pc_worst_delta", 999.0)

                    # Check if Tier 5 catches at -1.5 < eff <= -1.0
                    if (-1.5 < eff <= -1.0
                            and i3d >= 0.03 and sf < -3.0
                            and (td <= 0 or i3d >= td)):
                        tier5_catches.append({
                            "word": mut_words[wi], "mtype": mtype, "desc": desc,
                            "eff": round(eff, 3), "i3d": round(i3d, 3),
                            "sf": round(sf, 3), "td": round(td, 3),
                        })

                    # Check if pc catches at -1.5 < eff <= -1.0 with -6 < pc <= -4
                    if (-1.5 < eff <= -1.0
                            and pc < -4.0 and pc >= -6.0):
                        pc_tier2_catches.append({
                            "word": mut_words[wi], "mtype": mtype, "desc": desc,
                            "eff": round(eff, 3), "pc": round(pc, 2),
                        })

                    # Check whisper catches at -1.6 < eff <= -1.5
                    whisper_match = wr.get("whisper_match", True)
                    word_consonants = strip_diacritics(mut_words[wi])
                    frame_count = wr.get("frame_count", 999)
                    if (-1.6 < eff <= -1.5
                            and not whisper_match
                            and len(word_consonants) >= 3
                            and frame_count >= 5):
                        whisper_catches_border.append({
                            "word": mut_words[wi], "mtype": mtype, "desc": desc,
                            "eff": round(eff, 3),
                        })

            for wi, word in enumerate(pw):
                mutated, desc = mutate_i3rab(word)
                if mutated is None:
                    continue
                mut_words = list(pw)
                mut_words[wi] = mutated
                check_mutations(" ".join(mut_words), wi, "i3rab", desc)

            for wi, word in enumerate(pw):
                if len(strip_diacritics(word)) < 3:
                    continue
                mutated, desc = mutate_tashkeel(word)
                if mutated is None:
                    continue
                mut_words = list(pw)
                mut_words[wi] = mutated
                check_mutations(" ".join(mut_words), wi, "tashkeel", desc)

            candidates = [i for i, w in enumerate(pw) if len(strip_diacritics(w)) >= 3]
            if candidates:
                test_idxs = random.sample(candidates, min(2, len(candidates)))
                for wi in test_idxs:
                    mut_words_list, desc = mutate_word(pw, wi)
                    check_mutations(" ".join(mut_words_list), wi, "word", desc)

    print(f"\n{'='*60}")
    print(f"FP FIX IMPACT ANALYSIS")
    print(f"{'='*60}")

    print(f"\n1. i3rab Tier 5 catches at -1.5 < eff <= -1.0: {len(tier5_catches)}")
    print("   (These would be LOST if we restrict Tier 5 to eff > -1.0)")
    for c in tier5_catches:
        print(f"   {c['word']:20s} {c['mtype']:10s} {c['desc']:40s} eff={c['eff']} i3d={c['i3d']} sf={c['sf']} td={c['td']}")

    print(f"\n2. pc catches at -1.5 < eff <= -1.0 with -6 < pc <= -4: {len(pc_tier2_catches)}")
    print("   (These would be LOST if we revert pc threshold to -6.0)")
    for c in pc_tier2_catches:
        print(f"   {c['word']:20s} {c['mtype']:10s} {c['desc']:40s} eff={c['eff']} pc={c['pc']}")

    print(f"\n3. whisper catches at -1.6 < eff <= -1.5: {len(whisper_catches_border)}")
    print("   (These would be LOST if we tighten whisper to eff < -1.6)")
    for c in whisper_catches_border:
        print(f"   {c['word']:20s} {c['mtype']:10s} {c['desc']:40s} eff={c['eff']}")


if __name__ == "__main__":
    main()
