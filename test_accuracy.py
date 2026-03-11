#!/usr/bin/env python3
"""Accuracy tests for the i3rab hypothesis scorer.

Generates Arabic TTS audio for correct and incorrect diacritizations,
adds noise at various SNR levels, and measures scoring accuracy.
"""

import os
import io
import sys
import time
import tempfile

import numpy as np
import soundfile as sf

# ── Test Data ────────────────────────────────────────────────────────────────

# Each test case: (sentence, list of (word, correct_diac, wrong_diac, error_type))
TEST_SENTENCES = [
    {
        "name": "Basic MSA sentence",
        "text": "قَرَأَ الطَّالِبُ الكِتَابَ فِي المَكْتَبَةِ",
        "words": [
            ("قَرَأَ", "قَرَأَ", "قَرَأُ", "irab"),      # fatha -> damma
            ("الطَّالِبُ", "الطَّالِبُ", "الطَّالِبَ", "irab"),  # damma -> fatha
            ("الكِتَابَ", "الكِتَابَ", "الكِتَابُ", "irab"),    # fatha -> damma
            ("فِي", "فِي", None, None),                      # particle, no alt
            ("المَكْتَبَةِ", "المَكْتَبَةِ", "المَكْتَبَةُ", "irab"),  # kasra -> damma
        ],
    },
    {
        "name": "Passive vs Active",
        "text": "كُتِبَ الدَّرْسُ عَلَى السَّبُّورَةِ",
        "words": [
            ("كُتِبَ", "كُتِبَ", "كَتَبَ", "tashkeel"),    # passive -> active (internal)
            ("الدَّرْسُ", "الدَّرْسُ", "الدَّرْسَ", "irab"),    # damma -> fatha
            ("عَلَى", "عَلَى", None, None),                    # particle
            ("السَّبُّورَةِ", "السَّبُّورَةِ", "السَّبُّورَةَ", "irab"),  # kasra -> fatha
        ],
    },
    {
        "name": "Nominal sentence",
        "text": "الجَوُّ جَمِيلٌ فِي الرَّبِيعِ",
        "words": [
            ("الجَوُّ", "الجَوُّ", "الجَوَّ", "irab"),          # damma -> fatha
            ("جَمِيلٌ", "جَمِيلٌ", "جَمِيلاً", "irab"),        # dammatan -> fathatan
            ("فِي", "فِي", None, None),
            ("الرَّبِيعِ", "الرَّبِيعِ", "الرَّبِيعُ", "irab"),    # kasra -> damma
        ],
    },
]

# Full sentences for testing (correct versions)
CORRECT_SENTENCES = [
    "قَرَأَ الطَّالِبُ الكِتَابَ فِي المَكْتَبَةِ",
    "ذَهَبَ الوَلَدُ إِلَى المَدْرَسَةِ",
    "كُتِبَ الدَّرْسُ عَلَى السَّبُّورَةِ",
    "الجَوُّ جَمِيلٌ فِي الرَّبِيعِ",
]

# Wrong diacritization versions of the same sentences
WRONG_SENTENCES = [
    "قَرَأُ الطَّالِبَ الكِتَابُ فِي المَكْتَبَةُ",  # all case endings wrong
    "ذَهَبُ الوَلَدَ إِلَى المَدْرَسَةُ",
    "كَتَبَ الدَّرْسَ عَلَى السَّبُّورَةُ",           # active instead of passive + wrong endings
    "الجَوَّ جَمِيلاً فِي الرَّبِيعُ",
]

# ── TTS Audio Generation ─────────────────────────────────────────────────────


def generate_tts_audio(text: str, sample_rate: int = 16000) -> np.ndarray:
    """Generate Arabic TTS audio using gTTS."""
    import av
    from gtts import gTTS

    tts = gTTS(text=text, lang="ar")
    buf = io.BytesIO()
    tts.write_to_fp(buf)
    buf.seek(0)

    # Decode MP3 using PyAV (no system ffmpeg needed)
    container = av.open(buf)
    resampler = av.AudioResampler(format="s16", layout="mono", rate=sample_rate)

    frames = []
    for frame in container.decode(audio=0):
        resampled = resampler.resample(frame)
        for r in resampled:
            arr = r.to_ndarray()
            frames.append(arr.flatten())
    container.close()

    samples = np.concatenate(frames).astype(np.float32) / 32768.0
    return samples


def add_noise(audio: np.ndarray, snr_db: float) -> np.ndarray:
    """Add white Gaussian noise at a specified SNR level."""
    signal_power = np.mean(audio ** 2)
    if signal_power == 0:
        return audio
    noise_power = signal_power / (10 ** (snr_db / 10))
    noise = np.random.randn(len(audio)).astype(np.float32) * np.sqrt(noise_power)
    return audio + noise


# ── Test Runner ──────────────────────────────────────────────────────────────


def test_sentence_scoring(scorer, sentence: str, book_words, label: str, snr_db: float | None = None):
    """Test scoring on a single sentence at a given noise level."""
    from i3rab.models import Confidence

    # Generate audio
    audio = generate_tts_audio(sentence)

    noise_label = f"SNR {snr_db}dB" if snr_db is not None else "clean"

    if snr_db is not None:
        audio = add_noise(audio, snr_db)

    # Score all words
    t0 = time.time()
    scored_words = scorer.score_phrase(audio, book_words)
    elapsed = time.time() - t0

    results = []
    for scored in scored_words:
        w = scored.word
        det = scored.detected_hyp
        is_correct = det.is_correct if det else False
        is_pausal = det.is_pausal if det else False

        results.append({
            "word": w.correct_diac,
            "detected": det.diacritized if det else "?",
            "correct": is_correct,
            "pausal": is_pausal,
            "confidence": scored.confidence.value,
            "gap": scored.score_gap,
            "case_detected": det.case if det else "?",
        })

    n_correct = sum(1 for r in results if r["correct"] or r["pausal"])
    n_total = len(results)
    accuracy = n_correct / n_total * 100 if n_total > 0 else 0

    return {
        "label": label,
        "noise": noise_label,
        "accuracy": accuracy,
        "correct": n_correct,
        "total": n_total,
        "elapsed_ms": elapsed * 1000,
        "details": results,
    }


def run_full_test():
    """Run the complete accuracy test suite."""
    from i3rab.book import Book
    from i3rab.scorer import DiacriticsScorer
    from i3rab.config import Config

    print("=" * 70)
    print("i3rab Accuracy Test Suite")
    print("=" * 70)
    print()

    # Load scorer
    config = Config()
    scorer = DiacriticsScorer(config)
    scorer.load()

    noise_levels = [None, 20, 10, 5]  # None = clean, then SNR in dB
    all_results = []

    # ── Test 1: Correct sentences ────────────────────────────────────────
    print("\n" + "─" * 70)
    print("TEST 1: Correctly diacritized sentences")
    print("  Goal: scorer should detect the CORRECT diacritization")
    print("─" * 70)

    for sent_idx, sentence in enumerate(CORRECT_SENTENCES):
        book = Book.from_sentence(sentence)

        for snr in noise_levels:
            result = test_sentence_scoring(
                scorer, sentence, book.words,
                label=f"Correct S{sent_idx+1}",
                snr_db=snr,
            )
            all_results.append(result)

            noise_str = result["noise"]
            acc = result["accuracy"]
            elapsed = result["elapsed_ms"]
            print(f"  S{sent_idx+1} [{noise_str:>10s}]: {acc:5.1f}% ({result['correct']}/{result['total']}) [{elapsed:.0f}ms]")

            # Show per-word details for non-perfect scores
            if acc < 100:
                for d in result["details"]:
                    if not d["correct"] and not d["pausal"]:
                        print(f"    MISS: {d['word']} -> {d['detected']} ({d['case_detected']}, {d['confidence']})")

    # ── Test 2: Wrong sentences ──────────────────────────────────────────
    print("\n" + "─" * 70)
    print("TEST 2: Incorrectly diacritized sentences")
    print("  Goal: scorer should detect the WRONG diacritization (not mark as correct)")
    print("─" * 70)

    for sent_idx, (wrong_sent, correct_sent) in enumerate(zip(WRONG_SENTENCES, CORRECT_SENTENCES)):
        # Book uses the CORRECT diacritization as reference
        book = Book.from_sentence(correct_sent)

        for snr in [None, 10]:  # Only test clean and moderate noise
            result = test_sentence_scoring(
                scorer, wrong_sent, book.words,
                label=f"Wrong S{sent_idx+1}",
                snr_db=snr,
            )
            all_results.append(result)

            noise_str = result["noise"]
            # For wrong sentences, we WANT low accuracy (= it detected the errors)
            error_detection = 100 - result["accuracy"]
            print(f"  S{sent_idx+1} [{noise_str:>10s}]: {error_detection:5.1f}% errors detected ({result['total'] - result['correct']}/{result['total']} flagged)")

            for d in result["details"]:
                marker = "CORRECT" if d["correct"] else "FLAGGED"
                if d["pausal"]:
                    marker = "PAUSAL"
                print(f"    [{marker:>7s}] {d['word']:>20s} -> {d['detected']:>20s} ({d['case_detected']}, conf={d['confidence']})")

    # ── Test 3: Per-word hypothesis discrimination ───────────────────────
    print("\n" + "─" * 70)
    print("TEST 3: Per-word hypothesis discrimination (clean audio)")
    print("  Tests how well the scorer distinguishes between i3rab endings")
    print("─" * 70)

    test_words_data = [
        ("الكِتَابَ", "accusative (fatha)"),
        ("الكِتَابُ", "nominative (damma)"),
        ("الكِتَابِ", "genitive (kasra)"),
    ]

    for word_text, case_label in test_words_data:
        # Generate audio for this specific word
        audio = generate_tts_audio(word_text)

        # Create a book with الكتاب and all hypotheses
        book = Book.from_sentence("الكِتَابَ")  # Reference with fatha
        word = book.words[0]

        # Score
        scored = scorer.score_word(audio, word)
        det = scored.detected_hyp

        print(f"\n  Audio: {word_text} ({case_label})")
        print(f"  Detected: {det.diacritized} ({det.case}) [conf={scored.confidence.value}, gap={scored.score_gap:.3f}]")

        # Show all hypothesis scores
        encoder_out = scorer._get_encoder_output(audio)
        for hyp in word.hypotheses[:5]:
            score = scorer._score_text(encoder_out, hyp.diacritized)
            marker = " <--" if hyp.diacritized == det.diacritized else ""
            print(f"    {hyp.diacritized:>15s} ({hyp.case:>10s}): {score:.4f}{marker}")

    # ── Summary ──────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    # Aggregate by noise level
    for noise_label in ["clean", "SNR 20dB", "SNR 10dB", "SNR 5dB"]:
        correct_results = [r for r in all_results if r["noise"] == noise_label and "Correct" in r["label"]]
        if correct_results:
            total_correct = sum(r["correct"] for r in correct_results)
            total_words = sum(r["total"] for r in correct_results)
            overall_acc = total_correct / total_words * 100 if total_words > 0 else 0
            avg_ms = np.mean([r["elapsed_ms"] for r in correct_results])
            print(f"  Correct diac [{noise_label:>10s}]: {overall_acc:5.1f}% ({total_correct}/{total_words} words) avg {avg_ms:.0f}ms")

    print()
    for noise_label in ["clean", "SNR 10dB"]:
        wrong_results = [r for r in all_results if r["noise"] == noise_label and "Wrong" in r["label"]]
        if wrong_results:
            total_flagged = sum(r["total"] - r["correct"] for r in wrong_results)
            total_words = sum(r["total"] for r in wrong_results)
            detection_rate = total_flagged / total_words * 100 if total_words > 0 else 0
            print(f"  Error detect  [{noise_label:>10s}]: {detection_rate:5.1f}% ({total_flagged}/{total_words} errors flagged)")

    print()


if __name__ == "__main__":
    run_full_test()
