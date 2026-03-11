#!/usr/bin/env python3
"""Evaluate false positive rate on ClArTTS test set.

ClArTTS contains correctly-read diacritized Arabic. Every word should be
judged CORRECT or PAUSAL_OK.  Any WRONG_IRAB or WRONG_TASHKEEL is a
**false positive** — the system incorrectly flagged a correct reading.

Usage:
    python eval_clartts.py                     # basic evaluation
    python eval_clartts.py --max-samples 20    # quick test
    python eval_clartts.py --joint             # test joint lattice scoring
    python eval_clartts.py --noise 15          # add MUSAN noise at 15dB SNR
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent))

from i3rab.config import Config
from i3rab.pipeline import I3rabPipeline as Pipeline


def load_clartts_test(max_samples: int = 0):
    """Load ClArTTS test set from HuggingFace."""
    from datasets import load_dataset

    print("Loading ClArTTS test set...")
    ds = load_dataset("MBZUAI/ClArTTS", split="test")
    print(f"  {len(ds)} samples available")

    if max_samples > 0:
        ds = ds.select(range(min(max_samples, len(ds))))
        print(f"  Using first {len(ds)} samples")

    samples = []
    for item in ds:
        text = item["text"].strip()
        if not text:
            continue
        # Check it has diacritics
        if not any("\u064B" <= ch <= "\u0652" for ch in text):
            continue

        audio = np.array(item["audio"], dtype=np.float32)
        orig_sr = item["sampling_rate"]

        # Resample to 16kHz if needed
        if orig_sr != 16000:
            from scipy.signal import resample as scipy_resample
            num_samples = int(len(audio) * 16000 / orig_sr)
            audio = scipy_resample(audio, num_samples).astype(np.float32)

        # Normalize
        peak = np.abs(audio).max()
        if peak > 0:
            audio = audio / peak * 0.95

        duration = len(audio) / 16000
        if duration < 0.5 or duration > 20.0:
            continue

        samples.append({
            "text": text,
            "audio": audio,
            "duration": duration,
        })

    print(f"  {len(samples)} valid samples after filtering")
    return samples


def add_musan_noise(audio: np.ndarray, snr_db: float) -> np.ndarray:
    """Add simple white noise at specified SNR (no MUSAN download needed)."""
    signal_power = np.mean(audio ** 2) + 1e-10
    noise = np.random.randn(len(audio)).astype(np.float32)
    noise_power = np.mean(noise ** 2)
    scale = np.sqrt(signal_power / (noise_power * (10 ** (snr_db / 10))))
    mixed = audio + scale * noise
    peak = np.abs(mixed).max()
    if peak > 0.95:
        mixed = mixed * (0.95 / peak)
    return mixed


def evaluate_sample(pipeline, text, audio, config):
    """Run pipeline on a single sample and return per-word results."""
    from i3rab.book import Book
    from i3rab.tracker import PositionTracker
    book = Book.from_text(text)
    pipeline.book = book
    pipeline.tracker = PositionTracker(book, config)
    result = pipeline.evaluate_pcd_live(audio)
    return result


def main():
    parser = argparse.ArgumentParser(description="Evaluate false positive rate on ClArTTS")
    parser.add_argument("--max-samples", type=int, default=0,
                        help="Max samples to test (0 = all)")
    parser.add_argument("--joint", action="store_true",
                        help="Use joint lattice scoring instead of per-word")
    parser.add_argument("--noise", type=float, default=0,
                        help="Add white noise at this SNR (dB). 0 = no noise")
    parser.add_argument("--verbose", action="store_true",
                        help="Print per-sample details")
    args = parser.parse_args()

    # Load samples
    samples = load_clartts_test(args.max_samples)
    if not samples:
        print("No samples loaded!")
        return

    # Init pipeline with first sample's text
    from i3rab.book import Book
    config = Config()
    if args.joint:
        config.use_joint_scoring = True
    initial_book = Book.from_text(samples[0]["text"])
    pipeline = Pipeline(initial_book, config)
    pipeline.load_pcd()

    # Evaluate
    total_words = 0
    false_positives = {"irab": 0, "tashkeel": 0, "wrong": 0, "missing": 0}
    correct = 0
    pausal_ok = 0
    skipped_samples = 0
    errors_detail = []

    t0 = time.time()

    for si, sample in enumerate(samples):
        text = sample["text"]
        audio = sample["audio"]

        if args.noise > 0:
            audio = add_musan_noise(audio, args.noise)

        try:
            result = evaluate_sample(pipeline, text, audio, config)
        except Exception as e:
            skipped_samples += 1
            if args.verbose:
                print(f"  [{si+1}] ERROR: {e}")
            continue

        if not result or not result.get("scored_words"):
            skipped_samples += 1
            continue

        scored = result.get("scored_words", [])
        for w in scored:
            total_words += 1
            kind = w["kind"]
            if kind == "correct":
                correct += 1
            elif kind == "pausal_ok":
                pausal_ok += 1
            elif kind in ("irab", "tashkeel", "wrong"):
                false_positives[kind] += 1
                detail = {
                    "sample": si, "kind": kind,
                    "ref": w["ref_word"], "hyp": w.get("hyp_word"),
                    "det_case": w.get("detected_case"),
                    "exp_case": w.get("expected_case"),
                    "confidence": w.get("confidence"),
                    "diffs": w.get("haraka_diffs"),
                }
                errors_detail.append(detail)
                if args.verbose:
                    print(f"  FP [{kind}]: ref={w['ref_word']} hyp={w.get('hyp_word')} "
                          f"det={w.get('detected_case')} exp={w.get('expected_case')} "
                          f"conf={w.get('confidence')}")
            elif kind == "missing":
                false_positives["missing"] += 1

        if args.verbose and (si + 1) % 10 == 0:
            elapsed = time.time() - t0
            print(f"  [{si+1}/{len(samples)}] {elapsed:.1f}s — "
                  f"{total_words} words, {sum(false_positives.values())} FP")

    elapsed = time.time() - t0
    total_fp = sum(false_positives.values())
    fp_rate = total_fp / total_words * 100 if total_words > 0 else 0

    print(f"\n{'='*60}")
    print(f"ClArTTS False Positive Evaluation")
    print(f"{'='*60}")
    print(f"Samples: {len(samples) - skipped_samples}/{len(samples)} "
          f"({skipped_samples} skipped)")
    print(f"Total words: {total_words}")
    print(f"Correct: {correct} ({correct/total_words*100:.1f}%)")
    print(f"Pausal OK: {pausal_ok} ({pausal_ok/total_words*100:.1f}%)")
    print(f"False positives: {total_fp} ({fp_rate:.2f}%)")
    print(f"  Wrong i3rab:    {false_positives['irab']}")
    print(f"  Wrong tashkeel: {false_positives['tashkeel']}")
    print(f"  Wrong word:     {false_positives['wrong']}")
    print(f"  Missing:        {false_positives['missing']}")
    print(f"Time: {elapsed:.1f}s ({elapsed/max(1,len(samples)-skipped_samples):.2f}s/sample)")
    if args.joint:
        print(f"Scoring: JOINT lattice (beam search)")
    else:
        print(f"Scoring: INDEPENDENT (per-word)")
    if args.noise > 0:
        print(f"Noise: {args.noise} dB SNR")

    # Show error details
    if errors_detail:
        print(f"\n--- False Positive Details (first 20) ---")
        for err in errors_detail[:20]:
            if err["kind"] == "wrong_irab":
                print(f"  IRAB: {err['ref']} → {err['hyp']} "
                      f"(expected={err['exp_case']}, detected={err['det_case']}, "
                      f"conf={err['confidence']})")
            elif err["kind"] == "wrong_tashkeel":
                diffs_str = ""
                if err.get("diffs"):
                    diffs_str = "; ".join(
                        f"{d['letter']}@{d['position']}: {d['expected']}→{d['got']}"
                        for d in err["diffs"]
                    )
                print(f"  TASHKEEL: {err['ref']} → {err['hyp']} [{diffs_str}]")

    # Save results
    results = {
        "total_words": total_words,
        "correct": correct,
        "pausal_ok": pausal_ok,
        "false_positives": false_positives,
        "fp_rate_pct": round(fp_rate, 3),
        "scoring": "joint" if args.joint else "independent",
        "noise_snr": args.noise,
        "samples_evaluated": len(samples) - skipped_samples,
        "elapsed_seconds": round(elapsed, 1),
        "errors": errors_detail,
    }
    out_path = Path("eval_clartts_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
