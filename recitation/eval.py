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
  python eval.py                       # all available sources (full)
  python eval.py --quick               # fast smoke preset for iteration
  python eval.py --source sessions     # sessions only
  python eval.py --source corpus       # external corpus only
  python eval.py --limit 50            # cap corpus utterances (speed)
  python eval.py --report eval_baseline.json
"""
import sys, json, random, argparse, time
from pathlib import Path
from collections import defaultdict

import numpy as np
import torch

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

from engine import RecitationEngine, StreamingSession
from server import classify_words
from arabic import (
    FATHA, DAMMA, KASRA, FATHATAN, DAMMATAN, KASRATAN, SHADDA, SUKOON,
    SHORT_VOWELS, HARAKAT, strip_diacritics,
    generate_i3rab_alternatives, generate_tashkeel_alternatives,
    replace_final_diacritic,
)

MODEL_PATH = BASE / "models" / "xlsr_mixed"
FRAME_STRIDE = 320
SAMPLE_RATE = 16000

# Which engine error_types satisfy a given mutation kind.
# combos change >1 diacritic, so any diacritic-level flag counts as correct-type.
_MUTATION_EXPECTED_TYPES = {
    "i3rab": {"i3rab"},
    "tashkeel": {"tashkeel", "diacritic"},
    "word": {"wrong", "skipped"},
    "combo": {"i3rab", "tashkeel", "diacritic"},
}


# ── Mutation generators ──
# i3rab/tashkeel/combo mutations are enumerated in enumerate_word_mutations()
# (below) off the arabic.py alternative generators. Word substitution stays here.

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


def _score_phrase_with_whisper(engine, audio_segment, phrase_text, whisper_words,
                               model_out=None):
    """Score a phrase using CTC + Whisper + classify_words (production path).

    model_out: optional precomputed model forward for this exact audio_segment.
    Passing it skips the (dominant) wav2vec2 forward when scoring the same audio
    against many mutated texts. Results are identical to recomputing.

    Returns list of classified word dicts.
    """
    waveform = torch.from_numpy(audio_segment)
    word_results, greedy, full_score = engine.score_phrase(
        waveform, phrase_text, model_out=model_out)

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


# ── Mutation enumeration (wide coverage, driven off arabic.py generators) ──

def _internal_vowel_positions(word):
    """Indices of internal short-vowel marks (before the final consonant),
    excluding vowels on shadda'd consonants (the model can't disambiguate
    gemination). Mirrors the gating in generate_tashkeel_alternatives."""
    chars = list(word)
    last_cons = -1
    for i in range(len(chars) - 1, -1, -1):
        if chars[i] not in HARAKAT:
            last_cons = i
            break
    if last_cons == -1:
        return []
    positions = []
    for i, c in enumerate(chars):
        if c in SHORT_VOWELS and i < last_cons:
            cons_idx = i - 1
            while cons_idx >= 0 and chars[cons_idx] in HARAKAT:
                cons_idx -= 1
            cluster_end = cons_idx + 1
            while cluster_end < len(chars) and chars[cluster_end] in HARAKAT:
                cluster_end += 1
            if any(chars[j] == SHADDA for j in range(cons_idx + 1, cluster_end)):
                continue  # skip shadda'd consonant vowels
            positions.append(i)
    return positions


def _combo_variants(word):
    """Compound (multi-change) error variants for one word:
    (a) two internal vowels changed at once, (b) one internal vowel + the
    case ending changed together. Returns list of (sub_name, mutated_word)."""
    chars = list(word)
    positions = _internal_vowel_positions(word)
    out = []

    def _other_vowel(orig):
        for v in (FATHA, DAMMA, KASRA):
            if v != orig:
                return v
        return orig

    # (a) two internal vowels at once
    if len(positions) >= 2:
        p1, p2 = positions[0], positions[1]
        nc = chars.copy()
        nc[p1] = _other_vowel(nc[p1])
        nc[p2] = _other_vowel(nc[p2])
        out.append(("combo_two_internal", "".join(nc)))

    # (b) one internal vowel + case ending
    if positions:
        p = positions[0]
        nc = chars.copy()
        nc[p] = _other_vowel(nc[p])
        partial = "".join(nc)
        i3 = generate_i3rab_alternatives(partial)
        for name in ("nasb", "jarr", "raf3"):  # first that differs & isn't sukoon
            if name in i3 and i3[name] != partial:
                out.append(("combo_internal_plus_i3rab", i3[name]))
                break
    return out


def enumerate_word_mutations(pw, wi, tashkeel_cap=None, combo_cap=None, rng=random):
    """Yield (category, sub_name, mutated_phrase_words, target_idx) test cases
    for word wi. i3rab is always exhaustive (small). tashkeel/combo are capped
    when *_cap is set (corpus); None = exhaustive (sessions)."""
    word = pw[wi]
    cases = []

    # i3rab: every case-ending alternative except sukoon (final sukoon is always OK)
    for name, alt in generate_i3rab_alternatives(word).items():
        if name == "sukoon":
            continue
        mw = list(pw); mw[wi] = alt
        cases.append(("i3rab", name, mw, wi))

    # tashkeel: every internal swap (incl. dropped-vowel -> sukoon)
    tash = list(generate_tashkeel_alternatives(word).items())
    if tashkeel_cap is not None and len(tash) > tashkeel_cap:
        tash = rng.sample(tash, tashkeel_cap)
    for name, alt in tash:
        mw = list(pw); mw[wi] = alt
        cases.append(("tashkeel", name, mw, wi))

    # combination (multi-change)
    combos = _combo_variants(word)
    if combo_cap is not None and len(combos) > combo_cap:
        combos = rng.sample(combos, combo_cap)
    for name, alt in combos:
        mw = list(pw); mw[wi] = alt
        cases.append(("combo", name, mw, wi))

    return cases


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
             fp_acc, stats, tashkeel_cap=None, combo_cap=None, verbose=False):
    """FP check + wide mutation suite for one (audio, text) item.

    tashkeel_cap / combo_cap: None = exhaustive (sessions); int = sample N per
    word (corpus). i3rab and word swaps are always exhaustive / fixed.

    fp_acc: dict with keys 'total','fp','details' (mutated in place).
    stats:  defaultdict(category -> {total,detected,type_correct,missed,by_sub}).
    """
    pw = phrase_text.split()

    # The audio is fixed across the FP check and every mutation of this item, so
    # run the (dominant) model forward ONCE and reuse it for all scorings.
    model_out = engine.get_model_outputs(torch.from_numpy(audio_segment),
                                         output_hidden_states=True)

    # ── FP check: correct text should flag nothing ──
    classified = _score_phrase_with_whisper(engine, audio_segment, phrase_text,
                                            whisper_words, model_out=model_out)
    for cw in classified:
        fp_acc["total"] += 1
        if cw["status"] != "correct":
            fp_acc["fp"] += 1
            fp_acc["details"].append((item_id, cw["word"], cw["error_type"], cw["debug"]["eff"]))

    # ── Mutation suite ──
    def _run_one(mut_text, wi, mtype, sub, original, mutated):
        try:
            cls = _score_phrase_with_whisper(engine, audio_segment, mut_text,
                                             whisper_words, model_out=model_out)
        except Exception:
            return
        s = stats[mtype]
        s["total"] += 1
        sub_stat = s["by_sub"][sub]
        sub_stat["total"] += 1
        target = next((c for c in cls if c["idx"] == wi), None)
        if not target:
            return
        detected = target["status"] != "correct"
        got = target["error_type"] if detected else None
        type_ok = got in _MUTATION_EXPECTED_TYPES[mtype] if detected else False
        if detected:
            s["detected"] += 1
            sub_stat["detected"] += 1
            if type_ok:
                s["type_correct"] += 1
                sub_stat["type_correct"] += 1
        if not detected or not type_ok:
            _accumulate_missed(stats, mtype, target, item_id, wi, sub, original, mutated)

    # i3rab / tashkeel / combo: enumerated per word off arabic.py generators
    for wi, word in enumerate(pw):
        for (cat, sub, mw, twi) in enumerate_word_mutations(
                pw, wi, tashkeel_cap=tashkeel_cap, combo_cap=combo_cap, rng=random):
            _run_one(" ".join(mw), twi, cat, sub, word, mw[twi])

    # word substitution: 2 per phrase (kept from the original suite)
    cands = [i for i, w in enumerate(pw) if len(strip_diacritics(w)) >= 3]
    if cands:
        for wi in random.sample(cands, min(2, len(cands))):
            mw, desc = mutate_word(pw, wi)
            _run_one(" ".join(mw), wi, "word", desc, pw[wi], mw[wi])


# ── Session source ──

def iter_session_items(engine, max_items=None, verbose=False):
    """Yield (source_label, item_id, audio_segment, phrase_text, whisper_words)
    for every covered phrase across the best session per passage. max_items caps
    total phrases emitted (for --quick)."""
    sessions = find_best_sessions(BASE / "test_data" / "sessions")
    emitted = 0
    for pid in sorted(sessions):
        si = sessions[pid]
        phrases = si["meta"]["phrases"]
        audio = si["audio"]
        full_text = " ".join(phrases)
        waveform = torch.from_numpy(audio)
        word_results, _greedy, _fs = engine.score_phrase(waveform, full_text, compute_pd=False)
        segments = _extract_phrase_segments(word_results, phrases, audio)
        for pi in sorted(segments.keys()):
            if max_items is not None and emitted >= max_items:
                return
            seg = segments[pi]
            whisper_words = engine.whisper_transcribe(seg)
            emitted += 1
            yield (f"sessions:{pid}", f"{pid}/p{pi}", seg, phrases[pi], whisper_words)


def iter_corpus_items(engine, limit=None, shortest=False, verbose=False):
    """Yield items for the external MSA corpus. Each utterance = one item:
    score the whole utterance against its own (converted) transcript and
    mutate that transcript. shortest=True picks the shortest utterances first
    (used by --quick: short clips score far faster)."""
    from eval_corpus import load_corpus_index
    index = load_corpus_index()
    if shortest:
        index = sorted(index, key=lambda it: len(it[1].split()))
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

_CATEGORIES = ("i3rab", "tashkeel", "combo", "word")

def _empty_stats():
    return defaultdict(lambda: {
        "total": 0, "detected": 0, "type_correct": 0, "missed": [],
        "by_sub": defaultdict(lambda: {"total": 0, "detected": 0, "type_correct": 0}),
    })

def _summarize(fp_acc, stats):
    tot_mut = sum(s["total"] for s in stats.values())
    det = sum(s["detected"] for s in stats.values())
    typ = sum(s["type_correct"] for s in stats.values())

    def _subs(cat):
        # detection rate per sub-type (only sub-types with >=3 samples), sorted worst-first
        rows = []
        for name, ss in stats[cat]["by_sub"].items():
            if ss["total"] >= 3:
                rows.append((name, ss["detected"], ss["total"],
                             round(ss["detected"] / ss["total"] * 100)))
        return sorted(rows, key=lambda r: r[3])

    out = {
        "fp_rate": round(fp_acc["fp"] / fp_acc["total"] * 100, 2) if fp_acc["total"] else 0.0,
        "fp_count": fp_acc["fp"], "words": fp_acc["total"],
        "detection_rate": round(det / tot_mut * 100, 1) if tot_mut else 0.0,
        "correct_type_rate": round(typ / tot_mut * 100, 1) if tot_mut else 0.0,
        "mutations": tot_mut, "detected": det, "type_correct": typ,
        "by_category": {c: {"total": stats[c]["total"], "detected": stats[c]["detected"],
                            "type_correct": stats[c]["type_correct"]}
                        for c in _CATEGORIES},
        "worst_subtypes": {c: _subs(c)[:8] for c in _CATEGORIES},
    }
    return out

def _print_summary(label, summ):
    print(f"\n{'='*70}\nSOURCE: {label}\n{'='*70}")
    print(f"  FP rate:        {summ['fp_rate']}%  ({summ['fp_count']}/{summ['words']})")
    print(f"  Detection:      {summ['detection_rate']}%  ({summ['detected']}/{summ['mutations']})")
    print(f"  Correct type:   {summ['correct_type_rate']}%  ({summ['type_correct']}/{summ['mutations']})")
    for c in _CATEGORIES:
        b = summ["by_category"][c]
        dr = round(b["detected"] / b["total"] * 100) if b["total"] else 0
        print(f"    {c:10s}: {b['detected']}/{b['total']}  ({dr}%)")
    # lowest-detection sub-types (where there's a real sample) help spot blind spots
    worst = [(c, *r) for c in _CATEGORIES for r in summ["worst_subtypes"][c] if r[3] < 90]
    if worst:
        print("  weakest sub-types (<90%):")
        for c, name, det, tot, rate in worst[:10]:
            print(f"    [{c}] {name:32s} {det}/{tot}  ({rate}%)")

def run_source(engine, item_iter, tashkeel_cap=None, combo_cap=None, verbose=False):
    fp_acc = {"total": 0, "fp": 0, "details": []}
    stats = _empty_stats()
    for (_label, item_id, seg, text, ww) in item_iter:
        run_item(engine, item_id, seg, text, ww, fp_acc, stats,
                 tashkeel_cap=tashkeel_cap, combo_cap=combo_cap, verbose=verbose)
    return fp_acc, stats

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["sessions", "corpus", "all"], default="all")
    ap.add_argument("--limit", type=int, default=None, help="cap corpus utterances")
    ap.add_argument("--max-items", type=int, default=None,
                    help="cap phrases/utterances per source (both sources)")
    ap.add_argument("--corpus-tashkeel-cap", type=int, default=4,
                    help="max tashkeel mutations per word on corpus (sessions exhaustive by default)")
    ap.add_argument("--corpus-combo-cap", type=int, default=2,
                    help="max combo mutations per word on corpus (sessions exhaustive by default)")
    ap.add_argument("--sessions-tashkeel-cap", type=int, default=None,
                    help="max tashkeel mutations per word on sessions (default: exhaustive). "
                         "Set to bound runtime for a fast committed baseline.")
    ap.add_argument("--sessions-combo-cap", type=int, default=None,
                    help="max combo mutations per word on sessions (default: exhaustive)")
    ap.add_argument("--quick", action="store_true",
                    help="fast smoke preset for iteration: tiny subset + tight caps, both sources. "
                         "A sanity signal, NOT a real measurement.")
    ap.add_argument("--report", default=None, help="write JSON report to this path")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    # --quick preset: small, capped, SHORT clips -> ~1 min smoke. Tune here.
    if args.quick:
        if args.max_items is None:
            args.max_items = 3
        if args.limit is None:
            args.limit = 4
        sess_tcap, sess_ccap = 1, 1          # cap sessions too in quick mode
        corp_tcap, corp_ccap = 1, 1
    else:
        sess_tcap, sess_ccap = args.sessions_tashkeel_cap, args.sessions_combo_cap  # None = exhaustive
        corp_tcap, corp_ccap = args.corpus_tashkeel_cap, args.corpus_combo_cap

    random.seed(42)
    t_load = time.time()
    engine = RecitationEngine(str(MODEL_PATH))
    print(f"[engine loaded in {time.time() - t_load:.0f}s]")

    report = {"config": {
        "source": args.source, "quick": args.quick,
        "max_items": args.max_items, "corpus_limit": args.limit,
        "sessions_caps": [sess_tcap, sess_ccap],
        "corpus_caps": [corp_tcap, corp_ccap],
    }, "sources": {}}
    if args.source in ("sessions", "all"):
        t0 = time.time()
        fp_acc, stats = run_source(
            engine, iter_session_items(engine, max_items=args.max_items, verbose=args.verbose),
            tashkeel_cap=sess_tcap, combo_cap=sess_ccap, verbose=args.verbose)
        summ = _summarize(fp_acc, stats)
        summ["elapsed_s"] = round(time.time() - t0, 1)
        report["sources"]["sessions"] = summ
        _print_summary("sessions", summ)
        print(f"  ({summ['elapsed_s']}s)")

    if args.source in ("corpus", "all"):
        try:
            t0 = time.time()
            corpus_limit = args.limit if args.limit is not None else args.max_items
            fp_acc, stats = run_source(
                engine, iter_corpus_items(engine, limit=corpus_limit,
                                          shortest=args.quick, verbose=args.verbose),
                tashkeel_cap=corp_tcap, combo_cap=corp_ccap, verbose=args.verbose)
            summ = _summarize(fp_acc, stats)
            summ["elapsed_s"] = round(time.time() - t0, 1)
            report["sources"]["corpus"] = summ
            _print_summary("corpus", summ)
            print(f"  ({summ['elapsed_s']}s)")
        except (FileNotFoundError, ValueError) as e:
            print(f"\n[corpus skipped] {e}")

    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"\nWrote report: {args.report}")

if __name__ == "__main__":
    main()
