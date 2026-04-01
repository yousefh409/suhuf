#!/usr/bin/env python3
"""Test error detection by scoring real audio against mutated reference text.

Uses the production scoring pipeline (CTC + Whisper + classify_words).

The audio is a correct reading. We score it against:
1. The correct reference text (should flag nothing)
2. Mutated reference text (i3rab changes, tashkeel changes, word swaps)

If the system is working, (1) should be clean and (2) should flag errors —
because the audio doesn't match the mutated text.
"""
import sys
import json
import random
import numpy as np
import torch
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

from engine import RecitationEngine, StreamingSession
from server import classify_words
from arabic import (
    FATHA, DAMMA, KASRA, FATHATAN, DAMMATAN, KASRATAN, SUKOON, SHADDA,
    HARAKAT, strip_diacritics, generate_i3rab_alternatives, generate_tashkeel_alternatives,
)

MODEL_PATH = BASE / "models" / "ssl_xls_r_v5"
FRAME_STRIDE = 320  # wav2vec2: 320 samples per frame (20ms at 16kHz)
SAMPLE_RATE = 16000

# For mutation tests: which engine error_types satisfy a given mutation kind
_MUTATION_EXPECTED_TYPES = {
    "i3rab": {"i3rab"},
    "tashkeel": {"tashkeel", "diacritic"},
    "word": {"wrong", "skipped"},
}

# ── Mutation generators ──

def mutate_i3rab(word):
    """Change the final diacritic (case ending) of a word."""
    chars = list(word)
    last_cons = -1
    for i in range(len(chars) - 1, -1, -1):
        if chars[i] not in HARAKAT:
            last_cons = i
            break
    if last_cons < 0:
        return None, None

    diac_pos = None
    for i in range(last_cons + 1, len(chars)):
        if chars[i] in {FATHA, DAMMA, KASRA, FATHATAN, DAMMATAN, KASRATAN}:
            diac_pos = i
            break

    if diac_pos is None:
        return None, None

    original = chars[diac_pos]
    if original in {FATHA, DAMMA, KASRA}:
        alts = [d for d in [FATHA, DAMMA, KASRA] if d != original]
    elif original in {FATHATAN, DAMMATAN, KASRATAN}:
        alts = [d for d in [FATHATAN, DAMMATAN, KASRATAN] if d != original]
    else:
        return None, None

    new_diac = random.choice(alts)
    chars[diac_pos] = new_diac
    return "".join(chars), f"i3rab_{_diac_name(original)}->{_diac_name(new_diac)}"


def mutate_tashkeel(word):
    """Change an internal vowel (not the final one)."""
    chars = list(word)
    last_cons = -1
    for i in range(len(chars) - 1, -1, -1):
        if chars[i] not in HARAKAT:
            last_cons = i
            break

    candidates = []
    for i, ch in enumerate(chars):
        if ch in {FATHA, DAMMA, KASRA} and i < last_cons:
            if i > 0 and chars[i-1] == SHADDA:
                continue
            if i < len(chars) - 1 and chars[i+1] == SHADDA:
                continue
            candidates.append(i)

    if not candidates:
        return None, None

    pos = random.choice(candidates)
    original = chars[pos]
    alts = [d for d in [FATHA, DAMMA, KASRA] if d != original]
    new_diac = random.choice(alts)
    chars[pos] = new_diac
    return "".join(chars), f"tashkeel_{_diac_name(original)}->{_diac_name(new_diac)}"


def mutate_word(phrase_words, idx):
    """Replace a word with a different common Arabic word."""
    replacements = [
        "كِتَابٌ", "رَجُلٌ", "مَدِينَةٌ", "عِلْمٌ", "قَوْلٌ",
        "بَابٌ", "نَهْرٌ", "صَلَاةٌ", "حُكْمٌ", "وَلَدٌ",
    ]
    original = phrase_words[idx]
    repl = random.choice([r for r in replacements if strip_diacritics(r) != strip_diacritics(original)])
    new_words = list(phrase_words)
    new_words[idx] = repl
    return new_words, f"word_{strip_diacritics(original)}->{strip_diacritics(repl)}"


_DIAC_NAMES = {
    FATHA: "fatha", DAMMA: "damma", KASRA: "kasra",
    FATHATAN: "fathatan", DAMMATAN: "dammatan", KASRATAN: "kasratan",
}
def _diac_name(d):
    return _DIAC_NAMES.get(d, repr(d))


# ── Session discovery ──

def find_best_sessions(sessions_dir):
    """Find the longest session per passage type."""
    best = {}
    for d in sessions_dir.iterdir():
        if not d.is_dir():
            continue
        audio_path = d / "audio.raw"
        meta_path = d / "meta.json"
        if not audio_path.exists() or not meta_path.exists():
            continue
        dur = audio_path.stat().st_size / (SAMPLE_RATE * 4)
        meta = json.load(open(meta_path))
        pid = meta.get("passage_id", "")
        if not pid:
            continue
        if pid not in best or dur > best[pid][0]:
            best[pid] = (dur, d)

    result = {}
    for pid, (dur, d) in best.items():
        meta = json.load(open(d / "meta.json"))
        audio = np.fromfile(str(d / "audio.raw"), dtype=np.float32)
        result[pid] = {"session_dir": d, "meta": meta, "audio": audio, "duration": dur}
    return result


# ── Scoring ──

def _extract_phrase_segments(word_results, phrases, audio):
    """Extract per-phrase audio segments using CTC alignment boundaries.

    Uses start_frame/end_frame from CTC forced alignment to determine
    precise per-phrase audio boundaries, with 0.3s padding.
    """
    # Map global word indices to phrases
    phrase_word_ranges = []
    offset = 0
    for phrase in phrases:
        n = len(phrase.split())
        phrase_word_ranges.append((offset, offset + n))
        offset += n

    segments = {}
    pad_samples = int(0.3 * SAMPLE_RATE)

    for pi, (start_wi, end_wi) in enumerate(phrase_word_ranges):
        # Find frame range for this phrase's words
        min_frame = None
        max_frame = None
        word_count = 0
        for wr in word_results:
            wi = wr["word_idx"]
            if start_wi <= wi < end_wi:
                sf = wr.get("start_frame")
                ef = wr.get("end_frame")
                if sf is not None and ef is not None:
                    if min_frame is None or sf < min_frame:
                        min_frame = sf
                    if max_frame is None or ef > max_frame:
                        max_frame = ef
                    word_count += 1

        if min_frame is None or word_count < (end_wi - start_wi) * 0.5:
            continue

        # Convert frames to samples with padding
        start_sample = max(0, min_frame * FRAME_STRIDE - pad_samples)
        end_sample = min(len(audio), (max_frame + 1) * FRAME_STRIDE + pad_samples)

        if end_sample - start_sample >= SAMPLE_RATE * 0.5:  # at least 0.5s
            segments[pi] = audio[start_sample:end_sample]

    return segments


def _score_phrase_with_whisper(engine, audio_segment, phrase_text, whisper_words):
    """Score a phrase using CTC + Whisper + classify_words (production path).

    Returns list of classified word dicts.
    """
    waveform = torch.from_numpy(audio_segment)
    word_results, greedy, full_score = engine.score_phrase(waveform, phrase_text)

    # Add Whisper per-word matching (only trust on segments >= 3s with good match ratio)
    phrase_words = phrase_text.split()
    duration = len(audio_segment) / SAMPLE_RATE
    wmatch = StreamingSession._whisper_word_matches(whisper_words, phrase_words)
    match_ratio = sum(wmatch) / len(wmatch) if wmatch else 1.0
    trust_whisper = duration >= 3.0 and match_ratio >= 0.6

    for wr in word_results:
        wi = wr["word_idx"]
        if trust_whisper:
            wr["whisper_match"] = wmatch[wi] if wi < len(wmatch) else True
        else:
            wr["whisper_match"] = True

    return classify_words(word_results, phrase_words, streaming=False)


# ── Per-session runner ──

def run_session(engine, passage_id, session_info):
    """Run FP check + mutation tests for one session."""
    phrases = session_info["meta"]["phrases"]
    audio = session_info["audio"]
    full_text = " ".join(phrases)
    all_words = full_text.split()

    # Step 1: Score full audio against full text to get CTC alignment boundaries
    print(f"  Scoring full text ({len(all_words)} words, {len(audio)/SAMPLE_RATE:.1f}s)...")
    waveform = torch.from_numpy(audio)
    word_results, greedy, full_score = engine.score_phrase(waveform, full_text)

    # Step 2: Extract per-phrase audio segments from CTC boundaries
    segments = _extract_phrase_segments(word_results, phrases, audio)

    # Step 3: Run Whisper per segment for wrong-word detection
    whisper_per_phrase = {}
    covered_phrases = sorted(segments.keys())
    for pi in covered_phrases:
        seg = segments[pi]
        whisper_per_phrase[pi] = engine.whisper_transcribe(seg)
        pw = phrases[pi].split()
        dur = len(seg) / SAMPLE_RATE
        print(f"    Phrase {pi}: {dur:.1f}s, {len(pw)} words, "
              f"Whisper: {' '.join(whisper_per_phrase[pi][:6])}...")

    uncovered = [pi for pi in range(len(phrases)) if pi not in segments]
    if uncovered:
        print(f"    Skipped: {uncovered}")

    if not covered_phrases:
        print("  No covered phrases!")
        return 0, 0, [], defaultdict(lambda: {"total": 0, "detected": 0, "type_correct": 0, "missed": []})

    # ── PHASE 1: FP check ──
    print(f"\n  PHASE 1: Correct text (should have zero flags)")

    total_words = 0
    false_positives = 0
    fp_details = []

    for pi in covered_phrases:
        phrase = phrases[pi]
        whisper_words = whisper_per_phrase[pi]
        classified = _score_phrase_with_whisper(engine, segments[pi], phrase, whisper_words)

        phrase_flags = []
        for cw in classified:
            total_words += 1
            if cw["status"] != "correct":
                false_positives += 1
                phrase_flags.append(f"{cw['word']}({cw['error_type']})")
                fp_details.append((pi, cw['word'], cw['error_type'], cw['debug']['eff']))

        if phrase_flags:
            print(f"    [{pi:2d}] FP: {', '.join(phrase_flags)}")
            for cw in classified:
                if cw["status"] != "correct":
                    d = cw['debug']
                    print(f"        {cw['word']} signal={cw['error_type']} detail={cw.get('error_detail','')}")
                    print(f"          eff={d['eff']} i3rab_d={d.get('i3rab_delta')} tash_d={d.get('tash_delta')} "
                          f"pc={d.get('pc')} sf={d.get('sf_gop')} cm={d.get('consonant_match')}")
        else:
            print(f"    [{pi:2d}] OK ({len(phrase.split())} words)")

    fp_rate = false_positives / total_words * 100 if total_words > 0 else 0
    print(f"\n    Total: {total_words} words, {false_positives} FP ({fp_rate:.1f}%)")

    # ── PHASE 2: Mutation tests ──
    print(f"\n  PHASE 2: Mutated text (should detect errors)")

    stats = defaultdict(lambda: {"total": 0, "detected": 0, "type_correct": 0, "missed": []})

    for pi in covered_phrases:
        phrase = phrases[pi]
        pw = phrase.split()
        seg = segments[pi]
        whisper_words = whisper_per_phrase[pi]

        # i3rab mutations
        for wi, word in enumerate(pw):
            mutated, desc = mutate_i3rab(word)
            if mutated is None:
                continue
            mut_words = list(pw)
            mut_words[wi] = mutated
            mut_text = " ".join(mut_words)
            _test_mutation(engine, seg, phrase, mut_text, wi, "i3rab", desc,
                           stats, pi, word, mutated, whisper_words)

        # tashkeel mutations
        for wi, word in enumerate(pw):
            if len(strip_diacritics(word)) < 3:
                continue
            mutated, desc = mutate_tashkeel(word)
            if mutated is None:
                continue
            mut_words = list(pw)
            mut_words[wi] = mutated
            mut_text = " ".join(mut_words)
            _test_mutation(engine, seg, phrase, mut_text, wi, "tashkeel", desc,
                           stats, pi, word, mutated, whisper_words)

        # word replacements (2 per phrase)
        candidates = [i for i, w in enumerate(pw) if len(strip_diacritics(w)) >= 3]
        if candidates:
            test_idxs = random.sample(candidates, min(2, len(candidates)))
            for wi in test_idxs:
                mut_words_list, desc = mutate_word(pw, wi)
                mut_text = " ".join(mut_words_list)
                _test_mutation(engine, seg, phrase, mut_text, wi, "word", desc,
                               stats, pi, pw[wi], mut_words_list[wi], whisper_words)

    return total_words, false_positives, fp_details, stats


def _test_mutation(engine, audio_segment, original_phrase, mutated_text,
                   word_idx, mutation_type, desc, stats, pi,
                   original_word, mutated_word, whisper_words):
    """Run a single mutation test and record results."""
    try:
        classified = _score_phrase_with_whisper(
            engine, audio_segment, mutated_text, whisper_words)
    except Exception:
        return

    stats[mutation_type]["total"] += 1

    target_cw = None
    for cw in classified:
        if cw["idx"] == word_idx:
            target_cw = cw
            break

    if not target_cw:
        return

    detected = target_cw["status"] != "correct"
    got_type = target_cw["error_type"] if detected else None
    type_ok = got_type in _MUTATION_EXPECTED_TYPES[mutation_type] if detected else False

    if detected:
        stats[mutation_type]["detected"] += 1
        if type_ok:
            stats[mutation_type]["type_correct"] += 1

    if not detected or not type_ok:
        d = target_cw["debug"]
        miss = {
            "phrase": pi, "word_idx": word_idx, "desc": desc,
            "eff": d["eff"], "got_type": got_type,
        }
        if mutation_type == "word":
            miss.update({
                "consonant_match": d.get("consonant_match", 1.0),
                "frame_count": d.get("frame_count", 0),
                "greedy": target_cw.get("greedy", ""),
                "word": original_word,
            })
        else:
            miss.update({
                "alt_delta": d.get("i3rab_delta"),
                "tash_delta": d.get("tash_delta"),
                "pc": d.get("pc", 999),
                "sf": d.get("sf_gop", 999),
                "gdm": d.get("gdm", 0),
                "gfm": d.get("gfm", False),
                "word": original_word, "mutated": mutated_word,
            })
        stats[mutation_type]["missed"].append(miss)


def print_results(total_words, fp_count, fp_details, stats):
    """Print combined results."""
    fp_rate = fp_count / total_words * 100 if total_words > 0 else 0

    total_mutations = sum(s["total"] for s in stats.values())
    total_detected = sum(s["detected"] for s in stats.values())
    total_type_correct = sum(s["type_correct"] for s in stats.values())
    det_rate = total_detected / total_mutations * 100 if total_mutations > 0 else 0
    type_rate = total_type_correct / total_mutations * 100 if total_mutations > 0 else 0

    print(f"\nFalse positive rate:   {fp_rate:.1f}% ({fp_count}/{total_words})")
    print(f"Overall detection:     {det_rate:.1f}% ({total_detected}/{total_mutations})")
    print(f"Correct type:          {type_rate:.1f}% ({total_type_correct}/{total_mutations})")

    if fp_details:
        print(f"\n  FP details:")
        for pi, word, etype, eff in fp_details:
            print(f"    p{pi}: {word} ({etype}) eff={eff}")

    for cat in ["i3rab", "tashkeel", "word"]:
        s = stats[cat]
        d_rate = s["detected"] / s["total"] * 100 if s["total"] > 0 else 0
        t_rate = s["type_correct"] / s["total"] * 100 if s["total"] > 0 else 0
        wrong_type = s["detected"] - s["type_correct"]
        print(f"\n  {cat:10s}: {s['detected']}/{s['total']}  "
              f"detected={d_rate:.0f}%  correct_type={t_rate:.0f}%  "
              f"wrong_type={wrong_type}")

    for cat in ["i3rab", "tashkeel", "word"]:
        missed = stats[cat]["missed"]
        if missed:
            truly_missed = [m for m in missed if m.get("got_type") is None]
            wrong_typed = [m for m in missed if m.get("got_type") is not None]

            if truly_missed:
                print(f"\n  Missed {cat} mutations ({len(truly_missed)}):")
                for m in truly_missed[:20]:
                    line = f"    p{m['phrase']}w{m['word_idx']}: {m['desc']:40s}"
                    line += f"  eff={m['eff']}"
                    if 'pc' in m and m.get('pc') is not None and m['pc'] < 900:
                        line += f"  pc={m['pc']}"
                    if 'sf' in m and m.get('sf') is not None and m['sf'] < 900:
                        line += f"  sf={m['sf']}"
                    if 'alt_delta' in m and m['alt_delta'] is not None:
                        line += f"  alt_d={m['alt_delta']}"
                    if 'tash_delta' in m and m['tash_delta'] is not None:
                        line += f"  tash_d={m['tash_delta']}"
                    if 'gdm' in m:
                        line += f"  gdm={m['gdm']}"
                    if 'gfm' in m:
                        line += f"  gfm={m['gfm']}"
                    if 'consonant_match' in m:
                        line += f"  cm={m['consonant_match']}"
                    if 'frame_count' in m:
                        line += f"  fc={m['frame_count']}"
                    if 'greedy' in m:
                        line += f"  g='{m['greedy'][:20]}'"
                    print(line)

            if wrong_typed:
                print(f"\n  Wrong-type {cat} detections ({len(wrong_typed)}):")
                for m in wrong_typed[:10]:
                    print(f"    p{m['phrase']}w{m['word_idx']}: {m['desc']:40s}  got={m['got_type']}")


def main():
    random.seed(42)

    sessions_dir = BASE / "test_data" / "sessions"
    sessions = find_best_sessions(sessions_dir)

    if not sessions:
        print("No sessions found")
        return

    engine = RecitationEngine(str(MODEL_PATH))

    agg_words = 0
    agg_fp = 0
    agg_fp_details = []
    agg_stats = defaultdict(lambda: {"total": 0, "detected": 0, "type_correct": 0, "missed": []})

    for pid in sorted(sessions):
        si = sessions[pid]
        print(f"\n{'='*80}")
        print(f"SESSION: {si['session_dir'].name}  ({si['duration']:.1f}s)")
        print(f"PASSAGE: {pid}")
        print(f"{'='*80}")

        tw, fp, fp_det, stats = run_session(engine, pid, si)
        agg_words += tw
        agg_fp += fp
        agg_fp_details.extend(fp_det)

        for cat in ["i3rab", "tashkeel", "word"]:
            for key in ["total", "detected", "type_correct"]:
                agg_stats[cat][key] += stats[cat][key]
            agg_stats[cat]["missed"].extend(stats[cat]["missed"])

    print(f"\n{'='*80}")
    print(f"COMBINED RESULTS ({len(sessions)} sessions)")
    print(f"{'='*80}")
    print_results(agg_words, agg_fp, agg_fp_details, agg_stats)


if __name__ == "__main__":
    main()
