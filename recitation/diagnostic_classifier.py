#!/usr/bin/env python3
"""Diagnostic: check theoretical detection ceiling using a classifier on all signals.

Fits a simple logistic regression and decision tree on the full signal vector
to see what detection rate is achievable with the current model's signals,
ignoring the constraint of hand-tuned thresholds.
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

SIGNAL_KEYS = [
    "eff", "i3rab_delta", "tash_delta", "pc", "sf_gop", "mg",
    "consonant_match", "frame_count", "gdm", "gfm",
    "pd_i3rab", "pd_tashkeel", "local_pd_i", "local_pd_t",
    "fs", "rescored_sf", "rescored_pc",
]


def extract_features(d):
    """Extract feature vector from debug dict."""
    feats = []
    for k in SIGNAL_KEYS:
        v = d.get(k)
        if v is None or v == 999 or v == 999.0:
            feats.append(0.0)
        elif isinstance(v, bool):
            feats.append(1.0 if v else 0.0)
        else:
            feats.append(float(v))
    return feats


def main():
    random.seed(42)
    sessions_dir = BASE / "test_data" / "sessions"
    sessions = find_best_sessions(sessions_dir)
    if not sessions:
        return

    engine = RecitationEngine(str(MODEL_PATH))

    correct_feats = []
    mutated_feats = []
    mutated_types = []  # 'i3rab', 'tashkeel', 'word'

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

        # Correct text
        for pi in covered:
            phrase = phrases[pi]
            seg = segments[pi]
            classified = _score_phrase_with_whisper(engine, seg, phrase, whisper_per_phrase[pi])
            for cw in classified:
                correct_feats.append(extract_features(cw["debug"]))

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
                        mutated_feats.append(extract_features(cw["debug"]))
                        mutated_types.append("i3rab")

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
                        mutated_feats.append(extract_features(cw["debug"]))
                        mutated_types.append("tashkeel")

            candidates = [i for i, w in enumerate(pw) if len(strip_diacritics(w)) >= 3]
            if candidates:
                for wi in random.sample(candidates, min(2, len(candidates))):
                    mut_words_list, desc = mutate_word(pw, wi)
                    classified = _score_phrase_with_whisper(engine, seg, " ".join(mut_words_list), whisper_words)
                    for cw in classified:
                        if cw["idx"] == wi:
                            mutated_feats.append(extract_features(cw["debug"]))
                            mutated_types.append("word")

    X_correct = np.array(correct_feats)
    X_mutated = np.array(mutated_feats)

    print(f"\nCorrect: {len(X_correct)}, Mutated: {len(X_mutated)}")
    print(f"Features: {SIGNAL_KEYS}")

    # Combine and fit classifier
    X = np.vstack([X_correct, X_mutated])
    y = np.array([0] * len(X_correct) + [1] * len(X_mutated))

    # Replace NaN/inf
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    from sklearn.linear_model import LogisticRegression
    from sklearn.tree import DecisionTreeClassifier
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Logistic regression with different regularization
    for C in [0.01, 0.1, 1.0, 10.0]:
        lr = LogisticRegression(C=C, max_iter=1000, random_state=42)
        lr.fit(X_scaled, y)
        pred = lr.predict(X_scaled)
        fp = sum(pred[:len(X_correct)] == 1)
        tp = sum(pred[len(X_correct):] == 1)
        print(f"\nLogistic C={C}: FP={fp}/{len(X_correct)} ({100*fp/len(X_correct):.1f}%)  "
              f"detection={tp}/{len(X_mutated)} ({100*tp/len(X_mutated):.1f}%)")

    # Decision tree with max_depth
    for d in [3, 5, 8, 12, None]:
        dt = DecisionTreeClassifier(max_depth=d, random_state=42)
        dt.fit(X_scaled, y)
        pred = dt.predict(X_scaled)
        fp = sum(pred[:len(X_correct)] == 1)
        tp = sum(pred[len(X_correct):] == 1)
        print(f"DecisionTree d={d}: FP={fp}/{len(X_correct)} ({100*fp/len(X_correct):.1f}%)  "
              f"detection={tp}/{len(X_mutated)} ({100*tp/len(X_mutated):.1f}%)")

    # Gradient boosting (powerful nonlinear)
    for n in [50, 100, 200]:
        gb = GradientBoostingClassifier(n_estimators=n, max_depth=3, random_state=42)
        gb.fit(X_scaled, y)
        pred = gb.predict(X_scaled)
        fp = sum(pred[:len(X_correct)] == 1)
        tp = sum(pred[len(X_correct):] == 1)
        print(f"GBM n={n}: FP={fp}/{len(X_correct)} ({100*fp/len(X_correct):.1f}%)  "
              f"detection={tp}/{len(X_mutated)} ({100*tp/len(X_mutated):.1f}%)")

    # Check at specific FP rates
    print("\n\nDETECTION AT SPECIFIC FP RATES (GBM n=200):")
    gb = GradientBoostingClassifier(n_estimators=200, max_depth=4, random_state=42)
    gb.fit(X_scaled, y)
    probs = gb.predict_proba(X_scaled)[:, 1]
    correct_probs = probs[:len(X_correct)]
    mutated_probs = probs[len(X_correct):]

    for max_fp_rate in [0.01, 0.02, 0.03, 0.05, 0.10]:
        max_fp = int(max_fp_rate * len(X_correct))
        # Find threshold that gives exactly max_fp false positives
        sorted_c = sorted(correct_probs, reverse=True)
        if max_fp >= len(sorted_c):
            thresh = 0.0
        elif max_fp == 0:
            thresh = sorted_c[0] + 0.001
        else:
            thresh = sorted_c[max_fp - 1]
        fp = sum(correct_probs >= thresh)
        tp = sum(mutated_probs >= thresh)
        # Per-type detection
        tp_by_type = defaultdict(int)
        fn_by_type = defaultdict(int)
        for i, (p, t) in enumerate(zip(mutated_probs, mutated_types)):
            if p >= thresh:
                tp_by_type[t] += 1
            else:
                fn_by_type[t] += 1
        print(f"\n  FP<={100*max_fp_rate:.0f}%: threshold={thresh:.3f} FP={fp}  "
              f"detection={tp}/{len(X_mutated)} ({100*tp/len(X_mutated):.1f}%)")
        for t in ["i3rab", "tashkeel", "word"]:
            total_t = tp_by_type[t] + fn_by_type[t]
            print(f"    {t}: {tp_by_type[t]}/{total_t} ({100*tp_by_type[t]/total_t:.1f}%)")

    # Feature importance
    print("\n\nFEATURE IMPORTANCE (GBM):")
    for i, (name, imp) in enumerate(sorted(zip(SIGNAL_KEYS, gb.feature_importances_),
                                           key=lambda x: -x[1])):
        if imp > 0.01:
            print(f"  {name:20s}: {imp:.4f}")

    # By eff range
    print("\n\nDETECTION BY EFF RANGE (GBM at FP<=2%):")
    max_fp = int(0.02 * len(X_correct))
    sorted_c = sorted(correct_probs, reverse=True)
    thresh = sorted_c[max_fp - 1] if max_fp > 0 else sorted_c[0] + 0.001

    ranges = [
        ('>-0.5', lambda e: e > -0.5),
        ('-0.5 to -1.0', lambda e: -0.5 >= e > -1.0),
        ('-1.0 to -1.5', lambda e: -1.0 >= e > -1.5),
        ('<-1.5', lambda e: e <= -1.5),
    ]
    for rname, rfn in ranges:
        # Get indices of mutated in this range
        in_range = [i for i, f in enumerate(X_mutated) if rfn(f[0])]  # f[0] is eff
        if not in_range:
            continue
        caught = sum(1 for i in in_range if mutated_probs[i] >= thresh)
        print(f"  {rname:20s}: {caught}/{len(in_range)} ({100*caught/len(in_range):.1f}%)")


if __name__ == "__main__":
    main()
