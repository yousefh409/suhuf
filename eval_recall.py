#!/usr/bin/env python3
"""Evaluate error detection recall on ClArTTS test set.

Injects three types of errors into the reference text while keeping the
audio unchanged (audio is a correct reading):

1. IRAB errors     — swap case ending (e.g., nom→acc on final letter)
2. TASHKEEL errors — swap an internal vowel (e.g., fatha→kasra mid-word)
3. WRONG WORD      — replace word with a different word from the dataset

The system should detect each as wrong_irab, wrong_tashkeel, or wrong_word.

Usage:
    python eval_recall.py                     # all error types
    python eval_recall.py --max-samples 30    # quick test
    python eval_recall.py --verbose           # show each miss
"""

import argparse
import json
import random
import sys
import time
import unicodedata
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from i3rab.config import Config
from i3rab.pipeline import I3rabPipeline as Pipeline
from i3rab.models import CASE_HARAKAT, HARAKAT

HARAKA_TO_CASE = {v: k for k, v in CASE_HARAKAT.items()}
DEFINITE_CASES = {"nom": "\u064F", "acc": "\u064E", "gen": "\u0650"}
VOWELS = {"\u064E", "\u064F", "\u0650"}  # fatha, damma, kasra
VOWEL_NAMES = {"\u064E": "fatha", "\u064F": "damma", "\u0650": "kasra"}


def strip_harakat(text):
    return "".join(ch for ch in text if ch not in HARAKAT)


# ── Injection helpers ───────────────────────────────────────────────


def inject_irab_error(word, rng):
    """Swap the final case ending. Returns (modified, info) or (None, None)."""
    base_chars = [(i, ch) for i, ch in enumerate(word) if ch not in HARAKAT]
    if not base_chars:
        return None, None
    last_pos, last_char = base_chars[-1]
    if last_char in ("\u0629", "\u0627"):  # ة, ا
        return None, None

    # Find current case
    marks = []
    for j in range(last_pos + 1, len(word)):
        if word[j] in HARAKAT:
            marks.append(word[j])
        else:
            break
    orig_case = None
    for m in marks:
        if m in HARAKA_TO_CASE:
            orig_case = HARAKA_TO_CASE[m]
            break
    if orig_case not in DEFINITE_CASES:
        return None, None

    target_case = rng.choice([c for c in DEFINITE_CASES if c != orig_case])
    target_haraka = DEFINITE_CASES[target_case]

    prefix = word[:last_pos + 1]
    new_marks = []
    replaced = False
    text_after = ""
    for j in range(last_pos + 1, len(word)):
        if word[j] in HARAKAT:
            if word[j] == "\u0651":
                new_marks.append(word[j])
            elif word[j] in HARAKA_TO_CASE and not replaced:
                new_marks.append(target_haraka)
                replaced = True
            else:
                new_marks.append(word[j])
        else:
            text_after = word[j:]
            break
    if not replaced:
        new_marks.append(target_haraka)

    modified = unicodedata.normalize("NFC", prefix + "".join(new_marks) + text_after)
    if modified == word:
        return None, None
    return modified, {"type": "irab", "orig_case": orig_case, "target_case": target_case}


def inject_tashkeel_error(word, rng):
    """Swap an internal (non-final) vowel mark. Returns (modified, info) or (None, None)."""
    base_chars = [(i, ch) for i, ch in enumerate(word) if ch not in HARAKAT]
    if len(base_chars) < 3:
        return None, None

    # Find internal letters (not first, not last) that have a vowel mark
    candidates = []
    for bi in range(1, len(base_chars) - 1):
        char_pos = base_chars[bi][0]
        # Collect marks after this base char
        marks_after = []
        for j in range(char_pos + 1, len(word)):
            if word[j] in HARAKAT:
                marks_after.append((j, word[j]))
            else:
                break
        # Find a vowel mark (not shadda)
        for mark_pos, mark_char in marks_after:
            if mark_char in VOWELS:
                candidates.append((bi, mark_pos, mark_char))
                break

    if not candidates:
        return None, None

    bi, mark_pos, orig_vowel = rng.choice(candidates)
    target_vowel = rng.choice([v for v in VOWELS if v != orig_vowel])

    chars = list(word)
    chars[mark_pos] = target_vowel
    modified = unicodedata.normalize("NFC", "".join(chars))
    if modified == word:
        return None, None
    return modified, {
        "type": "tashkeel",
        "letter_idx": bi,
        "orig_vowel": VOWEL_NAMES.get(orig_vowel, "?"),
        "target_vowel": VOWEL_NAMES.get(target_vowel, "?"),
    }


def inject_wrong_word(word, word_pool, rng):
    """Replace with a different word of similar length. Returns (modified, info) or (None, None)."""
    base = strip_harakat(word)
    if len(base) <= 2:
        return None, None
    # Find a word with different base but similar length
    candidates = [w for w in word_pool
                  if strip_harakat(w) != base
                  and abs(len(strip_harakat(w)) - len(base)) <= 2
                  and len(strip_harakat(w)) >= 3]
    if not candidates:
        return None, None
    replacement = rng.choice(candidates)
    return replacement, {"type": "wrong_word", "replacement_base": strip_harakat(replacement)}


def inject_all_errors(text, word_pool, fraction=0.3, seed=42):
    """Inject a mix of irab, tashkeel, and wrong_word errors.

    Each eligible word gets at most one error type.
    Error type distribution: ~40% irab, ~40% tashkeel, ~20% wrong_word.
    """
    rng = random.Random(seed)
    words = text.split()
    injected = []

    for wi, word in enumerate(words):
        base = strip_harakat(word)
        if len(base) <= 2:
            continue
        if rng.random() > fraction:
            continue

        # Pick error type
        roll = rng.random()
        if roll < 0.4:
            error_type = "irab"
        elif roll < 0.8:
            error_type = "tashkeel"
        else:
            error_type = "wrong_word"

        modified, info = None, None
        if error_type == "irab":
            modified, info = inject_irab_error(word, rng)
        if error_type == "tashkeel" or (error_type == "irab" and modified is None):
            # Fallback to tashkeel if irab not possible
            modified, info = inject_tashkeel_error(word, rng)
        if error_type == "wrong_word" or (modified is None):
            # Fallback to wrong_word
            modified, info = inject_wrong_word(word, word_pool, rng)

        if modified and info:
            injected.append({
                "word_idx": wi,
                "original": word,
                "modified": modified,
                **info,
            })
            words[wi] = modified

    return " ".join(words), injected


# ── Data loading ────────────────────────────────────────────────────


def load_clartts_test(max_samples=0):
    from datasets import load_dataset
    print("Loading ClArTTS test set...")
    ds = load_dataset("MBZUAI/ClArTTS", split="test")
    if max_samples > 0:
        ds = ds.select(range(min(max_samples, len(ds))))
    samples = []
    for item in ds:
        text = item["text"].strip()
        if not text or not any("\u064B" <= ch <= "\u0652" for ch in text):
            continue
        audio = np.array(item["audio"], dtype=np.float32)
        orig_sr = item["sampling_rate"]
        if orig_sr != 16000:
            from scipy.signal import resample as scipy_resample
            n = int(len(audio) * 16000 / orig_sr)
            audio = scipy_resample(audio, n).astype(np.float32)
        peak = np.abs(audio).max()
        if peak > 0:
            audio = audio / peak * 0.95
        dur = len(audio) / 16000
        if dur < 0.5 or dur > 20.0:
            continue
        samples.append({"text": text, "audio": audio})
    print(f"  {len(samples)} valid samples")
    return samples


def add_noise(audio, snr_db):
    sig_pow = np.mean(audio ** 2) + 1e-10
    noise = np.random.randn(len(audio)).astype(np.float32)
    n_pow = np.mean(noise ** 2)
    scale = np.sqrt(sig_pow / (n_pow * (10 ** (snr_db / 10))))
    mixed = audio + scale * noise
    peak = np.abs(mixed).max()
    if peak > 0.95:
        mixed = mixed * (0.95 / peak)
    return mixed


# ── Main ────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Evaluate error detection recall")
    parser.add_argument("--max-samples", type=int, default=0)
    parser.add_argument("--noise", type=float, default=0)
    parser.add_argument("--fraction", type=float, default=0.4,
                        help="Fraction of eligible words to inject errors into")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    samples = load_clartts_test(args.max_samples)
    if not samples:
        return

    # Build word pool for wrong_word injection
    all_words_pool = []
    for s in samples:
        all_words_pool.extend(s["text"].split())
    # Deduplicate
    all_words_pool = list(set(all_words_pool))
    print(f"  Word pool: {len(all_words_pool)} unique words")

    from i3rab.book import Book
    from i3rab.tracker import PositionTracker

    config = Config()
    initial_book = Book.from_text(samples[0]["text"])
    pipeline = Pipeline(initial_book, config)
    pipeline.load_pcd()

    # Per-type counters
    stats = {}
    for etype in ("irab", "tashkeel", "wrong_word"):
        stats[etype] = {
            "injected": 0,
            "detected": 0,
            "missed": 0,
            "missed_pausal": 0,
            "missed_low_conf": 0,
            "missed_ctc_wrong": 0,
            "not_scored": 0,
        }
    total_clean = 0
    fp_on_clean = 0
    skipped = 0

    t0 = time.time()

    for si, sample in enumerate(samples):
        original_text = sample["text"]
        audio = sample["audio"]
        if args.noise > 0:
            audio = add_noise(audio, args.noise)

        modified_text, injections = inject_all_errors(
            original_text, all_words_pool,
            fraction=args.fraction, seed=si * 1000,
        )

        if not injections:
            continue

        try:
            book = Book.from_text(modified_text)
            pipeline.book = book
            pipeline.tracker = PositionTracker(book, config)
            result = pipeline.evaluate_pcd_live(audio)
        except Exception as e:
            skipped += 1
            if args.verbose:
                print(f"  [{si+1}] ERROR: {e}")
            continue

        if not result or not result.get("scored_words"):
            skipped += 1
            continue

        scored = result["scored_words"]
        scored_by_idx = {sw["index"]: sw for sw in scored}

        for inj in injections:
            etype = inj["type"]
            stats[etype]["injected"] += 1
            wi = inj["word_idx"]
            sw = scored_by_idx.get(wi)

            if sw is None or sw["kind"] == "missing":
                stats[etype]["not_scored"] += 1
                continue

            kind = sw["kind"]

            # Did we detect an error?
            # DiffKind values: "irab", "tashkeel", "wrong" (not "wrong_irab" etc.)
            is_detected = kind in ("irab", "tashkeel", "wrong")

            if is_detected:
                stats[etype]["detected"] += 1
                if args.verbose:
                    print(f"  CAUGHT [{etype}]: {inj['original']} → {inj['modified']} "
                          f"as {kind} (conf={sw.get('confidence')})")
            else:
                stats[etype]["missed"] += 1
                reason = ""
                if kind == "pausal_ok":
                    stats[etype]["missed_pausal"] += 1
                    reason = "pausal"
                elif sw.get("confidence") == "low":
                    stats[etype]["missed_low_conf"] += 1
                    reason = "low_conf"
                else:
                    stats[etype]["missed_ctc_wrong"] += 1
                    reason = "ctc_wrong"
                if args.verbose:
                    print(f"  MISSED [{etype}]: {inj['original']} → {inj['modified']} "
                          f"verdict={kind} reason={reason} conf={sw.get('confidence')}")

        # Track FP on non-injected words
        injected_idxs = {inj["word_idx"] for inj in injections}
        for sw in scored:
            if sw["index"] not in injected_idxs:
                total_clean += 1
                if sw["kind"] in ("irab", "tashkeel", "wrong"):
                    fp_on_clean += 1

        if args.verbose and (si + 1) % 20 == 0:
            elapsed = time.time() - t0
            total_det = sum(s["detected"] for s in stats.values())
            total_inj = sum(s["injected"] for s in stats.values())
            print(f"  [{si+1}/{len(samples)}] {elapsed:.1f}s — "
                  f"injected={total_inj}, caught={total_det}")

    elapsed = time.time() - t0
    fp_rate = fp_on_clean / total_clean * 100 if total_clean > 0 else 0

    print(f"\n{'='*60}")
    print(f"Error Detection Recall Evaluation")
    print(f"{'='*60}")

    for etype in ("irab", "tashkeel", "wrong_word"):
        s = stats[etype]
        scored = s["detected"] + s["missed"]
        recall = s["detected"] / scored * 100 if scored > 0 else 0
        print(f"\n  {etype.upper()} errors:")
        print(f"    Injected:  {s['injected']}")
        print(f"    Scored:    {scored}")
        print(f"    Detected:  {s['detected']}")
        print(f"    Missed:    {s['missed']}")
        if s["missed"] > 0:
            print(f"      pausal:   {s['missed_pausal']}")
            print(f"      low_conf: {s['missed_low_conf']}")
            print(f"      ctc_wrong:{s['missed_ctc_wrong']}")
        print(f"    Not scored: {s['not_scored']}")
        print(f"    Recall:    {s['detected']}/{scored} ({recall:.1f}%)")

    total_injected = sum(s["injected"] for s in stats.values())
    total_scored = sum(s["detected"] + s["missed"] for s in stats.values())
    total_detected = sum(s["detected"] for s in stats.values())
    overall_recall = total_detected / total_scored * 100 if total_scored > 0 else 0

    print(f"\n  OVERALL:")
    print(f"    Injected:  {total_injected}")
    print(f"    Scored:    {total_scored}")
    print(f"    Detected:  {total_detected}")
    print(f"    Recall:    {total_detected}/{total_scored} ({overall_recall:.1f}%)")
    print(f"")
    print(f"Non-injected words: {total_clean}")
    print(f"  False positives:  {fp_on_clean} ({fp_rate:.2f}%)")
    print(f"Time: {elapsed:.1f}s")
    if args.noise > 0:
        print(f"Noise: {args.noise} dB SNR")
    print(f"Skipped samples: {skipped}")

    # Save
    results = {
        "per_type": {k: dict(v) for k, v in stats.items()},
        "total_injected": total_injected,
        "total_scored": total_scored,
        "total_detected": total_detected,
        "overall_recall_pct": round(overall_recall, 1),
        "total_clean": total_clean,
        "fp_on_clean": fp_on_clean,
        "fp_rate_pct": round(fp_rate, 3),
        "noise_snr": args.noise,
        "fraction": args.fraction,
        "elapsed_seconds": round(elapsed, 1),
    }
    out_path = Path("eval_recall_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
