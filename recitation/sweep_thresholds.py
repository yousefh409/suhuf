#!/usr/bin/env python3
"""Sweep tashkeel verification threshold to find optimal FP/recall balance.

Tests different tashkeel_threshold values on:
1. ClArTTS clean data (measures false positives)
2. ClArTTS with injected errors (measures recall)
"""

import sys
import time
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from i3rab.config import Config
from i3rab.pipeline import I3rabPipeline
from i3rab.book import Book
from i3rab.tracker import PositionTracker
from eval_recall import inject_all_errors


def load_clartts_samples(max_samples: int = 60):
    """Load ClArTTS test set using same pattern as eval_clartts.py."""
    from datasets import load_dataset

    print("Loading ClArTTS test set...")
    ds = load_dataset("MBZUAI/ClArTTS", split="test")
    print(f"  {len(ds)} samples available")

    samples = []
    for item in ds:
        text = item["text"].strip()
        if not text:
            continue
        if not any("\u064B" <= ch <= "\u0652" for ch in text):
            continue

        audio = np.array(item["audio"], dtype=np.float32)
        orig_sr = item["sampling_rate"]

        if orig_sr != 16000:
            from scipy.signal import resample as scipy_resample
            num_samples = int(len(audio) * 16000 / orig_sr)
            audio = scipy_resample(audio, num_samples).astype(np.float32)

        peak = np.abs(audio).max()
        if peak > 0:
            audio = audio / peak * 0.95

        duration = len(audio) / 16000
        if duration < 0.5 or duration > 20.0:
            continue

        samples.append({"text": text, "audio": audio, "duration": duration})
        if max_samples > 0 and len(samples) >= max_samples:
            break

    print(f"  {len(samples)} valid samples after filtering")
    return samples


def evaluate_sample(pipeline, text, audio, config):
    book = Book.from_sentence(text)
    pipeline.book = book
    pipeline.tracker = PositionTracker(book, config)
    return pipeline.evaluate_pcd_live(audio)


def run_tests(pipeline, samples, config, rng, fraction=0.3):
    """Run both FP and recall tests in one pass over samples."""
    word_pool = []
    for s in samples:
        word_pool.extend(s["text"].split())
    word_pool = list(set(word_pool))

    fp_total_words = 0
    fp_count = 0
    recall_injected = 0
    recall_scored = 0
    recall_detected = 0
    skipped = 0

    for si, sample in enumerate(samples):
        text = sample["text"]
        audio = sample["audio"]

        # 1. FP test (clean)
        try:
            result = evaluate_sample(pipeline, text, audio, config)
        except Exception:
            skipped += 1
            continue
        if not result or not result.get("scored_words"):
            skipped += 1
            continue
        for w in result["scored_words"]:
            fp_total_words += 1
            if w["kind"] in ("irab", "tashkeel", "wrong"):
                fp_count += 1

        # 2. Recall test (injected errors)
        seed = int(rng.integers(0, 2**31)) + si
        modified_text, injections = inject_all_errors(text, word_pool, fraction, seed)

        try:
            result2 = evaluate_sample(pipeline, modified_text, audio, config)
        except Exception:
            continue
        if not result2 or not result2.get("scored_words"):
            continue

        scored_kinds = {sw["index"]: sw["kind"] for sw in result2["scored_words"]}
        for inj in injections:
            idx = inj["word_idx"]
            recall_injected += 1
            if idx not in scored_kinds:
                continue
            recall_scored += 1
            if scored_kinds[idx] in ("irab", "tashkeel", "wrong"):
                recall_detected += 1

    fp_rate = fp_count / fp_total_words * 100 if fp_total_words > 0 else 0
    recall = recall_detected / recall_scored * 100 if recall_scored > 0 else 0
    return {
        "fp": fp_count, "fp_total": fp_total_words, "fp_rate": fp_rate,
        "recall_det": recall_detected, "recall_scored": recall_scored,
        "recall_rate": recall, "skipped": skipped,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-samples", type=int, default=60)
    args = parser.parse_args()

    samples = load_clartts_samples(args.max_samples)

    configs = [
        # (name, tashkeel_threshold, low_conf_threshold)
        ("baseline",          2.0, 1.5),
        ("tashkeel=3.0",      3.0, 1.5),
        ("tashkeel=5.0",      5.0, 1.5),
        ("tashkeel=8.0",      8.0, 1.5),
        ("lowconf=1.0",       2.0, 1.0),
        ("lowconf=0.5",       2.0, 0.5),
        ("t=5.0+lc=1.0",     5.0, 1.0),
        ("t=3.0+lc=1.0",     3.0, 1.0),
    ]

    print(f"\n{'Config':<18s}  {'FP':>4s}  {'FP%':>6s}  {'Recall':>7s}  {'Det/Scored':>12s}  {'Time':>5s}")
    print("-" * 65)

    for name, tash_thresh, lc_thresh in configs:
        config = Config()
        config.rnnt_weight = 0.0
        config.tashkeel_threshold = tash_thresh
        config.low_confidence_threshold = lc_thresh

        initial_book = Book.from_sentence(samples[0]["text"])
        pipeline = I3rabPipeline(initial_book, config)

        rng = np.random.default_rng(42)
        t0 = time.time()
        r = run_tests(pipeline, samples, config, rng, fraction=0.3)
        elapsed = time.time() - t0

        print(f"  {name:<16s}  {r['fp']:4d}  {r['fp_rate']:5.2f}%  "
              f"{r['recall_rate']:5.1f}%  {r['recall_det']:4d}/{r['recall_scored']:<5d}  "
              f"{elapsed:.0f}s")


if __name__ == "__main__":
    main()
