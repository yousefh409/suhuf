# Scoring Pipeline Experiments Log

## Baseline (2026-04-01)

| Metric | Target | Baseline |
|---|---|---|
| FP rate | <2% | 5.2% (17/326) |
| I3rab detection | >90% | 51% (126/246) |
| Tashkeel detection | >90% | 61% (161/266) |
| Word detection | >95% | 52% (32/62) |
| Correct type overall | — | 50.2% (288/574) |

### Key observations
- daa-dawa passage is much worse (7.1% FP vs 3.5% for ajrumiyyah)
- 120 missed i3rab mutations, 105 missed tashkeel, 30 missed word
- Many misses have very negative `eff` scores (< -2.0), which means the quality gate (`effective_score < -2.0`) is suppressing detection
- Wrong word detection at 52% — consonant_match threshold of 0.4 is too strict, and frame_count filter blocks many
- Many i3rab false negatives: `skip_i3rab=True` when `sukoon_score > expected_score` blocks most i3rab testing

## Experiment History

(entries below)

## Phase 2 — accuracy push (2026-06-03)

Goal: push detection >90% across speakers while holding FP <2% (FP sacred).
Worked against `eval.py`; clean held-out corpus (full Arabic Speech Corpus,
leakage-free MSA speaker) is the trustworthy FP signal per the docs.

### What changed (engine.py + server.py)

1. **Internal dropped-vowel detection (the 0% blind spot fix).** `assess_word`
   conflated both directions of an internal vowel↔sukoon swap into one
   length-bias-gated channel (`'sukoon' in name`), so internal dropped vowels
   detected at **0%**. Split by direction: `best_addvowel_score` (sukoon→vowel —
   NOT length-bias-prone, the real dropped-vowel signal) vs `best_sukoon_score`
   (vowel→sukoon — kept gated). Added a `classify_words` tier on `addvowel_delta`
   (eff-adaptive + greedy-decode corroboration). Internal-sukoon subtypes moved
   off 0%; sessions tashkeel 48%→~54-73%.
2. **pd coverage-gap fill.** `pd_i3rab`/`pd_tashkeel` are structurally clean
   (correct words sit at pd=0; verified on 148 held-out words). The standalone
   pd tiers had eff-stratum gaps (pd_i3 missing −1.0<eff≤−0.5; pd_t missing
   eff>−0.5). Filled them → corpus detection 83%→~87% at near-0 added FP.
3. **FP reduction (comprehensive sessions FP was hidden by `max_items 10`).**
   Measured on ALL phrases, sessions FP was ~4%, not 0%. Reverted a weak
   two-channel i3rab tier (net-negative: +1-3 detections, caused داء/دواء FP);
   added a hard eff floor (no i3rab/tashkeel flag below eff −3.7, where forced
   alignment is too poor — the low-eff recovery tiers latch onto spurious
   windows on correct-but-misaligned words); floored the low-eff wrong rule at
   eff>−4.0. Sessions FP 3.99%→1.84%.
4. CUDA: Whisper un-pinned from CPU (engine.py) so the system runs on GPU in
   production (position tracking only; no effect on detection/FP).

### Result (comprehensive: all session phrases + corpus, caps 2/1)

| Speaker | FP | Detection | vs target (90% / <2%) |
|---|---|---|---|
| corpus (clean held-out MSA) | ~1.7% | ~87% | FP MET; detection −3 |
| sessions (noisy real human) | ~1.8% | ~67% | FP MET; detection short |

**FP <2% achieved on BOTH speakers (the sacred constraint).** Detection improved
on the clean signal (83→87%) and the internal-sukoon blind spot is fixed.

### Why >90% detection was not reached (evidence)

- **Acoustic ceiling.** Diagnosed the missed i3rab: correct words have
  i3rab_delta ≤ −0.03 and pd=0; ~half of missed errors have i3rab_delta ≈ 0 AND
  pd = 0 — i.e. the XLS-R model cannot acoustically distinguish the wrong final
  vowel from the right one for these. No threshold recovers a signal that isn't
  there.
- **Ensemble second opinion validated as NOT viable.** The in-hand NeMo ClArTTS
  diacritizer agrees with correct held-out-speaker references only ~90% on the
  final diacritic → ~8-10% standalone FP (4-5× over budget). Failures are
  structural, not noise: it drops phrase-final marks, predicts pausal-vs-
  contextual i3rab (both valid but disagree), and makes real case errors from
  the ClArTTS→ASC domain shift. **General insight:** any *ASR-based* (free
  diacritic prediction) second opinion shares this pausal/contextual FP risk;
  XLS-R's *hypothesis-scoring* is more FP-robust.
- **Noisy real-human audio.** Sessions detection at <2% FP is capped ~67%; the
  recordings have many low-eff (poorly aligned) words and documented small
  mispronunciations, so the FP-vs-detection trade is steep there.

### Path forward (the one remaining lever)

A **decorrelated diacritized-char CTC** trained on *different* data than XLS-R
v5 (e.g. Iqra_train / multi-speaker MSA), used as a second *hypothesis-scorer*
(not a free predictor) + agreement-gating. This avoids the ASR pausal/contextual
FP and could push the clean-corpus detection toward 90%. It is a multi-hour
training effort with uncertain payoff on the noisy sessions; deferred as a
separate track.
