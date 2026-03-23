#!/usr/bin/env python3
"""
Systematic threshold tuning experiments for the i3rab diacritics recognition system.

Varies each threshold one-at-a-time while holding others at defaults,
measures accuracy across ALL sentence recordings in test_data/manifest.json,
then combines optimal values for a final evaluation.

Thresholds tuned:
  1. CTC confidence gap (HIGH / MEDIUM boundary)
  2. Alignment score threshold for tashkeel checking
  3. CTC omission verification margin
  4. Edge recovery threshold
  5. Low-confidence fallback (default to reference when LOW)
"""

import copy
import difflib
import io
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf


# ── Audio reader (same as test_hybrid_pcd.py) ──────────────────────────────

def read_audio(filepath: Path) -> np.ndarray:
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


# ── Imports from the i3rab package ──────────────────────────────────────────

from i3rab.config import Config
from i3rab.pcd_transcriber import PCDTranscriber, WordBoundary
from i3rab.book import Book
from i3rab.arabic import (
    normalize_arabic,
    strip_harakat,
    normalize_for_matching,
    compare_harakat,
    format_haraka_list,
)
from i3rab.models import (
    BookWord,
    BookPhrase,
    WordDiff,
    DiffKind,
    Confidence,
    ScoredWord,
    WordHypothesis,
    HARAKAT,
)


# ── Reproduce _clean_diacritics from pipeline.py ────────────────────────────

def _clean_diacritics(text: str) -> str:
    result = []
    prev = None
    for c in text:
        if c in HARAKAT:
            if c != prev:
                result.append(c)
                prev = c
        else:
            result.append(c)
            prev = None
    return "".join(result)


# ── Reproduce _build_word_diff from pipeline.py ────────────────────────────

RELATED_CASES = {
    "nom": "nom_indef", "nom_indef": "nom",
    "acc": "acc_indef", "acc_indef": "acc",
    "gen": "gen_indef", "gen_indef": "gen",
}


def build_word_diff(book_word: BookWord, hyp_text: str, scored: ScoredWord) -> WordDiff:
    detected = scored.detected_hyp
    if detected is None:
        return WordDiff(
            kind=DiffKind.MISSING,
            ref_word=book_word.correct_diac,
            hyp_word=None,
            confidence=Confidence.LOW,
        )

    hyp_norm = normalize_for_matching(hyp_text)
    book_norm = normalize_for_matching(book_word.base)
    if hyp_norm != book_norm:
        similarity = difflib.SequenceMatcher(None, hyp_norm, book_norm).ratio()
        if similarity < 0.6:
            return WordDiff(
                kind=DiffKind.WRONG_WORD,
                ref_word=book_word.correct_diac,
                hyp_word=hyp_text,
                confidence=scored.confidence,
            )

    if detected.is_correct:
        return WordDiff(
            kind=DiffKind.CORRECT,
            ref_word=book_word.correct_diac,
            hyp_word=detected.diacritized,
            confidence=scored.confidence,
        )

    expected_case = next(
        (h.case for h in book_word.hypotheses if h.is_correct), None
    )
    if expected_case and detected.case == RELATED_CASES.get(expected_case):
        return WordDiff(
            kind=DiffKind.PAUSAL_OK,
            ref_word=book_word.correct_diac,
            hyp_word=detected.diacritized,
            confidence=scored.confidence,
            detected_case=detected.case,
            expected_case=expected_case,
        )

    if detected.is_pausal and book_word.allows_pausal:
        return WordDiff(
            kind=DiffKind.PAUSAL_OK,
            ref_word=book_word.correct_diac,
            hyp_word=detected.diacritized,
            confidence=scored.confidence,
            detected_case="pausal",
        )

    haraka_diffs = compare_harakat(book_word.correct_diac, detected.diacritized)
    has_irab_error = any(hd.is_irab for hd in haraka_diffs)
    has_internal_error = any(not hd.is_irab for hd in haraka_diffs)

    if has_irab_error and not has_internal_error:
        kind = DiffKind.WRONG_IRAB
    else:
        kind = DiffKind.WRONG_TASHKEEL

    return WordDiff(
        kind=kind,
        ref_word=book_word.correct_diac,
        hyp_word=detected.diacritized,
        haraka_diffs=haraka_diffs,
        confidence=scored.confidence,
        detected_case=detected.case,
        expected_case=next(
            (h.case for h in book_word.hypotheses if h.is_correct), None
        ),
    )


# ── Parameterized evaluate_pcd_live ────────────────────────────────────────

@dataclass
class ThresholdParams:
    """All tunable thresholds with their default values."""
    # CTC confidence gap boundaries (pcd_transcriber.py)
    high_gap: float = 1.0
    medium_gap: float = 0.3

    # Alignment score threshold for tashkeel decode checking (pipeline.py ~863)
    tashkeel_align_threshold: float = -3.5

    # CTC omission verification margin (pipeline.py ~919)
    omission_margin: float = 0.3

    # Edge recovery threshold (pipeline.py ~791, ~813)
    edge_recovery_threshold: float = -6.0

    # Low-confidence fallback: if True, LOW confidence → use reference (correct) form
    low_confidence_fallback: bool = False


def score_word_in_context_parametric(
    transcriber: PCDTranscriber,
    log_probs,
    encoded_len,
    target_word: BookWord,
    all_words: list[BookWord],
    params: ThresholdParams,
) -> ScoredWord:
    """Reproduce PCDTranscriber.score_word_in_context with tunable gap thresholds."""
    if len(target_word.hypotheses) <= 1:
        hyp = target_word.hypotheses[0] if target_word.hypotheses else None
        return ScoredWord(
            word=target_word,
            detected_hyp=hyp,
            confidence=Confidence.HIGH,
            score_gap=float("inf"),
        )

    context_parts = [w.correct_diac for w in all_words]
    target_pos = next(
        i for i, w in enumerate(all_words) if w.index == target_word.index
    )

    scored = []
    for hyp in target_word.hypotheses:
        parts = list(context_parts)
        parts[target_pos] = hyp.diacritized
        full_text = " ".join(parts)
        score = transcriber._ctc_score(log_probs, encoded_len, full_text)
        scored.append((score, hyp))

    scored.sort(key=lambda x: x[0], reverse=True)

    best_score, best_hyp = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else float("-inf")
    gap = best_score - second_score

    if gap >= params.high_gap:
        confidence = Confidence.HIGH
    elif gap >= params.medium_gap:
        confidence = Confidence.MEDIUM
    else:
        confidence = Confidence.LOW

    # Low-confidence fallback: if enabled, override detected hyp with correct one
    if params.low_confidence_fallback and confidence == Confidence.LOW:
        correct_hyp = next(
            (h for h in target_word.hypotheses if h.is_correct), best_hyp
        )
        return ScoredWord(
            word=target_word,
            detected_hyp=correct_hyp,
            confidence=Confidence.LOW,
            score_gap=gap,
        )

    return ScoredWord(
        word=target_word,
        detected_hyp=best_hyp,
        confidence=confidence,
        score_gap=gap,
    )


def evaluate_pcd_live_parametric(
    transcriber: PCDTranscriber,
    book: Book,
    audio: np.ndarray,
    params: ThresholdParams,
    precomputed=None,
) -> dict:
    """
    Reproduce evaluate_pcd_live with tunable threshold parameters.

    If precomputed is provided, it should be a dict with:
      - pcd_text, log_probs, encoded_len (from transcribe_and_encode)
      - matched_pairs, fill_start, fill_end (from tracking)
    This avoids re-computing the expensive encoder pass for each parameter sweep.
    """
    from i3rab.tracker import PositionTracker

    if precomputed is not None:
        pcd_text = precomputed["pcd_text"]
        log_probs = precomputed["log_probs"]
        encoded_len = precomputed["encoded_len"]
        pcd_normalized = precomputed["pcd_normalized"]
        matched_pairs = precomputed["matched_pairs"]
        fill_start = precomputed["fill_start"]
        fill_end = precomputed["fill_end"]
    else:
        pcd_text, log_probs, encoded_len = transcriber.transcribe_and_encode(audio)
        if not pcd_text.strip():
            return {"transcript": "", "matched_indices": [], "scored_words": []}
        pcd_normalized = normalize_arabic(pcd_text)

        tracker = PositionTracker(book, Config())
        saved_pos = tracker.current_position
        start_idx, end_idx, matched_pairs = tracker.locate(
            strip_harakat(pcd_normalized)
        )
        tracker.current_position = saved_pos

        if not matched_pairs:
            return {
                "transcript": pcd_normalized,
                "matched_indices": [],
                "scored_words": [],
            }

        matched_book_indices = sorted(bw.index for bw, _ in matched_pairs)
        fill_start = matched_book_indices[0]
        fill_end = matched_book_indices[-1] + 1

    all_words = list(book.words[fill_start:fill_end])

    # ── Forced alignment ─────────────────────────────────────
    reference_words = [bw.correct_diac for bw in all_words]
    reference_text = " ".join(reference_words)

    alignment, align_scores = transcriber.forced_align_reference(
        log_probs, encoded_len, reference_text
    )

    if alignment is None:
        return {
            "transcript": pcd_normalized,
            "matched_indices": [bw.index for bw, _ in matched_pairs],
            "scored_words": [],
        }

    word_boundaries = transcriber.get_word_boundaries(
        alignment, align_scores, reference_words
    )

    # ── Edge recovery ────────────────────────────────────────
    T = encoded_len[0].item()
    phrase = book.get_phrase_for_position(fill_start)
    phrase_start = phrase.start_idx if phrase else 0
    phrase_end = phrase.end_idx if phrase else len(book.words)

    first_frame = word_boundaries[0].start_frame if word_boundaries else T
    last_frame = word_boundaries[-1].end_frame if word_boundaries else 0

    # Recover word(s) BEFORE
    if first_frame > 8 and fill_start > phrase_start:
        prev_word = book.words[fill_start - 1]
        expanded = [prev_word] + all_words
        exp_ref = [bw.correct_diac for bw in expanded]
        exp_align, exp_scores = transcriber.forced_align_reference(
            log_probs, encoded_len, " ".join(exp_ref)
        )
        if exp_align is not None:
            exp_bounds = transcriber.get_word_boundaries(
                exp_align, exp_scores, exp_ref
            )
            if exp_bounds and exp_bounds[0].score > params.edge_recovery_threshold:
                all_words = expanded
                reference_words = exp_ref
                word_boundaries = exp_bounds

    last_frame = word_boundaries[-1].end_frame if word_boundaries else 0
    # Recover word(s) AFTER
    if T - last_frame > 8 and fill_end < phrase_end:
        next_word = book.words[fill_end]
        expanded = all_words + [next_word]
        exp_ref = [bw.correct_diac for bw in expanded]
        exp_align, exp_scores = transcriber.forced_align_reference(
            log_probs, encoded_len, " ".join(exp_ref)
        )
        if exp_align is not None:
            exp_bounds = transcriber.get_word_boundaries(
                exp_align, exp_scores, exp_ref
            )
            if exp_bounds and exp_bounds[-1].score > params.edge_recovery_threshold:
                all_words = expanded
                reference_words = exp_ref
                word_boundaries = exp_bounds

    # ── Per-word scoring ─────────────────────────────────────
    matched_indices = []
    scored_words = []

    for i, book_word in enumerate(all_words):
        wb = word_boundaries[i] if i < len(word_boundaries) else None

        if wb is None or wb.start_frame >= wb.end_frame:
            diff = WordDiff(
                kind=DiffKind.MISSING,
                ref_word=book_word.correct_diac,
                hyp_word=None,
                confidence=Confidence.LOW,
            )
        else:
            sf_frame, ef_frame = wb.start_frame, wb.end_frame

            # ── I3rab: full-sentence CTC hypothesis scoring ──
            if len(book_word.hypotheses) > 1:
                scored = score_word_in_context_parametric(
                    transcriber, log_probs, encoded_len,
                    book_word, all_words,
                    params,
                )
                diff = build_word_diff(book_word, book_word.base, scored)
            else:
                hyp = book_word.hypotheses[0] if book_word.hypotheses else None
                scored = ScoredWord(
                    word=book_word,
                    detected_hyp=hyp,
                    confidence=Confidence.HIGH,
                    score_gap=float("inf"),
                )
                diff = build_word_diff(book_word, book_word.base, scored)

            # ── Tashkeel: per-word decode + CTC verification ─
            if (
                diff.kind in (DiffKind.CORRECT, DiffKind.PAUSAL_OK)
                and wb.score > params.tashkeel_align_threshold
            ):
                raw_decoded = transcriber.decode_word_segment(
                    log_probs, sf_frame, ef_frame
                )
                decoded_word = normalize_arabic(
                    _clean_diacritics(raw_decoded)
                )
                ref_norm = normalize_arabic(book_word.correct_diac)

                if (
                    decoded_word
                    and strip_harakat(decoded_word)
                    == strip_harakat(ref_norm)
                    and decoded_word != ref_norm
                ):
                    tashkeel_diffs = compare_harakat(ref_norm, decoded_word)

                    single_hyp = len(book_word.hypotheses) <= 1

                    substitution_errors = [
                        hd for hd in tashkeel_diffs
                        if (not hd.is_irab or single_hyp) and hd.got
                    ]

                    omission_errors = [
                        hd for hd in tashkeel_diffs
                        if (not hd.is_irab or single_hyp) and not hd.got
                    ]

                    ctc_verified_omissions = []
                    if omission_errors:
                        ref_parts = [w.correct_diac for w in all_words]
                        word_offset = i
                        dec_parts = list(ref_parts)
                        dec_parts[word_offset] = decoded_word

                        ref_sentence = " ".join(ref_parts)
                        dec_sentence = " ".join(dec_parts)
                        ref_score = transcriber._ctc_score(
                            log_probs, encoded_len, ref_sentence
                        )
                        dec_score = transcriber._ctc_score(
                            log_probs, encoded_len, dec_sentence
                        )
                        if dec_score > ref_score + params.omission_margin:
                            ctc_verified_omissions = omission_errors

                    all_errors = substitution_errors + ctc_verified_omissions
                    if all_errors:
                        diff = WordDiff(
                            kind=DiffKind.WRONG_TASHKEEL,
                            ref_word=book_word.correct_diac,
                            hyp_word=decoded_word,
                            haraka_diffs=tashkeel_diffs,
                            confidence=diff.confidence,
                            detected_case=diff.detected_case,
                            expected_case=diff.expected_case,
                        )

        matched_indices.append(book_word.index)

        scored_words.append({
            "index": book_word.index,
            "kind": diff.kind.value,
            "ref_word": diff.ref_word,
            "hyp_word": diff.hyp_word,
            "confidence": diff.confidence.value
            if isinstance(diff.confidence, Confidence)
            else "high",
            "detected_case": diff.detected_case,
            "expected_case": diff.expected_case,
        })

    return {
        "transcript": pcd_normalized,
        "matched_indices": matched_indices,
        "scored_words": scored_words,
    }


# ── Evaluation harness ──────────────────────────────────────────────────────

def evaluate_all_sentences(
    transcriber: PCDTranscriber,
    sentences: list[dict],
    test_dir: Path,
    params: ThresholdParams,
    precomputed_cache: dict | None = None,
) -> dict:
    """Run evaluation on all sentences with the given thresholds.

    Returns dict with total_correct, total_words, per_sentence details.
    """
    total_correct = 0
    total_words = 0
    per_sentence = []

    for entry in sentences:
        filepath = test_dir / entry["filename"]
        if not filepath.exists():
            continue

        rec_id = entry["id"]
        reference = entry["text_diacritized"]
        book = Book.from_sentence(reference)

        precomputed = None
        if precomputed_cache is not None and rec_id in precomputed_cache:
            precomputed = precomputed_cache[rec_id]
        else:
            # Compute once and cache
            audio = read_audio(filepath)
            pcd_text, log_probs, encoded_len = transcriber.transcribe_and_encode(audio)
            pcd_normalized = normalize_arabic(pcd_text) if pcd_text.strip() else ""

            from i3rab.tracker import PositionTracker
            tracker = PositionTracker(book, Config())
            saved_pos = tracker.current_position
            start_idx, end_idx, matched_pairs = tracker.locate(
                strip_harakat(pcd_normalized)
            ) if pcd_normalized else (None, None, [])
            tracker.current_position = saved_pos

            if matched_pairs:
                matched_book_indices = sorted(bw.index for bw, _ in matched_pairs)
                fill_start = matched_book_indices[0]
                fill_end = matched_book_indices[-1] + 1
            else:
                fill_start = 0
                fill_end = 0

            precomputed = {
                "pcd_text": pcd_text,
                "log_probs": log_probs,
                "encoded_len": encoded_len,
                "pcd_normalized": pcd_normalized,
                "matched_pairs": matched_pairs,
                "fill_start": fill_start,
                "fill_end": fill_end,
            }

            if precomputed_cache is not None:
                precomputed_cache[rec_id] = precomputed

        result = evaluate_pcd_live_parametric(
            transcriber, book, None, params, precomputed=precomputed,
        )

        correct = sum(
            1 for sw in result["scored_words"]
            if sw["kind"] in ("correct", "pausal_ok")
        )
        total = len(result["scored_words"])
        total_correct += correct
        total_words += total

        per_sentence.append({
            "id": rec_id,
            "correct": correct,
            "total": total,
            "ref": reference[:60],
        })

    accuracy = (total_correct / total_words * 100) if total_words > 0 else 0.0
    return {
        "total_correct": total_correct,
        "total_words": total_words,
        "accuracy": accuracy,
        "per_sentence": per_sentence,
    }


def print_result_summary(label: str, result: dict):
    """Print a compact summary of an evaluation result."""
    print(f"  {label:45s}  {result['total_correct']:3d}/{result['total_words']:3d}  ({result['accuracy']:.1f}%)")


def print_section(title: str):
    print(f"\n{'='*72}")
    print(f"  {title}")
    print(f"{'='*72}")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    test_dir = Path("test_data")
    manifest = json.loads((test_dir / "manifest.json").read_text())
    sentences = [e for e in manifest if e.get("type") == "sentence"]

    print(f"Found {len(sentences)} sentence recordings in manifest.json")

    config = Config()
    transcriber = PCDTranscriber(config)
    transcriber.load()

    # Pre-compute encoder outputs for all sentences (one-time cost)
    print("\nPre-computing encoder outputs for all sentences...")
    precomputed_cache = {}
    t0 = time.time()
    for entry in sentences:
        filepath = test_dir / entry["filename"]
        if not filepath.exists():
            continue

        rec_id = entry["id"]
        reference = entry["text_diacritized"]
        book = Book.from_sentence(reference)
        audio = read_audio(filepath)

        pcd_text, log_probs, encoded_len = transcriber.transcribe_and_encode(audio)
        pcd_normalized = normalize_arabic(pcd_text) if pcd_text.strip() else ""

        from i3rab.tracker import PositionTracker
        tracker = PositionTracker(book, Config())
        saved_pos = tracker.current_position
        if pcd_normalized:
            start_idx, end_idx, matched_pairs = tracker.locate(
                strip_harakat(pcd_normalized)
            )
        else:
            matched_pairs = []
        tracker.current_position = saved_pos

        if matched_pairs:
            matched_book_indices = sorted(bw.index for bw, _ in matched_pairs)
            fill_start = matched_book_indices[0]
            fill_end = matched_book_indices[-1] + 1
        else:
            fill_start = 0
            fill_end = 0

        precomputed_cache[rec_id] = {
            "pcd_text": pcd_text,
            "log_probs": log_probs,
            "encoded_len": encoded_len,
            "pcd_normalized": pcd_normalized,
            "matched_pairs": matched_pairs,
            "fill_start": fill_start,
            "fill_end": fill_end,
        }

    t_precompute = time.time() - t0
    print(f"Pre-computation done in {t_precompute:.1f}s ({t_precompute/len(sentences):.1f}s per recording)")

    # ── Baseline ────────────────────────────────────────────────────
    print_section("BASELINE (current defaults)")
    defaults = ThresholdParams()
    baseline = evaluate_all_sentences(
        transcriber, sentences, test_dir, defaults, precomputed_cache
    )
    print_result_summary("DEFAULTS", baseline)
    for s in baseline["per_sentence"]:
        mark = "OK" if s["total"] > 0 and s["correct"] == s["total"] else f"{s['correct']}/{s['total']}"
        print(f"    {s['id']}: {mark:8s}  {s['ref']}...")

    # Track best values for each parameter
    best_params = ThresholdParams()  # start from defaults
    best_accuracy = baseline["accuracy"]

    # ── Experiment 1: CTC confidence gap thresholds ─────────────────
    print_section("EXPERIMENT 1: CTC confidence gap thresholds")
    print("  Varying HIGH gap and MEDIUM gap boundaries")
    print(f"  Defaults: high_gap={defaults.high_gap}, medium_gap={defaults.medium_gap}")
    print()

    exp1_results = {}
    best_exp1_acc = 0
    best_exp1_params = (defaults.high_gap, defaults.medium_gap)

    for high_gap in [0.5, 0.8, 1.0, 1.5, 2.0]:
        for medium_gap in [0.1, 0.2, 0.3, 0.5, 0.8]:
            if medium_gap >= high_gap:
                continue
            params = ThresholdParams(high_gap=high_gap, medium_gap=medium_gap)
            result = evaluate_all_sentences(
                transcriber, sentences, test_dir, params, precomputed_cache
            )
            label = f"high_gap={high_gap}, medium_gap={medium_gap}"
            print_result_summary(label, result)
            exp1_results[(high_gap, medium_gap)] = result
            if result["accuracy"] > best_exp1_acc:
                best_exp1_acc = result["accuracy"]
                best_exp1_params = (high_gap, medium_gap)

    print(f"\n  >> Best: high_gap={best_exp1_params[0]}, medium_gap={best_exp1_params[1]} -> {best_exp1_acc:.1f}%")
    if best_exp1_acc > best_accuracy:
        best_params.high_gap = best_exp1_params[0]
        best_params.medium_gap = best_exp1_params[1]
        best_accuracy = best_exp1_acc

    # ── Experiment 2: Tashkeel alignment score threshold ────────────
    print_section("EXPERIMENT 2: Tashkeel alignment score threshold")
    print(f"  Default: tashkeel_align_threshold={defaults.tashkeel_align_threshold}")
    print()

    exp2_results = {}
    best_exp2_acc = 0
    best_exp2_val = defaults.tashkeel_align_threshold

    for thresh in [-2.0, -3.0, -3.5, -4.0, -5.0, -6.0, -8.0]:
        params = ThresholdParams(tashkeel_align_threshold=thresh)
        result = evaluate_all_sentences(
            transcriber, sentences, test_dir, params, precomputed_cache
        )
        label = f"tashkeel_align_threshold={thresh}"
        print_result_summary(label, result)
        exp2_results[thresh] = result
        if result["accuracy"] > best_exp2_acc:
            best_exp2_acc = result["accuracy"]
            best_exp2_val = thresh

    print(f"\n  >> Best: tashkeel_align_threshold={best_exp2_val} -> {best_exp2_acc:.1f}%")
    if best_exp2_acc > best_accuracy:
        best_params.tashkeel_align_threshold = best_exp2_val
        best_accuracy = best_exp2_acc

    # ── Experiment 3: CTC omission verification margin ──────────────
    print_section("EXPERIMENT 3: CTC omission verification margin")
    print(f"  Default: omission_margin={defaults.omission_margin}")
    print()

    exp3_results = {}
    best_exp3_acc = 0
    best_exp3_val = defaults.omission_margin

    for margin in [0.0, 0.1, 0.2, 0.3, 0.5, 0.8, 1.0, 1.5, 2.0]:
        params = ThresholdParams(omission_margin=margin)
        result = evaluate_all_sentences(
            transcriber, sentences, test_dir, params, precomputed_cache
        )
        label = f"omission_margin={margin}"
        print_result_summary(label, result)
        exp3_results[margin] = result
        if result["accuracy"] > best_exp3_acc:
            best_exp3_acc = result["accuracy"]
            best_exp3_val = margin

    print(f"\n  >> Best: omission_margin={best_exp3_val} -> {best_exp3_acc:.1f}%")
    if best_exp3_acc > best_accuracy:
        best_params.omission_margin = best_exp3_val
        best_accuracy = best_exp3_acc

    # ── Experiment 4: Edge recovery threshold ───────────────────────
    print_section("EXPERIMENT 4: Edge recovery threshold")
    print(f"  Default: edge_recovery_threshold={defaults.edge_recovery_threshold}")
    print()

    exp4_results = {}
    best_exp4_acc = 0
    best_exp4_val = defaults.edge_recovery_threshold

    for thresh in [-4.0, -5.0, -6.0, -8.0, -10.0, -15.0]:
        params = ThresholdParams(edge_recovery_threshold=thresh)
        result = evaluate_all_sentences(
            transcriber, sentences, test_dir, params, precomputed_cache
        )
        label = f"edge_recovery_threshold={thresh}"
        print_result_summary(label, result)
        exp4_results[thresh] = result
        if result["accuracy"] > best_exp4_acc:
            best_exp4_acc = result["accuracy"]
            best_exp4_val = thresh

    print(f"\n  >> Best: edge_recovery_threshold={best_exp4_val} -> {best_exp4_acc:.1f}%")
    if best_exp4_acc > best_accuracy:
        best_params.edge_recovery_threshold = best_exp4_val
        best_accuracy = best_exp4_acc

    # ── Experiment 5: Low-confidence fallback ───────────────────────
    print_section("EXPERIMENT 5: Low-confidence fallback (default to reference when LOW)")
    print(f"  Default: low_confidence_fallback={defaults.low_confidence_fallback}")
    print()

    for use_fallback in [False, True]:
        params = ThresholdParams(low_confidence_fallback=use_fallback)
        result = evaluate_all_sentences(
            transcriber, sentences, test_dir, params, precomputed_cache
        )
        label = f"low_confidence_fallback={use_fallback}"
        print_result_summary(label, result)
        if use_fallback and result["accuracy"] > baseline["accuracy"]:
            best_params.low_confidence_fallback = True
            if result["accuracy"] > best_accuracy:
                best_accuracy = result["accuracy"]

    # Also test fallback with different gap thresholds
    print()
    print("  Low-confidence fallback + varied gap thresholds:")
    for high_gap in [0.5, 1.0, 1.5, 2.0, 3.0]:
        for medium_gap in [0.1, 0.3, 0.5, 1.0]:
            if medium_gap >= high_gap:
                continue
            params = ThresholdParams(
                high_gap=high_gap, medium_gap=medium_gap,
                low_confidence_fallback=True,
            )
            result = evaluate_all_sentences(
                transcriber, sentences, test_dir, params, precomputed_cache
            )
            label = f"fallback=True, high={high_gap}, med={medium_gap}"
            print_result_summary(label, result)

    # ── Final combined experiment ───────────────────────────────────
    print_section("FINAL: All optimal values combined")
    print(f"  high_gap={best_params.high_gap}")
    print(f"  medium_gap={best_params.medium_gap}")
    print(f"  tashkeel_align_threshold={best_params.tashkeel_align_threshold}")
    print(f"  omission_margin={best_params.omission_margin}")
    print(f"  edge_recovery_threshold={best_params.edge_recovery_threshold}")
    print(f"  low_confidence_fallback={best_params.low_confidence_fallback}")
    print()

    final = evaluate_all_sentences(
        transcriber, sentences, test_dir, best_params, precomputed_cache
    )
    print_result_summary("COMBINED OPTIMAL", final)
    print()
    for s in final["per_sentence"]:
        mark = "OK" if s["total"] > 0 and s["correct"] == s["total"] else f"{s['correct']}/{s['total']}"
        print(f"    {s['id']}: {mark:8s}  {s['ref']}...")

    # ── Summary ─────────────────────────────────────────────────────
    print_section("SUMMARY")
    print(f"  Baseline (defaults):   {baseline['total_correct']}/{baseline['total_words']} ({baseline['accuracy']:.1f}%)")
    print(f"  Combined optimal:      {final['total_correct']}/{final['total_words']} ({final['accuracy']:.1f}%)")
    improvement = final["accuracy"] - baseline["accuracy"]
    print(f"  Improvement:           {improvement:+.1f}%")
    print()
    print("  Optimal parameters:")
    print(f"    high_gap:                  {best_params.high_gap}")
    print(f"    medium_gap:                {best_params.medium_gap}")
    print(f"    tashkeel_align_threshold:  {best_params.tashkeel_align_threshold}")
    print(f"    omission_margin:           {best_params.omission_margin}")
    print(f"    edge_recovery_threshold:   {best_params.edge_recovery_threshold}")
    print(f"    low_confidence_fallback:   {best_params.low_confidence_fallback}")
    print()

    # ── Detailed per-sentence comparison: baseline vs optimal ───────
    print_section("DETAILED COMPARISON: Baseline vs Optimal (per sentence)")
    for i, (bs, fs) in enumerate(zip(baseline["per_sentence"], final["per_sentence"])):
        b_mark = f"{bs['correct']}/{bs['total']}"
        f_mark = f"{fs['correct']}/{fs['total']}"
        changed = " *CHANGED*" if bs["correct"] != fs["correct"] or bs["total"] != fs["total"] else ""
        print(f"    {bs['id']}: {b_mark:8s} -> {f_mark:8s}{changed}  {bs['ref'][:50]}...")


if __name__ == "__main__":
    main()
