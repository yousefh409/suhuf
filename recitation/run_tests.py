#!/usr/bin/env python3
"""CLI test runner for i3rab test recordings.

Loads all recordings from test_data/manifest.json, runs the scorer
on each one, and prints accuracy results. Supports both word-level
and sentence-level recordings.

Usage:
    python run_tests.py
    python run_tests.py --verbose
"""

import json
import sys
from pathlib import Path

import numpy as np

from i3rab.book import Book
from i3rab.config import Config
from i3rab.models import DiffKind
from i3rab.scorer import DiacriticsScorer
from i3rab.pipeline import I3rabPipeline

TEST_DATA_DIR = Path("test_data")
MANIFEST_PATH = TEST_DATA_DIR / "manifest.json"


def read_audio(filepath: Path) -> np.ndarray:
    """Read an audio file into float32 numpy array at 16kHz."""
    import io
    import soundfile as sf

    audio_bytes = filepath.read_bytes()
    sample_rate = 16000

    try:
        audio_data, sr = sf.read(io.BytesIO(audio_bytes), dtype="float32")
    except Exception:
        import av

        container = av.open(io.BytesIO(audio_bytes))
        resampler = av.AudioResampler(format="s16", layout="mono", rate=sample_rate)
        frames = []
        for frame in container.decode(audio=0):
            for r in resampler.resample(frame):
                frames.append(r.to_ndarray().flatten())
        container.close()
        if not frames:
            raise ValueError(f"No audio data decoded from {filepath}")
        return np.concatenate(frames).astype(np.float32) / 32768.0

    if audio_data.ndim > 1:
        audio_data = audio_data.mean(axis=1)
    if sr != sample_rate:
        from scipy.signal import resample

        num_samples = int(len(audio_data) * sample_rate / sr)
        audio_data = resample(audio_data, num_samples).astype(np.float32)
    return audio_data


def run_word_test(entry, scorer, verbose):
    """Run a single-word test. Returns (correct_count, total_count, error)."""
    audio_data = read_audio(TEST_DATA_DIR / entry["filename"])
    rec_id = entry["id"]

    word_book = Book.from_sentence(entry["word_diacritized"])
    if not word_book.words:
        print(f"  [{rec_id}] SKIP - no hypotheses generated")
        return 0, 0, True

    book_word = word_book.words[0]
    scored = scorer.score_word(audio_data, book_word)

    detected_case = scored.detected_hyp.case if scored.detected_hyp else None
    is_match = detected_case == entry["intended_case"]

    status = "PASS" if is_match else "FAIL"
    print(
        f"  [{rec_id}] {status}  "
        f"word={entry['word_diacritized']}  "
        f"intended={entry['intended_case']}  "
        f"detected={detected_case}  "
        f"conf={scored.confidence.value}  "
        f"gap={scored.score_gap:.4f}"
    )

    if verbose:
        encoder_out = scorer._get_encoder_output(audio_data)
        for hyp in book_word.hypotheses:
            score = scorer._score_text(encoder_out, hyp.diacritized)
            marker = " <--" if hyp.case == detected_case else ""
            print(
                f"           {hyp.diacritized:>20s}  "
                f"case={hyp.case:<6s}  "
                f"score={score:.4f}{marker}"
            )
        print()

    return (1 if is_match else 0), 1, False


def run_sentence_test(entry, scorer, verbose):
    """Run a sentence-level test. Returns (correct_count, total_count, error)."""
    audio_data = read_audio(TEST_DATA_DIR / entry["filename"])
    rec_id = entry["id"]
    text = entry["text_diacritized"]

    sentence_book = Book.from_sentence(text)
    if not sentence_book.words:
        print(f"  [{rec_id}] SKIP - no words generated for sentence")
        return 0, 0, True

    config = Config()
    pipe = I3rabPipeline(sentence_book, config)
    pipe.scorer = scorer  # reuse loaded model

    result = pipe.evaluate_phrase(audio_data)

    word_results = result["results"]
    correct = sum(
        1 for wd in word_results
        if wd.kind in (DiffKind.CORRECT, DiffKind.PAUSAL_OK)
    )
    total = len(word_results)
    all_correct = correct == total and total > 0

    status = "PASS" if all_correct else "FAIL"
    print(
        f"  [{rec_id}] {status}  "
        f"sentence=\"{text}\"  "
        f"words={correct}/{total}  "
        f"transcript=\"{result['transcript']}\""
    )

    if verbose or not all_correct:
        for wd in word_results:
            is_ok = wd.kind in (DiffKind.CORRECT, DiffKind.PAUSAL_OK)
            mark = "OK" if is_ok else "XX"
            det_case = wd.detected_case or ""
            exp_case = wd.expected_case or ""
            print(
                f"           [{mark}] {wd.ref_word:>15s}  "
                f"got={wd.hyp_word or '-':>15s}  "
                f"kind={wd.kind.value:<14s}  "
                f"expected_case={exp_case:<6s}  detected_case={det_case}"
            )
        print()

    return correct, total, False


def run_tests(verbose: bool = False):
    """Run all test recordings and print results."""
    if not MANIFEST_PATH.exists():
        print("No test data found. Record some samples at /test first.")
        sys.exit(1)

    manifest = json.loads(MANIFEST_PATH.read_text())
    if not manifest:
        print("Manifest is empty. Record some samples at /test first.")
        sys.exit(1)

    word_entries = [e for e in manifest if e.get("type", "word") == "word"]
    sentence_entries = [e for e in manifest if e.get("type") == "sentence"]

    print(f"Loading scorer...")
    config = Config()
    scorer = DiacriticsScorer(config)
    scorer.load()

    print(f"Found {len(word_entries)} word recordings, {len(sentence_entries)} sentence recordings\n")

    correct_total = 0
    words_total = 0
    errors = 0

    # Run word tests
    if word_entries:
        print("── Word Tests ─────────────────────────────────")
        for entry in word_entries:
            filepath = TEST_DATA_DIR / entry["filename"]
            if not filepath.exists():
                print(f"  [{entry['id']}] SKIP - file not found: {filepath}")
                errors += 1
                continue
            c, t, err = run_word_test(entry, scorer, verbose)
            if err:
                errors += 1
            else:
                correct_total += c
                words_total += t

    # Run sentence tests
    if sentence_entries:
        print("── Sentence Tests ─────────────────────────────")
        for entry in sentence_entries:
            filepath = TEST_DATA_DIR / entry["filename"]
            if not filepath.exists():
                print(f"  [{entry['id']}] SKIP - file not found: {filepath}")
                errors += 1
                continue
            c, t, err = run_sentence_test(entry, scorer, verbose)
            if err:
                errors += 1
            else:
                correct_total += c
                words_total += t

    # Summary
    print(f"\n{'='*50}")
    accuracy = round(correct_total / words_total * 100, 1) if words_total > 0 else 0
    print(f"Results: {correct_total}/{words_total} words correct ({accuracy}%)")
    if errors:
        print(f"Skipped: {errors} recordings (missing files or no hypotheses)")
    print(f"{'='*50}")


if __name__ == "__main__":
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    run_tests(verbose=verbose)
