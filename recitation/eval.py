#!/usr/bin/env python3
"""Unified recitation evaluation — the single source of truth for accuracy.

Methodology: mutation-based. We always know the exact text the audio says, so we
induce errors by mutating the reference text the model scores against while
holding the real audio fixed. For every data item we run:
  - FP check: score audio vs correct text (any flag = false positive)
  - Mutation suite: i3rab / tashkeel / word swaps, expect the target word flagged

Data sources (same methodology for each):
  - sessions: saved real-audio reading sessions (test_data/sessions/)
  - corpus:   external diacritized MSA corpus (Arabic Speech Corpus)

Usage:
  python eval.py                       # all available sources
  python eval.py --source sessions     # sessions only
  python eval.py --source corpus       # external corpus only
  python eval.py --limit 50            # cap corpus utterances (speed)
  python eval.py --report eval_baseline.json
"""
import sys, json, random, argparse
from pathlib import Path
from collections import defaultdict

import numpy as np
import torch

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

from engine import RecitationEngine, StreamingSession
from server import classify_words
from arabic import (
    FATHA, DAMMA, KASRA, FATHATAN, DAMMATAN, KASRATAN, SHADDA,
    HARAKAT, strip_diacritics,
)

MODEL_PATH = BASE / "models" / "ssl_xls_r_v5"
FRAME_STRIDE = 320
SAMPLE_RATE = 16000

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


# ── Per-item runner ──

def _accumulate_missed(stats, mutation_type, target_cw, pi, word_idx,
                       desc, original_word, mutated_word):
    d = target_cw["debug"]
    miss = {"phrase": pi, "word_idx": word_idx, "desc": desc,
            "eff": d["eff"], "got_type": target_cw.get("error_type")}
    if mutation_type == "word":
        miss.update({"consonant_match": d.get("consonant_match", 1.0),
                     "frame_count": d.get("frame_count", 0),
                     "greedy": target_cw.get("greedy", ""), "word": original_word})
    else:
        miss.update({"alt_delta": d.get("i3rab_delta"), "tash_delta": d.get("tash_delta"),
                     "pc": d.get("pc", 999), "sf": d.get("sf_gop", 999),
                     "gdm": d.get("gdm", 0), "gfm": d.get("gfm", False),
                     "word": original_word, "mutated": mutated_word})
    stats[mutation_type]["missed"].append(miss)


def run_item(engine, item_id, audio_segment, phrase_text, whisper_words,
             fp_acc, stats, verbose=False):
    """FP check + full mutation suite for one (audio, text) item.

    fp_acc: dict with keys 'total','fp','details' (mutated in place).
    stats:  defaultdict(category -> {total,detected,type_correct,missed}).
    """
    pw = phrase_text.split()

    # ── FP check: correct text should flag nothing ──
    classified = _score_phrase_with_whisper(engine, audio_segment, phrase_text, whisper_words)
    for cw in classified:
        fp_acc["total"] += 1
        if cw["status"] != "correct":
            fp_acc["fp"] += 1
            fp_acc["details"].append((item_id, cw["word"], cw["error_type"], cw["debug"]["eff"]))

    # ── Mutation suite ──
    def _run_one(mut_text, wi, mtype, desc, original, mutated):
        try:
            cls = _score_phrase_with_whisper(engine, audio_segment, mut_text, whisper_words)
        except Exception:
            return
        stats[mtype]["total"] += 1
        target = next((c for c in cls if c["idx"] == wi), None)
        if not target:
            return
        detected = target["status"] != "correct"
        got = target["error_type"] if detected else None
        type_ok = got in _MUTATION_EXPECTED_TYPES[mtype] if detected else False
        if detected:
            stats[mtype]["detected"] += 1
            if type_ok:
                stats[mtype]["type_correct"] += 1
        if not detected or not type_ok:
            _accumulate_missed(stats, mtype, target, item_id, wi, desc, original, mutated)

    for wi, word in enumerate(pw):
        m, desc = mutate_i3rab(word)
        if m is not None:
            mw = list(pw); mw[wi] = m
            _run_one(" ".join(mw), wi, "i3rab", desc, word, m)
    for wi, word in enumerate(pw):
        if len(strip_diacritics(word)) < 3:
            continue
        m, desc = mutate_tashkeel(word)
        if m is not None:
            mw = list(pw); mw[wi] = m
            _run_one(" ".join(mw), wi, "tashkeel", desc, word, m)
    cands = [i for i, w in enumerate(pw) if len(strip_diacritics(w)) >= 3]
    if cands:
        for wi in random.sample(cands, min(2, len(cands))):
            mw, desc = mutate_word(pw, wi)
            _run_one(" ".join(mw), wi, "word", desc, pw[wi], mw[wi])


# ── Session source ──

def iter_session_items(engine, verbose=False):
    """Yield (source_label, item_id, audio_segment, phrase_text, whisper_words)
    for every covered phrase across the best session per passage."""
    sessions = find_best_sessions(BASE / "test_data" / "sessions")
    for pid in sorted(sessions):
        si = sessions[pid]
        phrases = si["meta"]["phrases"]
        audio = si["audio"]
        full_text = " ".join(phrases)
        waveform = torch.from_numpy(audio)
        word_results, _greedy, _fs = engine.score_phrase(waveform, full_text, compute_pd=False)
        segments = _extract_phrase_segments(word_results, phrases, audio)
        for pi in sorted(segments.keys()):
            seg = segments[pi]
            whisper_words = engine.whisper_transcribe(seg)
            yield (f"sessions:{pid}", f"{pid}/p{pi}", seg, phrases[pi], whisper_words)


def iter_corpus_items(engine, limit=None, verbose=False):
    """Yield items for the external MSA corpus. Each utterance = one item:
    score the whole utterance against its own (converted) transcript and
    mutate that transcript."""
    from eval_corpus import load_corpus_index
    index = load_corpus_index()
    if limit:
        index = index[:limit]
    for (utt_id, text, wav_path) in index:
        try:
            waveform = engine.load_audio(wav_path)
        except Exception as e:
            if verbose:
                print(f"  skip {utt_id}: load failed ({e})")
            continue
        audio = waveform.numpy()
        if len(audio) < int(0.5 * SAMPLE_RATE):
            continue
        whisper_words = engine.whisper_transcribe(audio[-int(5.0 * SAMPLE_RATE):])
        yield ("corpus", utt_id, audio, text, whisper_words)


# ── Reporter ──

def _empty_stats():
    return defaultdict(lambda: {"total": 0, "detected": 0, "type_correct": 0, "missed": []})

def _summarize(fp_acc, stats):
    tot_mut = sum(s["total"] for s in stats.values())
    det = sum(s["detected"] for s in stats.values())
    typ = sum(s["type_correct"] for s in stats.values())
    out = {
        "fp_rate": round(fp_acc["fp"] / fp_acc["total"] * 100, 2) if fp_acc["total"] else 0.0,
        "fp_count": fp_acc["fp"], "words": fp_acc["total"],
        "detection_rate": round(det / tot_mut * 100, 1) if tot_mut else 0.0,
        "correct_type_rate": round(typ / tot_mut * 100, 1) if tot_mut else 0.0,
        "mutations": tot_mut, "detected": det, "type_correct": typ,
        "by_category": {c: {"total": stats[c]["total"], "detected": stats[c]["detected"],
                            "type_correct": stats[c]["type_correct"]}
                        for c in ("i3rab", "tashkeel", "word")},
    }
    return out

def _print_summary(label, summ):
    print(f"\n{'='*70}\nSOURCE: {label}\n{'='*70}")
    print(f"  FP rate:        {summ['fp_rate']}%  ({summ['fp_count']}/{summ['words']})")
    print(f"  Detection:      {summ['detection_rate']}%  ({summ['detected']}/{summ['mutations']})")
    print(f"  Correct type:   {summ['correct_type_rate']}%  ({summ['type_correct']}/{summ['mutations']})")
    for c in ("i3rab", "tashkeel", "word"):
        b = summ["by_category"][c]
        dr = round(b["detected"] / b["total"] * 100) if b["total"] else 0
        print(f"    {c:10s}: {b['detected']}/{b['total']}  ({dr}%)")

def run_source(engine, item_iter, verbose=False):
    fp_acc = {"total": 0, "fp": 0, "details": []}
    stats = _empty_stats()
    for (_label, item_id, seg, text, ww) in item_iter:
        run_item(engine, item_id, seg, text, ww, fp_acc, stats, verbose)
    return fp_acc, stats

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["sessions", "corpus", "all"], default="all")
    ap.add_argument("--limit", type=int, default=None, help="cap corpus utterances")
    ap.add_argument("--report", default=None, help="write JSON report to this path")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    random.seed(42)
    engine = RecitationEngine(str(MODEL_PATH))

    report = {"sources": {}}
    if args.source in ("sessions", "all"):
        fp_acc, stats = run_source(engine, iter_session_items(engine, args.verbose), args.verbose)
        summ = _summarize(fp_acc, stats)
        report["sources"]["sessions"] = summ
        _print_summary("sessions", summ)

    if args.source in ("corpus", "all"):
        try:
            fp_acc, stats = run_source(engine, iter_corpus_items(engine, args.limit, args.verbose), args.verbose)
            summ = _summarize(fp_acc, stats)
            report["sources"]["corpus"] = summ
            _print_summary("corpus", summ)
        except (FileNotFoundError, ValueError) as e:
            print(f"\n[corpus skipped] {e}")

    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"\nWrote report: {args.report}")

if __name__ == "__main__":
    main()
