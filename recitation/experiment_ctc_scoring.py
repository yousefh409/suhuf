#!/usr/bin/env python3
"""Experiment: Compare CTC scoring approaches for i3rab hypothesis ranking.

Approach A: Full-sentence CTC scoring (current)
  - Build full sentences with each hypothesis swapped in
  - Score each full sentence against the full audio
  - Pick the highest scoring hypothesis

Approach B: Segmented CTC scoring
  - Use forced alignment to get per-word frame boundaries
  - Score each hypothesis against ONLY that word's frame segment

Approach C: Combined scoring (multiple weight combinations)
  - Score both ways, then pick using weighted combination
  - Weights: 0.7*full + 0.3*seg, 0.5/0.5, 0.3*full + 0.7*seg
"""

import io
import json
import time
from pathlib import Path

import numpy as np
import soundfile as sf


def read_audio(filepath: Path) -> np.ndarray:
    """Read audio file, resample to 16kHz mono float32."""
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
        audio_data = np.concatenate(frames).astype(np.float32) / 32768.0
        return audio_data
    if audio_data.ndim > 1:
        audio_data = audio_data.mean(axis=1)
    if sr != 16000:
        from scipy.signal import resample
        num_samples = int(len(audio_data) * 16000 / sr)
        audio_data = resample(audio_data, num_samples).astype(np.float32)
    return audio_data


def main():
    from i3rab.config import Config
    from i3rab.pcd_transcriber import PCDTranscriber
    from i3rab.book import Book
    from i3rab.pipeline import I3rabPipeline
    from i3rab.arabic import normalize_arabic, strip_harakat
    from i3rab.models import BookWord, ScoredWord, Confidence

    config = Config()
    test_dir = Path("test_data")
    manifest = json.loads((test_dir / "manifest.json").read_text())
    sentences = [e for e in manifest if e.get("type") == "sentence"]

    print(f"Found {len(sentences)} sentence recordings in manifest.json")
    print()

    # ── Load model once ──────────────────────────────────────────────
    print("Loading PCD model...")
    transcriber = PCDTranscriber(config)
    transcriber.load()
    print()

    # ── Define weight combinations for Approach C ────────────────────
    combined_weights = [
        (0.7, 0.3, "C1 (0.7*full + 0.3*seg)"),
        (0.5, 0.5, "C2 (0.5*full + 0.5*seg)"),
        (0.3, 0.7, "C3 (0.3*full + 0.7*seg)"),
    ]

    # ── Accumulators ─────────────────────────────────────────────────
    total_a_correct = 0
    total_b_correct = 0
    total_c_correct = {label: 0 for _, _, label in combined_weights}
    total_multi_hyp_words = 0  # words that actually have >1 hypothesis (interesting ones)
    total_all_words = 0  # all words scored

    # Track per-word differences between approaches
    differences = []  # list of dicts with word details and per-approach results

    # Per-sentence results
    sentence_results = []

    for entry_idx, entry in enumerate(sentences):
        filepath = test_dir / entry["filename"]
        if not filepath.exists():
            print(f"  SKIP {entry['id']}: file not found")
            continue

        reference = entry["text_diacritized"]
        rec_id = entry["id"]

        # ── Load audio + encode once ─────────────────────────────────
        audio = read_audio(filepath)
        log_probs, encoded_len = transcriber.encode(audio)

        # ── Build book + get word list ───────────────────────────────
        book = Book.from_sentence(reference)
        all_words = book.words
        reference_words = [w.correct_diac for w in all_words]
        reference_text = " ".join(reference_words)

        # ── Forced alignment for word boundaries ─────────────────────
        alignment, align_scores = transcriber.forced_align_reference(
            log_probs, encoded_len, reference_text
        )

        if alignment is None:
            print(f"  SKIP {rec_id}: forced alignment failed")
            continue

        word_boundaries = transcriber.get_word_boundaries(
            alignment, align_scores, reference_words
        )

        # ── Score each multi-hypothesis word using all approaches ────
        sent_a_correct = 0
        sent_b_correct = 0
        sent_c_correct = {label: 0 for _, _, label in combined_weights}
        sent_multi_hyp = 0
        sent_total = len(all_words)

        for i, book_word in enumerate(all_words):
            total_all_words += 1

            # Words with <= 1 hypothesis: no scoring needed, always correct
            if len(book_word.hypotheses) <= 1:
                sent_a_correct += 1
                sent_b_correct += 1
                for _, _, label in combined_weights:
                    sent_c_correct[label] += 1
                continue

            sent_multi_hyp += 1
            total_multi_hyp_words += 1

            wb = word_boundaries[i] if i < len(word_boundaries) else None

            # ── Approach A: Full-sentence CTC scoring ────────────────
            scored_a = transcriber.score_word_in_context(
                log_probs, encoded_len, book_word, all_words
            )
            a_hyp = scored_a.detected_hyp
            a_correct = a_hyp is not None and a_hyp.is_correct

            # ── Approach B: Segmented CTC scoring ────────────────────
            if wb is not None and wb.start_frame < wb.end_frame:
                scored_b = transcriber.score_word_segmented(
                    log_probs, wb.start_frame, wb.end_frame, book_word
                )
            else:
                # No valid boundary => fallback to None
                scored_b = ScoredWord(
                    word=book_word,
                    detected_hyp=None,
                    confidence=Confidence.LOW,
                    score_gap=0.0,
                )
            b_hyp = scored_b.detected_hyp
            b_correct = b_hyp is not None and b_hyp.is_correct

            if a_correct:
                sent_a_correct += 1
            if b_correct:
                sent_b_correct += 1

            # ── Approach C: Combined scoring ─────────────────────────
            # We need per-hypothesis scores from both approaches
            # Recompute to get raw scores for combination

            # Full-sentence scores for each hypothesis
            context_parts = [w.correct_diac for w in all_words]
            target_pos = next(
                j for j, w in enumerate(all_words) if w.index == book_word.index
            )

            full_scores = {}
            for hyp in book_word.hypotheses:
                parts = list(context_parts)
                parts[target_pos] = hyp.diacritized
                full_text = " ".join(parts)
                score = transcriber._ctc_score(log_probs, encoded_len, full_text)
                full_scores[hyp.diacritized] = score

            # Segmented scores for each hypothesis
            seg_scores = {}
            if wb is not None and wb.start_frame < wb.end_frame:
                import torch
                segment = log_probs[:, wb.start_frame:wb.end_frame, :]
                seg_len = torch.tensor([wb.end_frame - wb.start_frame])
                for hyp in book_word.hypotheses:
                    score = transcriber._ctc_score(segment, seg_len, hyp.diacritized)
                    seg_scores[hyp.diacritized] = score
            else:
                for hyp in book_word.hypotheses:
                    seg_scores[hyp.diacritized] = float("-inf")

            # Normalize scores to [0, 1] range for fair combination
            # Use softmax-like normalization within each set
            def normalize_scores(scores_dict):
                vals = list(scores_dict.values())
                if not vals or all(v == float("-inf") for v in vals):
                    return {k: 0.0 for k in scores_dict}
                max_val = max(v for v in vals if v != float("-inf"))
                min_val = min(v for v in vals if v != float("-inf"))
                rng = max_val - min_val
                if rng < 1e-12:
                    return {k: 1.0 / len(scores_dict) for k in scores_dict}
                return {
                    k: (v - min_val) / rng if v != float("-inf") else 0.0
                    for k, v in scores_dict.items()
                }

            full_norm = normalize_scores(full_scores)
            seg_norm = normalize_scores(seg_scores)

            c_results = {}
            for w_full, w_seg, label in combined_weights:
                combined = {}
                for hyp in book_word.hypotheses:
                    key = hyp.diacritized
                    combined[key] = w_full * full_norm[key] + w_seg * seg_norm[key]

                best_key = max(combined, key=combined.get)
                best_hyp = next(h for h in book_word.hypotheses if h.diacritized == best_key)
                c_correct = best_hyp.is_correct
                c_results[label] = {
                    "hyp": best_hyp,
                    "correct": c_correct,
                }
                if c_correct:
                    sent_c_correct[label] += 1

            # ── Track differences ────────────────────────────────────
            # Check if any approach differs
            approaches_agree = (
                a_correct == b_correct
                and all(c_results[label]["correct"] == a_correct for _, _, label in combined_weights)
            )

            word_result = {
                "rec_id": rec_id,
                "word_idx": i,
                "word_base": book_word.base,
                "word_correct": book_word.correct_diac,
                "num_hypotheses": len(book_word.hypotheses),
                "approach_a": {
                    "correct": a_correct,
                    "detected": a_hyp.diacritized if a_hyp else None,
                    "detected_case": a_hyp.case if a_hyp else None,
                    "score_gap": scored_a.score_gap,
                },
                "approach_b": {
                    "correct": b_correct,
                    "detected": b_hyp.diacritized if b_hyp else None,
                    "detected_case": b_hyp.case if b_hyp else None,
                    "score_gap": scored_b.score_gap,
                },
            }
            for _, _, label in combined_weights:
                cr = c_results[label]
                word_result[label] = {
                    "correct": cr["correct"],
                    "detected": cr["hyp"].diacritized,
                    "detected_case": cr["hyp"].case,
                }

            if not approaches_agree:
                differences.append(word_result)

        total_a_correct += sent_a_correct
        total_b_correct += sent_b_correct
        for _, _, label in combined_weights:
            total_c_correct[label] += sent_c_correct[label]

        pct_a = 100 * sent_a_correct / sent_total if sent_total > 0 else 0
        pct_b = 100 * sent_b_correct / sent_total if sent_total > 0 else 0
        sentence_results.append({
            "rec_id": rec_id,
            "total_words": sent_total,
            "multi_hyp_words": sent_multi_hyp,
            "a_correct": sent_a_correct,
            "b_correct": sent_b_correct,
            **{label: sent_c_correct[label] for _, _, label in combined_weights},
        })

        print(f"  {rec_id}: {sent_total} words ({sent_multi_hyp} multi-hyp)  "
              f"A={sent_a_correct}/{sent_total}  B={sent_b_correct}/{sent_total}  "
              f"C1={sent_c_correct[combined_weights[0][2]]}/{sent_total}")

    # ══════════════════════════════════════════════════════════════════
    # RESULTS SUMMARY
    # ══════════════════════════════════════════════════════════════════
    print()
    print("=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print()
    print(f"Total sentences: {len(sentence_results)}")
    print(f"Total words: {total_all_words}")
    print(f"Multi-hypothesis words (interesting): {total_multi_hyp_words}")
    print()

    print("─" * 70)
    print(f"{'Approach':<35s} {'Correct':<12s} {'Total':<8s} {'Accuracy':<10s}")
    print("─" * 70)
    print(f"{'A: Full-sentence CTC':<35s} {total_a_correct:<12d} {total_all_words:<8d} {100*total_a_correct/total_all_words:.1f}%")
    print(f"{'B: Segmented CTC':<35s} {total_b_correct:<12d} {total_all_words:<8d} {100*total_b_correct/total_all_words:.1f}%")
    for w_full, w_seg, label in combined_weights:
        c_val = total_c_correct[label]
        print(f"{label:<35s} {c_val:<12d} {total_all_words:<8d} {100*c_val/total_all_words:.1f}%")
    print("─" * 70)

    # ── Multi-hypothesis-only accuracy ───────────────────────────────
    if total_multi_hyp_words > 0:
        # Recount multi-hyp-only correct
        mh_a = sum(1 for d in differences if d["approach_a"]["correct"]) + \
               (total_multi_hyp_words - len(differences))  # words where all agree
        # Actually, let's recount properly from the differences list
        # We need to track all multi-hyp word results, not just differences

        # We'll recompute from sentence_results minus single-hyp words
        # single-hyp words are always correct for all approaches
        single_hyp_words = total_all_words - total_multi_hyp_words
        mh_a = total_a_correct - single_hyp_words
        mh_b = total_b_correct - single_hyp_words
        mh_c = {label: total_c_correct[label] - single_hyp_words for _, _, label in combined_weights}

        print()
        print("Multi-hypothesis words only (where scoring actually matters):")
        print("─" * 70)
        print(f"{'Approach':<35s} {'Correct':<12s} {'Total':<8s} {'Accuracy':<10s}")
        print("─" * 70)
        print(f"{'A: Full-sentence CTC':<35s} {mh_a:<12d} {total_multi_hyp_words:<8d} {100*mh_a/total_multi_hyp_words:.1f}%")
        print(f"{'B: Segmented CTC':<35s} {mh_b:<12d} {total_multi_hyp_words:<8d} {100*mh_b/total_multi_hyp_words:.1f}%")
        for w_full, w_seg, label in combined_weights:
            c_val = mh_c[label]
            print(f"{label:<35s} {c_val:<12d} {total_multi_hyp_words:<8d} {100*c_val/total_multi_hyp_words:.1f}%")
        print("─" * 70)

    # ── Words where approaches disagree ──────────────────────────────
    print()
    print("=" * 70)
    print(f"WORDS WHERE APPROACHES DISAGREE ({len(differences)} words)")
    print("=" * 70)
    print()

    for d in differences:
        print(f"  {d['rec_id']} word[{d['word_idx']}]: {d['word_base']}  (correct: {d['word_correct']})")
        a = d["approach_a"]
        b = d["approach_b"]
        a_mark = "OK" if a["correct"] else "XX"
        b_mark = "OK" if b["correct"] else "XX"
        print(f"    A (full-sentence):  [{a_mark}] {a['detected']:<25s} case={a['detected_case']:<12s} gap={a['score_gap']:.2f}")
        print(f"    B (segmented):      [{b_mark}] {b['detected']:<25s} case={b['detected_case']:<12s} gap={b['score_gap']:.2f}")
        for _, _, label in combined_weights:
            c = d[label]
            c_mark = "OK" if c["correct"] else "XX"
            print(f"    {label}: [{c_mark}] {c['detected']:<25s} case={c['detected_case']}")
        print()

    # ── Per-sentence breakdown ───────────────────────────────────────
    print("=" * 70)
    print("PER-SENTENCE BREAKDOWN")
    print("=" * 70)
    print()
    print(f"{'Recording':<12s} {'Words':<7s} {'Multi':<7s} {'A':<8s} {'B':<8s} {'C1':<8s} {'C2':<8s} {'C3':<8s}")
    print("─" * 70)
    for sr in sentence_results:
        c1_label = combined_weights[0][2]
        c2_label = combined_weights[1][2]
        c3_label = combined_weights[2][2]
        print(f"{sr['rec_id']:<12s} {sr['total_words']:<7d} {sr['multi_hyp_words']:<7d} "
              f"{sr['a_correct']:<8d} {sr['b_correct']:<8d} "
              f"{sr.get(c1_label, 0):<8d} {sr.get(c2_label, 0):<8d} {sr.get(c3_label, 0):<8d}")
    print("─" * 70)

    # ── Which approach won? ──────────────────────────────────────────
    print()
    print("=" * 70)
    print("ANALYSIS: Which words improved or regressed?")
    print("=" * 70)
    print()

    a_only = [d for d in differences if d["approach_a"]["correct"] and not d["approach_b"]["correct"]]
    b_only = [d for d in differences if d["approach_b"]["correct"] and not d["approach_a"]["correct"]]
    neither = [d for d in differences if not d["approach_a"]["correct"] and not d["approach_b"]["correct"]]

    print(f"  A correct, B wrong:     {len(a_only)} words (full-sentence wins)")
    for d in a_only:
        print(f"    - {d['rec_id']} {d['word_base']} ({d['word_correct']})")
    print()

    print(f"  B correct, A wrong:     {len(b_only)} words (segmented wins)")
    for d in b_only:
        print(f"    - {d['rec_id']} {d['word_base']} ({d['word_correct']})")
    print()

    print(f"  Both wrong:             {len(neither)} words")
    for d in neither:
        print(f"    - {d['rec_id']} {d['word_base']} ({d['word_correct']})")
        print(f"      A detected: {d['approach_a']['detected']} ({d['approach_a']['detected_case']})")
        print(f"      B detected: {d['approach_b']['detected']} ({d['approach_b']['detected_case']})")
    print()

    # Best combined approach
    best_c_label = max(total_c_correct, key=total_c_correct.get)
    print(f"  Best combined approach: {best_c_label} with {total_c_correct[best_c_label]}/{total_all_words} correct")
    print()


if __name__ == "__main__":
    main()
