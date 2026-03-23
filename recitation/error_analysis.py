#!/usr/bin/env python3
"""Deep error pattern analysis for the i3rab Arabic recitation correction system.

Runs evaluate_pcd_live() on all sentence recordings from the test manifest,
collects every word-level error, and produces a comprehensive categorized
error report designed to surface systematic patterns.
"""

import json
import io
import sys
import os
from pathlib import Path
from collections import Counter, defaultdict

import numpy as np

# ── Setup ─────────────────────────────────────────────────────────────────

PROJECT = Path("/Users/yousefh/Desktop/Cool Code/i3rab")
TEST_DATA_DIR = PROJECT / "test_data"
MANIFEST_PATH = TEST_DATA_DIR / "manifest.json"

sys.path.insert(0, str(PROJECT))

from i3rab.book import Book
from i3rab.config import Config
from i3rab.pipeline import I3rabPipeline
from i3rab.arabic import strip_harakat, is_preposition, is_definite

# ── Arabic word-type classifier ───────────────────────────────────────────

PARTICLES = {
    "في", "من", "الى", "على", "عن", "إلى",  # prepositions
    "إن", "أن", "إنّ", "أنّ", "لن", "لم", "لا", "ما", "هل",
    "و", "ف", "ب", "ل", "ك", "ثم", "ثمّ",
    "هذا", "هذه", "ذلك", "تلك",
    "الذي", "التي", "عن", "من",
}

VERB_PREFIXES = {"ي", "ت", "ن", "أ"}  # present-tense prefixes


def classify_word_type(diacritized: str) -> str:
    """Rough Arabic word-type classifier."""
    base = strip_harakat(diacritized)
    if not base:
        return "unknown"

    if base in PARTICLES:
        return "preposition/particle"

    if is_preposition(diacritized):
        return "preposition/particle"

    if is_definite(diacritized):
        # Check if it's an adjective-like word (ends in يّ/ية pattern)
        if base.endswith("ية") or base.endswith("يّة"):
            return "adjective_with_article"
        return "noun_with_article"

    # Past-tense verbs: typically fatha pattern on first radical
    # Very simplified heuristic: 3-letter roots with past tense pattern
    if len(base) >= 3 and not base.startswith("ال"):
        # Check for verb prefixes (present tense markers)
        if base[0] in VERB_PREFIXES and len(base) >= 4:
            return "verb"
        # Check for common past-tense patterns (CaCaCa)
        # Words that end with a fatha on last letter and are short
        if len(base) <= 5 and not base.endswith("ة"):
            # Simple heuristic: past verbs are typically short words
            # without definite article
            harakat = []
            for c in diacritized:
                if c == "\u064E":  # fatha
                    harakat.append("a")
                elif c == "\u064F":  # damma
                    harakat.append("u")
                elif c == "\u0650":  # kasra
                    harakat.append("i")
            if len(harakat) >= 2 and harakat[0] in ("a", "u", "i"):
                return "verb"

    # Adjectives: often follow definite nouns, hard to detect in isolation
    # Use tanween as a heuristic (indefinite adjective/noun)
    for c in diacritized:
        if c in ("\u064B", "\u064C", "\u064D"):  # tanween
            return "indefinite_noun/adj"

    return "other_noun"


def word_position_label(idx: int, total: int) -> str:
    """Classify word position within the sentence."""
    if total <= 1:
        return "only"
    if idx == 0:
        return "first"
    if idx == total - 1:
        return "last"
    return "middle"


def sentence_length_category(n_words: int) -> str:
    """Categorize sentence by word count."""
    if n_words < 5:
        return "short (<5)"
    if n_words <= 15:
        return "medium (5-15)"
    return "long (>15)"


# ── Audio loading ─────────────────────────────────────────────────────────

def read_audio(filepath: Path) -> np.ndarray:
    """Read an audio file into float32 numpy array at 16kHz."""
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


# ── Main analysis ─────────────────────────────────────────────────────────

def run_error_analysis():
    print("=" * 80)
    print("   i3rab ERROR PATTERN ANALYSIS")
    print("   Using evaluate_pcd_live() on all sentence recordings")
    print("=" * 80)

    # Load manifest
    manifest = json.loads(MANIFEST_PATH.read_text())
    sentence_entries = [e for e in manifest if e.get("type") == "sentence"]
    print(f"\nFound {len(sentence_entries)} sentence recordings to analyze.\n")

    # Initialize pipeline (loads PCD model once)
    config = Config()
    # We'll create a pipeline per sentence since each has its own book

    all_errors = []          # Detailed per-error records
    all_words_results = []   # Every word result (correct or not)
    sentence_results = []    # Per-sentence summary

    for entry_idx, entry in enumerate(sentence_entries):
        rec_id = entry["id"]
        text_diac = entry["text_diacritized"]
        text_base = entry.get("text_base", strip_harakat(text_diac))
        filepath = TEST_DATA_DIR / entry["filename"]

        if not filepath.exists():
            print(f"  [{rec_id}] SKIP - file not found")
            continue

        ref_words = text_diac.split()
        n_words = len(ref_words)
        sent_len_cat = sentence_length_category(n_words)

        print(f"  [{rec_id}] Processing ({n_words} words, {sent_len_cat}): {text_base[:60]}...")

        try:
            audio = read_audio(filepath)
        except Exception as e:
            print(f"  [{rec_id}] ERROR reading audio: {e}")
            continue

        # Create a fresh book and pipeline for this sentence
        book = Book.from_sentence(text_diac)
        pipe = I3rabPipeline(book, config)

        try:
            result = pipe.evaluate_pcd_live(audio)
        except Exception as e:
            print(f"  [{rec_id}] ERROR in evaluate_pcd_live: {e}")
            import traceback
            traceback.print_exc()
            continue

        scored_words = result.get("scored_words", [])
        transcript = result.get("transcript", "")

        # Per-sentence stats
        n_correct = sum(1 for sw in scored_words if sw["kind"] in ("correct", "pausal_ok"))
        n_total = len(scored_words)

        sentence_results.append({
            "rec_id": rec_id,
            "n_words": n_words,
            "sent_len_cat": sent_len_cat,
            "n_scored": n_total,
            "n_correct": n_correct,
            "n_errors": n_total - n_correct,
            "transcript": transcript,
            "reference": text_diac,
        })

        # Process each scored word
        for sw in scored_words:
            word_idx_in_sentence = sw["index"]  # This is the book-level index
            ref_word = sw["ref_word"]
            hyp_word = sw.get("hyp_word")
            kind = sw["kind"]
            confidence = sw.get("confidence", "high")
            detected_case = sw.get("detected_case")
            expected_case = sw.get("expected_case")
            haraka_diffs = sw.get("haraka_diffs", [])

            # Determine position in sentence
            pos_label = word_position_label(word_idx_in_sentence, n_words)

            # Get the book word to check hypotheses
            bw = book.words[word_idx_in_sentence] if word_idx_in_sentence < len(book.words) else None
            n_hypotheses = len(bw.hypotheses) if bw else 0
            multi_hyp = n_hypotheses > 1

            # Classify word type
            word_type = classify_word_type(ref_word)

            # Check for substitution vs omission in haraka diffs
            substitution_errors = [hd for hd in haraka_diffs if hd.get("got") and hd["got"] != "(none)"]
            omission_errors = [hd for hd in haraka_diffs if not hd.get("got") or hd["got"] == "(none)"]

            word_record = {
                "rec_id": rec_id,
                "ref_word": ref_word,
                "hyp_word": hyp_word,
                "kind": kind,
                "confidence": confidence,
                "detected_case": detected_case,
                "expected_case": expected_case,
                "word_idx": word_idx_in_sentence,
                "position": pos_label,
                "word_type": word_type,
                "n_hypotheses": n_hypotheses,
                "multi_hyp": multi_hyp,
                "n_words_in_sentence": n_words,
                "sent_len_cat": sent_len_cat,
                "haraka_diffs": haraka_diffs,
                "n_substitution_errors": len(substitution_errors),
                "n_omission_errors": len(omission_errors),
            }

            all_words_results.append(word_record)

            if kind not in ("correct", "pausal_ok"):
                all_errors.append(word_record)

    # ══════════════════════════════════════════════════════════════════════
    # REPORT
    # ══════════════════════════════════════════════════════════════════════

    total_words_assessed = len(all_words_results)
    total_errors = len(all_errors)
    total_correct = total_words_assessed - total_errors

    print("\n")
    print("=" * 80)
    print("   COMPREHENSIVE ERROR ANALYSIS REPORT")
    print("=" * 80)

    # ── Overall Summary ──────────────────────────────────────────────────
    print("\n" + "-" * 80)
    print("1. OVERALL SUMMARY")
    print("-" * 80)
    print(f"   Sentences processed:     {len(sentence_results)}")
    print(f"   Total words assessed:    {total_words_assessed}")
    print(f"   Correct (incl pausal):   {total_correct}")
    print(f"   Errors:                  {total_errors}")
    if total_words_assessed > 0:
        print(f"   Accuracy:                {total_correct / total_words_assessed * 100:.1f}%")
        print(f"   Error rate:              {total_errors / total_words_assessed * 100:.1f}%")

    # ── Per-Sentence Summary ─────────────────────────────────────────────
    print("\n" + "-" * 80)
    print("2. PER-SENTENCE RESULTS")
    print("-" * 80)
    for sr in sentence_results:
        acc = sr["n_correct"] / sr["n_scored"] * 100 if sr["n_scored"] > 0 else 0
        status = "PASS" if sr["n_errors"] == 0 else "FAIL"
        print(f"   [{sr['rec_id']}] {status}  {sr['n_correct']}/{sr['n_scored']} correct ({acc:.0f}%)  [{sr['sent_len_cat']}]")
        if sr["n_errors"] > 0:
            # Show errors for this sentence
            sent_errors = [e for e in all_errors if e["rec_id"] == sr["rec_id"]]
            for e in sent_errors:
                print(f"           ERROR: {e['ref_word']} -> {e['hyp_word'] or '(missing)'} "
                      f"[{e['kind']}] conf={e['confidence']} "
                      f"exp_case={e['expected_case']} det_case={e['detected_case']}")

    # ── Error Type Distribution ──────────────────────────────────────────
    print("\n" + "-" * 80)
    print("3. ERROR TYPE DISTRIBUTION")
    print("-" * 80)
    error_type_counts = Counter(e["kind"] for e in all_errors)
    for kind, count in error_type_counts.most_common():
        pct = count / total_errors * 100 if total_errors > 0 else 0
        print(f"   {kind:<20s}  {count:>4d}  ({pct:5.1f}%)")

    # ── Errors by Word Position ──────────────────────────────────────────
    print("\n" + "-" * 80)
    print("4. ERROR RATE BY WORD POSITION")
    print("-" * 80)
    position_total = Counter(w["position"] for w in all_words_results)
    position_errors = Counter(e["position"] for e in all_errors)
    for pos in ["first", "middle", "last", "only"]:
        t = position_total.get(pos, 0)
        e = position_errors.get(pos, 0)
        rate = e / t * 100 if t > 0 else 0
        print(f"   {pos:<10s}  {e:>3d} errors / {t:>4d} total  ({rate:5.1f}% error rate)")

    # ── Errors by Word Type ──────────────────────────────────────────────
    print("\n" + "-" * 80)
    print("5. ERROR RATE BY WORD TYPE")
    print("-" * 80)
    type_total = Counter(w["word_type"] for w in all_words_results)
    type_errors = Counter(e["word_type"] for e in all_errors)
    for wtype in sorted(type_total.keys(), key=lambda x: type_errors.get(x, 0), reverse=True):
        t = type_total[wtype]
        e = type_errors.get(wtype, 0)
        rate = e / t * 100 if t > 0 else 0
        print(f"   {wtype:<25s}  {e:>3d} errors / {t:>4d} total  ({rate:5.1f}% error rate)")

    # ── Errors by Number of Hypotheses ───────────────────────────────────
    print("\n" + "-" * 80)
    print("6. ERROR RATE BY HYPOTHESIS COUNT (single vs multi)")
    print("-" * 80)
    for multi in [False, True]:
        label = "Multi-hyp (>1)" if multi else "Single-hyp (1)"
        t = sum(1 for w in all_words_results if w["multi_hyp"] == multi)
        e = sum(1 for err in all_errors if err["multi_hyp"] == multi)
        rate = e / t * 100 if t > 0 else 0
        print(f"   {label:<20s}  {e:>3d} errors / {t:>4d} total  ({rate:5.1f}% error rate)")

    # ── Errors by Sentence Length ────────────────────────────────────────
    print("\n" + "-" * 80)
    print("7. ERROR RATE BY SENTENCE LENGTH")
    print("-" * 80)
    for cat in ["short (<5)", "medium (5-15)", "long (>15)"]:
        t = sum(1 for w in all_words_results if w["sent_len_cat"] == cat)
        e = sum(1 for err in all_errors if err["sent_len_cat"] == cat)
        rate = e / t * 100 if t > 0 else 0
        print(f"   {cat:<18s}  {e:>3d} errors / {t:>4d} total  ({rate:5.1f}% error rate)")

    # ── Errors by Confidence Level ───────────────────────────────────────
    print("\n" + "-" * 80)
    print("8. ERROR DISTRIBUTION BY CONFIDENCE LEVEL")
    print("-" * 80)
    conf_total = Counter(w["confidence"] for w in all_words_results)
    conf_errors = Counter(e["confidence"] for e in all_errors)
    for conf in ["high", "medium", "low"]:
        t = conf_total.get(conf, 0)
        e = conf_errors.get(conf, 0)
        rate = e / t * 100 if t > 0 else 0
        print(f"   {conf:<10s}  {e:>3d} errors / {t:>4d} total  ({rate:5.1f}% error rate)")

    # ── Substitution vs Omission tashkeel errors ─────────────────────────
    print("\n" + "-" * 80)
    print("9. TASHKEEL ERROR SUB-TYPES (substitution vs omission)")
    print("-" * 80)
    tashkeel_errors = [e for e in all_errors if e["kind"] == "tashkeel"]
    n_sub = sum(1 for e in tashkeel_errors if e["n_substitution_errors"] > 0)
    n_omi = sum(1 for e in tashkeel_errors if e["n_omission_errors"] > 0)
    n_both = sum(1 for e in tashkeel_errors if e["n_substitution_errors"] > 0 and e["n_omission_errors"] > 0)
    print(f"   Total tashkeel errors:      {len(tashkeel_errors)}")
    print(f"   With substitution errors:   {n_sub}")
    print(f"   With omission errors:       {n_omi}")
    print(f"   With both:                  {n_both}")

    # ── Error Type x Word Type Cross-Table ───────────────────────────────
    print("\n" + "-" * 80)
    print("10. CROSS-TABLE: ERROR TYPE x WORD TYPE")
    print("-" * 80)
    cross = defaultdict(lambda: defaultdict(int))
    for e in all_errors:
        cross[e["kind"]][e["word_type"]] += 1

    all_word_types = sorted(set(e["word_type"] for e in all_errors))
    header = f"   {'Error Type':<20s}" + "".join(f" {wt[:12]:>12s}" for wt in all_word_types)
    print(header)
    for kind in sorted(cross.keys()):
        row = f"   {kind:<20s}"
        for wt in all_word_types:
            row += f" {cross[kind][wt]:>12d}"
        print(row)

    # ── Error Type x Sentence Length Cross-Table ─────────────────────────
    print("\n" + "-" * 80)
    print("11. CROSS-TABLE: ERROR TYPE x SENTENCE LENGTH")
    print("-" * 80)
    cross_len = defaultdict(lambda: defaultdict(int))
    for e in all_errors:
        cross_len[e["kind"]][e["sent_len_cat"]] += 1

    cats = ["short (<5)", "medium (5-15)", "long (>15)"]
    header = f"   {'Error Type':<20s}" + "".join(f" {c:>15s}" for c in cats)
    print(header)
    for kind in sorted(cross_len.keys()):
        row = f"   {kind:<20s}"
        for c in cats:
            row += f" {cross_len[kind][c]:>15d}"
        print(row)

    # ── Error Type x Word Position ───────────────────────────────────────
    print("\n" + "-" * 80)
    print("12. CROSS-TABLE: ERROR TYPE x WORD POSITION")
    print("-" * 80)
    cross_pos = defaultdict(lambda: defaultdict(int))
    for e in all_errors:
        cross_pos[e["kind"]][e["position"]] += 1

    positions = ["first", "middle", "last"]
    header = f"   {'Error Type':<20s}" + "".join(f" {p:>10s}" for p in positions)
    print(header)
    for kind in sorted(cross_pos.keys()):
        row = f"   {kind:<20s}"
        for p in positions:
            row += f" {cross_pos[kind][p]:>10d}"
        print(row)

    # ── Detailed Error Log ───────────────────────────────────────────────
    print("\n" + "-" * 80)
    print("13. DETAILED ERROR LOG (every failing word)")
    print("-" * 80)
    for i, e in enumerate(all_errors):
        print(f"\n   Error #{i+1}:")
        print(f"     Recording:       {e['rec_id']}")
        print(f"     Reference word:  {e['ref_word']}")
        print(f"     Detected word:   {e['hyp_word'] or '(missing)'}")
        print(f"     Error type:      {e['kind']}")
        print(f"     Word position:   {e['position']} (idx {e['word_idx']} of {e['n_words_in_sentence']})")
        print(f"     Word type:       {e['word_type']}")
        print(f"     Confidence:      {e['confidence']}")
        print(f"     Expected case:   {e['expected_case']}")
        print(f"     Detected case:   {e['detected_case']}")
        print(f"     Hypotheses:      {e['n_hypotheses']} ({'multi' if e['multi_hyp'] else 'single'})")
        print(f"     Sentence length: {e['sent_len_cat']}")
        if e["haraka_diffs"]:
            print(f"     Haraka diffs:")
            for hd in e["haraka_diffs"]:
                irab_label = " [I3RAB POS]" if hd.get("is_irab") else ""
                print(f"       letter='{hd['letter']}' pos={hd['position']} "
                      f"expected={hd['expected']} got={hd['got']}{irab_label}")
        print(f"     Sub-errors:      {e['n_substitution_errors']} substitution, {e['n_omission_errors']} omission")

    # ── Pattern Summary ──────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("   PATTERN ANALYSIS SUMMARY")
    print("=" * 80)

    if total_errors == 0:
        print("\n   No errors found! Perfect accuracy on all test sentences.")
    else:
        print("\n   KEY FINDINGS:\n")

        # Find most error-prone word type
        if type_errors:
            worst_type = max(type_errors.keys(),
                             key=lambda k: type_errors[k] / max(type_total[k], 1))
            wt_rate = type_errors[worst_type] / type_total[worst_type] * 100
            print(f"   1. Most error-prone word type: '{worst_type}' "
                  f"({type_errors[worst_type]}/{type_total[worst_type]} = {wt_rate:.0f}% error rate)")

        # Find most error-prone position
        if position_errors:
            worst_pos = max(position_errors.keys(),
                            key=lambda k: position_errors[k] / max(position_total[k], 1))
            wp_rate = position_errors[worst_pos] / position_total[worst_pos] * 100
            print(f"   2. Most error-prone position:  '{worst_pos}' "
                  f"({position_errors[worst_pos]}/{position_total[worst_pos]} = {wp_rate:.0f}% error rate)")

        # Most common error type
        if error_type_counts:
            most_common_kind, mc_count = error_type_counts.most_common(1)[0]
            print(f"   3. Most common error type:     '{most_common_kind}' ({mc_count} occurrences)")

        # Single vs multi hypothesis
        single_total = sum(1 for w in all_words_results if not w["multi_hyp"])
        single_errors_n = sum(1 for e in all_errors if not e["multi_hyp"])
        multi_total = sum(1 for w in all_words_results if w["multi_hyp"])
        multi_errors_n = sum(1 for e in all_errors if e["multi_hyp"])
        if single_total > 0 and multi_total > 0:
            print(f"   4. Single-hyp error rate:      {single_errors_n}/{single_total} = "
                  f"{single_errors_n / single_total * 100:.1f}%")
            print(f"      Multi-hyp error rate:       {multi_errors_n}/{multi_total} = "
                  f"{multi_errors_n / multi_total * 100:.1f}%")

        # Sentence length impact
        for cat in cats:
            t = sum(1 for w in all_words_results if w["sent_len_cat"] == cat)
            e = sum(1 for err in all_errors if err["sent_len_cat"] == cat)
            if t > 0:
                print(f"   5. Sentence '{cat}' error rate: {e}/{t} = {e / t * 100:.1f}%")

        # Confidence correlation
        high_errs = conf_errors.get("high", 0)
        low_errs = conf_errors.get("low", 0)
        med_errs = conf_errors.get("medium", 0)
        print(f"\n   6. Confidence distribution among errors:")
        print(f"      HIGH confidence errors:   {high_errs} (false positives - system was confident but wrong)")
        print(f"      MEDIUM confidence errors: {med_errs}")
        print(f"      LOW confidence errors:    {low_errs}")

        # I3rab vs tashkeel
        irab_n = error_type_counts.get("irab", 0)
        tash_n = error_type_counts.get("tashkeel", 0)
        if irab_n + tash_n > 0:
            print(f"\n   7. Diacritization error breakdown:")
            print(f"      I3rab (case ending only): {irab_n}")
            print(f"      Tashkeel (internal):      {tash_n}")

        # Most frequently failing words
        word_fail_count = Counter(e["ref_word"] for e in all_errors)
        print(f"\n   8. Most frequently failing reference words:")
        for word, count in word_fail_count.most_common(10):
            print(f"      '{word}': {count} failures")

    print("\n" + "=" * 80)
    print("   END OF REPORT")
    print("=" * 80)


if __name__ == "__main__":
    run_error_analysis()
