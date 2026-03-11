#!/usr/bin/env python3
"""
Final exhaustive grid search over the most promising threshold combinations
identified in the initial sweep, plus the baseline for comparison.
"""

import json
import time
from pathlib import Path
from threshold_tuning import (
    ThresholdParams,
    read_audio,
    evaluate_all_sentences,
)


def main():
    from i3rab.config import Config
    from i3rab.pcd_transcriber import PCDTranscriber
    from i3rab.book import Book
    from i3rab.arabic import normalize_arabic, strip_harakat
    from i3rab.tracker import PositionTracker

    test_dir = Path("test_data")
    manifest = json.loads((test_dir / "manifest.json").read_text())
    sentences = [e for e in manifest if e.get("type") == "sentence"]

    config = Config()
    transcriber = PCDTranscriber(config)
    transcriber.load()

    # Pre-compute encoder outputs
    print("Pre-computing encoder outputs...")
    precomputed_cache = {}
    for entry in sentences:
        filepath = test_dir / entry["filename"]
        if not filepath.exists():
            continue

        rec_id = entry["id"]
        reference = entry["text_diacritized"]
        book = Book.from_sentence(reference)
        audio = read_audio(filepath)

        pcd_text, log_probs, encoded_len = transcriber.transcribe_and_encode(audio)
        pcd_normalized = normalize_arabic(pcd_text) if pcd_text.strip() else ""

        tracker = PositionTracker(book, Config())
        saved_pos = tracker.current_position
        if pcd_normalized:
            start_idx, end_idx, matched_pairs = tracker.locate(
                strip_harakat(pcd_normalized)
            )
        else:
            matched_pairs = []
        tracker.current_position = saved_pos

        if matched_pairs:
            matched_book_indices = sorted(bw.index for bw, _ in matched_pairs)
            fill_start = matched_book_indices[0]
            fill_end = matched_book_indices[-1] + 1
        else:
            fill_start = 0
            fill_end = 0

        precomputed_cache[rec_id] = {
            "pcd_text": pcd_text,
            "log_probs": log_probs,
            "encoded_len": encoded_len,
            "pcd_normalized": pcd_normalized,
            "matched_pairs": matched_pairs,
            "fill_start": fill_start,
            "fill_end": fill_end,
        }
    print("Done.\n")

    # Grid search over promising combinations
    print("="*80)
    print("  EXHAUSTIVE GRID SEARCH OVER PROMISING COMBINATIONS")
    print("="*80)

    results = []

    for fallback in [True, False]:
        for high_gap in [0.5, 1.0, 1.5, 2.0, 3.0]:
            for medium_gap in [0.1, 0.3, 0.5, 1.0, 1.5]:
                if medium_gap >= high_gap:
                    continue
                for tashkeel_thresh in [-2.0, -3.0, -3.5]:
                    for omission_margin in [0.3, 1.0, 2.0]:
                        for edge_thresh in [-4.0, -6.0, -8.0]:
                            params = ThresholdParams(
                                high_gap=high_gap,
                                medium_gap=medium_gap,
                                tashkeel_align_threshold=tashkeel_thresh,
                                omission_margin=omission_margin,
                                edge_recovery_threshold=edge_thresh,
                                low_confidence_fallback=fallback,
                            )
                            result = evaluate_all_sentences(
                                transcriber, sentences, test_dir,
                                params, precomputed_cache,
                            )
                            results.append((params, result))

    # Sort by accuracy descending, then by correct/total
    results.sort(key=lambda x: (x[1]["accuracy"], x[1]["total_correct"]), reverse=True)

    # Print top 30
    print(f"\n{'='*80}")
    print(f"  TOP 30 CONFIGURATIONS (out of {len(results)} tested)")
    print(f"{'='*80}")
    print(f"  {'Rank':4s}  {'Score':8s}  {'Acc':6s}  {'H_gap':6s}  {'M_gap':6s}  {'Tash':5s}  {'Omis':5s}  {'Edge':5s}  {'Fall':5s}")
    print(f"  {'-'*4}  {'-'*8}  {'-'*6}  {'-'*6}  {'-'*6}  {'-'*5}  {'-'*5}  {'-'*5}  {'-'*5}")
    for rank, (params, result) in enumerate(results[:30], 1):
        print(
            f"  {rank:4d}  "
            f"{result['total_correct']:3d}/{result['total_words']:3d}  "
            f"{result['accuracy']:5.1f}%  "
            f"{params.high_gap:6.1f}  "
            f"{params.medium_gap:6.1f}  "
            f"{params.tashkeel_align_threshold:5.1f}  "
            f"{params.omission_margin:5.1f}  "
            f"{params.edge_recovery_threshold:5.1f}  "
            f"{'Y' if params.low_confidence_fallback else 'N':>5s}"
        )

    # Print bottom 5 for contrast
    print(f"\n  BOTTOM 5:")
    for rank, (params, result) in enumerate(results[-5:], len(results)-4):
        print(
            f"  {rank:4d}  "
            f"{result['total_correct']:3d}/{result['total_words']:3d}  "
            f"{result['accuracy']:5.1f}%  "
            f"{params.high_gap:6.1f}  "
            f"{params.medium_gap:6.1f}  "
            f"{params.tashkeel_align_threshold:5.1f}  "
            f"{params.omission_margin:5.1f}  "
            f"{params.edge_recovery_threshold:5.1f}  "
            f"{'Y' if params.low_confidence_fallback else 'N':>5s}"
        )

    # Best configuration details
    best_params, best_result = results[0]
    print(f"\n{'='*80}")
    print(f"  BEST CONFIGURATION")
    print(f"{'='*80}")
    print(f"  Accuracy: {best_result['total_correct']}/{best_result['total_words']} ({best_result['accuracy']:.1f}%)")
    print(f"  Parameters:")
    print(f"    high_gap:                  {best_params.high_gap}")
    print(f"    medium_gap:                {best_params.medium_gap}")
    print(f"    tashkeel_align_threshold:  {best_params.tashkeel_align_threshold}")
    print(f"    omission_margin:           {best_params.omission_margin}")
    print(f"    edge_recovery_threshold:   {best_params.edge_recovery_threshold}")
    print(f"    low_confidence_fallback:   {best_params.low_confidence_fallback}")

    # Baseline
    baseline_params = ThresholdParams()
    baseline = evaluate_all_sentences(
        transcriber, sentences, test_dir, baseline_params, precomputed_cache,
    )
    print(f"\n  Baseline:   {baseline['total_correct']}/{baseline['total_words']} ({baseline['accuracy']:.1f}%)")
    print(f"  Best:       {best_result['total_correct']}/{best_result['total_words']} ({best_result['accuracy']:.1f}%)")
    print(f"  Delta:      +{best_result['accuracy'] - baseline['accuracy']:.1f}%")

    # Per-sentence breakdown for best config
    print(f"\n{'='*80}")
    print(f"  PER-SENTENCE: Baseline vs Best")
    print(f"{'='*80}")
    for bs, fs in zip(baseline["per_sentence"], best_result["per_sentence"]):
        b_mark = f"{bs['correct']}/{bs['total']}"
        f_mark = f"{fs['correct']}/{fs['total']}"
        changed = " *CHANGED*" if bs["correct"] != fs["correct"] or bs["total"] != fs["total"] else ""
        print(f"    {bs['id']}: {b_mark:8s} -> {f_mark:8s}{changed}  {bs['ref'][:50]}...")


if __name__ == "__main__":
    main()
