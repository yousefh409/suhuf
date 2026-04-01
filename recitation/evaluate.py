#!/usr/bin/env python3
"""Evaluation harness: run all test recordings through the scoring pipeline.

Uses the same classify_words() as production, with CTC scoring + Whisper
for wrong word detection. Simulates a streaming session where the position
is already known (which it would be in production by the time words are scored).
"""

import sys, json, time, re
import numpy as np
import torch
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

from engine import RecitationEngine, StreamingSession
from server import classify_words
from arabic import strip_diacritics

MODEL_PATH = BASE / "models" / "ssl_xls_r_v5"
PASSAGES_FILE = BASE / "passage.json"
MANIFEST_FILE = BASE / "test_data" / "manifest.jsonl"
TEST_DIR = BASE / "test_data"


def load_passages():
    """Load all passages from passage.json."""
    with open(PASSAGES_FILE) as f:
        data = json.load(f)
    return {p["id"]: p["phrases"] for p in data["passages"] if "phrases" in p}


def load_manifest():
    entries = []
    with open(MANIFEST_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def score_with_whisper(engine, audio_np, phrase_text):
    """Score a phrase using CTC + Whisper (same signals as production).

    In production streaming, position is already known by the time words
    are scored. This simulates that: CTC scores the known phrase, Whisper
    provides wrong-word detection.

    Returns (word_results, greedy, whisper_words).
    """
    waveform = torch.from_numpy(audio_np)
    word_results, greedy, full_score = engine.score_phrase(waveform, phrase_text)

    # Whisper transcription for wrong word detection
    # Use last 5s, same as streaming pipeline
    max_samples = int(5.0 * 16000)
    whisper_audio = audio_np[-max_samples:] if len(audio_np) > max_samples else audio_np
    whisper_words = engine.whisper_transcribe(whisper_audio)

    # Compute per-word Whisper match (same as StreamingSession)
    phrase_words = phrase_text.split()
    wmatch = StreamingSession._whisper_word_matches(whisper_words, phrase_words)

    # Only trust Whisper mismatches if it matched a reasonable fraction of
    # the phrase. If Whisper missed most words, it's a transcription quality
    # issue, not evidence of wrong words.
    match_ratio = sum(wmatch) / len(wmatch) if wmatch else 1.0
    trust_whisper = match_ratio >= 0.5

    for wr in word_results:
        wi = wr["word_idx"]
        if trust_whisper:
            wr["whisper_match"] = wmatch[wi] if wi < len(wmatch) else True
        else:
            wr["whisper_match"] = True  # Don't trust incomplete Whisper

    return word_results, greedy, whisper_words


# Transliteration-to-word-index for ajrumiyyah phrases (verified against passage.json)
_TRANSLIT_MAP = {
    (0, "kalam"): 0, (0, "lafth"): 2, (0, "lafz"): 2,
    (0, "murakab"): 3, (0, "mufeed"): 4, (0, "wad3"): 5,
    (1, "aqsamuhu"): 0, (1, "ism"): 2, (1, "fe3l"): 3, (1, "fi3l"): 3,
    (1, "harf"): 4,
    (2, "ism"): 0, (2, "khafdh"): 2, (2, "tanween"): 3,
    (2, "alif"): 5, (2, "lam"): 6,
    (3, "rubba"): 8, (3, "ba2"): 9, (3, "kaf"): 10, (3, "lam"): 11,
    (5, "seen"): 3, (5, "ta2neeth"): 6, (5, "sakinah"): 7,
    (7, "taghyeer"): 2,
    (8, "aqsamuhu"): 0, (8, "raf3"): 2, (8, "nasb"): 3,
    (8, "khafdh"): 4, (8, "jazm"): 5,
    (9, "raf3"): 3, (9, "nasb"): 4, (9, "khafdh"): 5, (9, "jazm"): 7,
    (10, "raf3"): 3, (10, "nasb"): 4, (10, "jazm"): 5,
}


def _parse_clause(phrase_idx, clause, phrase_word_count):
    """Parse one atomic clause into [(word_idx, error_type)] or None if unparseable."""
    clause = clause.lower().strip()

    if (re.match(r"sukoon\s+on", clause)
            and "no tanween" not in clause
            and not re.search(r"fatha|kasra|dhamma|damma", clause)):
        return []

    m = re.match(
        r"(?:fatha|kasra|dhamma|damma)\s+on\s+(?:the\s+)?last\s+letters?\s+of\s+(.+)",
        clause,
    )
    if m:
        words_str = m.group(1)
        words = re.split(r",\s*and\s+|,\s*|\s+and\s+", words_str)
        results = []
        for w in words:
            w = w.strip()
            if not w:
                continue
            idx = _TRANSLIT_MAP.get((phrase_idx, w))
            if idx is not None:
                results.append((idx, "i3rab"))
        return results if results else None

    m = re.match(
        r"(?:fatha|kasra|dhamma|damma)\s+on\s+the\s+\w+\s+in\s+(\w+)",
        clause,
    )
    if m:
        word = m.group(1)
        idx = _TRANSLIT_MAP.get((phrase_idx, word))
        if idx is not None:
            return [(idx, "tashkeel")]
        return None

    if "no tanween" in clause and "last word" in clause:
        return [(phrase_word_count - 1, "diacritic")]
    if "no tanween" in clause:
        return [(phrase_word_count - 1, "diacritic")]

    return None


def parse_note_errors(phrase_idx, notes, phrase_word_count):
    """Parse notes into structured expected errors."""
    text = notes.lower().strip()
    if text.startswith("correct reading"):
        text = text[len("correct reading"):].strip().lstrip(",").strip()

    all_errors = []
    has_unparseable = False
    sentences = [s.strip().rstrip(".") for s in text.split(". ")]
    sentences = [s for s in sentences if s]

    for sentence in sentences:
        result = _parse_clause(phrase_idx, sentence, phrase_word_count)
        if result is None:
            if sentence.startswith("sukoon"):
                m = re.search(
                    r",\s*((?:fatha|kasra|dhamma|damma|no tanween)\s+on\s+.+)$",
                    sentence,
                )
                if m:
                    result2 = _parse_clause(phrase_idx, m.group(1), phrase_word_count)
                    if result2 is not None:
                        all_errors.extend(result2)
                        continue
            has_unparseable = True
        else:
            all_errors.extend(result)

    return all_errors, has_unparseable


def classify_recording(notes):
    """Classify a recording as correct or error based on its notes."""
    notes = notes.lower().strip()
    if notes in ("correct reading", "correct ereading", "test"):
        return True
    if notes.startswith("correct reading"):
        detail = notes[len("correct reading"):].strip().lstrip(",").strip()
        if not detail:
            return True
        detail_lower = detail.lower()
        acceptable = ("sukoon" in detail_lower or "pause" in detail_lower
                      or "correct" in detail_lower)
        has_vowel_error = any(x in detail_lower for x in
                             ("fatha", "kasra", "dhamma", "damma", "tanween"))
        if acceptable and not has_vowel_error:
            return True
        if has_vowel_error:
            return False
        return True
    for part in notes.split("."):
        part = part.strip()
        if not part:
            continue
        if "sukoon" in part and "no tanween" not in part and not any(
                x in part for x in ("kasra", "fatha", "dhamma", "damma")):
            continue
        return False
    return True


def run_evaluation(engine, all_passages, manifest, verbose=False):
    """Run all recordings through the scoring pipeline."""
    all_results = []

    for idx, entry in enumerate(manifest):
        audio_path = TEST_DIR / entry["file"]
        phrase_idx = entry["phrase_idx"]
        notes = entry["notes"]
        passage_id = entry.get("passage_id", "ajrumiyyah")

        phrases = all_passages.get(passage_id)
        if not phrases or phrase_idx >= len(phrases):
            continue

        phrase_text = phrases[phrase_idx]
        all_words = phrase_text.split()
        is_correct = classify_recording(notes)
        phrase_word_count = len(all_words)
        expected_errors, _ = parse_note_errors(phrase_idx, notes, phrase_word_count)

        t0 = time.time()
        try:
            waveform = engine.load_audio(str(audio_path))
            audio_np = waveform.numpy()
            word_results, greedy, whisper_words = score_with_whisper(
                engine, audio_np, phrase_text)
        except Exception as e:
            print(f"      ERROR: {e}")
            continue
        elapsed = time.time() - t0

        # Classify using production classify_words
        classified = classify_words(word_results, all_words, streaming=False)

        rec_result = {
            "idx": idx,
            "file": entry["file"],
            "phrase_idx": phrase_idx,
            "notes": notes,
            "is_correct": is_correct,
            "expected_errors": expected_errors,
            "classified": classified,
            "whisper_words": whisper_words,
            "elapsed": elapsed,
        }
        all_results.append(rec_result)

        if verbose:
            print(f"\n[{idx:3d}] {entry['file']}")
            print(f"      Notes: {notes}")
            print(f"      Whisper: {' '.join(whisper_words)}")
            for cw in classified:
                d = cw['debug']
                print(f"        {cw['word']:>20s}  {cw['status']:>8s}  "
                      f"type={cw.get('error_type') or '-':>12s}  eff={d['eff']}")

    return all_results


def analyze_results(all_results):
    """Analyze results and report accuracy metrics."""

    print(f"\n{'='*80}")
    print(f"EVALUATION RESULTS  (production classify_words)")
    print(f"{'='*80}")
    print(f"Total recordings: {len(all_results)}")

    correct_recs = [r for r in all_results if r["is_correct"]]
    error_recs = [r for r in all_results if not r["is_correct"]]
    print(f"Correct recordings: {len(correct_recs)}")
    print(f"Error recordings: {len(error_recs)}")

    # ── False positives on correct recordings ──
    total_correct_words = 0
    false_positives = 0
    fp_details = []

    for rec in correct_recs:
        for cw in rec["classified"]:
            total_correct_words += 1
            if cw["status"] != "correct":
                false_positives += 1
                fp_details.append({
                    "file": rec["file"],
                    "word": cw["word"],
                    "eff": cw["debug"]["eff"],
                    "type": cw["error_type"],
                    "detail": cw.get("error_detail", ""),
                })

    fp_rate = false_positives / total_correct_words * 100 if total_correct_words > 0 else 0

    print(f"\n── False Positives (correct readings flagged as errors) ──")
    print(f"Total correct words: {total_correct_words}")
    print(f"False positives: {false_positives}  ({fp_rate:.1f}%)")
    if fp_details:
        print(f"Details:")
        for fp in fp_details[:20]:
            print(f"  {fp['file']}: {fp['word']}  eff={fp['eff']}  "
                  f"[{fp['type']}] {fp['detail']}")

    # ── Precise detection (word-level, type-checked) ──
    COMPATIBLE_TYPES = {
        "i3rab": {"i3rab"},
        "tashkeel": {"tashkeel", "diacritic"},
        "diacritic": {"diacritic", "tashkeel", "i3rab"},
    }

    parseable_recs = [r for r in error_recs if r.get("expected_errors")]
    print(f"\n── Precise Detection (word-level, type-checked) ──")
    print(f"  Parseable error recordings: {len(parseable_recs)} / {len(error_recs)}")

    total_expected = 0
    detected_any = 0
    detected_correct_type = 0
    missed_details = []

    for rec in parseable_recs:
        flagged_map = {}
        for cw in rec["classified"]:
            if cw["status"] != "correct":
                flagged_map[cw["idx"]] = cw["error_type"]

        for (exp_wi, exp_type) in rec["expected_errors"]:
            total_expected += 1
            got_type = flagged_map.get(exp_wi)
            if got_type is not None:
                detected_any += 1
                if got_type in COMPATIBLE_TYPES.get(exp_type, {exp_type}):
                    detected_correct_type += 1
                else:
                    missed_details.append({
                        "file": rec["file"], "idx": rec["idx"],
                        "word_idx": exp_wi, "expected": exp_type,
                        "got": got_type, "note": rec["notes"][:60],
                    })
            else:
                missed_details.append({
                    "file": rec["file"], "idx": rec["idx"],
                    "word_idx": exp_wi, "expected": exp_type,
                    "got": None, "note": rec["notes"][:60],
                })

    any_rate = detected_any / total_expected * 100 if total_expected else 0
    type_rate = detected_correct_type / total_expected * 100 if total_expected else 0
    print(f"  Expected error words:       {total_expected}")
    print(f"  Detected (any signal):      {detected_any}  ({any_rate:.1f}%)")
    print(f"  Detected (correct type):    {detected_correct_type}  ({type_rate:.1f}%)")

    if missed_details:
        print(f"\n  Missed / mistyped ({len(missed_details)}):")
        for m in missed_details:
            got_str = m["got"] or "MISSED"
            print(f"    [{m['idx']:3d}] word[{m['word_idx']}]  "
                  f"expected={m['expected']}  got={got_str}  [{m['note']}]")


def main():
    if "--mutations" in sys.argv:
        # Run the mutation test suite (primary test)
        import test_mutations
        test_mutations.main()
        return

    all_passages = load_passages()
    manifest = load_manifest()
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    engine = RecitationEngine(str(MODEL_PATH))

    print(f"Running {len(manifest)} recordings through pipeline (CTC + Whisper)...")
    results = run_evaluation(engine, all_passages, manifest, verbose=verbose)
    analyze_results(results)

    print(f"\nNOTE: For the primary test, run: python test_mutations.py")


if __name__ == "__main__":
    main()
