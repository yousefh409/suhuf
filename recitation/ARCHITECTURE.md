# Recitation System Architecture

## Overview

A live Arabic readalong system. A student reads diacritized Arabic text aloud; the system follows along word-by-word and flags errors in real time (wrong words, wrong i3rab/case endings, wrong internal tashkeel/vowels).

Two models work together:
- **Whisper** (openai/whisper-small, 244M) — position tracking: "where in the text is the reader?"
- **XLS-R CTC** (fine-tuned Wav2Vec2, 300M) — error scoring: "did they say the right diacritics?"

## File Map

```
recitation/
├── engine.py            # Core: both models, scoring logic, StreamingSession
├── arabic.py            # Arabic text utils: diacritics, i3rab/tashkeel alternatives
├── server.py            # FastAPI server: REST + WebSocket, error classification
├── scorer.py            # MixGoP GMM scorer (lazy-loaded by engine if models/gmm/ exists)
├── auth.py              # Token signing/verification for the API
├── eval.py              # Unified evaluation — single source of truth (mutation-based)
├── eval_corpus.py       # External MSA corpus loader (Arabic Speech Corpus; Buckwalter→Arabic)
├── eval_baseline.json   # Committed honest baseline report, per source/speaker
├── test_streaming.py    # Automated streaming tests (TTS via edge-tts + WebSocket)
├── test_auth.py         # Auth unit test
├── passage.json         # Diacritized passages (ajrumiyyah, daa-dawa, ihya)
├── training/            # Build tool (not runtime): build_gmm.py regenerates models/gmm/
├── models/
│   ├── ssl_xls_r_v5/    # Fine-tuned XLS-R 300M CTC model (HuggingFace format)
│   ├── gmm/             # MixGoP GMMs (loaded by scorer.py if present)
│   ├── error_classifier.pkl  # GBM fallback classifier (loaded by server.py)
│   └── type_classifier.pkl   # GBM error-type classifier
├── data/                # External corpora cache (gitignored); e.g. data/asc/ = Arabic Speech Corpus
├── static/
│   ├── index.html       # Live readalong UI (single-file, ~600 lines)
│   └── record.html      # Test data recorder
└── test_data/
    ├── manifest.jsonl    # Recording metadata
    ├── recordings/       # .webm test recordings
    └── sessions/         # Saved streaming sessions (audio.raw + meta.json + scores.json)
```

## engine.py — The Core

### RecitationEngine

Singleton, loaded once at server startup. Holds both models.

**CTC model** (always loaded):
- `Wav2Vec2ForCTC` + `Wav2Vec2FeatureExtractor`, loaded from `models/ssl_xls_r_v5/`
- 58 Arabic character tokens including all diacritics
- 16 kHz input, runs on CPU (MPS disabled — flaky with wav2vec2)
- Key methods:
  - `get_log_probs(waveform)` → `(T, V)` log-probability matrix
  - `forced_align(log_probs, tokens)` → Viterbi CTC alignment spans
  - `word_boundaries_from_alignment(spans, tokens)` → per-word frame boundaries
  - `assess_word(log_probs_segment, expected_word)` → hypothesis scoring dict
  - `score_hypothesis(log_probs_segment, text)` → normalized CTC log-prob
  - `per_char_worst_delta(log_probs, char_spans)` → per-character diacritic confidence
  - `greedy_diacritic_mismatch(greedy_segment, expected_word)` → consonant-aligned vowel comparison
  - `score_phrase(waveform, phrase_text)` → full phrase batch scoring
  - `locate_and_score(waveform, full_text, phrases)` → find phrase + score (REST API)

**Whisper model** (lazy-loaded on first streaming use):
- `WhisperForConditionalGeneration` + `WhisperProcessor` from `openai/whisper-small`
- Auto-downloads ~500MB on first use
- Uses direct model API, NOT `pipeline()` (torchcodec import error with pipeline)
- `whisper_transcribe(audio_np)` → list of undiacritized Arabic word strings

### StreamingSession

One instance per WebSocket connection. Manages the streaming reading session.

**State:**
- `audio_ring` — 8-second sliding window of raw PCM float32 @ 16kHz
- `cursor_phrase` — which phrase index the reader is currently on
- `scored_words` — `{global_word_idx: assessment_dict}`, accumulated across cycles
- `_best_spoken` — `{phrase_idx: max_spoken_up_to}`, high-water mark per phrase
- `_cached_whisper_words` — Whisper output cache (skip if <0.5s new audio)

**score_cycle(final=False)** — the main loop, called every ~0.5-0.75s:

```
Phase 1: Position tracking (Whisper)
  ├─ _get_whisper_words(audio_np) — transcribe last 5s, with silence check
  ├─ _get_candidates() — [cursor-1, cursor, cursor+1, ..., cursor+5]
  ├─ _match_phrase(whisper_words, candidates) — first above 0.25 threshold
  └─ _spoken_word_count(whisper_words, phrase_words) — 3-pass fuzzy forward match
     └─ Incremental continuation via _best_spoken high-water mark

Phase 2: CTC scoring
  ├─ get_log_probs(audio) — run CTC model once
  ├─ forced_align(log_probs, tokens) — Viterbi alignment on spoken portion only
  └─ For each word: assess_word + per_char + greedy_diacritic_mismatch
     └─ Score locking: after 3 consistent scores, word is locked

Phase 3: Cursor advance
  ├─ Cap to +1 per cycle (prevents wild jumps from common-word overlaps)
  └─ Only advance from nearly_done when best_idx == cursor_phrase
```

**Key mechanisms that prevent cursor problems:**

1. **5s Whisper window** — only last 5s sent to Whisper (not full 8s ring buffer), prevents old-phrase audio from contaminating transcription
2. **Lookbehind** — candidates include `cursor-1`, so old audio in the ring buffer matches the previous phrase instead of falsely jumping to a distant future phrase
3. **+1 cap** — cursor can only advance by 1 per cycle via `best_idx`, no matter how far ahead a phrase matches
4. **best_idx == cursor guard** — the `nearly_done` / `next_started` check only fires when Whisper matched the current cursor phrase (prevents double-advance from stale data)
5. **High-water mark** (`_best_spoken`) — remembers peak `spoken_up_to` per phrase; when the start of a phrase leaves the 5s window, the system still knows those words were spoken and can continue matching from that point forward

**Word matching functions (module-level):**

- `_word_match(a, b)` — exact for words <4 chars, fuzzy (LCS>0.6) for 4+ chars. Prevents false matches on common Arabic particles (و, في, من, أما, لله).
- `_phrase_coverage(greedy_words, phrase_words)` — order-preserving LCS normalized by phrase length, uses `_word_match`
- `_spoken_word_count(whisper_words, phrase_words)` — 3-pass forward matching with `_lcs_ratio > 0.5` (more permissive than `_phrase_coverage`). Pass 1: direct forward. Pass 2: skip first 1-3 Whisper words (previous phrase bleed). Pass 3: find first phrase word anywhere in output.
- `_lcs_ratio(a, b)` — character-level LCS ratio: `2*LCS_len/(len_a+len_b)`

## server.py — API & Classification

### Endpoints

- `GET /` — live readalong UI
- `GET /record` — test data recorder
- `GET /api/passages` — all passages from passage.json
- `POST /api/score` — batch score a single audio file against a passage
- `POST /api/save` — save a test recording
- `GET /api/recordings` — list saved recordings
- `WS /ws/score` — streaming scoring

### WebSocket Protocol

1. Client sends JSON: `{"passage_id": "ajrumiyyah", "debug": true}`
2. Client streams raw PCM float32 @ 16kHz as binary frames
3. Server responds with JSON: `{"words": [...], "matched_phrase_idx": N}`
4. Client sends text `"done"` → server runs final score cycle with batch thresholds
5. Server responds with `{"words": [...], "final": true}`

When `debug: true`, the server saves `audio.raw`, `meta.json`, and `scores.json` to `test_data/sessions/`.

### classify_words() — Error Classification

Takes raw engine assessment dicts and applies threshold-based rules to classify each word. Uses **dual thresholds**: streaming (conservative) vs batch (tighter).

| Threshold | Batch | Streaming |
|-----------|-------|-----------|
| i3rab | 0.08 | 0.15 |
| tashkeel | 0.20 | 0.20 |
| shadda | 0.20 | 0.30 |
| pc_tier1_delta | -4.5 | -6.0 |
| pc_tier1_eff | -0.7 | -0.7 |
| pc_tier2_delta | -2.5 | -3.5 |
| pc_tier2_eff | -0.3 | -0.3 |

**Six detection signals** (evaluated in order, first match wins):

| # | Signal | What it detects | Key condition |
|---|--------|----------------|---------------|
| S0 | Wrong word | Different consonant structure | `consonant_match < 0.4` and `eff > -1.0` |
| S-1 | Skipped word | Very few frames + poor score | `frame_count < 3` and `eff < -3.5` |
| S1 | CTC i3rab | Wrong case ending | `alt_score > eff + i3rab_thresh` |
| S2 | CTC tashkeel | Wrong internal vowel | `tash_score > eff + tash_thresh` |
| S2b | CTC sukoon | Missing vowel | `sukoon_score > eff + tash_thresh + 0.10` |
| S3 | Per-char | Frame-level diacritic | Two-tier: `(pc < -4.5 & eff > -0.7)` OR `(pc < -2.5 & eff > -0.3)` |
| S4 | Shadda | Vowel on geminated consonant | `shadda_score > eff + shadda_thresh` |
| S5 | Greedy internal | Greedy decode vowel mismatch | `gdm >= 1` + CTC or pc confirmation |
| S5b | Confirmed greedy | Batch-only, lower eff gate | `gdm >= 1` and `-1.5 < eff <= -1.0` |
| S6 | Greedy final | Greedy final mismatch | `gfm` and `pc < -2.0` and `eff > -1.0` |

## arabic.py — Text Utilities

- `strip_diacritics(text)` — remove all harakat
- `get_final_diacritic(word)` → `(diacritics_string, last_consonant_index)`
- `replace_final_diacritic(word, new_mark)` — swap case ending
- `make_sukoon_variant(word)` — replace final diacritic with sukoon (pausal form)
- `generate_i3rab_alternatives(word)` → dict of `{name: alt_word}` for all case endings
- `generate_tashkeel_alternatives(word)` → dict of `{name: alt_word}` for internal vowel swaps (skips shadda'd consonants)

**Important Unicode detail**: Arabic diacritic order in the text is `consonant + vowel + shadda` (not `consonant + shadda + vowel`). The `generate_tashkeel_alternatives` function skips shadda'd consonants because CTC can't distinguish vowel quality through gemination.

## static/index.html — Frontend

Single-file HTML/CSS/JS (~600 lines). Key behaviors:

- Passage selector dropdown → fetches from `/api/passages`
- Record button → captures audio via `AudioWorklet` (or `ScriptProcessorNode` fallback)
- Streams PCM float32 @ 16kHz over WebSocket to `/ws/score`
- Merges incremental word results: new results override old, locked words persist
- Color coding: green = correct, red = wrong word, blue = i3rab error, orange = tashkeel error
- Tap a word to see debug overlay (effective score, deltas, greedy decode)
- "Done" button sends final signal → batch thresholds applied
- Debug toggle saves session data server-side

## Current Metrics

Accuracy is measured by `eval.py` (the single source of truth) and recorded in
`eval_baseline.json`, broken out **per source / speaker**. The methodology is
mutation-based: real audio is held fixed and the reference text is mutated
(i3rab / tashkeel / word) to induce errors on demand.

Measured comprehensively (ALL session phrases, not a capped subset) — see
`eval_baseline.json` for current figures and `experiments.md` (Phase 2) for the
methodology and the FP-vs-detection analysis:

- **corpus** (Arabic Speech Corpus — held-out second MSA speaker, clean studio
  audio, the trustworthy generalization signal): **~1.7% FP, ~87% detection**.
- **sessions** (in-domain, single human speaker, noisy laptop-mic audio):
  **~1.8% FP, ~67% detection**. Lower detection than the clean corpus because the
  real-speech audio has many poorly-aligned words and documented small
  mispronunciations, so the conservative (FP-sacred) operating point trades away
  more detection here.

False positives are held **<2% on both speakers** — the primary constraint.
Note: mutation-based detection is inherently easier than genuine human
mispronunciations; the FP rate on an unseen speaker is the key generalization
signal. An earlier figure of "~93% detection" came from a capped 10-phrase
subset that also hid the comprehensive false-positive rate; the numbers above are
the honest all-phrases measurement.

## Error-scoring ensemble — decorrelated agreement (Phase 3-4, PROVISIONAL)

The single XLS-R discriminator has a per-error-type ceiling. Phases 3-4 added an
optional **ensemble of decorrelated diacritized-char CTC models** combined via
FP-safe agreement-gating. Full log in `experiments.md` (Phases 3-4).

**Members** (all score identically — reference-vs-error margin via `assess_word`):
- `base` (`ssl_xls_r_v5`) — careful-studio ASC; strongest single on i3rab.
- **contrastive fine-tunes** — same architecture, trained with a *margin* loss on
  one-diacritic-off hard negatives, specialized per error type (i3rab-only /
  tashkeel-only / consonant-only negatives) from different starts/seeds, so their
  errors decorrelate (`xlsr_i3rab_contr`, `xlsr_i3rab_v2/v3`, `xlsr_consfix`,
  `xlsr_consv2`, `xlsr_tashcontr` — on the network volume).
- IqraEval phoneme-CTC — a different model *family*, a decorrelated vote.

**Combination** — per error type, route to a small set and flag only if **≥k
members agree** (each above its own FP-safe threshold). Agreement is the
false-positive control; decorrelation is essential (identical models voting does
nothing).

**Honest numbers (5-fold CV on the careful sessions, de-overfit):** i3rab ~92,
tashkeel ~86, consonant ~88 (up from base 86/91/71) — but held-out FP ~2.5% (over
budget) and selected on only ~206 words. The **mechanism** is the transferable
result; the **specific member set + thresholds are data-limited and PENDING
validation on a larger / more general dataset** before being trusted as the
production default.

**Implementation (shipped):** `ensemble.py` → `RoutedEnsemble`, a drop-in scorer
selected at startup by `load_ensemble_or_engine` from `ensemble_config.json`. It
wraps the member engines and adds `ensemble_i3rab/tashkeel/consonant` agreement
flags per word; `classify_words` uses them when present and the existing
single-model logic otherwise. **Both entrypoints are wired** — `/ws/score`
(streaming, via `score_phrase`) and `/api/score` (batch, via `locate_and_score`,
which maps the matched phrase's local word indices back to global). A `consonant`
channel (makhraj-confusable single-swap scoring) is added here since `assess_word`
covers only i3rab+tashkeel.

**Deploy safety / fallback:** the loader resolves member dirs relative to the
config and verifies every *used* member's weights are on disk. If any are missing
(the 5 non-`base` members currently live on the region-locked RunPod volume
`29p3s0lzcq`), it logs and **falls back to single-model** — a server with only
`base` runs exactly as before, never crashing on a missing optional weight. Drop
the member dirs in next to the config and the full ensemble auto-activates on the
next startup. `ensemble_config.example.json` documents the schema.

**Casual reading (Phase 3):** fine-tuning on Qur'an-filtered Common Voice
(`xlsr_mixed`) roughly doubled casual tashkeel/consonant detection; casual
*vowel* detection is acoustically capped (87-97% on clearly-pronounced errors,
undetectable on under-articulated ones — acceptable per the sukoon rule).

**Latency:** the ensemble runs 2-3 model forwards per word — fine for batch, a
real cost on the per-word streaming path; deployment trims to minimal members.

### Streaming (test_streaming.py)
- Correct readings: ~0% FP; i3rab/tashkeel errors caught; ~1.2s to first response; no flicker.

## How to Run

```bash
cd recitation
python -m uvicorn server:app --host 0.0.0.0 --port 8000
# Open http://localhost:8000
```

Python: `/opt/homebrew/Caskroom/miniconda/base/bin/python3` (3.13)

### Running Evaluation

```bash
# Unified eval — single source of truth (sessions + external MSA corpus)
python eval.py                    # all sources, full
python eval.py --quick            # ~30s smoke preset for iteration (tiny subset, short clips)
python eval.py --source sessions  # real-audio sessions only
python eval.py --source corpus --limit 40
python eval.py --report eval_baseline.json
```

**Mutation suite (wide coverage).** For each word, mutations are enumerated off the
`arabic.py` generators: every i3rab case ending (except sukoon, always acceptable),
every internal tashkeel position × vowel (including dropped-vowel → sukoon), and
multi-change combos (two internal vowels; internal + case ending). Word-substitution
too. The report prints a per-sub-type "weakest <90%" breakdown so blind spots are
visible (e.g. internal dropped-vowel detection). Sessions are scored exhaustively;
the corpus samples per word (`--corpus-tashkeel-cap`, `--corpus-combo-cap`).

**Speed.** The wav2vec2 forward is cached per clip (`score_phrase(model_out=...)`) and
reused across every mutation of that audio. `--quick` uses short clips for a fast loop;
full corpus runs are slower (long clips). Per-source timing is printed.

```bash
# Streaming behavior test (requires running server on port 8000)
python test_streaming.py
```

The external corpus lives at `data/asc/` (Arabic Speech Corpus, gitignored). Download
it from `https://en.arabicspeechcorpus.com/arabic-speech-corpus.zip` and unzip there.

## Key Design Decisions

1. **Conservative error detection**: false negatives >> false positives. A student flagged incorrectly destroys trust. Missing a subtle error is tolerable.

2. **Dual thresholds**: streaming uses wider margins (more conservative) because partial audio is noisier. When the client sends "done", final scoring uses tighter batch thresholds.

3. **Sukoon always acceptable**: the final letter with sukoon (pausal/waqf form) is never flagged as an error. `make_sukoon_variant()` is scored alongside the expected form; `effective_score = max(expected, sukoon)`.

4. **Whisper for position, CTC for scoring**: Whisper is good at recognizing what was said (position tracking) but doesn't have diacritized tokens. CTC has 58 diacritized character tokens and can distinguish فَ from فُ from فِ, but its greedy decode is unreliable for position tracking. The dual-model split plays to each model's strength.

5. **Score locking**: after 3 consistent scoring cycles, a word's assessment is locked. This prevents late-arriving audio from degrading earlier scores. `final=True` overrides all locks.

6. **High-water mark for position**: the `_best_spoken` dict remembers the max `spoken_up_to` per phrase. When the reader progresses and earlier words leave the 5s Whisper window, the system remembers them and can continue counting from where it left off.

## Common Pitfalls

- **Don't use `pipeline("automatic-speech-recognition")`** — it imports `torchcodec` which has FFmpeg version conflicts. Use `WhisperForConditionalGeneration` + `WhisperProcessor` directly.
- **Don't use MPS for wav2vec2** — produces incorrect results on Apple Silicon. Force CPU.
- **Don't use exact word matching for phrase coverage** — Whisper garbles Arabic words (هريرة→هيرايروت, فقد ثبت→فقلتابت). Fuzzy matching with `_word_match` is required.
- **Don't allow cursor jumps > 1** — common Arabic words (في, من, الله, صحيح, حديث) appear across many phrases. Without the +1 cap, the cursor can jump to a distant phrase that shares these words.
- **Don't run nearly_done on wrong phrase data** — if `best_idx != cursor_phrase`, the `spoken_up_to` is for a different phrase. Applying `nearly_done` would cause the cursor to advance based on stale data.
- **Test recordings may have small errors** — occasional background noise, slight mispronunciations not noted. Treat as real-world data, not lab-perfect ground truth.
