#!/usr/bin/env python3
"""Experiment: Does RNN-T provide better vowel discrimination than CTC?

For each ClArTTS test sample:
1. Take words with internal vowels
2. Generate tashkeel alternatives (swap one internal vowel)
3. Score both correct and alternative with CTC segment + RNN-T full-sentence
4. Measure: how often does each method correctly prefer the reference?
5. Check: does RNN-T catch cases CTC misses?

This tells us whether RNN-T is worth re-enabling for tashkeel verification.
"""

import io
import json
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

sys.path.insert(0, ".")
from i3rab.config import Config
from i3rab.pipeline import _generate_tashkeel_alternatives
from i3rab.pcd_transcriber import PCDTranscriber
from i3rab.arabic import normalize_arabic, strip_harakat
from i3rab.book import Book


def read_audio(filepath):
    audio_bytes = filepath.read_bytes()
    try:
        audio_data, sr = sf.read(io.BytesIO(audio_bytes), dtype="float32")
    except Exception:
        import av
        container = av.open(io.BytesIO(audio_bytes))
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
        frames = []
        for frame in container.decode(audio=0):
            for r in resampler.resample(frame):
                frames.append(r.to_ndarray().flatten())
        container.close()
        return np.concatenate(frames).astype(np.float32) / 32768.0
    if audio_data.ndim > 1:
        audio_data = audio_data.mean(axis=1)
    if sr != 16000:
        from scipy.signal import resample
        num_samples = int(len(audio_data) * 16000 / sr)
        audio_data = resample(audio_data, num_samples).astype(np.float32)
    return audio_data


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-recordings", type=int, default=10)
    parser.add_argument("--max-words-per-rec", type=int, default=5)
    args = parser.parse_args()

    config = Config()
    transcriber = PCDTranscriber(config)
    transcriber.load()

    test_dir = Path("test_data")
    manifest = json.loads((test_dir / "manifest.json").read_text())
    sentences = [e for e in manifest if e.get("type") == "sentence"]
    sentences = sentences[:args.max_recordings]

    # Counters
    total_words = 0
    ctc_seg_correct = 0
    ctc_fs_correct = 0
    rnnt_correct = 0
    both_wrong = 0
    ctc_wrong_rnnt_right = 0  # <-- the key metric
    rnnt_wrong_ctc_right = 0
    both_right = 0

    ctc_seg_gaps = []
    ctc_fs_gaps = []
    rnnt_gaps = []

    ctc_seg_times = []
    rnnt_times = []

    for si, entry in enumerate(sentences):
        audio = read_audio(test_dir / entry["filename"])
        text = entry["text_diacritized"]

        book = Book.from_sentence(text)
        all_words = list(book.words)
        ref_parts = [w.correct_diac for w in all_words]

        # Encode once
        log_probs, encoded_len, encoded = transcriber.encode(audio)

        # Forced alignment for segment boundaries
        ref_text = " ".join(ref_parts)
        try:
            alignment, scores = transcriber.forced_align_reference(
                log_probs, encoded_len, ref_text
            )
            word_boundaries = transcriber.get_word_boundaries(
                alignment, scores, ref_parts
            )
        except Exception:
            print(f"  [{entry['id']}] alignment failed, skipping")
            continue

        words_tested = 0
        for i, bw in enumerate(all_words):
            if words_tested >= args.max_words_per_rec:
                break
            if i >= len(word_boundaries):
                continue

            ref_norm = normalize_arabic(bw.correct_diac)
            alts = _generate_tashkeel_alternatives(ref_norm)
            if not alts:
                continue

            wb = word_boundaries[i]
            sf_, ef_ = wb.start_frame, wb.end_frame

            # Pick the best alternative (most different)
            best_alt = alts[0]
            alt_word = best_alt[0]

            # --- CTC segment scoring ---
            t0 = time.time()
            ref_seg = transcriber._ctc_score_segment(
                log_probs, sf_, ef_, ref_norm
            )
            alt_seg = transcriber._ctc_score_segment(
                log_probs, sf_, ef_, alt_word
            )
            ctc_seg_time = time.time() - t0
            ctc_seg_times.append(ctc_seg_time)

            seg_gap = ref_seg - alt_seg  # positive = correct preferred

            # --- CTC full-sentence scoring ---
            alt_parts = list(ref_parts)
            alt_parts[i] = alt_word
            ref_fs = transcriber._ctc_score(
                log_probs, encoded_len, " ".join(ref_parts)
            )
            alt_fs = transcriber._ctc_score(
                log_probs, encoded_len, " ".join(alt_parts)
            )
            fs_gap = ref_fs - alt_fs

            # --- RNN-T scoring ---
            t0 = time.time()
            ref_rnnt = transcriber._rnnt_score(
                encoded, encoded_len, " ".join(ref_parts)
            )
            alt_rnnt = transcriber._rnnt_score(
                encoded, encoded_len, " ".join(alt_parts)
            )
            rnnt_time = time.time() - t0
            rnnt_times.append(rnnt_time)

            rnnt_gap = ref_rnnt - alt_rnnt

            # Record
            total_words += 1
            words_tested += 1

            ctc_seg_ok = seg_gap > 0
            ctc_fs_ok = fs_gap > 0
            rnnt_ok = rnnt_gap > 0

            if ctc_seg_ok:
                ctc_seg_correct += 1
            if ctc_fs_ok:
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
            ctc_fs_gaps.append(fs_gap)
            rnnt_gaps.append(rnnt_gap)

            if not ctc_seg_ok and rnnt_ok:
                print(f"  ** RNN-T saves: {bw.correct_diac} → {alt_word}  "
                      f"CTC_seg={seg_gap:.2f} CTC_fs={fs_gap:.2f} RNNT={rnnt_gap:.2f}")
            elif not ctc_seg_ok and not rnnt_ok:
                print(f"  -- Both wrong: {bw.correct_diac} → {alt_word}  "
                      f"CTC_seg={seg_gap:.2f} CTC_fs={fs_gap:.2f} RNNT={rnnt_gap:.2f}")

        print(f"[{entry['id']}] tested {words_tested} words  "
              f"(CTC_seg: {ctc_seg_time*1000:.0f}ms/word, "
              f"RNNT: {rnnt_time*1000:.0f}ms/pair)")

    # Summary
    print("\n" + "=" * 60)
    print(f"RESULTS ({total_words} words tested)")
    print("=" * 60)
    print(f"\nCorrect preference (ref > alt):")
    print(f"  CTC segment: {ctc_seg_correct}/{total_words} ({100*ctc_seg_correct/total_words:.1f}%)")
    print(f"  CTC full-sent: {ctc_fs_correct}/{total_words} ({100*ctc_fs_correct/total_words:.1f}%)")
    print(f"  RNN-T:         {rnnt_correct}/{total_words} ({100*rnnt_correct/total_words:.1f}%)")

    print(f"\nAgreement matrix:")
    print(f"  Both right:          {both_right}")
    print(f"  CTC wrong, RNNT right: {ctc_wrong_rnnt_right}  ← RNN-T would help")
    print(f"  RNNT wrong, CTC right: {rnnt_wrong_ctc_right}")
    print(f"  Both wrong:          {both_wrong}")

    if ctc_wrong_rnnt_right + both_wrong > 0:
        rescue_rate = ctc_wrong_rnnt_right / (ctc_wrong_rnnt_right + both_wrong)
        print(f"\n  RNN-T rescue rate (of CTC failures): {100*rescue_rate:.1f}%")

    print(f"\nGap statistics (positive = correctly prefers reference):")
    print(f"  CTC segment: mean={np.mean(ctc_seg_gaps):.2f}, "
          f"median={np.median(ctc_seg_gaps):.2f}, "
          f"std={np.std(ctc_seg_gaps):.2f}")
    print(f"  CTC full-sent: mean={np.mean(ctc_fs_gaps):.2f}, "
          f"median={np.median(ctc_fs_gaps):.2f}, "
          f"std={np.std(ctc_fs_gaps):.2f}")
    print(f"  RNN-T:         mean={np.mean(rnnt_gaps):.2f}, "
          f"median={np.median(rnnt_gaps):.2f}, "
          f"std={np.std(rnnt_gaps):.2f}")

    print(f"\nTiming:")
    print(f"  CTC segment: {1000*np.mean(ctc_seg_times):.1f}ms avg per word")
    print(f"  RNN-T pair:  {1000*np.mean(rnnt_times):.1f}ms avg per pair (2 scores)")

    # Correlation
    ctc_arr = np.array(ctc_seg_gaps)
    rnnt_arr = np.array(rnnt_gaps)
    corr = np.corrcoef(ctc_arr, rnnt_arr)[0, 1]
    print(f"\n  CTC-seg vs RNN-T correlation: {corr:.3f}")
    print(f"  (Low correlation = independent signals, high = redundant)")


if __name__ == "__main__":
    main()
