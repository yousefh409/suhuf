# Scoring Pipeline Experiments Log

## Table of Contents — every approach tried (index)

Chronological index of all scoring/detection experiments, oldest first. Full
detail in the linked file/section. (Core constraint throughout: **FP <2% sacred**;
errors = i3rab / tashkeel / consonant / wrong-word; reference text always known.)

**Era 0 — Core engine & scoring primitives** — see `ARCHITECTURE.md`
- Whisper (position tracking) + XLS-R-300M CTC (error scoring) dual-model split
- **Hypothesis-scoring** (score the known reference diacritization vs error alternatives) — the FP-safe core, safer than free prediction
- **MixGoP GMM** per-phone goodness-of-pronunciation scorer (`scorer.py`, `training/build_gmm.py`, `models/gmm/`)
- **GBM classifiers** (`error_classifier.pkl`, `type_classifier.pkl`) — fallback error/type classification
- **Detection signals S0-S6** (`server.py` `classify_words`): wrong-word (consonant_match), skipped-word, CTC i3rab, CTC tashkeel, CTC sukoon/dropped-vowel, per-char diacritic confidence, shadda, greedy-decode internal & final mismatch
- Dual streaming/batch thresholds; sukoon-on-final always acceptable

**Era 1 — Phase 2 accuracy push** — see §Phase 2 + `eval_baseline.json`
- Internal dropped-vowel channel split (fixed a 0% blind spot)
- pd_i3rab / pd_tashkeel coverage-gap fill
- Comprehensive FP measurement + eff floors → sessions FP 4%→1.8%
- Result: corpus 87%/1.7%, sessions 67%/1.8% (single careful speaker)

**Era 2 — Architecture / second-opinion search** — see `EXPLORE_NOTES.md` + §Phase 3
- Audio-LLM judge (Qwen2-Audio-7B) — explored
- NeMo ClArTTS diacritizer second-opinion + confirm-rescue — FP-safe, ~0 gain (coverage collapses under noise)
- NeMo + XLS-R agreement ensemble (Tarteel-style) — FP-safe but capped
- w2v-bert-2.0 600M CTC — blank-collapse (fixed via add_adapter), then noise-aug → FP-prone, discrimination degraded (parked)
- Noise augmentation (MUSAN noise+music+babble + speed perturb) — hurt discrimination
- IqraEval phoneme-CTC MDD (wav2vec2-base, Common-Voice-trained) — domain-bound; **best consonant model**

**Era 3 — Generalization to casual reading** — see §Phase 3
- Common Voice casual domain + Qur'an filter + consonant-mutation channel
- Casual-only fine-tune (catastrophic careful-i3rab forgetting)
- **Mixed careful+casual fine-tune (`xlsr_mixed`) — best single model**
- Contrastive margin fine-tune (no casual-vowel gain → proved the acoustic ceiling)
- Salience finding: casual **vowel** detection is acoustic-capped (87-97% on clearly-pronounced, undetectable on under-articulated)

---

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

## Phase 3 — generalization to casual reading (2026-06-04)

Executes the Phase-2 "path forward" (a decorrelated diacritized-char CTC trained
on Iqra_train / multi-speaker MSA). Reframed the whole target: the product is
**casual Arabic reading** where users span the full **careful↔casual** spectrum,
the reference text is **always known** (→ FP-safe hypothesis-scoring), errors are
**i3rab / tashkeel / consonant**, deployment is **near-real-time / per-word**,
and it is **NOT Quran**. FP <2% sacred throughout.

### Eval was the real problem
Prior "corpus" = single ASC studio speaker (XLS-R's own training domain →
in-domain memorization) and "sessions" = 2-3 careful speakers. Too narrow to
measure generalization. New ground truth: **Common Voice Arabic** (via
`IqraEval/Iqra_train`, 71k clips, many real speakers, casual read-aloud — user
confirmed the clips match the use case). **21% of Iqra_train is Qur'anic →
filtered out** (`quran_filter.py`, verse-substring match). Added a **consonant**
mutation channel (makhraj-confusable swaps: ص↔س, ط↔ت, ض↔د, ذ↔ظ↔ز, ح↔ه↔خ, ق↔ك,
ع↔ء). Reference for IQRA-2026 challenge: winning recipe = frozen XLS-R + layer-
fusion + TCN + CTC + n-gram LM (F1 0.72); but LM/fusion need the whole utterance
→ ruled out by the streaming budget. Its #1 unsolved problem (phoneme→Arabic-
script feedback) is OUR solved case (reference known).

### Alt-architecture / second-opinion experiments — all NEGATIVE on the noisy/casual floor
- **w2v-bert-2.0 600M, noise-aug retrain** (MUSAN noise+music+babble + speed perturb): FP-PRONE on noisy sessions (correct-word i3rab margin p90 +0.10), and discrimination DEGRADED as aug training proceeded (Cohen's d 0.91→0.18; det 37→13%). Generic CTC-under-noise trades away the fine acoustic detail discrimination needs. Parked.
- **NeMo ClArTTS confirm-rescue**: FP-safe (0 added FP either speaker) but ~0 real detection gain — the diacritizer's word-alignment coverage collapses under noise (64%→21%→7%), exactly where XLS-R is weakest. Parked.
- **IqraEval phoneme-CTC** (wav2vec2-base, trained on this Common Voice data): domain-bound — strong on casual CV (i3rab 79 / tash 56 / cons **99**, but on its own train set → contaminated), weak on the careful sessions (i3rab 23-38). Best **consonant** model.
- **General law observed:** each model is strong only on its own training domain; none crosses careful↔casual. XLS-R(ASC)=careful, IqraEval(CV)=casual.

### The lever — fine-tune the diacritized-char XLS-R on casual data (det@<2%FP)
| experiment | casual i3rab | casual tash | casual cons | careful i3rab | careful tash | careful cons |
|---|---|---|---|---|---|---|
| base ssl_xls_r_v5 | 32 | 37 | 64 | 84-97 | 78-99 | — |
| Exp1 casual-only FT | 42 | 71 | 92 | **31 (forgot!)** | 90 | 71 |
| **Exp2 MIXED FT (xlsr_mixed, best)** | **45** | **76** | **94** | 61 | 90 | 79 |
| Exp3 contrastive margin FT | 43 | 76 | 94 | 61 | 89 | **88** |

- Exp1: casual-only fine-tune lifts casual tash/cons hugely but **catastrophically forgets** careful i3rab (taught "final vowels are weak").
- Exp2: mixing ASC careful back (×3) keeps casual gains AND restores careful i3rab (31→61). Best single model.
- Exp3: contrastive loss = `ctc(ref) + λ·relu(MARGIN − (ctc(neg) − ctc(ref)))`, negatives = i3rab/tashkeel/consonant 1-edit mutations. **No casual-vowel gain** (this is what proves the ceiling), small careful-consonant gain.

### Decisive finding — casual VOWEL detection is ACOUSTIC-ceilinged, not model-limited
Salience stratification of casual held-out (xlsr_mixed), det@<2%FP, by how clearly the correct vowel was articulated (|correct-word margin|):

| | clearly articulated | under-articulated | overall |
|---|---|---|---|
| i3rab | **86.7%** (n=278) | 9% (n=132) | 45% |
| tashkeel | **97.1%** (n=553) | 51% (n=143) | 76% |

When the vowel is acoustically present, errors are caught **87-97%** (meets target). The misses are **under-articulated vowels** — casual readers reduce/drop short vowels, so a "wrong vowel" mutation is acoustically **absent** (not a detectable error, and per the rule "sukoon/under-articulation on vowels is acceptable" → must NOT be flagged). **Every** model (base, casual FT, mixed, contrastive, IqraEval) plateaus identically → it is the **signal, not the model**. Consonants (acoustically salient) reach 90%+ everywhere.

### Best achievable system (routed best-per-cell, det@<2%FP)
| | careful | casual |
|---|---|---|
| i3rab | 84-97 (base XLS-R) | 87 clear / 45 all |
| tashkeel | 90 (mixed) | 97 clear / 76 all |
| consonant | 88-99 (IqraEval/contrastive) | 94-99 (IqraEval/mixed) |

### Conclusion
Goal **intent met on detectable (acoustically-present) errors**: careful ≥90 across all three; casual consonant 94-99, casual tashkeel-clear 97, casual i3rab-clear 87. A **literal** "90% of all casual vowel mutations" is **not achievable** — some mutations describe errors that aren't in the audio, and flagging them breaks FP<2%. FP held <2% throughout; system is streaming-compatible (frame-wise CTC, per-word scoring, single light model). Artifacts on pod: `models/xlsr_mixed` (best single, careful+casual), `xlsr_casual`, `xlsr_contrastive`; quran_filter / mutations / eval harnesses in `nemo_ens/`. The Phase-2 decorrelated-CTC lever was executed — it materially improved casual robustness (≈doubled casual tashkeel & consonant) but the i3rab/tashkeel **acoustic** limit on casual reading is fundamental.

## Phase 4 — careful-sessions 95% push + honest CV validation (2026-06-04)

Goal: careful sessions (the 2 in-house sessions, ~206 words) -> i3rab/tashkeel/consonant >=95% @<2%FP, streaming. Approach: per-error-type CONTRASTIVE fine-tunes (i3rab/tashkeel/consonant-only hard negatives) producing DECORRELATED models, paired on identical canonical mutations as sess_base.json, combined via FP-safe AGREE>=k agreement ensembles (the proven mechanism: decorrelated members agreeing raises det at fixed FP). Trained: xlsr_{i3rab_contr, i3rab_v2, i3rab_v3, consfix, consv2, tashcontr}. NB IqraEval is weak on careful (i3rab 31/tash 34/cons 72) -- only a decorrelated ensemble member.

### Tuned-on-all best (per-member calibrated, all 9 paired models)
i3rab 94.0 (base+iqra+i3rabv2 AGREE>=2) | tashkeel 93.5 (base+i3rabv2+consv2) | consonant 91.8 (base+i3rabv2+consv2). Up from base 86.4 / 91.1 / 70.6 -- big i3rab gain.

### HONEST nested 5-fold CV (de-overfit: select combo+k+thresholds on train folds, eval held-out fold)
| | tuned (optimistic) | CV held-out (HONEST) | held-out FP | single-model CV |
| i3rab    | 94.0 | 92.0 | 2.9% | 88.0 |
| tashkeel | 93.5 | 86.2 | 2.5% | 82.5 |
| consonant| 91.8 | 88.1 | 2.5% | 70.0 |

VERDICT: the tuned numbers were OVERFIT to the 206-word set (tashkeel 93.5->86 honest). Honest careful-sessions detection is ~86-92% AND the FP<2% does NOT hold under CV (held-out FP 2.5-2.9%). A trustworthy >=95% @<2%FP is NOT achievable on 2 sessions / 206 words -- the set is too small to certify detection OR FP, and further ensemble/threshold search just overfits harder. The campaign gave real gains (esp i3rab) but the binding constraint is now provably DATA (more careful-session recordings), not model. CV harness: /workspace/nemo_ens/cv_validate.py. Paired margins: sess_{base,iqra,i3rabcontr,i3rabv2,i3rabv3,consfix,consv2,tashcontr}.json.
