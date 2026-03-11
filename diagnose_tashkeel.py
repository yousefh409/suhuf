#!/usr/bin/env python3
"""Diagnose tashkeel detection: measure segment CTC gaps for true errors vs clean words."""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from i3rab.config import Config
from i3rab.pipeline import I3rabPipeline, _generate_tashkeel_alternatives
from i3rab.book import Book
from i3rab.tracker import PositionTracker
from i3rab.arabic import normalize_arabic, strip_harakat
from eval_recall import inject_all_errors


def load_samples(n=30):
    from datasets import load_dataset
    ds = load_dataset("MBZUAI/ClArTTS", split="test")
    samples = []
    for item in ds:
        text = item["text"].strip()
        if not text or not any("\u064B" <= ch <= "\u0652" for ch in text):
            continue
        audio = np.array(item["audio"], dtype=np.float32)
        sr = item["sampling_rate"]
        if sr != 16000:
            from scipy.signal import resample
            audio = resample(audio, int(len(audio) * 16000 / sr)).astype(np.float32)
        peak = np.abs(audio).max()
        if peak > 0:
            audio = audio / peak * 0.95
        if len(audio) / 16000 < 0.5 or len(audio) / 16000 > 20.0:
            continue
        samples.append({"text": text, "audio": audio})
        if len(samples) >= n:
            break
    return samples


def main():
    samples = load_samples(30)
    print(f"Loaded {len(samples)} samples")

    config = Config()
    config.rnnt_weight = 0.0
    # Disable proactive scoring temporarily - we'll score manually
    config.proactive_tashkeel_threshold = 999.0

    word_pool = list(set(w for s in samples for w in s["text"].split()))

    # Collect gaps for: (1) clean words, (2) injected tashkeel errors
    clean_gaps = []  # (word, best_seg_gap, best_fs_gap)
    error_gaps = []  # (word, best_seg_gap, best_fs_gap, detected_by_threshold_X)

    for si, sample in enumerate(samples):
        text, audio = sample["text"], sample["audio"]

        # Run on injected errors
        mod_text, injections = inject_all_errors(text, word_pool, 0.5, si * 1000)
        tash_injs = {inj["word_idx"] for inj in injections if inj["type"] == "tashkeel"}
        if not tash_injs:
            continue

        book = Book.from_sentence(mod_text)
        pipeline = I3rabPipeline(book, config)
        pipeline.tracker = PositionTracker(book, config)
        pipeline.load_pcd()

        # Encode and align
        pcd_text, log_probs, encoded_len, encoded = (
            pipeline._pcd_transcriber.transcribe_and_encode(audio)
        )
        if not pcd_text.strip():
            continue

        from i3rab.arabic import normalize_for_matching
        pcd_norm = normalize_arabic(pcd_text)
        saved = pipeline.tracker.current_position
        start_idx, end_idx, matched_pairs = pipeline.tracker.locate(
            strip_harakat(pcd_norm)
        )
        pipeline.tracker.current_position = saved
        if not matched_pairs:
            continue

        matched_indices = sorted(bw.index for bw, _ in matched_pairs)
        fill_start, fill_end = matched_indices[0], matched_indices[-1] + 1
        all_words = list(book.words[fill_start:fill_end])

        ref_words = [bw.correct_diac for bw in all_words]
        ref_text = " ".join(ref_words)
        try:
            alignment, align_scores = pipeline._pcd_transcriber.forced_align_reference(
                log_probs, encoded_len, ref_text
            )
        except Exception:
            continue
        if alignment is None:
            continue
        word_boundaries = pipeline._pcd_transcriber.get_word_boundaries(
            alignment, align_scores, ref_words
        )

        # Now score each word's tashkeel alternatives
        for i, bw in enumerate(all_words):
            if i >= len(word_boundaries):
                continue
            wb = word_boundaries[i]
            if wb.start_frame >= wb.end_frame or wb.score < -4.0:
                continue

            sf, ef = wb.start_frame, wb.end_frame
            ref_norm = normalize_arabic(bw.correct_diac)
            alts = _generate_tashkeel_alternatives(ref_norm)
            if not alts:
                continue

            # Segment-level scoring
            ref_seg = pipeline._pcd_transcriber._ctc_score_segment(
                log_probs, sf, ef, ref_norm
            )
            best_seg_gap = 0.0
            for alt_word, bi, ov, nv in alts:
                alt_seg = pipeline._pcd_transcriber._ctc_score_segment(
                    log_probs, sf, ef, alt_word
                )
                gap = alt_seg - ref_seg
                if gap > best_seg_gap:
                    best_seg_gap = gap

            # Full-sentence scoring
            ref_parts = [w.correct_diac for w in all_words]
            ref_sc = pipeline._pcd_transcriber._ctc_score(
                log_probs, encoded_len, " ".join(ref_parts)
            )
            best_fs_gap = 0.0
            for alt_word, bi, ov, nv in alts:
                alt_parts = list(ref_parts)
                alt_parts[i] = alt_word
                alt_sc = pipeline._pcd_transcriber._ctc_score(
                    log_probs, encoded_len, " ".join(alt_parts)
                )
                gap = alt_sc - ref_sc
                if gap > best_fs_gap:
                    best_fs_gap = gap

            is_injected = (bw.index - fill_start + fill_start) in tash_injs
            # Map back to original word index
            orig_idx = fill_start + i
            is_injected = orig_idx in tash_injs

            entry = (strip_harakat(ref_norm), best_seg_gap, best_fs_gap)
            if is_injected:
                error_gaps.append(entry)
            else:
                clean_gaps.append(entry)

        if (si + 1) % 10 == 0:
            print(f"  [{si+1}/{len(samples)}] errors={len(error_gaps)} clean={len(clean_gaps)}")

    # Print distribution
    print(f"\n{'='*60}")
    print(f"TASHKEEL GAP DISTRIBUTION")
    print(f"{'='*60}")

    print(f"\nInjected tashkeel errors (should have high gaps):")
    print(f"  Total: {len(error_gaps)}")
    if error_gaps:
        seg_gaps = [g[1] for g in error_gaps]
        fs_gaps = [g[2] for g in error_gaps]
        thresholds = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0]
        print(f"  Segment gaps: min={min(seg_gaps):.2f} median={sorted(seg_gaps)[len(seg_gaps)//2]:.2f} max={max(seg_gaps):.2f}")
        print(f"  FS gaps:      min={min(fs_gaps):.2f} median={sorted(fs_gaps)[len(fs_gaps)//2]:.2f} max={max(fs_gaps):.2f}")
        for t in thresholds:
            n_seg = sum(1 for g in seg_gaps if g > t)
            n_fs = sum(1 for g in fs_gaps if g > t)
            n_both = sum(1 for sg, fg in zip(seg_gaps, fs_gaps) if sg > t and fg > 0)
            n_either = sum(1 for sg, fg in zip(seg_gaps, fs_gaps) if sg > t or fg > t)
            print(f"    seg>{t:.1f}: {n_seg}/{len(seg_gaps)} ({100*n_seg/len(seg_gaps):.0f}%)  "
                  f"fs>{t:.1f}: {n_fs}/{len(fs_gaps)} ({100*n_fs/len(fs_gaps):.0f}%)  "
                  f"seg>{t:.1f}+fs>0: {n_both}/{len(seg_gaps)} ({100*n_both/len(seg_gaps):.0f}%)")

    print(f"\nClean words (should have low gaps = no false detections):")
    print(f"  Total: {len(clean_gaps)}")
    if clean_gaps:
        seg_gaps = [g[1] for g in clean_gaps]
        fs_gaps = [g[2] for g in clean_gaps]
        thresholds = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0]
        print(f"  Segment gaps: min={min(seg_gaps):.2f} median={sorted(seg_gaps)[len(seg_gaps)//2]:.2f} max={max(seg_gaps):.2f}")
        print(f"  FS gaps:      min={min(fs_gaps):.2f} median={sorted(fs_gaps)[len(fs_gaps)//2]:.2f} max={max(fs_gaps):.2f}")
        for t in thresholds:
            n_seg = sum(1 for g in seg_gaps if g > t)
            n_fs = sum(1 for g in fs_gaps if g > t)
            n_both = sum(1 for sg, fg in zip(seg_gaps, fs_gaps) if sg > t and fg > 0)
            print(f"    seg>{t:.1f}: {n_seg}/{len(seg_gaps)} ({100*n_seg/len(seg_gaps):.1f}%)  "
                  f"fs>{t:.1f}: {n_fs}/{len(fs_gaps)} ({100*n_fs/len(fs_gaps):.1f}%)  "
                  f"seg>{t:.1f}+fs>0: {n_both}/{len(seg_gaps)} ({100*n_both/len(seg_gaps):.1f}%)")


if __name__ == "__main__":
    main()
