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
    python eval_recall.py --exclude-final     # skip sentence-final words
    python eval_recall.py --tashkeel-on       # enable tashkeel detection
"""

import argparse
from collections import defaultdict
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
VOWEL_FROM_NAME = {v: k for k, v in VOWEL_NAMES.items()}


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

    orig_haraka = DEFINITE_CASES[orig_case]
    orig_vowel_name = VOWEL_NAMES.get(orig_haraka, "?")
    target_vowel_name = VOWEL_NAMES.get(target_haraka, "?")

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
    return modified, {
        "type": "irab",
        "orig_case": orig_case,
        "target_case": target_case,
        "orig_vowel": orig_vowel_name,
        "target_vowel": target_vowel_name,
    }


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


def inject_all_errors(text, word_pool, fraction=0.3, seed=42, exclude_final=False):
    """Inject a mix of irab, tashkeel, and wrong_word errors.

    Each eligible word gets at most one error type.
    Error type distribution: ~40% irab, ~40% tashkeel, ~20% wrong_word.
    """
    rng = random.Random(seed)
    words = text.split()
    injected = []

    last_idx = len(words) - 1

    for wi, word in enumerate(words):
        is_final = (wi == last_idx)
        if exclude_final and is_final:
            continue

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
            info["is_final"] = is_final
            injected.append({
                "word_idx": wi,
                "original": word,
                "modified": modified,
                **info,
            })
            words[wi] = modified

    return " ".join(words), injected


# ── Data loading ────────────────────────────────────────────────────


def load_clartts_test(max_samples=0, split="test"):
    from datasets import load_dataset
    print(f"Loading ClArTTS {split} set...")
    ds = load_dataset("MBZUAI/ClArTTS", split=split)
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


# ── Confusion tracking ─────────────────────────────────────────────


def confusion_key(orig_vowel, target_vowel):
    """Canonical key for a vowel confusion pair."""
    return f"{orig_vowel}→{target_vowel}"


# ── Main ────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Evaluate error detection recall")
    parser.add_argument("--max-samples", type=int, default=0)
    parser.add_argument("--noise", type=float, default=0)
    parser.add_argument("--fraction", type=float, default=0.4,
                        help="Fraction of eligible words to inject errors into")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--exclude-final", action="store_true",
                        help="Skip sentence-final words (avoids pausal misses)")
    parser.add_argument("--tashkeel-on", action="store_true",
                        help="Enable tashkeel detection in PCD pipeline")
    parser.add_argument("--split", type=str, default="test",
                        help="ClArTTS split: test, train, or all")
    parser.add_argument("--ssl-model", type=str, default="",
                        help="Path to SSL CTC model dir (use instead of NeMo PCD)")
    parser.add_argument("--low-conf-thresh", type=float, default=0,
                        help="Override low_confidence_threshold (0 = use default)")
    parser.add_argument("--ssl-training-sr", type=int, default=0,
                        help="Override ssl_training_sr (0 = use default)")
    args = parser.parse_args()

    if args.split == "all":
        samples_train = load_clartts_test(0, split="train")
        samples_test = load_clartts_test(0, split="test")
        samples = samples_train + samples_test
        if args.max_samples > 0:
            samples = samples[:args.max_samples]
    else:
        samples = load_clartts_test(args.max_samples, split=args.split)
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
    if args.ssl_model:
        config.ssl_model_dir = args.ssl_model
    if args.low_conf_thresh > 0:
        config.low_confidence_threshold = args.low_conf_thresh
    if args.ssl_training_sr > 0:
        config.ssl_training_sr = args.ssl_training_sr
    if args.tashkeel_on:
        config.pcd_tashkeel_detection = True
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
            # Separate final vs non-final
            "final_injected": 0,
            "final_detected": 0,
            "final_missed": 0,
            "nonfinal_injected": 0,
            "nonfinal_detected": 0,
            "nonfinal_missed": 0,
        }
    total_clean = 0
    fp_on_clean = 0
    skipped = 0

    # Confusion matrix: tracks which vowel swaps get missed
    # Key: (error_type, "orig_vowel→target_vowel"), Value: {"detected": N, "missed": N}
    confusion = defaultdict(lambda: {"detected": 0, "missed": 0})

    # Detailed miss log for JSON output
    miss_log = []
    # FP log — clean words that got falsely flagged
    fp_log = []

    t0 = time.time()

    for si, sample in enumerate(samples):
        original_text = sample["text"]
        audio = sample["audio"]
        if args.noise > 0:
            audio = add_noise(audio, args.noise)

        modified_text, injections = inject_all_errors(
            original_text, all_words_pool,
            fraction=args.fraction, seed=si * 1000,
            exclude_final=args.exclude_final,
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
            is_final = inj.get("is_final", False)
            stats[etype]["injected"] += 1
            if is_final:
                stats[etype]["final_injected"] += 1
            else:
                stats[etype]["nonfinal_injected"] += 1

            wi = inj["word_idx"]
            sw = scored_by_idx.get(wi)

            if sw is None or sw["kind"] == "missing":
                stats[etype]["not_scored"] += 1
                continue

            kind = sw["kind"]

            # Build confusion key for vowel-based errors
            ckey = None
            if etype in ("irab", "tashkeel"):
                orig_v = inj.get("orig_vowel", "?")
                tgt_v = inj.get("target_vowel", "?")
                ckey = confusion_key(orig_v, tgt_v)

            # Did we detect an error?
            is_detected = kind in ("irab", "tashkeel", "wrong")

            if is_detected:
                stats[etype]["detected"] += 1
                if is_final:
                    stats[etype]["final_detected"] += 1
                else:
                    stats[etype]["nonfinal_detected"] += 1
                if ckey:
                    confusion[(etype, ckey)]["detected"] += 1
                if args.verbose:
                    print(f"  CAUGHT [{etype}]: {inj['original']} → {inj['modified']} "
                          f"as {kind} (conf={sw.get('confidence')})"
                          f"{' [FINAL]' if is_final else ''}")
            else:
                stats[etype]["missed"] += 1
                if is_final:
                    stats[etype]["final_missed"] += 1
                else:
                    stats[etype]["nonfinal_missed"] += 1
                if ckey:
                    confusion[(etype, ckey)]["missed"] += 1

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

                miss_log.append({
                    "sample_idx": si,
                    "error_type": etype,
                    "original": inj["original"],
                    "modified": inj["modified"],
                    "verdict": kind,
                    "reason": reason,
                    "is_final": is_final,
                    "orig_vowel": inj.get("orig_vowel"),
                    "target_vowel": inj.get("target_vowel"),
                    "confidence": sw.get("confidence"),
                })

                if args.verbose:
                    vowel_info = ""
                    if ckey:
                        vowel_info = f" ({ckey})"
                    print(f"  MISSED [{etype}]: {inj['original']} → {inj['modified']} "
                          f"verdict={kind} reason={reason}{vowel_info}"
                          f"{' [FINAL]' if is_final else ''}")

        # Track FP on non-injected words
        injected_idxs = {inj["word_idx"] for inj in injections}
        orig_words = original_text.split()
        for sw in scored:
            if sw["index"] not in injected_idxs:
                total_clean += 1
                if sw["kind"] in ("irab", "tashkeel", "wrong"):
                    fp_on_clean += 1
                    orig_word = orig_words[sw["index"]] if sw["index"] < len(orig_words) else "?"
                    fp_log.append({
                        "sample_idx": si,
                        "word_idx": sw["index"],
                        "word": orig_word,
                        "fp_kind": sw["kind"],
                        "confidence": sw.get("confidence"),
                        "ref_word": sw.get("ref_word", ""),
                        "hyp_word": sw.get("hyp_word", ""),
                    })
                    if args.verbose:
                        print(f"  FP [{sw['kind']}]: '{orig_word}' flagged as {sw['kind']} "
                              f"(conf={sw.get('confidence')})")

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
    if args.exclude_final:
        print(f"  (sentence-final words EXCLUDED from injection)")
    if args.tashkeel_on:
        print(f"  (tashkeel detection ENABLED)")
    print(f"{'='*60}")

    for etype in ("irab", "tashkeel", "wrong_word"):
        s = stats[etype]
        scored_count = s["detected"] + s["missed"]
        recall = s["detected"] / scored_count * 100 if scored_count > 0 else 0

        # Non-final only recall (excludes pausal ceiling)
        nf_scored = s["nonfinal_detected"] + s["nonfinal_missed"]
        nf_recall = s["nonfinal_detected"] / nf_scored * 100 if nf_scored > 0 else 0

        print(f"\n  {etype.upper()} errors:")
        print(f"    Injected:  {s['injected']}")
        print(f"    Scored:    {scored_count}")
        print(f"    Detected:  {s['detected']}")
        print(f"    Missed:    {s['missed']}")
        if s["missed"] > 0:
            print(f"      pausal:    {s['missed_pausal']}")
            print(f"      low_conf:  {s['missed_low_conf']}")
            print(f"      ctc_wrong: {s['missed_ctc_wrong']}")
        print(f"    Not scored: {s['not_scored']}")
        print(f"    Recall (all):       {s['detected']}/{scored_count} ({recall:.1f}%)")
        if nf_scored > 0 and nf_scored != scored_count:
            print(f"    Recall (non-final): {s['nonfinal_detected']}/{nf_scored} ({nf_recall:.1f}%)")

    # Overall stats
    total_injected = sum(s["injected"] for s in stats.values())
    total_scored = sum(s["detected"] + s["missed"] for s in stats.values())
    total_detected = sum(s["detected"] for s in stats.values())
    overall_recall = total_detected / total_scored * 100 if total_scored > 0 else 0

    total_nf_scored = sum(s["nonfinal_detected"] + s["nonfinal_missed"] for s in stats.values())
    total_nf_detected = sum(s["nonfinal_detected"] for s in stats.values())
    nf_overall = total_nf_detected / total_nf_scored * 100 if total_nf_scored > 0 else 0

    total_pausal = sum(s["missed_pausal"] for s in stats.values())
    total_low_conf = sum(s["missed_low_conf"] for s in stats.values())
    total_ctc_wrong = sum(s["missed_ctc_wrong"] for s in stats.values())

    print(f"\n  OVERALL:")
    print(f"    Injected:  {total_injected}")
    print(f"    Scored:    {total_scored}")
    print(f"    Detected:  {total_detected}")
    print(f"    Recall (all):       {total_detected}/{total_scored} ({overall_recall:.1f}%)")
    if total_nf_scored > 0 and total_nf_scored != total_scored:
        print(f"    Recall (non-final): {total_nf_detected}/{total_nf_scored} ({nf_overall:.1f}%)")
    print(f"    Missed breakdown:   {total_pausal} pausal, {total_low_conf} low_conf, {total_ctc_wrong} ctc_wrong")
    print(f"")
    print(f"Non-injected words: {total_clean}")
    print(f"  False positives:  {fp_on_clean} ({fp_rate:.2f}%)")
    if fp_log:
        print(f"\n  FP details:")
        for fp in fp_log:
            print(f"    [{fp['fp_kind']}] '{fp['word']}' (sample {fp['sample_idx']}, conf={fp['confidence']})")
    print(f"Time: {elapsed:.1f}s")
    if args.noise > 0:
        print(f"Noise: {args.noise} dB SNR")
    print(f"Skipped samples: {skipped}")

    # ── Confusion matrix ────────────────────────────────────────────
    if confusion:
        print(f"\n{'='*60}")
        print(f"Vowel Confusion Matrix (injected swap → detected/missed)")
        print(f"{'='*60}")

        for etype in ("irab", "tashkeel"):
            type_confusions = {k: v for k, v in confusion.items() if k[0] == etype}
            if not type_confusions:
                continue

            print(f"\n  {etype.upper()}:")
            # Sort by miss count descending
            sorted_conf = sorted(type_confusions.items(),
                                 key=lambda x: x[1]["missed"], reverse=True)
            for (_, ckey), counts in sorted_conf:
                total = counts["detected"] + counts["missed"]
                det_rate = counts["detected"] / total * 100 if total > 0 else 0
                bar_len = counts["missed"]
                bar = "█" * min(bar_len, 30)
                print(f"    {ckey:16s}  det={counts['detected']:3d}  miss={counts['missed']:3d}  "
                      f"({det_rate:5.1f}% caught)  {bar}")

        # Summary: which vowel is hardest to distinguish?
        print(f"\n  Per-vowel miss summary:")
        vowel_misses = defaultdict(int)
        vowel_totals = defaultdict(int)
        for (etype, ckey), counts in confusion.items():
            # Extract target vowel (what we swapped TO — false label)
            parts = ckey.split("→")
            if len(parts) == 2:
                orig, tgt = parts
                vowel_misses[f"audio={orig}, label={tgt}"] += counts["missed"]
                vowel_totals[f"audio={orig}, label={tgt}"] += counts["detected"] + counts["missed"]

        for key in sorted(vowel_misses.keys(), key=lambda k: vowel_misses[k], reverse=True):
            total = vowel_totals[key]
            missed = vowel_misses[key]
            det = total - missed
            rate = det / total * 100 if total > 0 else 0
            print(f"    {key:32s}  {det}/{total} ({rate:.1f}% caught)")

    # ── Save results ────────────────────────────────────────────────
    # Build confusion data for JSON
    confusion_data = {}
    for (etype, ckey), counts in confusion.items():
        if etype not in confusion_data:
            confusion_data[etype] = {}
        confusion_data[etype][ckey] = counts

    results = {
        "per_type": {},
        "total_injected": total_injected,
        "total_scored": total_scored,
        "total_detected": total_detected,
        "overall_recall_pct": round(overall_recall, 1),
        "nonfinal_recall_pct": round(nf_overall, 1),
        "total_clean": total_clean,
        "fp_on_clean": fp_on_clean,
        "fp_rate_pct": round(fp_rate, 3),
        "noise_snr": args.noise,
        "fraction": args.fraction,
        "exclude_final": args.exclude_final,
        "tashkeel_on": args.tashkeel_on,
        "elapsed_seconds": round(elapsed, 1),
        "confusion": confusion_data,
        "miss_log": miss_log,
        "fp_log": fp_log,
    }
    for etype in ("irab", "tashkeel", "wrong_word"):
        results["per_type"][etype] = dict(stats[etype])

    out_path = Path("eval_recall_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
