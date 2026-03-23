#!/usr/bin/env python3
"""Test RNN-T vs CTC on INJECTED tashkeel errors (matching eval_recall scenario).

For each ClArTTS sample:
1. Inject a tashkeel error (swap one internal vowel)
2. Use the MODIFIED reference for forced alignment
3. Score: modified reference vs correct alternative
4. Check: does CTC/RNN-T prefer the correct form (= detect the error)?

This directly measures whether RNN-T helps on the cases CTC misses.
"""

import io
import json
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, ".")
from i3rab.config import Config
from i3rab.pcd_transcriber import PCDTranscriber
from i3rab.arabic import normalize_arabic, strip_harakat
from i3rab.book import Book

# Vowel injection (same as eval_recall.py)
FATHA = "\u064e"
DAMMA = "\u064f"
KASRA = "\u0650"
VOWELS = {FATHA, DAMMA, KASRA}
HARAKAT = set("\u064b\u064c\u064d\u064e\u064f\u0650\u0651\u0652")


def inject_tashkeel_error(word: str, rng: random.Random):
    """Swap one internal vowel (not the last)."""
    positions = []
    base_idx = -1
    for i, ch in enumerate(word):
        if ch not in HARAKAT:
            base_idx += 1
        elif ch in VOWELS and base_idx >= 0:
            # Check it's internal (not the last base character's vowel)
            remaining_bases = sum(1 for c in word[i+1:] if c not in HARAKAT)
            if remaining_bases > 0:
                positions.append((i, ch))
    if not positions:
        return None, None
    pos, orig = rng.choice(positions)
    alternatives = list(VOWELS - {orig})
    new_v = rng.choice(alternatives)
    modified = word[:pos] + new_v + word[pos+1:]
    return modified, word  # (modified_ref, correct_form)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-samples", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    config = Config()
    transcriber = PCDTranscriber(config)
    transcriber.load()

    # Load ClArTTS test data
    try:
        from datasets import load_dataset
        ds = load_dataset("MBZUAI/ClArTTS", split="test")
    except Exception as e:
        print(f"Failed to load ClArTTS: {e}")
        return

    total = 0
    ctc_seg_correct = 0
    ctc_fs_correct = 0
    rnnt_correct = 0
    both_wrong = 0
    ctc_wrong_rnnt_right = 0
    rnnt_wrong_ctc_right = 0
    both_right = 0

    ctc_seg_gaps = []
    rnnt_gaps = []

    samples = list(range(len(ds)))
    rng.shuffle(samples)
    samples = samples[:args.max_samples]

    for si, sample_idx in enumerate(samples):
        sample = ds[sample_idx]
        text = sample["text"].strip()
        has_diac = any("\u064b" <= ch <= "\u0652" for ch in text)
        if not has_diac:
            continue

        audio_data = np.array(sample["audio"], dtype=np.float32)
        sr = sample["sampling_rate"]
        if sr != 16000:
            from scipy.signal import resample
            num = int(len(audio_data) * 16000 / sr)
            audio_data = resample(audio_data, num).astype(np.float32)

        words = text.split()
        if len(words) < 3:
            continue

        # Pick a word to inject error
        candidates = []
        for wi, w in enumerate(words):
            mod, orig = inject_tashkeel_error(w, rng)
            if mod:
                candidates.append((wi, mod, orig))
        if not candidates:
            continue

        wi, modified_word, correct_word = rng.choice(candidates)

        # Build modified reference (what the pipeline gets)
        mod_words = list(words)
        mod_words[wi] = modified_word
        mod_ref = " ".join(mod_words)
        orig_ref = " ".join(words)

        # Encode audio (audio matches ORIGINAL text, not modified)
        log_probs, encoded_len, encoded = transcriber.encode(audio_data)

        # Forced alignment against MODIFIED reference
        # (this is what the pipeline does — aligns to what it thinks is correct)
        mod_norm = normalize_arabic(mod_ref)
        try:
            alignment, scores = transcriber.forced_align_reference(
                log_probs, encoded_len, mod_norm
            )
            mod_norm_words = [normalize_arabic(w) for w in mod_words]
            wbs = transcriber.get_word_boundaries(alignment, scores, mod_norm_words)
        except Exception:
            continue

        if wi >= len(wbs):
            continue

        wb = wbs[wi]
        sf_, ef_ = wb.start_frame, wb.end_frame

        # Score: modified reference vs correct form
        ref_norm = normalize_arabic(modified_word)
        alt_norm = normalize_arabic(correct_word)

        # CTC segment
        ref_seg = transcriber._ctc_score_segment(log_probs, sf_, ef_, ref_norm)
        alt_seg = transcriber._ctc_score_segment(log_probs, sf_, ef_, alt_norm)
        seg_gap = alt_seg - ref_seg  # positive = correct preferred = error detected

        # CTC full-sentence
        ref_fs = transcriber._ctc_score(log_probs, encoded_len, mod_norm)
        alt_fs = transcriber._ctc_score(
            log_probs, encoded_len, normalize_arabic(orig_ref)
        )
        fs_gap = alt_fs - ref_fs

        # RNN-T full-sentence
        ref_rnnt = transcriber._rnnt_score(encoded, encoded_len, mod_norm)
        alt_rnnt = transcriber._rnnt_score(
            encoded, encoded_len, normalize_arabic(orig_ref)
        )
        rnnt_gap = alt_rnnt - ref_rnnt

        total += 1
        ctc_seg_ok = seg_gap > 0
        rnnt_ok = rnnt_gap > 0

        if ctc_seg_ok:
            ctc_seg_correct += 1
        if fs_gap > 0:
            ctc_fs_correct += 1
        if rnnt_ok:
            rnnt_correct += 1

        if ctc_seg_ok and rnnt_ok:
            both_right += 1
        elif not ctc_seg_ok and not rnnt_ok:
            both_wrong += 1
        elif not ctc_seg_ok and rnnt_ok:
            ctc_wrong_rnnt_right += 1
        elif ctc_seg_ok and not rnnt_ok:
            rnnt_wrong_ctc_right += 1

        ctc_seg_gaps.append(seg_gap)
        rnnt_gaps.append(rnnt_gap)

        status = ""
        if not ctc_seg_ok and rnnt_ok:
            status = "** RNNT SAVES"
        elif not ctc_seg_ok and not rnnt_ok:
            status = "-- BOTH FAIL"
        elif ctc_seg_ok and not rnnt_ok:
            status = "~~ CTC SAVES"

        if status:
            print(f"  {status}: {modified_word} → {correct_word}  "
                  f"CTC_seg={seg_gap:.2f} RNNT={rnnt_gap:.2f} "
                  f"(wb.score={wb.score:.2f})")

        if (si + 1) % 10 == 0:
            print(f"  ... {si+1}/{len(samples)} samples processed "
                  f"({total} valid)")

    print(f"\n{'='*60}")
    print(f"INJECTED TASHKEEL ERROR RESULTS ({total} words)")
    print(f"{'='*60}")
    print(f"\nError detection rate (correct > modified):")
    print(f"  CTC segment:   {ctc_seg_correct}/{total} "
          f"({100*ctc_seg_correct/total:.1f}%)")
    print(f"  CTC full-sent:  {ctc_fs_correct}/{total} "
          f"({100*ctc_fs_correct/total:.1f}%)")
    print(f"  RNN-T:          {rnnt_correct}/{total} "
          f"({100*rnnt_correct/total:.1f}%)")

    print(f"\nAgreement (CTC-seg vs RNN-T):")
    print(f"  Both detect:       {both_right}")
    print(f"  CTC miss, RNNT ok: {ctc_wrong_rnnt_right}  ← RNNT would help")
    print(f"  RNNT miss, CTC ok: {rnnt_wrong_ctc_right}")
    print(f"  Both miss:         {both_wrong}")

    ctc_failures = ctc_wrong_rnnt_right + both_wrong
    if ctc_failures > 0:
        print(f"\n  RNNT rescue rate (of CTC failures): "
              f"{100*ctc_wrong_rnnt_right/ctc_failures:.1f}%")

    print(f"\nGap statistics:")
    print(f"  CTC segment: mean={np.mean(ctc_seg_gaps):.2f}, "
          f"median={np.median(ctc_seg_gaps):.2f}")
    print(f"  RNN-T:       mean={np.mean(rnnt_gaps):.2f}, "
          f"median={np.median(rnnt_gaps):.2f}")

    corr = np.corrcoef(ctc_seg_gaps, rnnt_gaps)[0, 1]
    print(f"\n  Correlation: {corr:.3f}")

    # Potential improvement
    combined = both_right + ctc_wrong_rnnt_right + rnnt_wrong_ctc_right
    print(f"\n  Combined (either detects): {combined}/{total} "
          f"({100*combined/total:.1f}%)")
    print(f"  vs CTC alone:              {ctc_seg_correct}/{total} "
          f"({100*ctc_seg_correct/total:.1f}%)")
    print(f"  Potential gain:             +"
          f"{100*(combined - ctc_seg_correct)/total:.1f}%")


if __name__ == "__main__":
    main()
