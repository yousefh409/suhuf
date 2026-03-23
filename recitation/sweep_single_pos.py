#!/usr/bin/env python3
"""Quick sweep of single-position tashkeel threshold on small sample."""

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


def load_clartts_samples(max_samples=30):
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

    for si, sample in enumerate(samples):
        text, audio = sample["text"], sample["audio"]
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

        # Recall
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

    fp_rate = fp_count / fp_total * 100 if fp_total > 0 else 0
    recall = recall_det / recall_scored * 100 if recall_scored > 0 else 0
    return fp_count, fp_total, fp_rate, recall_det, recall_scored, recall, skipped


def main():
    samples = load_clartts_samples(30)
    print(f"Loaded {len(samples)} samples\n")

    # Test different single-position tashkeel thresholds
    # We patch the pipeline code behavior through config
    thresholds = [2.0, 5.0, 8.0, 10.0, 12.0, 15.0, 20.0]

    print(f"{'Thresh':>7s}  {'FP':>4s}  {'FP%':>6s}  {'Recall':>7s}  {'Det/Scored':>12s}  {'Skip':>4s}  {'Time':>5s}")
    print("-" * 60)

    for thresh in thresholds:
        config = Config()
        config.rnnt_weight = 0.0
        # We encode the single-pos threshold in a custom attribute
        config.single_pos_tashkeel_threshold = thresh

        initial_book = Book.from_sentence(samples[0]["text"])
        pipeline = I3rabPipeline(initial_book, config)

        t0 = time.time()
        fp, fp_total, fp_rate, rec_det, rec_scored, recall, skip = run_eval(
            pipeline, samples, config
        )
        elapsed = time.time() - t0

        print(f"  {thresh:5.1f}  {fp:4d}  {fp_rate:5.2f}%  "
              f"{recall:5.1f}%  {rec_det:4d}/{rec_scored:<5d}  {skip:4d}  {elapsed:.0f}s")


if __name__ == "__main__":
    main()
