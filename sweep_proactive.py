#!/usr/bin/env python3
"""Sweep proactive tashkeel segment+FS thresholds."""

import sys, time
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from i3rab.config import Config
from i3rab.pipeline import I3rabPipeline
from i3rab.book import Book
from i3rab.tracker import PositionTracker
from eval_recall import inject_all_errors


def load_clartts_samples(max_samples=40):
    from datasets import load_dataset
    ds = load_dataset("MBZUAI/ClArTTS", split="test")
    samples = []
    for item in ds:
        text = item["text"].strip()
        if not text or not any("\u064B" <= ch <= "\u0652" for ch in text):
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
        samples.append({"text": text, "audio": audio})
        if len(samples) >= max_samples:
            break
    return samples


def run_eval(pipeline, samples, config, fraction=0.3, seed=42):
    word_pool = list(set(w for s in samples for w in s["text"].split()))
    fp_total = fp_count = recall_scored = recall_det = skipped = 0
    tash_scored = tash_det = 0

    for si, sample in enumerate(samples):
        text, audio = sample["text"], sample["audio"]
        # FP test
        book = Book.from_sentence(text)
        pipeline.book = book
        pipeline.tracker = PositionTracker(book, config)
        try:
            result = pipeline.evaluate_pcd_live(audio)
        except Exception:
            skipped += 1
            continue
        if not result or not result.get("scored_words"):
            skipped += 1
            continue
        for w in result["scored_words"]:
            fp_total += 1
            if w["kind"] in ("irab", "tashkeel", "wrong"):
                fp_count += 1

        # Recall test
        mod_text, injections = inject_all_errors(text, word_pool, fraction, seed + si)
        book2 = Book.from_sentence(mod_text)
        pipeline.book = book2
        pipeline.tracker = PositionTracker(book2, config)
        try:
            result2 = pipeline.evaluate_pcd_live(audio)
        except Exception:
            continue
        if not result2 or not result2.get("scored_words"):
            continue
        scored_kinds = {sw["index"]: sw["kind"] for sw in result2["scored_words"]}
        for inj in injections:
            idx = inj["word_idx"]
            if idx in scored_kinds:
                recall_scored += 1
                if scored_kinds[idx] in ("irab", "tashkeel", "wrong"):
                    recall_det += 1
                if inj["type"] == "tashkeel":
                    tash_scored += 1
                    if scored_kinds[idx] in ("irab", "tashkeel", "wrong"):
                        tash_det += 1

    fp_rate = fp_count / fp_total * 100 if fp_total > 0 else 0
    recall = recall_det / recall_scored * 100 if recall_scored > 0 else 0
    tash_recall = tash_det / tash_scored * 100 if tash_scored > 0 else 0
    return {
        "fp": fp_count, "fp_total": fp_total, "fp_rate": fp_rate,
        "recall_det": recall_det, "recall_scored": recall_scored,
        "recall": recall, "tash_det": tash_det, "tash_scored": tash_scored,
        "tash_recall": tash_recall, "skipped": skipped,
    }


def main():
    samples = load_clartts_samples(40)
    print(f"Loaded {len(samples)} samples\n")

    # Sweep segment threshold x FS threshold
    configs = [
        ("seg=1.0 fs=0.0", 1.0, 0.0),
        ("seg=1.0 fs=0.5", 1.0, 0.5),
        ("seg=1.0 fs=1.0", 1.0, 1.0),
        ("seg=1.5 fs=0.0", 1.5, 0.0),
        ("seg=1.5 fs=0.5", 1.5, 0.5),
        ("seg=1.5 fs=1.0", 1.5, 1.0),
        ("seg=2.0 fs=0.0", 2.0, 0.0),
        ("seg=2.0 fs=0.5", 2.0, 0.5),
        ("seg=2.0 fs=1.0", 2.0, 1.0),
        ("seg=2.5 fs=0.0", 2.5, 0.0),
        ("seg=3.0 fs=0.0", 3.0, 0.0),
    ]

    print(f"{'Config':<18s}  {'FP':>4s}  {'FP%':>6s}  {'All%':>6s}  {'Tash%':>6s}  {'T-det/scr':>10s}  {'Skip':>4s}  {'Time':>5s}")
    print("-" * 75)

    for name, seg_thresh, fs_thresh in configs:
        config = Config()
        config.rnnt_weight = 0.0
        config.proactive_tashkeel_threshold = seg_thresh
        config.proactive_fs_threshold = fs_thresh

        initial_book = Book.from_sentence(samples[0]["text"])
        pipeline = I3rabPipeline(initial_book, config)

        t0 = time.time()
        r = run_eval(pipeline, samples, config)
        elapsed = time.time() - t0

        print(f"  {name:<16s}  {r['fp']:4d}  {r['fp_rate']:5.2f}%  "
              f"{r['recall']:5.1f}%  {r['tash_recall']:5.1f}%  "
              f"{r['tash_det']:4d}/{r['tash_scored']:<5d}  {r['skipped']:4d}  {elapsed:.0f}s")


if __name__ == "__main__":
    main()
