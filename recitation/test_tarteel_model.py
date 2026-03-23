#!/usr/bin/env python3
"""Quick test: does IJyad/whisper-large-v3-Tarteel improve diacritics discrimination?

Tests the 4 error cases where whisper-large-v3 picks the wrong case ending.
"""

import io
import json
from pathlib import Path

import numpy as np
import torch

from i3rab.book import Book
from i3rab.scorer import DiacriticsScorer
from i3rab.config import Config

TEST_DATA_DIR = Path("test_data")
MANIFEST_PATH = TEST_DATA_DIR / "manifest.json"

ERROR_CASES = [
    {"rec": "rec_031", "word": "\u0633\u064e\u0623\u064e\u0644\u064e", "correct_case": "acc"},
    {"rec": "rec_039", "word": "\u0623\u064e\u0639\u064e\u062f\u0651\u064e\u062a\u0650", "correct_case": "gen"},
    {"rec": "rec_039", "word": "\u0627\u0644\u0644\u0651\u064e\u0630\u0650\u064a\u0630\u064e", "correct_case": "acc"},
    {"rec": "rec_040", "word": "\u0627\u0644\u0637\u0651\u064e\u0627\u0632\u0650\u062c\u064e", "correct_case": "acc"},
]

CONTROL_CASES = [
    {"rec": "rec_016", "word": "\u0627\u0644\u0637\u0651\u064e\u0627\u0644\u0650\u0628\u064f", "correct_case": "nom"},
    {"rec": "rec_016", "word": "\u0627\u0644\u0643\u0650\u062a\u064e\u0627\u0628\u064e", "correct_case": "acc"},
    {"rec": "rec_016", "word": "\u0627\u0644\u0645\u064e\u0643\u0652\u062a\u064e\u0628\u064e\u0629\u0650", "correct_case": "gen"},
    {"rec": "rec_019", "word": "\u0627\u0644\u0648\u064e\u0644\u064e\u062f\u064f", "correct_case": "nom"},
    {"rec": "rec_019", "word": "\u0627\u0644\u0645\u064e\u0627\u0621\u064e", "correct_case": "acc"},
    {"rec": "rec_019", "word": "\u0627\u0644\u0628\u064e\u0627\u0631\u0650\u062f\u064e", "correct_case": "acc"},
    {"rec": "rec_032", "word": "\u0627\u0644\u0639\u0650\u0644\u0652\u0645\u064f", "correct_case": "nom"},
    {"rec": "rec_032", "word": "\u0627\u0644\u0641\u064e\u0631\u064e\u062c\u0650", "correct_case": "gen"},
]


def read_audio(filepath):
    import soundfile as sf
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


def find_word_in_book(book, target_diac):
    from i3rab.arabic import strip_harakat
    target_base = strip_harakat(target_diac)
    for w in book.words:
        if w.correct_diac == target_diac:
            return w
    for w in book.words:
        if w.base == target_base:
            return w
    return None


def test_model(model_name, cases, manifest_by_id, label):
    print(f"\n{'='*60}")
    print(f"Model: {model_name}")
    print(f"{'='*60}")

    config = Config()
    config.asr_model = model_name
    scorer = DiacriticsScorer(config)
    scorer.load()

    audio_cache = {}
    book_cache = {}
    enc_cache = {}

    correct = 0
    total = 0

    for case in cases:
        rec_id = case["rec"]
        if rec_id not in audio_cache:
            entry = manifest_by_id[rec_id]
            audio_cache[rec_id] = read_audio(TEST_DATA_DIR / entry["filename"])
            book_cache[rec_id] = Book.from_sentence(entry["text_diacritized"])

        audio = audio_cache[rec_id]
        book = book_cache[rec_id]

        if rec_id not in enc_cache:
            enc_cache[rec_id] = scorer._get_encoder_output(audio)
        enc_out = enc_cache[rec_id]

        book_word = find_word_in_book(book, case["word"])
        if not book_word:
            print(f"  SKIP: word not found in {rec_id}")
            continue

        scored = []
        for hyp in book_word.hypotheses:
            score = scorer._score_text(enc_out, hyp.diacritized)
            scored.append((hyp.diacritized, hyp.case, score))
        scored.sort(key=lambda x: x[2], reverse=True)

        pick = scored[0][1]
        gap = scored[0][2] - scored[1][2] if len(scored) > 1 else float("inf")
        is_correct = pick == case["correct_case"]
        if is_correct:
            correct += 1
        total += 1

        mark = "OK" if is_correct else "XX"
        print(f"  [{mark}] [{rec_id}] {case['word']:>15s}  correct={case['correct_case']:<10s}  picked={pick:<10s}  gap={gap:.4f}")

        # Show top 3 scores for error cases
        if not is_correct or label == "errors":
            for diac, cas, sc in scored[:4]:
                marker = " <--" if cas == case["correct_case"] else ""
                print(f"         {diac:>20s}  {cas:<10s}  {sc:.4f}{marker}")

    print(f"\n{label}: {correct}/{total}")
    return correct, total


def main():
    manifest = json.loads(MANIFEST_PATH.read_text())
    manifest_by_id = {e["id"]: e for e in manifest}

    models = [
        "openai/whisper-large-v3",
        "IJyad/whisper-large-v3-Tarteel",
    ]

    for model_name in models:
        e_correct, e_total = test_model(model_name, ERROR_CASES, manifest_by_id, "errors")
        c_correct, c_total = test_model(model_name, CONTROL_CASES, manifest_by_id, "controls")
        print(f"\n  TOTAL: {e_correct + c_correct}/{e_total + c_total} ({model_name})")


if __name__ == "__main__":
    main()
