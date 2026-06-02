# Recitation: Cleanup & Eval Consolidation (Phase 1)

Date: 2026-06-02
Status: Design — pending implementation plan

## Background

The recitation system (live Arabic readalong) is functional but the codebase has
accumulated heavy cruft from a long iterative tuning process: ~30 Python files,
most of them one-off diagnostic and threshold-optimization scripts, plus large
JSON signal dumps. Evaluation is split across three scripts with overlapping
purposes, and the headline accuracy number (76% detection / 1.8% FP) is measured
on a single speaker and is no longer trusted as current or representative.

This effort is split into two phases. **This spec covers Phase 1 only.**

- **Phase 1 (this spec):** Clean up the code and consolidate all evaluation into a
  single trustworthy script. No change to scoring behavior. Produce one honest
  baseline number.
- **Phase 2 (later, separate spec):** The improvement loop — research and iterate
  on architectures (learned decision layer, model ensembles, acoustic retraining)
  until detection is solidly above 90%, plus production deployment as a parallel
  track. Phase 2 will be kicked off separately with the `/goal` command.

## Problem

1. The repository is dominated by dead experiment scripts that obscure the live
   system and make it hard to reason about what actually runs in production.
2. Evaluation logic is spread across `test_mutations.py`, `evaluate.py`, and
   `measure_tashkeel.py`, each with its own data path and metrics. There is no
   single source of truth for "how good is the system right now."
3. The eval coverage is single-speaker, so any accuracy number is at risk of
   being an overfit mirage that will not generalize to other readers.

## Goals

- Remove all dead/experimental code and stale artifacts.
- Consolidate evaluation into exactly **one** script (`eval.py`) that is the
  single source of truth for system accuracy.
- Broaden evaluation beyond one speaker by adding a second, external real-speaker
  data source — evaluated with the same methodology.
- Produce a single honest baseline report that Phase 2 will iterate against.

## Non-Goals (deferred to Phase 2)

- Any change to `classify_words`, detection rules, thresholds, the GBM fallback,
  the GMM/MixGoP scorer, or the models.
- Improving the detection number itself.
- Production deployment.

Phase 1 is a pure refactor + consolidation. Correctness criterion: the new
`eval.py` must reproduce the current system's results on the existing sessions
(within run-to-run noise) before it is trusted.

## Live vs. Dead Inventory

Verified by tracing runtime imports and artifact loads.

**Live — keep untouched:**
`engine.py`, `server.py`, `arabic.py`, `auth.py`, `scorer.py` (MixGoP, lazy-loaded
by `engine.py` when `models/gmm/gmms.pkl` exists), `passage.json`, `static/`,
`requirements.txt`, `Dockerfile`, and the model artifacts
`models/{ssl_xls_r_v5, gmm, error_classifier.pkl, type_classifier.pkl}`
(the two `.pkl` classifiers are loaded by the `classify_words` GBM fallback).

**Dead experiments — delete:**
the 11 `diagnostic_*.py` scripts, `optimize_rules.py`, `optimize_thresholds.py`,
`threshold_scan.py`, `dump_signals.py`, `diagnose_tts.py`, `analyze_misses.py`,
the stale prototype tests (`test_prototype.py`, `test_extend_phrases.py`,
`test_inline_passage.py`, `test_retreat.py`), and the large JSON dumps
(`rescored_dump.json`, `signal_dump.json`).

**Fold into `eval.py` then delete originals:**
`test_mutations.py` (the core — its mutation generators and session helpers are
preserved into `eval.py`), `evaluate.py`, `measure_tashkeel.py`.

**Build tools — keep but move out of the top level (e.g. a `training/` folder):**
`build_gmm.py`, `train_classifier.py`, `train_type_classifier.py`. These
regenerate live artifacts and may be used in Phase 2; they are not runtime code.

`test_auth.py` and `test_streaming.py` are retained (auth unit test; streaming
behavior test).

## The Unified `eval.py`

One script, one command, one report. It is the single source of truth for
accuracy.

### Methodology — mutation-based only

We do not rely on human-labeled error recordings. Because we always know the
exact text the audio corresponds to, we induce errors by **mutating the
reference text** the model scores against, while holding the real audio fixed.
This lets us generate any error type (i3rab, tashkeel, word swap) at any position
on demand, and it is the only methodology `eval.py` uses.

For each data item the script runs:

- **FP check:** score the real audio against the *correct* text. Any flag is a
  false positive.
- **Mutation suite:** for each eligible word, generate i3rab, tashkeel, and
  word-swap mutations of the reference text and verify the targeted word is
  flagged with the correct error type.

This is exactly the methodology already proven in `test_mutations.py`; Phase 1
generalizes it across data sources and unifies reporting.

### Data sources

1. **Saved sessions** — real human audio (the current `test_mutations.py` path):
   force-align the full reading, slice per-phrase segments, run FP + mutation
   suite. Covers Ajrumiyyah and Daa-Dawa.
2. **External MSA corpus** — a second real speaker (see below): align audio to its
   diacritized transcript, slice to phrase-sized segments, run the same FP +
   mutation suite.

### Reporting

- A single structured report (machine-readable JSON + human console summary).
- Metrics: false-positive rate and detection-by-type (i3rab / tashkeel / word),
  plus correct-type rate.
- **Broken out per data source / speaker**, never collapsed into one blended
  number — the per-speaker split is what reveals generalization.
- Deterministic (seeded) so Phase 2 can compare runs meaningfully. This report
  format is the Phase 2 scoreboard.

## External Corpus Selection

Constraints: real human speech, fully diacritized transcript, **non-Quran**
(normal MSA to start), and **no overlap with any corpus used to train the
existing models** (notably ClArTTS) to avoid leakage inflating the number.

Leading candidate: **Arabic Speech Corpus (Nawar Halabi)** — MSA, fully
diacritized, clean, a different speaker than the existing sessions. Single
speaker, but it still adds the crucial second-speaker signal to start.

Fallbacks if availability or licensing blocks it: a confirmed held-out split of
ClArTTS (only if the exact training split can be recovered), or another
diacritized MSA corpus identified during research. Multi-speaker breadth can be
expanded in Phase 2. The exact corpus is confirmed during implementation
research; the selection criteria above are fixed.

## Worktree & Data Logistics

- Use the existing worktree (`claude/pensive-greider-611eeb`). Do not create a
  new `group-c-recitation` worktree.
- The worktree lacks `models/` and the audio under `test_data/` (gitignored /
  uncommitted). The plan symlinks these from the main checkout so `eval.py` runs.
- No audio or model weights are committed. The external corpus is downloaded to a
  local, gitignored cache.

## Acceptance Criteria (Phase 1)

1. All files in the "delete" list are removed; build tools relocated; live files
   untouched.
2. `eval.py` is the only evaluation script. `test_mutations.py`, `evaluate.py`,
   and `measure_tashkeel.py` no longer exist.
3. `eval.py` runs end-to-end on the saved sessions and reproduces the current
   detection/FP results within run-to-run noise (proves the refactor preserved
   behavior).
4. `eval.py` also evaluates the external MSA corpus and reports per-source metrics.
5. A single committed baseline report captures the honest current numbers,
   per source/speaker.
6. Docs (`docs/recitation/`, `recitation/ARCHITECTURE.md`) updated to reflect the
   consolidated layout and the single eval entry point.

## Phase 2 Preview (not in scope)

Once the baseline is trustworthy: error-analyze where misses come from across
speakers, then iterate — likely starting by replacing the hand-tuned rule sprawl
with a single regularized learned decision layer, escalating to model ensembles
or acoustic retraining only if the error analysis demands it. Deployment to a GPU
host proceeds as a parallel track. Phase 2 begins with the `/goal` command.
