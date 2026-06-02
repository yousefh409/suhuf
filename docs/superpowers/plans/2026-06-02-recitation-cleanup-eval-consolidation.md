# Recitation Cleanup & Eval Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove dead experiment code and fold three overlapping eval scripts into a single mutation-based `eval.py` that evaluates both the saved sessions and an external MSA corpus, producing one honest per-speaker baseline — with zero change to scoring behavior.

**Architecture:** `eval.py` becomes the single source of truth for accuracy. It reuses the *exact* proven scoring path from the current `test_mutations.py` (engine CTC + Whisper + `server.classify_words`) and its mutation generators, wrapped behind a small data-source abstraction so the same FP-check + mutation suite runs over (a) saved real-audio sessions and (b) an external diacritized MSA corpus (Arabic Speech Corpus by Nawar Halabi). A correctness gate requires `eval.py` to reproduce the pre-refactor `test_mutations.py` numbers before any deletion happens.

**Tech Stack:** Python 3, PyTorch, HuggingFace Transformers (Wav2Vec2 CTC + Whisper), the existing `engine.py` / `server.py` / `arabic.py` / `scorer.py`. No new heavy deps.

---

## Spec Reference

Implements `docs/superpowers/specs/2026-06-02-recitation-cleanup-eval-consolidation-design.md`.

## Working Directory & Conventions

- All paths below are relative to the repo root of the worktree:
  `/Users/yousefh/Desktop/Cool Code/suhuf/.claude/worktrees/pensive-greider-611eeb`
- Recitation code lives under `recitation/`. Run all Python from inside `recitation/`.
- Python interpreter: `/opt/homebrew/Caskroom/miniconda/base/bin/python3` (call it `python` below; it has torch/transformers/edge-tts installed in the main checkout's env).
- **Shipping:** never raw `git push`. Commit locally each task. The user ships with `./bin/suhuf ship` at the end.
- **Behavior-preservation is the prime directive for Phase 1.** Do not edit `engine.py`, `server.py`, `arabic.py`, or `scorer.py` logic. `eval.py` only *calls* them.

## File Structure

**Created:**
- `recitation/eval.py` — the single unified evaluation script (data-source abstraction, FP + mutation suite, per-source reporter).
- `recitation/eval_corpus.py` — external-corpus loader (download/locate Arabic Speech Corpus, yield `(utterance_id, waveform, diacritized_text)`).
- `recitation/training/` — relocation target for build tools (`build_gmm.py`, `train_classifier.py`, `train_type_classifier.py`).
- `recitation/eval_baseline.json` — committed honest baseline report (small JSON, no audio).

**Deleted (dead experiments):**
`diagnostic_classifier.py`, `diagnostic_ctc.py`, `diagnostic_cv.py`, `diagnostic_fp_fix.py`, `diagnostic_framescan.py`, `diagnostic_local_pd.py`, `diagnostic_local_pd2.py`, `diagnostic_lpd_extended.py`, `diagnostic_rescored.py`, `diagnostic_rules.py`, `optimize_rules.py`, `optimize_thresholds.py`, `threshold_scan.py`, `dump_signals.py`, `diagnose_tts.py`, `analyze_misses.py`, `test_prototype.py`, `test_extend_phrases.py`, `test_inline_passage.py`, `test_retreat.py`, `rescored_dump.json`, `signal_dump.json`.

**Deleted after folding into `eval.py`:**
`test_mutations.py`, `evaluate.py`, `measure_tashkeel.py`.

**Unchanged live files:**
`engine.py`, `server.py`, `arabic.py`, `auth.py`, `scorer.py`, `passage.json`, `static/`, `requirements.txt`, `Dockerfile`, `test_auth.py`, `test_streaming.py`, `models/`.

**Docs updated:** `recitation/ARCHITECTURE.md`, `docs/recitation/system.md`, `docs/testing/recitation-system.md`.

---

## Task 1: Worktree data setup (symlinks)

The worktree has no `models/` and no audio under `test_data/` (gitignored / uncommitted in this worktree). Symlink them from the main checkout so anything can run.

**Files:**
- Create symlinks: `recitation/models`, `recitation/test_data/recordings`, `recitation/test_data/sessions`, `recitation/.tts_cache`

- [ ] **Step 1: Verify the main checkout has the assets**

Run:
```bash
ls -d "/Users/yousefh/Desktop/Cool Code/suhuf/recitation/models/ssl_xls_r_v5" \
      "/Users/yousefh/Desktop/Cool Code/suhuf/recitation/test_data/sessions" \
      "/Users/yousefh/Desktop/Cool Code/suhuf/recitation/test_data/recordings"
```
Expected: all three paths print (exist).

- [ ] **Step 2: Create the symlinks in the worktree**

Run (from worktree root):
```bash
cd recitation
MAIN="/Users/yousefh/Desktop/Cool Code/suhuf/recitation"
ln -sfn "$MAIN/models" models
mkdir -p test_data
ln -sfn "$MAIN/test_data/recordings" test_data/recordings
ln -sfn "$MAIN/test_data/sessions" test_data/sessions
ln -sfn "$MAIN/.tts_cache" .tts_cache
ls -la models test_data/sessions | head
cd ..
```
Expected: symlinks resolve; `test_data/sessions` lists the 3 session dirs.

- [ ] **Step 3: Confirm symlinks are gitignored (no weights committed)**

Run:
```bash
git -C . check-ignore recitation/models recitation/test_data/sessions recitation/.tts_cache
```
Expected: all three paths printed (ignored). If any is NOT ignored, add it to `recitation/.gitignore` and re-check. Do NOT `git add` any audio or weights.

- [ ] **Step 4: Commit (gitignore only, if changed)**

```bash
git add recitation/.gitignore 2>/dev/null || true
git commit -m "chore(recitation): ignore symlinked models/test_data in worktree" || echo "nothing to commit"
```

---

## Task 2: Capture the pre-refactor baseline (reference snapshot)

Before changing anything, snapshot the current `test_mutations.py` output. This is the reference `eval.py` must reproduce (acceptance criterion 3).

**Files:**
- Create: `recitation/.eval_reference.txt` (gitignored scratch, not committed)

- [ ] **Step 1: Run the existing primary test and save output**

Run (from `recitation/`):
```bash
cd recitation
python test_mutations.py 2>&1 | tee .eval_reference.txt
cd ..
```
Expected: prints per-session SESSION/PASSAGE blocks and a final `COMBINED RESULTS` block with `False positive rate`, `Overall detection`, `Correct type`, and per-category (`i3rab`, `tashkeel`, `word`) lines. Note these numbers — they are the reference.

- [ ] **Step 2: Record the reference numbers in the plan tracking**

Read `.eval_reference.txt`; copy the `COMBINED RESULTS` block and each per-session FP/detection summary into your task notes. These exact figures (within run-to-run noise; the run is seeded `random.seed(42)`) are what Task 4 must match.

- [ ] **Step 3: Ensure the scratch file is ignored**

Run:
```bash
grep -q '^recitation/.eval_reference.txt$' recitation/.gitignore 2>/dev/null || echo 'recitation/.eval_reference.txt' >> recitation/.gitignore
git add recitation/.gitignore && git commit -m "chore(recitation): ignore eval reference scratch" || echo "nothing to commit"
```

---

## Task 3: Create `eval.py` with the session source (behavior-preserving fold of `test_mutations.py`)

Build `eval.py` by moving the proven functions out of `test_mutations.py` unchanged, then add a thin source abstraction + structured reporter around them. This is DRY: we relocate, not rewrite, the scoring/mutation logic.

**Files:**
- Create: `recitation/eval.py`
- Source of moved functions: `recitation/test_mutations.py` (do not delete yet — Task 7)

- [ ] **Step 1: Scaffold `eval.py` — header, imports, moved helpers**

Create `recitation/eval.py`. Start with the header below (it already defines the
module constants `MODEL_PATH`, `FRAME_STRIDE`, `SAMPLE_RATE`, and
`_MUTATION_EXPECTED_TYPES` — do NOT also copy those from `test_mutations.py`).
Then (Step 1b) copy these **functions only**, verbatim, from `test_mutations.py`:
`mutate_i3rab`, `mutate_tashkeel`, `mutate_word`, `_DIAC_NAMES`, `_diac_name`,
`find_best_sessions`, `_extract_phrase_segments`, `_score_phrase_with_whisper`.

Top of file:

```python
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
```

Then (Step 1b) paste the seven functions listed above, unchanged, below the header.

- [ ] **Step 2: Add the per-item mutation runner (extracted from `run_session`/`_test_mutation`)**

Add a function that runs the FP check + mutation suite for ONE already-segmented item (audio segment + phrase text + whisper words), returning structured counts. This is the inner loop of the current `run_session` Phase 1 + Phase 2, with `_test_mutation` inlined into accumulation. Add to `eval.py`:

```python
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
```

- [ ] **Step 3: Add the session source — yields ready-to-run items**

Add a generator that reproduces the current session segmentation (full-audio align → per-phrase segments → Whisper per segment), yielding items for `run_item`. Add to `eval.py`:

```python
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
```

- [ ] **Step 4: Add the reporter + `main()` (sessions source only for now)**

Add per-source aggregation, JSON + console output, and CLI. Add to `eval.py`:

```python
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

    # corpus source wired in Task 5

    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"\nWrote report: {args.report}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run `eval.py` on sessions and compare to the reference**

Run (from `recitation/`):
```bash
cd recitation
python eval.py --source sessions 2>&1 | tee .eval_new.txt
cd ..
```
Expected: a `SOURCE: sessions` summary. Compare its FP rate and per-category detected/total against the `COMBINED RESULTS` you captured in Task 2. They must match within run-to-run noise (same seed → expect identical counts). If they differ materially, diff the logic against `test_mutations.py` until they match — do not proceed until reproduced.

- [ ] **Step 6: Commit**

```bash
git add recitation/eval.py
git commit -m "feat(recitation): unified eval.py session source (reproduces test_mutations)"
```

---

## Task 4: Reproduce-baseline gate (lock in correctness)

Make the reproduction explicit and durable so future edits can't silently drift.

**Files:**
- Modify: `recitation/eval.py` (add a `--assert-sessions-baseline` self-check is optional; primary gate is manual diff here)

- [ ] **Step 1: Diff new vs reference**

Run:
```bash
cd recitation
diff <(grep -E "FP rate|Detection|i3rab|tashkeel|word" .eval_new.txt) \
     <(grep -E "False positive|Overall detection|i3rab|tashkeel|word" .eval_reference.txt) || true
cd ..
```
Expected: the detected/total counts for `i3rab`, `tashkeel`, `word` and the FP count agree with the reference. (Formatting differs; compare the numbers.)

- [ ] **Step 2: If counts match, record confirmation**

Note in task tracking: "eval.py sessions source reproduces test_mutations.py baseline: FP=X/Y, i3rab=a/b, tashkeel=c/d, word=e/f." If they do NOT match, fix `eval.py` (Task 3) and repeat. Behavior preservation is mandatory before any deletion.

---

## Task 5: Add the external MSA corpus source

Add `eval_corpus.py` (loader) and wire a `corpus` source into `eval.py` using the **same** `run_item` methodology. Corpus utterances are short and already have their own transcript, so each utterance is one item (no full-reading force-align needed).

**Files:**
- Create: `recitation/eval_corpus.py`
- Modify: `recitation/eval.py` (wire corpus source into `main`)
- Local data (gitignored): `recitation/data/asc/`

- [ ] **Step 1: Acquire the Arabic Speech Corpus and inspect its layout**

The Arabic Speech Corpus (Nawar Halabi, MSA, fully diacritized, ~1.5GB) is at
`http://en.arabicspeechcorpus.com/` (and mirrored on Kaggle: `nawarhalabi/arabic-speech-corpus`).
Download into `recitation/data/asc/` and inspect:
```bash
cd recitation && mkdir -p data/asc
# Download the archive into data/asc/ (browser or curl), then:
ls -R data/asc | head -40
cd ..
```
Expected: a `wav/` directory of `.wav` files and a transcript file mapping each wav id to **diacritized** Arabic orthography (commonly an `orthographic-transcript.txt` with lines like `"ARA NORM  0002.wav" "النَّصُّ ..."`). Note the EXACT transcript file name and line format — the loader in Step 3 is written to that format.

- [ ] **Step 2: Confirm no training overlap + gitignore the data**

The existing models were fine-tuned on **ClArTTS**, not ASC, so ASC is a safe held-out source. Confirm by checking `recitation/models/training.log` for any mention of "arabicspeechcorpus"/"ASC":
```bash
grep -i "arabicspeech\|\basc\b\|halabi" recitation/models/training.log || echo "no ASC mention — safe"
```
Expected: "no ASC mention — safe". Then gitignore the data dir:
```bash
grep -q '^recitation/data/$' recitation/.gitignore 2>/dev/null || echo 'recitation/data/' >> recitation/.gitignore
git add recitation/.gitignore && git commit -m "chore(recitation): ignore local corpus data dir" || echo "nothing to commit"
```

- [ ] **Step 3: Write the corpus loader**

Create `recitation/eval_corpus.py`. Adjust the transcript parsing to the format observed in Step 1; the version below targets the standard ASC `orthographic-transcript.txt`:

```python
"""Arabic Speech Corpus (Nawar Halabi) loader for eval.py.

Yields (utterance_id, diacritized_text, wav_path). MSA, fully diacritized,
single speaker — a held-out second speaker relative to the saved sessions.
"""
import re
from pathlib import Path

BASE = Path(__file__).parent
ASC_DIR = BASE / "data" / "asc"

def _find(name_options):
    for n in name_options:
        hits = list(ASC_DIR.rglob(n))
        if hits:
            return hits[0]
    return None

def load_corpus_index():
    """Return list of (utt_id, diacritized_text, wav_path)."""
    transcript = _find(["orthographic-transcript.txt", "*orthographic*.txt"])
    if transcript is None:
        raise FileNotFoundError(
            f"No orthographic transcript under {ASC_DIR}. "
            "Inspect the archive layout (Task 5 Step 1) and update _find().")
    wav_root = transcript.parent
    items = []
    for line in transcript.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        # Standard ASC line: "ARA NORM  0002.wav" "النص المشكول ..."
        m = re.match(r'"[^"]*?(\S+\.wav)"\s+"(.+)"\s*$', line)
        if not m:
            continue
        wav_name, text = m.group(1), m.group(2).strip()
        wav_path = next(iter(wav_root.rglob(wav_name)), None)
        if wav_path and text:
            items.append((wav_name.replace(".wav", ""), text, str(wav_path)))
    if not items:
        raise ValueError("Parsed 0 corpus items — transcript format differs; "
                         "update the regex in eval_corpus.py to the layout from Task 5 Step 1.")
    return items
```

- [ ] **Step 4: Wire the corpus source into `eval.py`**

Add a corpus item iterator to `eval.py` (below `iter_session_items`):

```python
def iter_corpus_items(engine, limit=None, verbose=False):
    """Yield items for the external MSA corpus. Each utterance = one item.
    The utterance text is already short, so we score the whole utterance
    against its own transcript and mutate that transcript."""
    from eval_corpus import load_corpus_index
    index = load_corpus_index()
    if limit:
        index = index[:limit]
    for (utt_id, text, wav_path) in index:
        try:
            waveform = engine.load_audio(wav_path)  # 16kHz mono float32 tensor
        except Exception as e:
            if verbose:
                print(f"  skip {utt_id}: load failed ({e})")
            continue
        audio = waveform.numpy()
        if len(audio) < int(0.5 * SAMPLE_RATE):
            continue
        whisper_words = engine.whisper_transcribe(audio[-int(5.0 * SAMPLE_RATE):])
        yield (f"corpus", utt_id, audio, text, whisper_words)
```

Then in `main()`, replace the `# corpus source wired in Task 5` comment with:

```python
    if args.source in ("corpus", "all"):
        try:
            fp_acc, stats = run_source(engine, iter_corpus_items(engine, args.limit, args.verbose), args.verbose)
            summ = _summarize(fp_acc, stats)
            report["sources"]["corpus"] = summ
            _print_summary("corpus", summ)
        except (FileNotFoundError, ValueError) as e:
            print(f"\n[corpus skipped] {e}")
```

- [ ] **Step 5: Smoke-test the corpus source on a small limit**

Run:
```bash
cd recitation
python eval.py --source corpus --limit 10 --verbose 2>&1 | tail -30
cd ..
```
Expected: a `SOURCE: corpus` summary with non-zero `words` and `mutations`. If it prints `[corpus skipped]`, fix the transcript parsing in `eval_corpus.py` per the real layout (Task 5 Step 1) and retry. A high FP rate here is EXPECTED and fine — Phase 1 only measures honestly; improving it is Phase 2.

- [ ] **Step 6: Commit**

```bash
git add recitation/eval.py recitation/eval_corpus.py
git commit -m "feat(recitation): add external MSA corpus (ASC) source to eval.py"
```

---

## Task 6: Generate and commit the honest baseline report

**Files:**
- Create: `recitation/eval_baseline.json` (committed — small, no audio)

- [ ] **Step 1: Run the full eval and write the report**

Run (corpus limit keeps runtime sane; raise/remove later):
```bash
cd recitation
python eval.py --source all --limit 200 --report eval_baseline.json 2>&1 | tee .eval_full.txt
cd ..
```
Expected: `eval_baseline.json` written with `sources.sessions` and `sources.corpus` objects, each containing `fp_rate`, `detection_rate`, `correct_type_rate`, and `by_category`.

- [ ] **Step 2: Sanity-check the report**

Run:
```bash
python -c "import json;d=json.load(open('recitation/eval_baseline.json'));print(list(d['sources']));print(d['sources']['sessions'])"
```
Expected: shows `['sessions', 'corpus']` and the sessions summary dict. Confirm sessions numbers match the Task 4 reference.

- [ ] **Step 3: Commit the baseline**

```bash
git add recitation/eval_baseline.json
git commit -m "chore(recitation): commit honest per-source eval baseline"
```

---

## Task 7: Delete folded eval scripts

Now that `eval.py` reproduces sessions and adds corpus, remove the three scripts it replaces. Confirm nothing else imports them first.

**Files:**
- Delete: `recitation/test_mutations.py`, `recitation/evaluate.py`, `recitation/measure_tashkeel.py`

- [ ] **Step 1: Confirm no remaining importers**

Run:
```bash
cd recitation
grep -rn "import test_mutations\|from test_mutations\|import evaluate\|from evaluate\|import measure_tashkeel\|from measure_tashkeel" . --include=*.py | grep -v "^./eval"
cd ..
```
Expected: no output (the diagnostic scripts that imported `test_mutations` are deleted in Task 8 — if any still reference it, delete those in Task 8 first, then return here). If the only hits are files slated for deletion in Task 8, proceed.

- [ ] **Step 2: Delete the three scripts**

```bash
git rm recitation/test_mutations.py recitation/evaluate.py recitation/measure_tashkeel.py
```

- [ ] **Step 3: Verify eval still runs**

```bash
cd recitation && python eval.py --source sessions 2>&1 | tail -8 && cd ..
```
Expected: `SOURCE: sessions` summary still prints (eval.py is self-contained).

- [ ] **Step 4: Commit**

```bash
git commit -m "refactor(recitation): remove eval scripts folded into eval.py"
```

---

## Task 8: Delete dead experiment scripts and artifacts

**Files:** see "Deleted (dead experiments)" list in File Structure.

- [ ] **Step 1: Delete diagnostic + optimization + dump scripts and JSON dumps**

```bash
cd recitation
git rm diagnostic_classifier.py diagnostic_ctc.py diagnostic_cv.py diagnostic_fp_fix.py \
       diagnostic_framescan.py diagnostic_local_pd.py diagnostic_local_pd2.py \
       diagnostic_lpd_extended.py diagnostic_rescored.py diagnostic_rules.py \
       optimize_rules.py optimize_thresholds.py threshold_scan.py dump_signals.py \
       diagnose_tts.py analyze_misses.py \
       test_prototype.py test_extend_phrases.py test_inline_passage.py test_retreat.py \
       rescored_dump.json signal_dump.json
cd ..
```
Expected: all removed without error. (If git complains a file is already untracked/missing, drop it from the list and continue.)

- [ ] **Step 2: Verify the live system still imports cleanly**

```bash
cd recitation
python -c "import engine, server, arabic, scorer, auth; print('live imports OK')"
python eval.py --source sessions 2>&1 | tail -5
cd ..
```
Expected: `live imports OK`, and the sessions summary still prints. If any ImportError names a deleted module, that import was a hidden live dependency — restore the file and investigate before continuing.

- [ ] **Step 3: Commit**

```bash
git commit -m "chore(recitation): delete dead diagnostic/optimization scripts and dumps"
```

---

## Task 9: Relocate build tools to `training/`

These regenerate live artifacts (`models/gmm/`, `*.pkl`) and may be used in Phase 2; they are not runtime code, so move them out of the top level.

**Files:**
- Move: `build_gmm.py`, `train_classifier.py`, `train_type_classifier.py` → `recitation/training/`

- [ ] **Step 1: Move the files**

```bash
cd recitation && mkdir -p training
git mv build_gmm.py training/build_gmm.py
git mv train_classifier.py training/train_classifier.py
git mv train_type_classifier.py training/train_type_classifier.py
cd ..
```

- [ ] **Step 2: Fix their imports if needed**

These scripts do `from engine import ...` / `from scorer import ...` assuming the parent dir is on the path. Add a path shim at the top of each moved file (right after the existing imports of `sys`/`Path`, or add them):

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```
Then verify each compiles:
```bash
cd recitation && python -m py_compile training/build_gmm.py training/train_classifier.py training/train_type_classifier.py && echo OK && cd ..
```
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add -A recitation/training
git commit -m "chore(recitation): relocate build/training tools under training/"
```

---

## Task 10: Update documentation

Reflect the consolidated layout and the single eval entry point.

**Files:**
- Modify: `recitation/ARCHITECTURE.md`, `docs/recitation/system.md`, `docs/testing/recitation-system.md`

- [ ] **Step 1: Update `recitation/ARCHITECTURE.md` File Map and run instructions**

In the File Map (around lines 13-32), remove the deleted scripts and the separate eval scripts; replace the testing section so `eval.py` is the single eval entry point. Replace the "Running Tests" block with:

```
### Running Evaluation

# Unified eval — single source of truth (sessions + external MSA corpus)
python eval.py                    # all sources
python eval.py --source sessions  # real-audio sessions only
python eval.py --source corpus --limit 200
python eval.py --report eval_baseline.json

# Streaming behavior test (requires running server on port 8000)
python test_streaming.py
```
Also update the "Current Metrics" section to state the numbers now come from `eval.py` / `eval_baseline.json`, reported per source/speaker.

- [ ] **Step 2: Update `docs/recitation/system.md`**

In the "Key Files" table, remove rows for deleted scripts; change the `evaluate.py` row to `eval.py` ("unified mutation-based evaluation; single source of truth; sessions + external MSA corpus"); add a `training/` note for build tools. In "Current Metrics", note the baseline is now `recitation/eval_baseline.json`, per source.

- [ ] **Step 3: Update `docs/testing/recitation-system.md`**

Replace references to `test_mutations.py` / `evaluate.py` / `measure_tashkeel.py` as the eval harness with `eval.py`. Describe the two sources (sessions, external MSA corpus) and the mutation methodology. Keep `test_streaming.py` as the streaming test.

- [ ] **Step 4: Commit**

```bash
git add recitation/ARCHITECTURE.md docs/recitation/system.md docs/testing/recitation-system.md
git commit -m "docs(recitation): consolidate eval docs around single eval.py"
```

---

## Task 11: Final verification

- [ ] **Step 1: Repo is clean and live system intact**

```bash
cd recitation
python -c "import engine, server, arabic, scorer, auth; print('live OK')"
ls *.py
cd ..
```
Expected: `live OK`. Top-level `recitation/*.py` should now be only: `engine.py`, `server.py`, `arabic.py`, `auth.py`, `scorer.py`, `eval.py`, `eval_corpus.py`, `test_auth.py`, `test_streaming.py`.

- [ ] **Step 2: Single eval runs end-to-end**

```bash
cd recitation && python eval.py --source all --limit 50 2>&1 | tail -20 && cd ..
```
Expected: both `SOURCE: sessions` and `SOURCE: corpus` summaries print.

- [ ] **Step 3: Run the suhuf verify gate**

```bash
./bin/suhuf verify --base origin/main 2>&1 | tail -20
```
Expected: passes (recitation Python package: compileall + pytest --co tolerated). Fix any compile errors surfaced.

- [ ] **Step 4: Confirm acceptance criteria**

Verify against the spec: (1) dead files gone, build tools relocated, live files untouched; (2) `eval.py` is the only eval script; (3) sessions numbers reproduce the Task 2 reference; (4) corpus source reports per-source metrics; (5) `eval_baseline.json` committed; (6) docs updated. Report status to the user.

- [ ] **Step 5: Ship (with user confirmation)**

Ask the user "Ready to ship Phase 1?" Then on yes: `./bin/suhuf ship` and open a PR with `gh pr create --fill`. Do not push directly.

---

## Notes for the executor

- **Do not modify scoring logic.** Any change in sessions numbers vs. the Task 2 reference means a bug in the fold — fix it, don't accept the drift.
- The corpus FP/detection numbers being poor at first is fine and expected; Phase 1 only establishes an honest baseline. Improvement is Phase 2 (kicked off separately with `/goal`).
- If the ASC transcript format differs from the assumed layout, the only file to touch is `eval_corpus.py` (parsing) — `eval.py` is format-agnostic.
- Engine APIs used (already exist, do not change): `RecitationEngine(model_path)`, `engine.score_phrase(waveform, text, compute_pd=False)`, `engine.whisper_transcribe(audio_np)`, `engine.load_audio(path)`, `StreamingSession._whisper_word_matches`, `server.classify_words(word_results, phrase_words, streaming=False)`.
