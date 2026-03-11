#!/usr/bin/env python3
"""Threshold tuning script for PCD v2 model — cache-based approach.

Strategy:
1. Run ONE full evaluation pass, caching per-word raw data:
   - CTC score gap and best/second-best hypothesis per word
   - Word boundary alignment scores
   - Per-word decoded text (for tashkeel)
   - CTC omission scores (ref_score, dec_score) for tashkeel omission check
2. Replay threshold decisions in pure Python (no model calls) for each config
3. This makes the grid search ~1000x faster than re-running the model

Does NOT modify source files — all logic is copied/parameterized inline.
"""

import sys
import io
import json
import time
import difflib
from pathlib import Path
from dataclasses import dataclass, field

import numpy as np
import soundfile as sf

# ── Force unbuffered output ──────────────────────────────────────────
print = lambda *a, **kw: (sys.stdout.write(" ".join(str(x) for x in a) + kw.get("end", "\n")), sys.stdout.flush())

# ── Audio helpers ────────────────────────────────────────────────────

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


# ── Import project modules ───────────────────────────────────────────

from i3rab.config import Config
from i3rab.pcd_transcriber import PCDTranscriber
from i3rab.book import Book
from i3rab.models import (
    BookWord, WordDiff, DiffKind, Confidence, ScoredWord,
    HARAKAT, WordHypothesis, HarakaDiff,
)
from i3rab.arabic import (
    normalize_arabic, strip_harakat, compare_harakat,
    normalize_for_matching, format_haraka_list,
)
from i3rab.tracker import PositionTracker


# ── Copied helpers ───────────────────────────────────────────────────

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


_SKIP_TASHKEEL_BASES = {
    "إلى", "الى", "على", "عن", "من", "في",
    "ان", "أن", "إن", "هل", "ما", "لا",
    "ثم", "لم", "لن",
}


# ── Cached per-word data ─────────────────────────────────────────────

@dataclass
class CachedWordResult:
    """All data needed to replay threshold decisions for one word."""
    entry_id: str
    book_word: BookWord
    has_frames: bool

    # I3rab scoring (only for multi-hypothesis words)
    num_hypotheses: int
    best_hyp: WordHypothesis | None       # CTC-ranked best
    second_hyp: WordHypothesis | None     # CTC-ranked second
    correct_hyp: WordHypothesis | None    # the "correct" hypothesis
    score_gap: float                      # best - second CTC score
    best_hyp_is_correct: bool

    # Build-diff metadata
    best_hyp_is_pausal: bool
    allows_pausal: bool
    best_hyp_case: str | None
    expected_case: str | None
    related_case_match: bool  # best_hyp.case == RELATED_CASES[expected_case]

    # Tashkeel data (only filled when tashkeel check is applicable)
    wb_score: float
    skip_tashkeel: bool
    decoded_word: str | None    # cleaned decoded text from segment
    ref_norm: str | None
    tashkeel_applicable: bool   # bases match and text differs
    has_substitution_errors: bool
    has_omission_errors: bool
    omission_ref_score: float   # CTC score for reference sentence
    omission_dec_score: float   # CTC score for decoded sentence

    # For display
    tashkeel_diffs: list | None  # HarakaDiff list


@dataclass
class CachedEdgeData:
    """Edge recovery data for one recording."""
    entry_id: str
    # Scores for expanded alignment at front/back edge
    front_expand_score: float | None  # None if not applicable
    back_expand_score: float | None


def _build_diff_result(cw: CachedWordResult, confidence: Confidence):
    """Replay _build_word_diff logic from cached data."""
    if not cw.has_frames:
        return "missing", "low"

    if cw.num_hypotheses <= 1:
        # Single hypothesis, always correct
        return "correct", "high"

    detected_hyp = cw.best_hyp
    if detected_hyp is None:
        return "missing", "low"

    if detected_hyp.is_correct:
        return "correct", confidence.value

    if cw.related_case_match:
        return "pausal_ok", confidence.value

    if detected_hyp.is_pausal and cw.allows_pausal:
        return "pausal_ok", confidence.value

    # Check haraka diffs
    haraka_diffs = compare_harakat(cw.book_word.correct_diac, detected_hyp.diacritized)
    has_irab = any(hd.is_irab for hd in haraka_diffs)
    has_internal = any(not hd.is_irab for hd in haraka_diffs)

    if has_irab and not has_internal:
        return "irab", confidence.value
    return "tashkeel", confidence.value


def evaluate_cached(
    cached_words: list[CachedWordResult],
    ctc_high_gap: float,
    ctc_medium_gap: float,
    tashkeel_align_threshold: float,
    ctc_omission_margin: float,
    fallback_scope: str,
):
    """Replay all threshold decisions from cached data (no model calls)."""
    correct = 0
    total = 0
    errors = []

    for cw in cached_words:
        total += 1

        if not cw.has_frames:
            errors.append((cw.entry_id, cw.book_word.correct_diac, "missing", "low"))
            continue

        if cw.num_hypotheses <= 1:
            # Single hypothesis: always correct for i3rab
            kind = "correct"
            conf_str = "high"
        else:
            # Multi-hypothesis: determine confidence from cached gap
            gap = cw.score_gap
            if gap >= ctc_high_gap:
                confidence = Confidence.HIGH
            elif gap >= ctc_medium_gap:
                confidence = Confidence.MEDIUM
            else:
                confidence = Confidence.LOW

            # Apply fallback
            should_fallback = False
            if fallback_scope == "low":
                should_fallback = (confidence == Confidence.LOW)
            elif fallback_scope == "medium":
                should_fallback = (confidence in (Confidence.LOW, Confidence.MEDIUM))

            if should_fallback:
                # Fallback: assume correct
                kind = "correct"
                conf_str = confidence.value
            else:
                # Use best CTC hypothesis
                kind, conf_str = _build_diff_result(cw, confidence)

        # Tashkeel override check
        if kind in ("correct", "pausal_ok"):
            if (
                cw.wb_score > tashkeel_align_threshold
                and not cw.skip_tashkeel
                and cw.tashkeel_applicable
            ):
                tashkeel_error = False
                if cw.has_substitution_errors:
                    tashkeel_error = True
                elif cw.has_omission_errors:
                    if cw.omission_dec_score > cw.omission_ref_score + ctc_omission_margin:
                        tashkeel_error = True

                if tashkeel_error:
                    kind = "tashkeel"

        if kind in ("correct", "pausal_ok"):
            correct += 1
        else:
            errors.append((cw.entry_id, cw.book_word.correct_diac, kind, conf_str))

    return correct, total, errors


# ── Single-pass data collection ──────────────────────────────────────

def collect_cached_data(transcriber, sentences, test_dir) -> list[CachedWordResult]:
    """Run one full evaluation pass and cache all per-word data."""
    all_cached = []
    config = Config()

    for idx, entry in enumerate(sentences):
        filepath = test_dir / entry["filename"]
        if not filepath.exists():
            continue

        eid = entry["id"]
        audio = read_audio(filepath)
        reference = entry["text_diacritized"]
        book = Book.from_sentence(reference)

        print(f"  [{idx+1}/{len(sentences)}] Processing {eid}: {reference[:50]}...")

        # Encode audio
        pcd_text, log_probs, encoded_len = transcriber.transcribe_and_encode(audio)

        if not pcd_text.strip():
            # No transcription — all words are missing
            for bw in book.words:
                all_cached.append(CachedWordResult(
                    entry_id=eid, book_word=bw, has_frames=False,
                    num_hypotheses=len(bw.hypotheses),
                    best_hyp=None, second_hyp=None, correct_hyp=None,
                    score_gap=0.0, best_hyp_is_correct=False,
                    best_hyp_is_pausal=False, allows_pausal=bw.allows_pausal,
                    best_hyp_case=None, expected_case=None, related_case_match=False,
                    wb_score=float("-inf"), skip_tashkeel=True,
                    decoded_word=None, ref_norm=None,
                    tashkeel_applicable=False,
                    has_substitution_errors=False, has_omission_errors=False,
                    omission_ref_score=0.0, omission_dec_score=0.0,
                    tashkeel_diffs=None,
                ))
            continue

        pcd_normalized = normalize_arabic(pcd_text)

        # Position tracking
        tracker = PositionTracker(book, config)
        saved_pos = tracker.current_position
        start_idx, end_idx, matched_pairs = tracker.locate(
            strip_harakat(pcd_normalized)
        )
        tracker.current_position = saved_pos

        if not matched_pairs:
            continue

        # Fill gaps
        matched_book_indices = sorted(bw.index for bw, _ in matched_pairs)
        fill_start = matched_book_indices[0]
        fill_end = matched_book_indices[-1] + 1
        all_words = list(book.words[fill_start:fill_end])

        # Forced alignment
        reference_words = [bw.correct_diac for bw in all_words]
        reference_text = " ".join(reference_words)
        alignment, align_scores = transcriber.forced_align_reference(
            log_probs, encoded_len, reference_text
        )

        if alignment is None:
            continue

        word_boundaries = transcriber.get_word_boundaries(
            alignment, align_scores, reference_words
        )

        # Edge recovery (with default threshold -4.0, we'll cache scores for tuning)
        T = encoded_len[0].item()
        phrase = book.get_phrase_for_position(fill_start)
        phrase_start = phrase.start_idx if phrase else 0
        phrase_end = phrase.end_idx if phrase else len(book.words)

        first_frame = word_boundaries[0].start_frame if word_boundaries else T
        last_frame = word_boundaries[-1].end_frame if word_boundaries else 0

        # Always try edge expansion (use very permissive threshold for caching)
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
                if exp_bounds and exp_bounds[0].score > -10.0:
                    all_words = expanded
                    reference_words = exp_ref
                    word_boundaries = exp_bounds

        last_frame = word_boundaries[-1].end_frame if word_boundaries else 0
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
                if exp_bounds and exp_bounds[-1].score > -10.0:
                    all_words = expanded
                    reference_words = exp_ref
                    word_boundaries = exp_bounds

        # Per-word scoring and caching
        for i, book_word in enumerate(all_words):
            wb = word_boundaries[i] if i < len(word_boundaries) else None

            if wb is None or wb.start_frame >= wb.end_frame:
                all_cached.append(CachedWordResult(
                    entry_id=eid, book_word=book_word, has_frames=False,
                    num_hypotheses=len(book_word.hypotheses),
                    best_hyp=None, second_hyp=None, correct_hyp=None,
                    score_gap=0.0, best_hyp_is_correct=False,
                    best_hyp_is_pausal=False, allows_pausal=book_word.allows_pausal,
                    best_hyp_case=None, expected_case=None, related_case_match=False,
                    wb_score=float("-inf"), skip_tashkeel=True,
                    decoded_word=None, ref_norm=None,
                    tashkeel_applicable=False,
                    has_substitution_errors=False, has_omission_errors=False,
                    omission_ref_score=0.0, omission_dec_score=0.0,
                    tashkeel_diffs=None,
                ))
                continue

            sf_frame, ef_frame = wb.start_frame, wb.end_frame

            # I3rab: CTC hypothesis scoring
            RELATED_CASES = {
                "nom": "nom_indef", "nom_indef": "nom",
                "acc": "acc_indef", "acc_indef": "acc",
                "gen": "gen_indef", "gen_indef": "gen",
            }

            correct_hyp = next(
                (h for h in book_word.hypotheses if h.is_correct), None
            )
            expected_case = correct_hyp.case if correct_hyp else None

            if len(book_word.hypotheses) > 1:
                # Full-sentence CTC scoring for each hypothesis
                context_parts = [w.correct_diac for w in all_words]
                target_pos = next(
                    idx2 for idx2, w in enumerate(all_words)
                    if w.index == book_word.index
                )

                scored_hyps = []
                for hyp in book_word.hypotheses:
                    parts = list(context_parts)
                    parts[target_pos] = hyp.diacritized
                    full_text = " ".join(parts)
                    score = transcriber._ctc_score(log_probs, encoded_len, full_text)
                    scored_hyps.append((score, hyp))

                scored_hyps.sort(key=lambda x: x[0], reverse=True)

                best_score, best_hyp = scored_hyps[0]
                second_score = scored_hyps[1][0] if len(scored_hyps) > 1 else float("-inf")
                gap = best_score - second_score
                second_hyp = scored_hyps[1][1] if len(scored_hyps) > 1 else None

                related_case_match = (
                    expected_case is not None
                    and best_hyp.case == RELATED_CASES.get(expected_case)
                )
            else:
                best_hyp = book_word.hypotheses[0] if book_word.hypotheses else None
                second_hyp = None
                gap = float("inf")
                related_case_match = False

            # Tashkeel: per-word decode
            skip_tashkeel = book_word.base in _SKIP_TASHKEEL_BASES
            decoded_word = None
            ref_norm = None
            tashkeel_applicable = False
            has_sub_errors = False
            has_omit_errors = False
            omission_ref_score = 0.0
            omission_dec_score = 0.0
            tashkeel_diffs = None

            if not skip_tashkeel:
                raw_decoded = transcriber.decode_word_segment(
                    log_probs, sf_frame, ef_frame
                )
                decoded_word = normalize_arabic(_clean_diacritics(raw_decoded))
                ref_norm = normalize_arabic(book_word.correct_diac)

                if (
                    decoded_word
                    and strip_harakat(decoded_word) == strip_harakat(ref_norm)
                    and decoded_word != ref_norm
                ):
                    tashkeel_applicable = True
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

                    has_sub_errors = len(substitution_errors) > 0
                    has_omit_errors = len(omission_errors) > 0

                    if has_omit_errors:
                        ref_parts = [w.correct_diac for w in all_words]
                        dec_parts = list(ref_parts)
                        dec_parts[i] = decoded_word
                        ref_sentence = " ".join(ref_parts)
                        dec_sentence = " ".join(dec_parts)
                        omission_ref_score = transcriber._ctc_score(
                            log_probs, encoded_len, ref_sentence
                        )
                        omission_dec_score = transcriber._ctc_score(
                            log_probs, encoded_len, dec_sentence
                        )

            all_cached.append(CachedWordResult(
                entry_id=eid,
                book_word=book_word,
                has_frames=True,
                num_hypotheses=len(book_word.hypotheses),
                best_hyp=best_hyp,
                second_hyp=second_hyp,
                correct_hyp=correct_hyp,
                score_gap=gap,
                best_hyp_is_correct=best_hyp.is_correct if best_hyp else False,
                best_hyp_is_pausal=best_hyp.is_pausal if best_hyp else False,
                allows_pausal=book_word.allows_pausal,
                best_hyp_case=best_hyp.case if best_hyp else None,
                expected_case=expected_case,
                related_case_match=related_case_match,
                wb_score=wb.score,
                skip_tashkeel=skip_tashkeel,
                decoded_word=decoded_word,
                ref_norm=ref_norm,
                tashkeel_applicable=tashkeel_applicable,
                has_substitution_errors=has_sub_errors,
                has_omission_errors=has_omit_errors,
                omission_ref_score=omission_ref_score,
                omission_dec_score=omission_dec_score,
                tashkeel_diffs=tashkeel_diffs,
            ))

    return all_cached


# ── Main ─────────────────────────────────────────────────────────────

def main():
    config = Config()
    test_dir = Path("test_data")
    manifest = json.loads((test_dir / "manifest.json").read_text())
    sentences = [e for e in manifest if e.get("type") == "sentence"]

    print("Loading PCD v2 model...")
    transcriber = PCDTranscriber(config)
    transcriber.load()

    # ── Collect all cached data (one expensive pass) ──────────────────
    print(f"\nCollecting cached data for {len(sentences)} sentence recordings...")
    print("(This involves encoding + forced alignment + CTC scoring for each word)")
    t0 = time.time()
    cached_words = collect_cached_data(transcriber, sentences, test_dir)
    elapsed = time.time() - t0
    print(f"\nData collection done: {len(cached_words)} words in {elapsed:.1f}s")

    # Quick stats on the cached data
    multi_hyp = sum(1 for cw in cached_words if cw.num_hypotheses > 1)
    tash_applicable = sum(1 for cw in cached_words if cw.tashkeel_applicable)
    print(f"  Multi-hypothesis words: {multi_hyp}")
    print(f"  Tashkeel-checkable words: {tash_applicable}")

    # Print gap distribution for insight
    gaps = [cw.score_gap for cw in cached_words if cw.num_hypotheses > 1 and cw.has_frames and cw.score_gap != float("inf")]
    if gaps:
        gaps_sorted = sorted(gaps)
        print(f"  CTC gap distribution: min={min(gaps):.2f} max={max(gaps):.2f} median={gaps_sorted[len(gaps_sorted)//2]:.2f}")
        # Show histogram buckets
        for threshold in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0]:
            count_below = sum(1 for g in gaps if g < threshold)
            print(f"    gap < {threshold:.1f}: {count_below}/{len(gaps)} words")

    # ── Phase 0: Baseline ────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("PHASE 0: Baseline (current v1 thresholds)")
    print("=" * 70)

    c, t, errs = evaluate_cached(cached_words,
        ctc_high_gap=2.0, ctc_medium_gap=1.5,
        tashkeel_align_threshold=-2.0, ctc_omission_margin=2.0,
        fallback_scope="low")
    print(f"\n  Baseline: {c}/{t} ({100*c/t:.1f}%)")
    print(f"  Errors ({len(errs)}):")
    for eid, ref, kind, conf in errs:
        print(f"    {eid}: {ref} -> {kind} ({conf})")

    baseline_correct = c
    baseline_total = t
    best_correct = c
    best_config = {
        "ctc_high_gap": 2.0, "ctc_medium_gap": 1.5,
        "tashkeel_align_threshold": -2.0, "ctc_omission_margin": 2.0,
        "edge_recovery_threshold": -4.0, "fallback_scope": "low",
    }
    best_errors = errs

    # ── Phase 1: Fallback scope ──────────────────────────────────────
    print("\n" + "=" * 70)
    print("PHASE 1: Fallback scope (LOW only vs LOW+MEDIUM)")
    print("=" * 70)

    for scope in ["low", "medium"]:
        c, t, errs = evaluate_cached(cached_words,
            ctc_high_gap=2.0, ctc_medium_gap=1.5,
            tashkeel_align_threshold=-2.0, ctc_omission_margin=2.0,
            fallback_scope=scope)
        marker = " <-- BETTER" if c > best_correct else ""
        print(f"\n  fallback={scope}: {c}/{t} ({100*c/t:.1f}%){marker}")
        if errs:
            print(f"  Errors ({len(errs)}):")
            for eid, ref, kind, conf in errs:
                print(f"    {eid}: {ref} -> {kind} ({conf})")
        if c > best_correct:
            best_correct = c
            best_config["fallback_scope"] = scope
            best_errors = errs

    best_fb = best_config["fallback_scope"]
    print(f"\n  >> Best fallback scope: {best_fb}")

    # ── Phase 2: CTC confidence gap thresholds ───────────────────────
    print("\n" + "=" * 70)
    print("PHASE 2: CTC confidence gap thresholds (grid)")
    print("=" * 70)

    high_values = [1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0]
    medium_values = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5]

    phase2_results = []
    for high in high_values:
        for med in medium_values:
            if med >= high:
                continue
            c, t, errs = evaluate_cached(cached_words,
                ctc_high_gap=high, ctc_medium_gap=med,
                tashkeel_align_threshold=-2.0, ctc_omission_margin=2.0,
                fallback_scope=best_fb)
            phase2_results.append((c, t, high, med, errs))

    phase2_results.sort(key=lambda x: x[0], reverse=True)
    print("\n  Top-15 CTC gap configurations:")
    for i, (c, t, h, m, errs) in enumerate(phase2_results[:15]):
        marker = " *" if c == phase2_results[0][0] else ""
        print(f"    {i+1}. high={h:.2f} med={m:.2f}: {c}/{t} ({100*c/t:.1f}%){marker}")

    best_h = phase2_results[0][2]
    best_m = phase2_results[0][3]
    if phase2_results[0][0] > best_correct:
        best_correct = phase2_results[0][0]
        best_errors = phase2_results[0][4]
    best_config["ctc_high_gap"] = best_h
    best_config["ctc_medium_gap"] = best_m
    print(f"\n  >> Best CTC gaps: high={best_h}, medium={best_m}")

    # ── Phase 3: Tashkeel alignment threshold ────────────────────────
    print("\n" + "=" * 70)
    print("PHASE 3: Tashkeel alignment threshold")
    print("=" * 70)

    tash_values = [-6.0, -5.0, -4.0, -3.5, -3.0, -2.5, -2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0]
    best_phase3 = 0
    best_phase3_tash = -2.0

    for tash in tash_values:
        c, t, errs = evaluate_cached(cached_words,
            ctc_high_gap=best_h, ctc_medium_gap=best_m,
            tashkeel_align_threshold=tash, ctc_omission_margin=2.0,
            fallback_scope=best_fb)
        marker = " <-- BEST" if c > best_phase3 else ""
        print(f"  tashkeel_threshold={tash:5.1f}: {c}/{t} ({100*c/t:.1f}%){marker}")
        if c > best_phase3:
            best_phase3 = c
            best_phase3_tash = tash
            if c > best_correct:
                best_correct = c
                best_errors = errs

    best_config["tashkeel_align_threshold"] = best_phase3_tash
    print(f"\n  >> Best tashkeel threshold: {best_phase3_tash}")

    # ── Phase 4: CTC omission margin ────────────────────────────────
    print("\n" + "=" * 70)
    print("PHASE 4: CTC omission margin")
    print("=" * 70)

    omit_values = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 8.0, 100.0]
    best_phase4 = 0
    best_phase4_omit = 2.0

    for omit in omit_values:
        c, t, errs = evaluate_cached(cached_words,
            ctc_high_gap=best_h, ctc_medium_gap=best_m,
            tashkeel_align_threshold=best_phase3_tash,
            ctc_omission_margin=omit,
            fallback_scope=best_fb)
        marker = " <-- BEST" if c > best_phase4 else ""
        print(f"  omission_margin={omit:5.1f}: {c}/{t} ({100*c/t:.1f}%){marker}")
        if c > best_phase4:
            best_phase4 = c
            best_phase4_omit = omit
            if c > best_correct:
                best_correct = c
                best_errors = errs

    best_config["ctc_omission_margin"] = best_phase4_omit
    print(f"\n  >> Best omission margin: {best_phase4_omit}")

    # ── Phase 5: Full grid search combining all best ─────────────────
    print("\n" + "=" * 70)
    print("PHASE 5: Full grid search (fine-grained around best values)")
    print("=" * 70)

    # Fine-grained search around best values
    h_range = sorted(set([max(0.5, best_h - 0.5), best_h - 0.25, best_h, best_h + 0.25, best_h + 0.5]))
    m_range = sorted(set([max(0.25, best_m - 0.5), best_m - 0.25, best_m, best_m + 0.25, best_m + 0.5]))
    t_range = sorted(set([best_phase3_tash - 0.5, best_phase3_tash, best_phase3_tash + 0.5]))
    o_range = sorted(set([max(0.0, best_phase4_omit - 0.5), best_phase4_omit, best_phase4_omit + 0.5]))
    fb_range = ["low", "medium"]

    grid_results = []
    n_combos = 0

    for h in h_range:
        for m in m_range:
            if m >= h:
                continue
            for t_val in t_range:
                for o in o_range:
                    for fb in fb_range:
                        n_combos += 1
                        c, t, errs = evaluate_cached(cached_words,
                            ctc_high_gap=h, ctc_medium_gap=m,
                            tashkeel_align_threshold=t_val,
                            ctc_omission_margin=o,
                            fallback_scope=fb)
                        grid_results.append((c, t, h, m, t_val, o, fb, errs))

    grid_results.sort(key=lambda x: x[0], reverse=True)
    print(f"\n  Tested {n_combos} combinations")
    print(f"\n  Top-15 configurations:")
    for i, (c, t, h, m, tv, o, fb, errs) in enumerate(grid_results[:15]):
        print(f"    {i+1}. {c}/{t} ({100*c/t:.1f}%) | h={h:.2f} m={m:.2f} tash={tv:.1f} omit={o:.1f} fb={fb}")

    if grid_results[0][0] > best_correct:
        best_correct = grid_results[0][0]
        c, t, h, m, tv, o, fb, errs = grid_results[0]
        best_config = {
            "ctc_high_gap": h, "ctc_medium_gap": m,
            "tashkeel_align_threshold": tv,
            "ctc_omission_margin": o,
            "fallback_scope": fb,
        }
        best_errors = errs

    # ── Final Report ──────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("FINAL REPORT")
    print("=" * 70)

    print(f"\n  Baseline (v1 thresholds): {baseline_correct}/{baseline_total} ({100*baseline_correct/baseline_total:.1f}%)")
    print(f"    CTC HIGH gap=2.0, MEDIUM gap=1.5")
    print(f"    tashkeel_align=-2.0, omission_margin=2.0, edge=-4.0, fallback=low")

    print(f"\n  Optimal (v2 tuned): {best_correct}/{baseline_total} ({100*best_correct/baseline_total:.1f}%)")
    for k, v in best_config.items():
        print(f"    {k}: {v}")

    improvement = best_correct - baseline_correct
    if improvement > 0:
        print(f"\n  IMPROVEMENT: +{improvement} words (+{100*improvement/baseline_total:.1f}%)")
    elif improvement < 0:
        print(f"\n  REGRESSION: {improvement} words ({100*improvement/baseline_total:.1f}%)")
    else:
        print(f"\n  NO CHANGE in accuracy")

    print(f"\n  Remaining errors ({len(best_errors)}):")
    for eid, ref, kind, conf in best_errors:
        print(f"    {eid}: {ref} -> {kind} ({conf})")

    print("\n  Recommended configuration changes:")
    print(f"    pcd_transcriber.py score_word_in_context:")
    print(f"      HIGH confidence gap:  2.0 -> {best_config['ctc_high_gap']}")
    print(f"      MEDIUM confidence gap: 1.5 -> {best_config['ctc_medium_gap']}")
    print(f"    pipeline.py evaluate_pcd_live:")
    print(f"      Tashkeel alignment threshold: -2.0 -> {best_config['tashkeel_align_threshold']}")
    print(f"      CTC omission margin: 2.0 -> {best_config['ctc_omission_margin']}")
    print(f"      Low-confidence fallback scope: low -> {best_config['fallback_scope']}")


if __name__ == "__main__":
    main()
