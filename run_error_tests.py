#!/usr/bin/env python3
"""Error detection tests for i3rab.

Tests two dimensions:
1. TRUE POSITIVE RATE: When the user reads a wrong case ending, does the
   system correctly detect the error? (Uses existing audio with modified
   expected text to simulate errors.)
2. FALSE POSITIVE RATE: When the user reads correctly, does the system
   avoid flagging errors? (Re-runs existing correct tests.)

Strategy: Reuse existing audio recordings. Since all recordings have the
user reading correctly, we simulate errors by changing the expected
diacritization in the book — if the book says "acc" but the user said "nom",
the system should detect "nom" and flag it as WRONG_IRAB.
"""

import json
import sys
from pathlib import Path

import numpy as np

from i3rab.arabic import strip_harakat, set_last_letter_harakat, get_last_letter_harakat
from i3rab.book import Book
from i3rab.config import Config
from i3rab.models import DiffKind, CASE_HARAKAT
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


def swap_case_ending(word_diac: str, new_case: str) -> str:
    """Replace the case ending of a diacritized word with a different one.

    For fathatan+alef words (e.g., جَمِيلًا), handles removing the alef
    for non-fathatan cases.
    """
    haraka = CASE_HARAKAT[new_case]
    base = strip_harakat(word_diac)

    # Handle fathatan+alef words
    if base.endswith("\u0627") and len(base) > 2:
        current = get_last_letter_harakat(word_diac)
        pre_alef_harakat = []
        # Check the letter before alef for fathatan
        from i3rab.arabic import get_harakat_map
        hmap = get_harakat_map(word_diac)
        pre_alef_idx = len(base) - 2
        pre_alef_h = hmap.get(pre_alef_idx, [])
        if "\u064B" in pre_alef_h:
            # This is a fathatan+alef word; work on the pre-alef letter
            word_no_alef = word_diac
            # Remove trailing alef
            while word_no_alef and strip_harakat(word_no_alef)[-1] == "\u0627":
                word_no_alef = word_no_alef[:-1]
            new_harakat = [h for h in pre_alef_h if h == "\u0651"]  # keep shadda
            new_harakat.append(haraka)
            return set_last_letter_harakat(word_no_alef, new_harakat)

    # Regular word: just swap the last letter's haraka
    current = get_last_letter_harakat(word_diac)
    new_harakat = [h for h in current if h == "\u0651"]  # keep shadda
    new_harakat.append(haraka)
    return set_last_letter_harakat(word_diac, new_harakat)


# ── Word-level error detection tests ───────────────────────────

# Map each word recording to its actual spoken case and the word used
WORD_RECORDINGS = {
    # الكتاب: rec_001 (acc), rec_002 (nom), rec_003 (gen)
    "rec_001": {"case": "acc", "word": "الكِتَابَ", "base": "الكتاب"},
    "rec_002": {"case": "nom", "word": "الكِتَابُ", "base": "الكتاب"},
    "rec_003": {"case": "gen", "word": "الكِتَابِ", "base": "الكتاب"},
    # الطالب: rec_004 (nom), rec_005 (acc), rec_006 (gen)
    "rec_004": {"case": "nom", "word": "الطَّالِبُ", "base": "الطالب"},
    "rec_005": {"case": "acc", "word": "الطَّالِبَ", "base": "الطالب"},
    "rec_006": {"case": "gen", "word": "الطَّالِبِ", "base": "الطالب"},
    # المدرسة: rec_007 (nom), rec_008 (acc), rec_009 (gen)
    "rec_007": {"case": "nom", "word": "المَدْرَسَةُ", "base": "المدرسة"},
    "rec_008": {"case": "acc", "word": "المَدْرَسَةَ", "base": "المدرسة"},
    "rec_009": {"case": "gen", "word": "المَدْرَسَةِ", "base": "المدرسة"},
    # العلم: rec_010 (nom), rec_011 (acc), rec_012 (gen)
    "rec_010": {"case": "nom", "word": "العِلْمُ", "base": "العلم"},
    "rec_011": {"case": "acc", "word": "العِلْمَ", "base": "العلم"},
    "rec_012": {"case": "gen", "word": "العِلْمِ", "base": "العلم"},
    # المعلم: rec_013 (nom), rec_014 (acc), rec_015 (gen)
    "rec_013": {"case": "nom", "word": "المُعَلِّمُ", "base": "المعلم"},
    "rec_014": {"case": "acc", "word": "المُعَلِّمَ", "base": "المعلم"},
    "rec_015": {"case": "gen", "word": "المُعَلِّمِ", "base": "المعلم"},
}

# All basic definite cases to test against
CASES = ["nom", "acc", "gen"]


def run_word_error_tests(scorer, verbose):
    """Test word-level error detection.

    For each word recording (spoken with case X), test the scorer with
    the book expecting case Y (where Y != X). The system should detect
    that the spoken case is X and flag it as an error.

    Returns (detected, total, false_positive, fp_total).
    """
    print("── Word-Level Error Detection ─────────────────")
    print("  (Audio spoken as case X, book expects case Y ≠ X)")
    print()

    errors_detected = 0
    errors_total = 0
    false_positives = 0
    fp_total = 0

    for rec_id, info in WORD_RECORDINGS.items():
        audio_path = TEST_DATA_DIR / f"{rec_id}.webm"
        if not audio_path.exists():
            continue

        audio = read_audio(audio_path)
        spoken_case = info["case"]

        for expected_case in CASES:
            if expected_case == spoken_case:
                # This is the "correct" case — test for false positives
                word_book = Book.from_sentence(info["word"])
                book_word = word_book.words[0]
                scored = scorer.score_word(audio, book_word)
                detected = scored.detected_hyp.case if scored.detected_hyp else None

                fp_total += 1
                if detected != spoken_case:
                    false_positives += 1
                    if verbose:
                        print(
                            f"  [{rec_id}] FALSE POS  "
                            f"word={info['word']}  "
                            f"spoken={spoken_case}  "
                            f"detected={detected}  "
                            f"(should be correct but detected wrong case)"
                        )
                continue

            # Error test: book expects a different case than what was spoken
            wrong_word = swap_case_ending(info["word"], expected_case)
            word_book = Book.from_sentence(wrong_word)
            book_word = word_book.words[0]
            scored = scorer.score_word(audio, book_word)
            detected = scored.detected_hyp.case if scored.detected_hyp else None

            errors_total += 1

            if detected == spoken_case:
                # System correctly detected the spoken case (which differs
                # from expected) → error would be caught
                errors_detected += 1
                status = "DETECT"
            elif detected != expected_case:
                # System detected some other case (not spoken, not expected)
                # Still an error detection since it didn't say "correct"
                errors_detected += 1
                status = "DETECT*"
            else:
                # System detected the expected (wrong) case — missed the error
                status = "MISS  "

            if verbose or status.startswith("MISS"):
                print(
                    f"  [{rec_id}] {status}  "
                    f"word={info['base']}  "
                    f"spoken={spoken_case}  "
                    f"book_expects={expected_case}  "
                    f"detected={detected}  "
                    f"gap={scored.score_gap:.4f}"
                )

    return errors_detected, errors_total, false_positives, fp_total


# ── Sentence-level error detection tests ───────────────────────

# Each test: use audio from a correct recording, but modify one word's
# expected case ending. The system should flag that word as WRONG_IRAB.
SENTENCE_ERROR_TESTS = [
    # rec_016: "قَرَأَ الطَّالِبُ الكِتَابَ فِي المَكْتَبَةِ"
    {
        "audio_id": "rec_016",
        "original_text": "قَرَأَ الطَّالِبُ الكِتَابَ فِي المَكْتَبَةِ",
        "target_word": "الطَّالِبُ",
        "new_case": "acc",
        "desc": "الطَّالِبُ(nom)→الطَّالِبَ(acc)",
    },
    {
        "audio_id": "rec_016",
        "original_text": "قَرَأَ الطَّالِبُ الكِتَابَ فِي المَكْتَبَةِ",
        "target_word": "الكِتَابَ",
        "new_case": "gen",
        "desc": "الكِتَابَ(acc)→الكِتَابِ(gen)",
    },
    {
        "audio_id": "rec_016",
        "original_text": "قَرَأَ الطَّالِبُ الكِتَابَ فِي المَكْتَبَةِ",
        "target_word": "الكِتَابَ",
        "new_case": "nom",
        "desc": "الكِتَابَ(acc)→الكِتَابُ(nom)",
    },
    # rec_017: "ذَهَبَ المُعَلِّمُ إِلَى المَدْرَسَةِ"
    {
        "audio_id": "rec_017",
        "original_text": "ذَهَبَ المُعَلِّمُ إِلَى المَدْرَسَةِ",
        "target_word": "المُعَلِّمُ",
        "new_case": "gen",
        "desc": "المُعَلِّمُ(nom)→المُعَلِّمِ(gen)",
    },
    {
        "audio_id": "rec_017",
        "original_text": "ذَهَبَ المُعَلِّمُ إِلَى المَدْرَسَةِ",
        "target_word": "المُعَلِّمُ",
        "new_case": "acc",
        "desc": "المُعَلِّمُ(nom)→المُعَلِّمَ(acc)",
    },
    {
        "audio_id": "rec_017",
        "original_text": "ذَهَبَ المُعَلِّمُ إِلَى المَدْرَسَةِ",
        "target_word": "المَدْرَسَةِ",
        "new_case": "nom",
        "desc": "المَدْرَسَةِ(gen)→المَدْرَسَةُ(nom)",
    },
    # rec_018: "كَتَبَ الطَّالِبُ الدَّرْسَ"
    {
        "audio_id": "rec_018",
        "original_text": "كَتَبَ الطَّالِبُ الدَّرْسَ",
        "target_word": "الطَّالِبُ",
        "new_case": "gen",
        "desc": "الطَّالِبُ(nom)→الطَّالِبِ(gen)",
    },
    {
        "audio_id": "rec_018",
        "original_text": "كَتَبَ الطَّالِبُ الدَّرْسَ",
        "target_word": "الدَّرْسَ",
        "new_case": "nom",
        "desc": "الدَّرْسَ(acc)→الدَّرْسُ(nom)",
    },
    # rec_019: "شَرِبَ الوَلَدُ المَاءَ البَارِدَ"
    {
        "audio_id": "rec_019",
        "original_text": "شَرِبَ الوَلَدُ المَاءَ البَارِدَ",
        "target_word": "الوَلَدُ",
        "new_case": "acc",
        "desc": "الوَلَدُ(nom)→الوَلَدَ(acc)",
    },
    {
        "audio_id": "rec_019",
        "original_text": "شَرِبَ الوَلَدُ المَاءَ البَارِدَ",
        "target_word": "البَارِدَ",
        "new_case": "gen",
        "desc": "البَارِدَ(acc)→البَارِدِ(gen)",
    },
    # rec_022: "إِنَّ العِلْمَ نُورٌ"
    {
        "audio_id": "rec_022",
        "original_text": "إِنَّ العِلْمَ نُورٌ",
        "target_word": "العِلْمَ",
        "new_case": "nom",
        "desc": "العِلْمَ(acc)→العِلْمُ(nom)",
    },
    {
        "audio_id": "rec_022",
        "original_text": "إِنَّ العِلْمَ نُورٌ",
        "target_word": "العِلْمَ",
        "new_case": "gen",
        "desc": "العِلْمَ(acc)→العِلْمِ(gen)",
    },
    # rec_021: "الكِتَابُ مُفِيدٌ"
    {
        "audio_id": "rec_021",
        "original_text": "الكِتَابُ مُفِيدٌ",
        "target_word": "الكِتَابُ",
        "new_case": "acc",
        "desc": "الكِتَابُ(nom)→الكِتَابَ(acc)",
    },
    {
        "audio_id": "rec_021",
        "original_text": "الكِتَابُ مُفِيدٌ",
        "target_word": "الكِتَابُ",
        "new_case": "gen",
        "desc": "الكِتَابُ(nom)→الكِتَابِ(gen)",
    },
    # rec_020: "المُعَلِّمُ فِي الفَصْلِ"
    {
        "audio_id": "rec_020",
        "original_text": "المُعَلِّمُ فِي الفَصْلِ",
        "target_word": "المُعَلِّمُ",
        "new_case": "acc",
        "desc": "المُعَلِّمُ(nom)→المُعَلِّمَ(acc)",
    },
    {
        "audio_id": "rec_020",
        "original_text": "المُعَلِّمُ فِي الفَصْلِ",
        "target_word": "الفَصْلِ",
        "new_case": "nom",
        "desc": "الفَصْلِ(gen)→الفَصْلُ(nom)",
    },
    # rec_032: "العِلْمُ نُورٌ وَالجَهْلُ ظَلَامٌ وَالصَّبْرُ مِفْتَاحُ الفَرَجِ"
    {
        "audio_id": "rec_032",
        "original_text": "العِلْمُ نُورٌ وَالجَهْلُ ظَلَامٌ وَالصَّبْرُ مِفْتَاحُ الفَرَجِ",
        "target_word": "العِلْمُ",
        "new_case": "acc",
        "desc": "العِلْمُ(nom)→العِلْمَ(acc)",
    },
    {
        "audio_id": "rec_032",
        "original_text": "العِلْمُ نُورٌ وَالجَهْلُ ظَلَامٌ وَالصَّبْرُ مِفْتَاحُ الفَرَجِ",
        "target_word": "الفَرَجِ",
        "new_case": "nom",
        "desc": "الفَرَجِ(gen)→الفَرَجُ(nom)",
    },
]


def run_sentence_error_tests(scorer, verbose):
    """Test sentence-level error detection.

    For each test case, take a correctly-read sentence audio and modify
    one word's expected case ending. The system should flag that specific
    word as WRONG_IRAB (or WRONG_TASHKEEL).

    Returns (detected, total, details).
    """
    print("── Sentence-Level Error Detection ─────────────")
    print("  (Audio is correct, book has wrong expected case on one word)")
    print()

    detected = 0
    total = 0
    details = []

    for test in SENTENCE_ERROR_TESTS:
        audio_path = TEST_DATA_DIR / f"{test['audio_id']}.webm"
        if not audio_path.exists():
            print(f"  [{test['audio_id']}] SKIP - file not found")
            continue

        audio = read_audio(audio_path)

        # Modify the expected text: swap the target word's case ending
        modified_text = test["original_text"].replace(
            test["target_word"],
            swap_case_ending(test["target_word"], test["new_case"]),
        )

        # Run pipeline with modified expected text
        sentence_book = Book.from_sentence(modified_text)
        config = Config()
        pipe = I3rabPipeline(sentence_book, config)
        pipe.scorer = scorer

        result = pipe.evaluate_phrase(audio)
        word_results = result["results"]

        # Find the target word in results
        target_base = strip_harakat(test["target_word"])
        target_found = False
        error_caught = False

        for wd in word_results:
            ref_base = strip_harakat(wd.ref_word) if wd.ref_word else ""
            if ref_base == target_base:
                target_found = True
                # Check if the system flagged it as wrong
                is_error = wd.kind in (
                    DiffKind.WRONG_IRAB,
                    DiffKind.WRONG_TASHKEEL,
                )
                error_caught = is_error
                total += 1

                if error_caught:
                    detected += 1
                    status = "DETECT"
                else:
                    status = "MISS  "

                if verbose or not error_caught:
                    print(
                        f"  [{test['audio_id']}] {status}  "
                        f"{test['desc']}  "
                        f"kind={wd.kind.value}  "
                        f"detected_case={wd.detected_case}  "
                        f"expected_case={wd.expected_case}"
                    )

                details.append({
                    "test": test["desc"],
                    "audio": test["audio_id"],
                    "caught": error_caught,
                    "kind": wd.kind.value,
                    "detected_case": wd.detected_case,
                    "expected_case": wd.expected_case,
                })
                break

        if not target_found:
            total += 1
            print(
                f"  [{test['audio_id']}] MISS   "
                f"{test['desc']}  "
                f"(target word '{target_base}' not found in results)"
            )
            details.append({
                "test": test["desc"],
                "audio": test["audio_id"],
                "caught": False,
                "kind": "not_found",
            })

    return detected, total, details


# ── Sentence-level false positive check ────────────────────────

def run_sentence_fp_tests(scorer, verbose):
    """Re-run correct sentence tests to check for false positives.

    Uses the existing manifest's sentence entries. All words should be
    CORRECT or PAUSAL_OK since the user read them correctly.

    Returns (false_positives, total_words, details).
    """
    print("── Sentence-Level False Positive Check ────────")
    print("  (Audio is correct, book is correct → should all be CORRECT)")
    print()

    manifest = json.loads(MANIFEST_PATH.read_text())
    sentence_entries = [e for e in manifest if e.get("type") == "sentence"]

    false_positives = 0
    total_words = 0
    fp_details = []

    for entry in sentence_entries:
        filepath = TEST_DATA_DIR / entry["filename"]
        if not filepath.exists():
            continue

        audio = read_audio(filepath)
        text = entry["text_diacritized"]
        sentence_book = Book.from_sentence(text)
        if not sentence_book.words:
            continue

        config = Config()
        pipe = I3rabPipeline(sentence_book, config)
        pipe.scorer = scorer

        result = pipe.evaluate_phrase(audio)
        word_results = result["results"]

        for wd in word_results:
            total_words += 1
            is_ok = wd.kind in (DiffKind.CORRECT, DiffKind.PAUSAL_OK)
            if not is_ok:
                false_positives += 1
                fp_details.append({
                    "rec_id": entry["id"],
                    "word": wd.ref_word,
                    "kind": wd.kind.value,
                    "detected": wd.detected_case,
                    "expected": wd.expected_case,
                })
                if verbose:
                    print(
                        f"  [{entry['id']}] FALSE POS  "
                        f"word={wd.ref_word}  "
                        f"kind={wd.kind.value}  "
                        f"detected={wd.detected_case}  "
                        f"expected={wd.expected_case}"
                    )

    return false_positives, total_words, fp_details


def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    print("Loading scorer...")
    config = Config()
    scorer = DiacriticsScorer(config)
    scorer.load()
    print()

    # 1. Word-level error detection
    w_detected, w_total, w_fp, w_fp_total = run_word_error_tests(scorer, verbose)
    print()

    # 2. Sentence-level error detection
    s_detected, s_total, s_details = run_sentence_error_tests(scorer, verbose)
    print()

    # 3. Sentence-level false positive check
    fp_count, fp_total, fp_details = run_sentence_fp_tests(scorer, verbose)
    print()

    # ── Summary ──────────────────────────────────────────
    print("=" * 60)
    print("ERROR DETECTION SUMMARY")
    print("=" * 60)
    print()

    # Word-level
    w_rate = w_detected / w_total * 100 if w_total > 0 else 0
    print(f"Word-Level Error Detection:")
    print(f"  Errors detected: {w_detected}/{w_total} ({w_rate:.1f}%)")
    w_fp_rate = w_fp / w_fp_total * 100 if w_fp_total > 0 else 0
    print(f"  False positives: {w_fp}/{w_fp_total} ({w_fp_rate:.1f}%)")
    print()

    # Sentence-level
    s_rate = s_detected / s_total * 100 if s_total > 0 else 0
    print(f"Sentence-Level Error Detection:")
    print(f"  Errors detected: {s_detected}/{s_total} ({s_rate:.1f}%)")
    print()

    # False positives (sentence)
    fp_rate = fp_count / fp_total * 100 if fp_total > 0 else 0
    print(f"Sentence-Level False Positives:")
    print(f"  False alarms: {fp_count}/{fp_total} words ({fp_rate:.1f}%)")
    if fp_details:
        print(f"  Details:")
        for fp in fp_details:
            print(
                f"    [{fp['rec_id']}] {fp['word']}  "
                f"kind={fp['kind']}  "
                f"detected={fp['detected']}  expected={fp['expected']}"
            )
    print()

    # Combined
    total_errors = w_total + s_total
    total_detected = w_detected + s_detected
    combined_rate = total_detected / total_errors * 100 if total_errors > 0 else 0
    total_fp = w_fp + fp_count
    total_fp_pool = w_fp_total + fp_total
    combined_fp_rate = total_fp / total_fp_pool * 100 if total_fp_pool > 0 else 0

    print(f"Combined:")
    print(f"  Error detection rate: {total_detected}/{total_errors} ({combined_rate:.1f}%)")
    print(f"  False positive rate:  {total_fp}/{total_fp_pool} ({combined_fp_rate:.1f}%)")
    print("=" * 60)

    # Missed errors detail
    missed = [d for d in s_details if not d["caught"]]
    if missed:
        print()
        print("MISSED ERRORS (sentence-level):")
        for m in missed:
            print(f"  [{m['audio']}] {m['test']}  kind={m['kind']}")


if __name__ == "__main__":
    main()
