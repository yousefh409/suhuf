#!/usr/bin/env python3
"""Test runner using PCD model (NeMo FastConformer) instead of Whisper.

Evaluates the fine-tuned PCD model on the same test recordings as run_tests.py
for direct comparison.

Usage:
    python run_tests_pcd.py
    python run_tests_pcd.py --verbose
    python run_tests_pcd.py --model models/pcd_clartts_v3.nemo
"""

import json
import sys
from pathlib import Path

import numpy as np

from i3rab.book import Book
from i3rab.config import Config
from i3rab.models import DiffKind
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


def run_word_test(entry, pipeline, verbose):
    """Run a single-word test using PCD CTC scoring."""
    audio_data = read_audio(TEST_DATA_DIR / entry["filename"])
    rec_id = entry["id"]

    word_book = Book.from_sentence(entry["word_diacritized"])
    if not word_book.words:
        print(f"  [{rec_id}] SKIP - no hypotheses generated")
        return 0, 0, True

    book_word = word_book.words[0]

    # Use PCD CTC scoring
    pcd = pipeline._pcd_transcriber
    log_probs, encoded_len, encoded = pcd.encode(audio_data)

    # Score hypotheses
    scored = pcd.score_word_in_context(
        log_probs, encoded_len,
        book_word, word_book.words,
        encoded=encoded,
    )

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
        for hyp in book_word.hypotheses:
            score = pcd._ctc_score(log_probs, encoded_len, hyp.diacritized)
            marker = " <--" if hyp.case == detected_case else ""
            print(
                f"           {hyp.diacritized:>20s}  "
                f"case={hyp.case:<6s}  "
                f"score={score:.4f}{marker}"
            )
        print()

    return (1 if is_match else 0), 1, False


def run_sentence_test(entry, pipeline, verbose):
    """Run a sentence-level test using PCD evaluate_pcd_live."""
    audio_data = read_audio(TEST_DATA_DIR / entry["filename"])
    rec_id = entry["id"]
    text = entry["text_diacritized"]

    sentence_book = Book.from_sentence(text)
    if not sentence_book.words:
        print(f"  [{rec_id}] SKIP - no words generated for sentence")
        return 0, 0, True

    # Create a fresh pipeline for this sentence
    config = pipeline.config
    pipe = I3rabPipeline(sentence_book, config)
    pipe._pcd_transcriber = pipeline._pcd_transcriber  # reuse loaded model

    result = pipe.evaluate_pcd_live(audio_data)

    scored_words = result.get("scored_words", [])

    correct = sum(
        1 for sw in scored_words
        if sw["kind"] in ("correct", "pausal_ok")
    )
    total = len(scored_words)
    all_correct = correct == total and total > 0

    status = "PASS" if all_correct else "FAIL"
    transcript = result.get("transcript", "")
    print(
        f"  [{rec_id}] {status}  "
        f"sentence=\"{text[:60]}...\"  "
        f"words={correct}/{total}  "
        f"transcript=\"{transcript[:60]}...\""
    )

    if verbose or not all_correct:
        for sw in scored_words:
            is_ok = sw["kind"] in ("correct", "pausal_ok")
            mark = "OK" if is_ok else "XX"
            det_case = sw.get("detected_case") or ""
            exp_case = sw.get("expected_case") or ""
            ref = sw.get("ref_word", "")
            hyp = sw.get("hyp_word") or "-"
            kind = sw.get("kind", "")
            print(
                f"           [{mark}] {ref:>15s}  "
                f"got={hyp:>15s}  "
                f"kind={kind:<14s}  "
                f"expected_case={exp_case:<6s}  detected_case={det_case}"
            )
        print()

    return correct, total, False


def run_tests(verbose: bool = False, model_path: str = None, tashkeel_on: bool = False,
              ssl_model: str = None, ssl_training_sr: int = 0):
    """Run all test recordings using PCD model."""
    if not MANIFEST_PATH.exists():
        print("No test data found. Record some samples at /test first.")
        sys.exit(1)

    manifest = json.loads(MANIFEST_PATH.read_text())
    if not manifest:
        print("Manifest is empty.")
        sys.exit(1)

    word_entries = [e for e in manifest if e.get("type", "word") == "word"]
    sentence_entries = [e for e in manifest if e.get("type") == "sentence"]

    config = Config()
    if model_path:
        config.pcd_model_path = model_path
    if ssl_model:
        config.ssl_model_dir = ssl_model
    if ssl_training_sr > 0:
        config.ssl_training_sr = ssl_training_sr
    if tashkeel_on:
        config.pcd_tashkeel_detection = True

    model_name = ssl_model or config.pcd_model_path
    print(f"Loading model from {model_name}...")

    # Create a dummy pipeline just to load PCD
    dummy_book = Book.from_sentence("تَجْرِبَةٌ")
    pipeline = I3rabPipeline(dummy_book, config)
    pipeline.load_pcd()

    print(f"Found {len(word_entries)} word recordings, {len(sentence_entries)} sentence recordings\n")

    correct_total = 0
    words_total = 0
    errors = 0

    # Run word tests
    if word_entries:
        print("── Word Tests (PCD CTC) ───────────────────────")
        for entry in word_entries:
            filepath = TEST_DATA_DIR / entry["filename"]
            if not filepath.exists():
                print(f"  [{entry['id']}] SKIP - file not found: {filepath}")
                errors += 1
                continue
            c, t, err = run_word_test(entry, pipeline, verbose)
            if err:
                errors += 1
            else:
                correct_total += c
                words_total += t

    # Run sentence tests
    if sentence_entries:
        print("── Sentence Tests (PCD evaluate_pcd_live) ─────")
        for entry in sentence_entries:
            filepath = TEST_DATA_DIR / entry["filename"]
            if not filepath.exists():
                print(f"  [{entry['id']}] SKIP - file not found: {filepath}")
                errors += 1
                continue
            c, t, err = run_sentence_test(entry, pipeline, verbose)
            if err:
                errors += 1
            else:
                correct_total += c
                words_total += t

    # Summary
    print(f"\n{'='*50}")
    accuracy = round(correct_total / words_total * 100, 1) if words_total > 0 else 0
    print(f"PCD Results: {correct_total}/{words_total} words correct ({accuracy}%)")
    if errors:
        print(f"Skipped: {errors} recordings (missing files or no hypotheses)")
    print(f"{'='*50}")


if __name__ == "__main__":
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    tashkeel_on = "--tashkeel-on" in sys.argv
    model_path = None
    ssl_model = None
    ssl_training_sr = 0
    for i, arg in enumerate(sys.argv):
        if arg == "--model" and i + 1 < len(sys.argv):
            model_path = sys.argv[i + 1]
        if arg == "--ssl-model" and i + 1 < len(sys.argv):
            ssl_model = sys.argv[i + 1]
        if arg == "--ssl-training-sr" and i + 1 < len(sys.argv):
            ssl_training_sr = int(sys.argv[i + 1])
    run_tests(verbose=verbose, model_path=model_path, tashkeel_on=tashkeel_on,
              ssl_model=ssl_model, ssl_training_sr=ssl_training_sr)
