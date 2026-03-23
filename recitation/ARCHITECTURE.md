# i3rab Architecture Overview

## Core Idea

i3rab turns Arabic diacritics detection from an open-ended recognition problem into a **constrained hypothesis test**. Since we know the book text, each word has only 3-8 possible diacritized forms. We encode the user's audio with XLS-R, compute CTC log-probabilities, and score each hypothesis via forced alignment.

## Production Model: XLS-R v5

**Architecture**: `facebook/wav2vec2-xls-r-300m` (300M parameter self-supervised speech model) with a CTC head over 58 Arabic character tokens (letters + diacritics + space + blank).

**Training**:
- Fine-tuned with frozen encoder, CTC head only
- 39.5K training samples: ClArTTS (9.5K) + contrastive pairs (20K) + TTS (10K)
- Online augmentation: speed perturbation (0.9-1.1x), additive noise (SNR 15-40dB), random gain (0.8-1.2x)
- 15 epochs, lr=1e-4, batch=8, grad_accum=4
- eval_loss: 0.1487

**Why XLS-R over Whisper**: Whisper's encoder-decoder uses attention (non-monotonic), causing attention drift and unreliable log-probs for diacritical differences. CTC is monotonic and directly scores character sequences against audio frames — a much better fit for pronunciation assessment where we know the expected text.

## Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│  User reads aloud                                               │
│       ↓                                                         │
│  Audio (16kHz float32)                                          │
│       ↓                                                         │
│  ┌──────────────┐                                               │
│  │   XLS-R 300M  │──→ CTC log-probs (T × 58 tokens)            │
│  │   Encoder     │                                              │
│  │   + CTC Head  │──→ Greedy decode → free transcript           │
│  └──────────────┘                                               │
│       ↓                                                         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Position Tracking + Forced Alignment                     │   │
│  │  - Free transcript fuzzy-matched to book text             │   │
│  │  - CTC forced alignment → per-word time boundaries        │   │
│  └──────────────────────────────────────────────────────────┘   │
│       ↓                                                         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Per-word Hypothesis Scoring                              │   │
│  │  - For each word, generate all valid diacritized forms    │   │
│  │  - Score each via CTC log-likelihood over word segment    │   │
│  │  - Best score = what user pronounced                      │   │
│  └──────────────────────────────────────────────────────────┘   │
│       ↓                                                         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Post-processing                                          │   │
│  │  - Low-confidence revert (gap < threshold → assume OK)    │   │
│  │  - Pausal-bias re-verification                            │   │
│  │  - Segment cross-check (MEDIUM confidence)                │   │
│  │  - Proactive i3rab & tashkeel (segment-level scoring)     │   │
│  └──────────────────────────────────────────────────────────┘   │
│       ↓                                                         │
│  Compare detected vs. correct → WordDiff                        │
│  (correct / wrong_irab / wrong_tashkeel / pausal_ok / wrong)   │
└─────────────────────────────────────────────────────────────────┘
```

## Modules

### `ssl_transcriber.py` — XLS-R CTC Transcriber (Production)

The production scoring engine. Loads a fine-tuned wav2vec2 model and provides:

- **`encode(audio)`** → CTC log-probabilities (T × vocab) + greedy-decoded transcript
- **`get_word_boundaries(log_probs, reference)`** → CTC forced alignment to find per-word audio segments
- **`score_hypothesis(log_probs, start, end, text)`** → CTC log-likelihood for a specific diacritized form over a time range

Key details:
- Audio resampled to 16kHz (model's native sample rate)
- Vocabulary: 58 tokens (Arabic letters, diacritics, space, blank)
- Runs on MPS (Apple Silicon) or CUDA

### `book.py` — Book + Hypothesis Generation

Loads diacritized Arabic text and generates all valid diacritized forms per word.

- **Rule-based** (default): For last letter, tries damma/fatha/kasra (definite), dammatan/fathatan/kasratan (indefinite), sukun (jussive), and pausal (no ending). Preserves shadda.
- **CAMeL Tools** (optional): NYU Abu Dhabi's morphological analyzer for linguistically-informed hypotheses.
- **CATT** (optional): Auto-diacritizes undiacritized book text.

Typical word → 7-8 hypotheses. Particles/prepositions → 1 hypothesis (no i3rab).

### `pipeline.py` — Orchestrator

The main scoring pipeline (`evaluate_pcd_live`):

1. **Encode** → XLS-R log_probs + free transcript
2. **Position tracking** → fuzzy match free transcript to book text
3. **Forced alignment** → CTC-based word boundaries
4. **Per-word i3rab scoring** → full-sentence CTC hypothesis scoring
5. **Low-confidence revert** → if score gap < `low_confidence_threshold` (1.5), assume correct
6. **Pausal-bias re-verification** → context-aware margin for pausal forms
7. **Segment cross-check** → re-score MEDIUM confidence words on isolated segments
8. **Proactive i3rab** → segment-level decode-assisted error detection
9. **Tashkeel scoring** → greedy decode + CTC-verified comparison
10. **Proactive tashkeel** → segment-level alternative detection

### `aligner.py` — CTC Forced Alignment

Implements CTC forced alignment using dynamic programming over log-probabilities. Maps each character in the reference text to a time frame, then aggregates to word-level boundaries.

### `tracker.py` — Position Tracking

Determines where in the book the user is reading. Uses the CTC free transcript (stripped of diacritics) and fuzzy-matches against the book's base words via `difflib.SequenceMatcher`.

Searches a window around the current position first (fast), falls back to full-book scan if match < 50%.

### `scorer.py` — Whisper Hypothesis Scoring (Legacy)

Original Whisper encoder-decoder scoring. Superseded by `ssl_transcriber.py` for production use. Kept for comparison/fallback.

### `pcd_transcriber.py` — NeMo PCD Transcriber (Legacy)

NeMo FastConformer CTC adapter. Was the first CTC-based approach before XLS-R. The NeMo v4b model achieves 96.5% on user recordings but only ~84% ClArTTS recall.

### `models.py` — Data Types

Core types: `BookWord`, `WordHypothesis`, `ScoredWord`, `WordDiff`, `HarakaDiff`, `Confidence`, `DiffKind`.

### `config.py` — Settings

Model paths, confidence thresholds, tracker window size, audio parameters, `low_confidence_threshold` (1.5).

### `arabic.py` — Arabic Text Utilities

Strip/compare/manipulate harakat, normalize Arabic text, detect last-letter position for i3rab operations.

### `irab_agent.py` — Grammar Explanations

Uses GPT-4o to explain i3rab grammar rules for detected errors. Optional, requires OpenAI API key.

### `cache.py` — Audio/Result Caching

Caches transcription results to avoid re-processing the same audio.

### `pdf_extractor.py` — PDF Text Extraction

Extracts diacritized Arabic text from PDF files for use as book input.

## Interfaces

### CLI (`main.py`)

Phrase-by-phrase reading with mic input. Shows colored terminal output. Optional GPT-4o i3rab explanations.

### Web (`server.py` + `static/index.html`)

FastAPI backend. Browser records audio via MediaRecorder, sends to `/api/transcribe`. Parchment-styled UI with word cards showing color-coded results and confidence badges.

## Training

Training scripts are in `recitation/training/`. The production model (XLS-R v5) was trained on RunPod (A100 80GB).

### Data Sources

| Dataset | Samples | Description |
|---------|---------|-------------|
| ClArTTS | 9,500 | Professional diacritized Arabic speech (only dataset with full case endings) |
| Contrastive | 20,000 | TTS-generated minimal pairs with diacritization differences |
| TTS | 10,000 | edge-tts generated diacritized Arabic |

### Training Script

`training/finetune_ssl_ctc.py` — Fine-tunes wav2vec2-xls-r-300m with:
- Frozen feature encoder (only CTC head trained)
- Online augmentation via custom `DataCollatorCTCWithAugmentation`
- `SaveBestCallback` for reliable checkpoint saving
- HuggingFace Trainer with `save_strategy="no"` (custom callback handles saves)

## Key Design Decisions

1. **CTC over attention**: CTC's monotonic alignment is a natural fit for pronunciation assessment. Whisper's attention-based decoder caused drift and hallucinations on diacritical differences.

2. **Hypothesis scoring over free transcription**: Rather than transcribing freely and diffing, we score known hypotheses. This is more accurate because we're asking "which of these 3-8 options did they say?" rather than "what did they say?"

3. **Full-sentence scoring**: Each word is scored in the context of the full sentence's CTC log-probs (not isolated). This captures coarticulation effects that influence how case endings are pronounced.

4. **Low-confidence revert**: When the score gap between hypotheses is small (< 1.5), we assume the user is correct. This dramatically reduces false positives with minimal impact on recall.

5. **Multi-stage verification**: The pipeline has several post-processing stages (pausal bias, segment cross-check, proactive scoring) that catch errors missed by the initial scoring pass.
