#!/usr/bin/env python3
"""Diagnostic: WHY does CTC scoring miss diacritic mutations?

This script investigates the core question: when we swap a diacritic in the
reference text, why does the CTC score barely change?

Analysis:
1. Score correct text -> per-word CTC scores
2. Swap final diacritic (i3rab) -> score mutated text -> measure delta
3. Per-frame posterior probabilities at aligned diacritic frames
4. Compare local posterior ratios: does the model see the diacritics?
5. Alternative scoring: frame-level posterior extraction vs full CTC score
"""

import sys
import json
import numpy as np
import torch
import torch.nn.functional as F
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

from engine import RecitationEngine
from arabic import (
    FATHA, DAMMA, KASRA, FATHATAN, DAMMATAN, KASRATAN, SUKOON, SHADDA,
    HARAKAT, strip_diacritics, get_final_diacritic, replace_final_diacritic,
)

MODEL_PATH = BASE / "models" / "ssl_xls_r_v5"
SESSIONS_DIR = BASE / "test_data" / "sessions"

# Diacritic names for display
DIAC_NAMES = {
    FATHA: "fatha", DAMMA: "damma", KASRA: "kasra",
    FATHATAN: "fathatan", DAMMATAN: "dammatan", KASRATAN: "kasratan",
    SUKOON: "sukoon", SHADDA: "shadda",
}

SHORT_VOWELS = [FATHA, DAMMA, KASRA]
TANWEEN = [FATHATAN, DAMMATAN, KASRATAN]


def load_session(engine, session_dir):
    """Load a session's audio and metadata."""
    meta_path = session_dir / "meta.json"
    audio_path = session_dir / "audio.raw"

    with open(meta_path) as f:
        meta = json.load(f)

    audio = np.fromfile(str(audio_path), dtype=np.float32)
    waveform = torch.from_numpy(audio.copy())
    return meta, waveform


def get_phrase_audio_segment(engine, log_probs, phrase_text):
    """Force-align a phrase and return word boundaries."""
    tokens = engine.text_to_tokens(phrase_text)
    T = log_probs.shape[0]
    if not tokens or T < len(tokens):
        return None

    spans = engine.forced_align(log_probs, tokens)
    word_bounds = engine.word_boundaries_from_alignment(spans, tokens)
    return word_bounds


def analyze_ctc_score_deltas(engine, log_probs, phrase_text, word_bounds):
    """For each word, score correct vs i3rab-mutated and report delta."""
    words = phrase_text.split()
    T = log_probs.shape[0]

    print("\n" + "=" * 80)
    print("ANALYSIS 1: CTC Score Deltas (correct vs mutated i3rab)")
    print("=" * 80)

    results = []
    for wb in word_bounds:
        wi = wb["word_idx"]
        if wi >= len(words):
            continue
        word = words[wi]
        sf, ef = wb["start_frame"], wb["end_frame"]

        # Get segment with small margin
        margin = 2
        sf_m = max(0, sf - margin)
        ef_m = min(T - 1, ef + margin)
        segment = log_probs[sf_m: ef_m + 1]

        # Score the correct word
        correct_tokens = engine.text_to_tokens(word)
        if not correct_tokens or segment.shape[0] < len(correct_tokens):
            continue
        correct_score = engine.ctc_log_prob(segment, correct_tokens) / segment.shape[0]

        # Get the final diacritic
        final_diac, _ = get_final_diacritic(word)
        if not final_diac or final_diac == SUKOON:
            continue  # skip words without a case ending

        # Try all alternative diacritics
        alternatives = {}
        for alt in SHORT_VOWELS + TANWEEN:
            if DIAC_NAMES.get(alt) == DIAC_NAMES.get(final_diac):
                continue
            mutated = replace_final_diacritic(word, alt)
            if mutated == word:
                continue
            mut_tokens = engine.text_to_tokens(mutated)
            if not mut_tokens or segment.shape[0] < len(mut_tokens):
                continue
            mut_score = engine.ctc_log_prob(segment, mut_tokens) / segment.shape[0]
            delta = correct_score - mut_score
            alternatives[DIAC_NAMES[alt]] = {
                "score": mut_score,
                "delta": delta,
                "mutated_word": mutated,
            }

        stripped = strip_diacritics(word)
        print(f"\n  Word [{wi}]: {word}  (consonants: {stripped})")
        print(f"    Correct i3rab: {DIAC_NAMES.get(final_diac, '?')}")
        print(f"    Correct CTC score: {correct_score:.4f}")
        print(f"    Segment frames: {segment.shape[0]} (word frames: {ef - sf + 1})")

        for alt_name, alt_info in sorted(alternatives.items(), key=lambda x: x[1]["delta"]):
            d = alt_info["delta"]
            marker = "  <-- WRONG WINS" if d < 0 else ""
            print(f"    vs {alt_name:12s}: score={alt_info['score']:.4f}  delta={d:+.4f}{marker}")

        results.append({
            "word_idx": wi,
            "word": word,
            "correct_score": correct_score,
            "final_diac": DIAC_NAMES.get(final_diac),
            "alternatives": alternatives,
            "frames": segment.shape[0],
        })

    return results


def analyze_frame_posteriors(engine, log_probs, phrase_text, word_bounds):
    """At frames aligned to diacritics, what are the posteriors for fatha/damma/kasra?"""
    words = phrase_text.split()
    T = log_probs.shape[0]

    # Get full char-level alignment
    tokens = engine.text_to_tokens(phrase_text)
    spans = engine.forced_align(log_probs, tokens)

    print("\n" + "=" * 80)
    print("ANALYSIS 2: Per-Frame Posteriors at Diacritic Positions")
    print("=" * 80)

    # Build token -> char mapping
    token_chars = []
    for tok_id in tokens:
        ch = engine.id2char.get(tok_id, "")
        token_chars.append(ch)

    # Get vocab IDs for diacritics
    diac_ids = {}
    for d in SHORT_VOWELS + TANWEEN + [SUKOON]:
        if d in engine.vocab:
            diac_ids[DIAC_NAMES[d]] = engine.vocab[d]

    print(f"\n  Diacritic token IDs: {diac_ids}")

    # Convert log_probs to probs for readability
    probs = torch.exp(log_probs)  # (T, V)

    results = []
    for span_idx, (target_idx, token_id, sf, ef) in enumerate(spans):
        char = engine.id2char.get(token_id, "")
        if char not in {FATHA, DAMMA, KASRA, FATHATAN, DAMMATAN, KASRATAN}:
            continue

        # Which word does this belong to?
        word_idx = None
        for wb in word_bounds:
            for cs in wb["char_spans"]:
                if cs[0] == target_idx and cs[1] == token_id:
                    word_idx = wb["word_idx"]
                    break

        word_str = words[word_idx] if word_idx is not None and word_idx < len(words) else "?"

        # Check if this is the FINAL diacritic (i3rab position)
        is_final = False
        if word_idx is not None and word_idx < len(words):
            final_diac, _ = get_final_diacritic(words[word_idx])
            # Check if this diacritic's target_idx is in the final position
            # by seeing if there are any non-diacritic tokens after it in this word
            is_final = True  # assume final unless proven otherwise
            for later_span in spans[span_idx + 1:]:
                later_char = engine.id2char.get(later_span[1], "")
                if later_char == "|" or later_char == " ":
                    break  # word boundary
                if later_char not in HARAKAT and later_char != "":
                    is_final = False  # there's another consonant after
                    break

        # Average posterior across aligned frames
        frame_range = list(range(sf, min(ef + 1, T)))
        if not frame_range:
            continue

        avg_probs = probs[frame_range].mean(dim=0)  # (V,)
        avg_log_probs = log_probs[frame_range].mean(dim=0)

        # Get posteriors for all diacritic tokens
        diac_posteriors = {}
        for dname, did in diac_ids.items():
            diac_posteriors[dname] = float(avg_probs[did])

        # Also get blank and top-5 tokens
        blank_prob = float(avg_probs[engine.blank_id])
        top5_indices = avg_probs.topk(5).indices.tolist()
        top5 = [(engine.id2char.get(idx, f"[{idx}]"), float(avg_probs[idx])) for idx in top5_indices]

        correct_name = DIAC_NAMES[char]
        correct_prob = diac_posteriors.get(correct_name, 0)

        # Best alternative in the same group
        if char in {FATHA, DAMMA, KASRA}:
            group = ["fatha", "damma", "kasra"]
        else:
            group = ["fathatan", "dammatan", "kasratan"]

        best_alt_name = None
        best_alt_prob = 0
        for g in group:
            if g != correct_name and diac_posteriors.get(g, 0) > best_alt_prob:
                best_alt_prob = diac_posteriors[g]
                best_alt_name = g

        position_tag = " [FINAL/I3RAB]" if is_final else " [internal]"
        print(f"\n  Word '{word_str}' [{word_idx}], diacritic: {correct_name}{position_tag}")
        print(f"    Aligned frames: {sf}-{ef} ({ef - sf + 1} frames)")
        print(f"    Blank prob:    {blank_prob:.4f}")
        print(f"    Correct ({correct_name:8s}): prob={correct_prob:.6f}")
        if best_alt_name:
            ratio = correct_prob / best_alt_prob if best_alt_prob > 0 else float('inf')
            print(f"    Best alt ({best_alt_name:8s}): prob={best_alt_prob:.6f}  ratio={ratio:.2f}x")
        print(f"    All diacritic posteriors:")
        for dname in sorted(diac_posteriors.keys()):
            marker = " <-- CORRECT" if dname == correct_name else ""
            print(f"      {dname:12s}: {diac_posteriors[dname]:.6f}{marker}")
        print(f"    Top-5 tokens at these frames: {top5}")

        results.append({
            "word_idx": word_idx,
            "word": word_str,
            "diac": correct_name,
            "is_final": is_final,
            "frames": ef - sf + 1,
            "correct_prob": correct_prob,
            "best_alt_name": best_alt_name,
            "best_alt_prob": best_alt_prob,
            "blank_prob": blank_prob,
            "all_posteriors": diac_posteriors,
        })

    return results


def analyze_token_contribution(engine, log_probs, phrase_text, word_bounds):
    """Quantify how much each token contributes to the total CTC score.

    Key question: What fraction of the CTC score comes from consonants vs diacritics?
    """
    words = phrase_text.split()
    T = log_probs.shape[0]
    tokens = engine.text_to_tokens(phrase_text)

    print("\n" + "=" * 80)
    print("ANALYSIS 3: Token Contribution to CTC Score")
    print("=" * 80)

    # Full phrase CTC score
    full_score = engine.ctc_log_prob(log_probs, tokens) / T
    print(f"\n  Full phrase CTC score (per frame): {full_score:.4f}")
    print(f"  Total frames: {T}, Total tokens: {len(tokens)}")

    # Count token types
    n_consonants = 0
    n_diacritics = 0
    n_separators = 0
    for tok_id in tokens:
        ch = engine.id2char.get(tok_id, "")
        if ch in HARAKAT:
            n_diacritics += 1
        elif ch == "|" or ch == " ":
            n_separators += 1
        else:
            n_consonants += 1

    print(f"  Token breakdown: {n_consonants} consonants, {n_diacritics} diacritics, {n_separators} separators")
    print(f"  Diacritic fraction: {n_diacritics / len(tokens):.1%}")

    # Score the phrase with ALL diacritics removed (consonants + separators only)
    stripped_text = strip_diacritics(phrase_text)
    stripped_tokens = engine.text_to_tokens(stripped_text)
    if stripped_tokens and T >= len(stripped_tokens):
        stripped_score = engine.ctc_log_prob(log_probs, stripped_tokens) / T
        print(f"\n  Stripped (no diacritics) CTC score: {stripped_score:.4f}")
        print(f"  Difference (full - stripped): {full_score - stripped_score:.4f}")
        print(f"  => Diacritics contribute {full_score - stripped_score:.4f} per frame to the CTC score")
    else:
        print(f"\n  Could not score stripped text (T={T}, tokens={len(stripped_tokens)})")

    # Per-word analysis: score each word with/without diacritics
    print(f"\n  Per-word diacritized vs stripped scores:")
    for wb in word_bounds:
        wi = wb["word_idx"]
        if wi >= len(words):
            continue
        word = words[wi]
        sf, ef = wb["start_frame"], wb["end_frame"]
        margin = 2
        sf_m = max(0, sf - margin)
        ef_m = min(T - 1, ef + margin)
        segment = log_probs[sf_m: ef_m + 1]

        word_tokens = engine.text_to_tokens(word)
        stripped_word = strip_diacritics(word)
        stripped_word_tokens = engine.text_to_tokens(stripped_word)

        if not word_tokens or segment.shape[0] < len(word_tokens):
            continue
        if not stripped_word_tokens or segment.shape[0] < len(stripped_word_tokens):
            continue

        word_score = engine.ctc_log_prob(segment, word_tokens) / segment.shape[0]
        stripped_word_score = engine.ctc_log_prob(segment, stripped_word_tokens) / segment.shape[0]
        diff = word_score - stripped_word_score

        n_word_diac = sum(1 for t in word_tokens if engine.id2char.get(t, "") in HARAKAT)
        n_word_cons = len(word_tokens) - n_word_diac

        print(f"    [{wi}] {word} ({stripped_word})")
        print(f"        diacritized: {word_score:.4f}, stripped: {stripped_word_score:.4f}, diff: {diff:+.4f}")
        print(f"        tokens: {n_word_cons} cons + {n_word_diac} diac = {len(word_tokens)} total, {segment.shape[0]} frames")


def analyze_local_posterior_scoring(engine, log_probs, phrase_text, word_bounds):
    """Alternative scoring method: use ONLY the posteriors at diacritic-aligned frames.

    Instead of full CTC score, we:
    1. Force-align to get frame assignments for each token
    2. At frames assigned to the final diacritic, read posterior for each alternative
    3. Pick the highest-posterior diacritic as the "heard" one
    4. Compare with expected
    """
    words = phrase_text.split()
    T = log_probs.shape[0]
    tokens = engine.text_to_tokens(phrase_text)
    spans = engine.forced_align(log_probs, tokens)

    print("\n" + "=" * 80)
    print("ANALYSIS 4: Local Posterior Ratio at I3rab Position")
    print("=" * 80)

    probs = torch.exp(log_probs)

    # Build word -> final diacritic span mapping
    # We need to find which span corresponds to the final diacritic of each word
    token_chars = [engine.id2char.get(t, "") for t in tokens]

    # Map target_idx -> word_idx
    word_idx_for_token = {}
    current_word = 0
    for ti, tok_id in enumerate(tokens):
        ch = engine.id2char.get(tok_id, "")
        if ch == "|" or ch == " ":
            current_word += 1
        else:
            word_idx_for_token[ti] = current_word

    # For each word, find its last diacritic span
    word_final_diac_spans = {}  # word_idx -> (span info)
    for target_idx, token_id, sf, ef in spans:
        ch = engine.id2char.get(token_id, "")
        wi = word_idx_for_token.get(target_idx)
        if wi is None:
            continue
        if ch in {FATHA, DAMMA, KASRA, FATHATAN, DAMMATAN, KASRATAN}:
            # Always overwrite — we want the LAST diacritic in the word
            word_final_diac_spans[wi] = (target_idx, token_id, sf, ef, ch)

    print(f"\n  Found final diacritic spans for {len(word_final_diac_spans)} words")

    results = []
    for wi in sorted(word_final_diac_spans.keys()):
        if wi >= len(words):
            continue
        word = words[wi]
        target_idx, token_id, sf, ef, char = word_final_diac_spans[wi]

        # Verify this is actually the final diacritic (i3rab)
        final_diac, _ = get_final_diacritic(word)
        if not final_diac or final_diac == SUKOON:
            continue

        # Get frame range
        frame_range = list(range(sf, min(ef + 1, T)))
        if not frame_range:
            continue

        # Average posterior at these frames
        avg_probs = probs[frame_range].mean(dim=0)

        # Get posteriors for the 3 short vowels
        correct_name = DIAC_NAMES[char]
        posteriors = {}
        for d in SHORT_VOWELS:
            did = engine.vocab.get(d)
            if did is not None:
                posteriors[DIAC_NAMES[d]] = float(avg_probs[did])

        # Also add tanween posteriors if relevant
        for d in TANWEEN:
            did = engine.vocab.get(d)
            if did is not None:
                posteriors[DIAC_NAMES[d]] = float(avg_probs[did])

        blank_prob = float(avg_probs[engine.blank_id])

        # Determine which diacritic the model thinks is most likely
        best_diac = max(posteriors.items(), key=lambda x: x[1])

        # Widen window analysis: how does the ratio change with wider context?
        windows = [0, 1, 2, 4, 8]
        ratio_by_window = {}
        for w in windows:
            w_range = list(range(max(0, sf - w), min(ef + 1 + w, T)))
            if not w_range:
                continue
            w_probs = probs[w_range].mean(dim=0)
            correct_p = float(w_probs[engine.vocab[char]])
            # Sum of all alternative short vowels
            if char in {FATHA, DAMMA, KASRA}:
                alts = [d for d in SHORT_VOWELS if d != char]
            else:
                alts = [d for d in TANWEEN if d != char]
            alt_total = sum(float(w_probs[engine.vocab[a]]) for a in alts if a in engine.vocab)
            ratio = correct_p / alt_total if alt_total > 0 else float('inf')
            ratio_by_window[w] = (correct_p, alt_total, ratio)

        correct_wins = best_diac[0] == correct_name

        marker = "CORRECT" if correct_wins else "WRONG"
        print(f"\n  [{wi}] {word} — expected: {correct_name}, model says: {best_diac[0]} [{marker}]")
        print(f"      Frames: {sf}-{ef} ({len(frame_range)} frames), blank_prob: {blank_prob:.4f}")
        print(f"      Posteriors: ", end="")
        for dname, dval in sorted(posteriors.items(), key=lambda x: -x[1]):
            tag = " *" if dname == correct_name else ""
            print(f"{dname}={dval:.6f}{tag}  ", end="")
        print()
        print(f"      Window analysis (correct_prob / alt_sum = ratio):")
        for w, (cp, ap, r) in sorted(ratio_by_window.items()):
            print(f"        +/-{w} frames: {cp:.6f} / {ap:.6f} = {r:.2f}x")

        results.append({
            "word_idx": wi,
            "word": word,
            "correct_name": correct_name,
            "model_best": best_diac[0],
            "correct_wins": correct_wins,
            "posteriors": posteriors,
            "blank_prob": blank_prob,
        })

    # Summary
    if results:
        n_correct = sum(1 for r in results if r["correct_wins"])
        print(f"\n  SUMMARY: {n_correct}/{len(results)} words have correct diacritic as top posterior")
        print(f"           Accuracy: {n_correct / len(results):.1%}")
    return results


def analyze_ctc_length_bias(engine, log_probs, phrase_text, word_bounds):
    """Investigate CTC length bias: does adding/removing a diacritic token
    change the score mostly because of sequence length, not content?"""
    words = phrase_text.split()
    T = log_probs.shape[0]

    print("\n" + "=" * 80)
    print("ANALYSIS 5: CTC Length Bias Investigation")
    print("=" * 80)

    print("\n  When we swap fatha->damma in the token sequence, the CTC score")
    print("  changes by some delta. But how much of that delta is due to the")
    print("  model actually distinguishing the sounds vs just CTC mechanics?")
    print()
    print("  Test: for each word, compare:")
    print("    A) Full word CTC score")
    print("    B) Remove ONLY the final diacritic token -> CTC score")
    print("    C) Replace final diacritic with each alternative -> CTC score")
    print("  If B is close to A, diacritics barely matter to CTC.")

    for wb in word_bounds:
        wi = wb["word_idx"]
        if wi >= len(words):
            continue
        word = words[wi]
        sf, ef = wb["start_frame"], wb["end_frame"]
        margin = 2
        sf_m = max(0, sf - margin)
        ef_m = min(T - 1, ef + margin)
        segment = log_probs[sf_m: ef_m + 1]
        T_seg = segment.shape[0]

        final_diac, _ = get_final_diacritic(word)
        if not final_diac or final_diac == SUKOON:
            continue

        word_tokens = engine.text_to_tokens(word)
        if not word_tokens or T_seg < len(word_tokens):
            continue

        # A) Full word score
        full_score = engine.ctc_log_prob(segment, word_tokens) / T_seg

        # B) Remove final diacritic token
        # Find and remove the last diacritic token
        tokens_no_final = list(word_tokens)
        for i in range(len(tokens_no_final) - 1, -1, -1):
            ch = engine.id2char.get(tokens_no_final[i], "")
            if ch in {FATHA, DAMMA, KASRA, FATHATAN, DAMMATAN, KASRATAN}:
                tokens_no_final.pop(i)
                break
        if T_seg >= len(tokens_no_final):
            no_final_score = engine.ctc_log_prob(segment, tokens_no_final) / T_seg
        else:
            no_final_score = -999

        # C) Replace final diacritic with alternatives
        alt_scores = {}
        for alt in SHORT_VOWELS:
            if alt == final_diac:
                continue
            alt_word = replace_final_diacritic(word, alt)
            alt_tokens = engine.text_to_tokens(alt_word)
            if not alt_tokens or T_seg < len(alt_tokens):
                continue
            alt_score = engine.ctc_log_prob(segment, alt_tokens) / T_seg
            alt_scores[DIAC_NAMES[alt]] = alt_score

        print(f"\n  [{wi}] {word}")
        print(f"      A) Full word score:      {full_score:.4f} ({len(word_tokens)} tokens)")
        print(f"      B) Remove final diac:    {no_final_score:.4f} ({len(tokens_no_final)} tokens)")
        print(f"      => Diacritic contributes: {full_score - no_final_score:+.4f} per frame")
        for alt_name, alt_score in sorted(alt_scores.items()):
            delta = full_score - alt_score
            print(f"      C) {alt_name:8s}: {alt_score:.4f}  delta={delta:+.4f}")


def analyze_frame_assignment_density(engine, log_probs, phrase_text):
    """How many frames get assigned to diacritic tokens vs consonant tokens?"""
    tokens = engine.text_to_tokens(phrase_text)
    T = log_probs.shape[0]
    spans = engine.forced_align(log_probs, tokens)

    print("\n" + "=" * 80)
    print("ANALYSIS 6: Frame Assignment Density")
    print("=" * 80)

    cons_frames = 0
    diac_frames = 0
    blank_frames = 0
    sep_frames = 0

    for target_idx, token_id, sf, ef in spans:
        n_frames = ef - sf + 1
        ch = engine.id2char.get(token_id, "")
        if ch in HARAKAT:
            diac_frames += n_frames
        elif ch == "|" or ch == " ":
            sep_frames += n_frames
        else:
            cons_frames += n_frames

    # Frames not assigned to any token are blank
    assigned = set()
    for _, _, sf, ef in spans:
        for f in range(sf, ef + 1):
            assigned.add(f)
    blank_frames = T - len(assigned)

    total_assigned = cons_frames + diac_frames + sep_frames
    print(f"\n  Total frames: {T}")
    print(f"  Assigned frames: {total_assigned} ({total_assigned / T:.1%})")
    print(f"    Consonant frames: {cons_frames} ({cons_frames / T:.1%})")
    print(f"    Diacritic frames: {diac_frames} ({diac_frames / T:.1%})")
    print(f"    Separator frames: {sep_frames} ({sep_frames / T:.1%})")
    print(f"  Unassigned (blank) frames: {blank_frames} ({blank_frames / T:.1%})")

    if diac_frames > 0:
        print(f"\n  Ratio cons:diac frames = {cons_frames / diac_frames:.1f}:1")
    else:
        print(f"\n  NO frames assigned to diacritics!")

    # Per-diacritic breakdown
    diac_frame_counts = {}
    for target_idx, token_id, sf, ef in spans:
        ch = engine.id2char.get(token_id, "")
        if ch in HARAKAT:
            name = DIAC_NAMES.get(ch, ch)
            diac_frame_counts[name] = diac_frame_counts.get(name, 0) + (ef - sf + 1)

    if diac_frame_counts:
        print(f"\n  Per-diacritic frame counts:")
        for name, count in sorted(diac_frame_counts.items(), key=lambda x: -x[1]):
            print(f"    {name:12s}: {count} frames")


def main():
    print("Loading engine...")
    engine = RecitationEngine(str(MODEL_PATH))

    # Use the longer ajrumiyyah session (63s of audio)
    session_dir = SESSIONS_DIR / "20260401_104623_ajrumiyyah"
    if not session_dir.exists():
        sessions = sorted(SESSIONS_DIR.iterdir())
        session_dir = sessions[-1]

    print(f"\nUsing session: {session_dir.name}")
    meta, waveform = load_session(engine, session_dir)
    phrases = meta["phrases"]
    print(f"Audio: {waveform.shape[0] / 16000:.1f}s")

    # Strategy: force-align the FULL concatenated text to the full audio,
    # then slice out per-phrase segments for analysis.
    # This gives us proper alignment since the audio IS a reading of all phrases.

    full_text = " ".join(phrases)
    print("Running model inference on full audio...")
    model_out = engine.get_model_outputs(waveform, output_hidden_states=False)
    log_probs = model_out['log_probs']
    T = log_probs.shape[0]
    print(f"Frames: {T}")

    greedy = engine.greedy_decode(log_probs)
    print(f"\nGreedy decode (first 300 chars): {greedy[:300]}...")

    # Force-align the full text
    full_tokens = engine.text_to_tokens(full_text)
    print(f"\nFull text tokens: {len(full_tokens)}")
    if T < len(full_tokens):
        print(f"WARNING: not enough frames ({T}) for full text ({len(full_tokens)} tokens)")
        print("Trying with just the first few phrases...")
        # Try progressively fewer phrases
        for n_phrases in range(len(phrases), 0, -1):
            partial_text = " ".join(phrases[:n_phrases])
            partial_tokens = engine.text_to_tokens(partial_text)
            if T >= len(partial_tokens):
                full_text = partial_text
                full_tokens = partial_tokens
                phrases = phrases[:n_phrases]
                print(f"Using first {n_phrases} phrases ({len(full_tokens)} tokens)")
                break

    print("Force-aligning full text...")
    all_spans = engine.forced_align(log_probs, full_tokens)
    all_word_bounds = engine.word_boundaries_from_alignment(all_spans, full_tokens)
    all_words = full_text.split()
    print(f"Aligned {len(all_word_bounds)} words total")

    # Now map word bounds to phrases
    phrase_word_offsets = []
    offset = 0
    for ph in phrases:
        n_words = len(ph.split())
        phrase_word_offsets.append((offset, offset + n_words))
        offset += n_words

    # Analyze up to 3 phrases
    analyzed = 0
    for phrase_idx, (start_wi, end_wi) in enumerate(phrase_word_offsets):
        if analyzed >= 3:
            break

        phrase = phrases[phrase_idx]

        # Find word bounds for this phrase
        phrase_wbs = [wb for wb in all_word_bounds if start_wi <= wb["word_idx"] < end_wi]
        if not phrase_wbs:
            continue

        # Get the frame range for this phrase
        first_frame = phrase_wbs[0]["start_frame"]
        last_frame = phrase_wbs[-1]["end_frame"]

        # Remap word_idx to be relative to this phrase
        remapped_wbs = []
        for wb in phrase_wbs:
            rwb = dict(wb)
            rwb["word_idx"] = wb["word_idx"] - start_wi
            remapped_wbs.append(rwb)

        # Slice the log_probs to this phrase's frame range
        # (but use the full log_probs for alignment-based analyses)
        phrase_lp = log_probs[first_frame:last_frame + 1]
        tokens = engine.text_to_tokens(phrase)
        if phrase_lp.shape[0] < len(tokens):
            print(f"  Skipping phrase {phrase_idx}: not enough frames")
            continue

        # Quick quality check: CTC score
        phrase_ctc = engine.ctc_log_prob(phrase_lp, tokens) / phrase_lp.shape[0]

        print(f"\n\n{'#' * 80}")
        print(f"PHRASE {phrase_idx}: {phrase}")
        print(f"Frames: {first_frame}-{last_frame} ({last_frame - first_frame + 1} frames)")
        print(f"CTC/frame: {phrase_ctc:.4f}")
        print(f"{'#' * 80}")

        if phrase_ctc < -3.0:
            print(f"  Skipping: poor alignment quality (CTC={phrase_ctc:.4f})")
            continue

        # Re-align within the phrase's own frame slice for cleaner per-word analysis
        phrase_spans = engine.forced_align(phrase_lp, tokens)
        phrase_word_bounds = engine.word_boundaries_from_alignment(phrase_spans, tokens)

        if not phrase_word_bounds:
            print(f"  Skipping: re-alignment within phrase slice failed")
            continue

        print(f"  Aligned {len(phrase_word_bounds)} words within phrase slice")

        # Run all analyses using the phrase-local log probs and word bounds
        analyze_ctc_score_deltas(engine, phrase_lp, phrase, phrase_word_bounds)
        analyze_frame_posteriors(engine, phrase_lp, phrase, phrase_word_bounds)
        analyze_token_contribution(engine, phrase_lp, phrase, phrase_word_bounds)
        analyze_local_posterior_scoring(engine, phrase_lp, phrase, phrase_word_bounds)
        analyze_ctc_length_bias(engine, phrase_lp, phrase, phrase_word_bounds)
        analyze_frame_assignment_density(engine, phrase_lp, phrase)

        analyzed += 1

    # ── Global Summary ──
    print("\n\n" + "=" * 80)
    print("GLOBAL SUMMARY")
    print("=" * 80)
    print("""
Key questions answered:
1. CTC Score Deltas: How much does swapping i3rab change the overall CTC score?
2. Frame Posteriors: At the aligned diacritic frames, does the model give higher
   probability to the correct diacritic?
3. Token Contribution: What fraction of CTC score comes from consonants vs diacritics?
4. Local Posterior Ratio: Can we use frame-level posteriors instead of CTC scores?
5. Length Bias: Does CTC score change mostly due to sequence length differences?
6. Frame Density: How many frames are assigned to diacritics vs consonants?

If the frame-level posteriors clearly distinguish diacritics but the CTC score
doesn't change much, the solution is to use posterior-based scoring rather than
(or in addition to) CTC hypothesis comparison.
""")


if __name__ == "__main__":
    main()
