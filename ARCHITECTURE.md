# i3rab Architecture Overview

## Core Idea

i3rab turns Arabic diacritics detection from an open-ended recognition problem into a **constrained hypothesis test**. Since we know the book text, each word has only 3-8 possible diacritized forms. We score the user's audio against all of them and pick the best match.

## Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│  User reads aloud                                               │
│       ↓                                                         │
│  Audio (16kHz float32)                                          │
│       ↓                                                         │
│  ┌──────────────┐    ┌───────────────────┐                      │
│  │   Whisper     │───→│  Position Tracker │→ which words are     │
│  │  Transcribe   │    │  (fuzzy match to  │  they reading?       │
│  │  (undiacr.)   │    │   book text)      │                      │
│  └──────────────┘    └───────────────────┘                      │
│       ↓                                                         │
│  ┌──────────────┐    ┌───────────────────┐                      │
│  │   Whisper     │───→│ Hypothesis Scorer │→ for each word,      │
│  │   Encoder     │    │  (decoder log-    │  which diacritization │
│  │  (encode once)│    │   likelihood per  │  did they say?       │
│  └──────────────┘    │   hypothesis)     │                      │
│                      └───────────────────┘                      │
│       ↓                                                         │
│  Compare detected vs. correct → WordDiff (correct/wrong_irab/   │
│                                  wrong_tashkeel/pausal_ok/...)  │
└─────────────────────────────────────────────────────────────────┘
```

## Modules

### `book.py` — Book + Hypothesis Generation

Loads diacritized Arabic text and generates all valid diacritized forms per word.

- **Rule-based** (default): For last letter, tries damma/fatha/kasra (definite), dammatan/fathatan/kasratan (indefinite), sukun (jussive), and pausal (no ending). Preserves shadda.
- **CAMeL Tools** (optional): Uses NYU Abu Dhabi's morphological analyzer for linguistically-informed hypotheses with grammatical case labels.
- **CATT** (optional): Auto-diacritizes undiacritized book text (SOTA Arabic diacritizer).

Typical word → 7-8 hypotheses. Particles/prepositions → 1 hypothesis (no i3rab).

### `scorer.py` — Whisper Hypothesis Scoring

The core innovation. Uses Tarteel Whisper (`tarteel-ai/whisper-base-ar-quran`), whose tokenizer produces **different token IDs for different diacritizations** (verified):

```
الكتابَ → [..., 16758, 6808]   (fatha)
الكتابُ → [..., 16758, 10859]  (damma)
الكتابِ → [..., 16758, 11082]  (kasra)
```

**Scoring method**: Encode audio once with Whisper encoder. For each hypothesis, run the decoder with forced text tokens and compute the average per-token log-probability. Highest score = what the user most likely said.

**Confidence**: Based on the gap between best and second-best hypothesis scores:
- HIGH: gap ≥ 0.3 (reliable detection)
- MEDIUM: gap ≥ 0.15 (likely correct)
- LOW: gap < 0.15 (ambiguous)

### `tracker.py` — Position Tracking

Determines where in the book the user is reading. Uses standard Whisper transcription (undiacritized) and fuzzy-matches against the book's base words via `difflib.SequenceMatcher`.

Searches a window around the current position first (fast), falls back to full-book scan if match < 50%.

### `pipeline.py` — Orchestrator

Ties everything together:

1. **Transcribe** → undiacritized text (for position tracking)
2. **Track** → find matched BookWords in the book
3. **Score** → test each word's hypotheses against audio
4. **Diff** → classify each word as correct/wrong_irab/wrong_tashkeel/pausal_ok/missing/extra

**Error classification logic**:
- Only last-letter harakat differ → `WRONG_IRAB` (case ending error)
- Internal harakat differ → `WRONG_TASHKEEL` (vowel error)
- Pausal form at phrase boundary → `PAUSAL_OK` (acceptable)
- Different base consonants → `WRONG_WORD`

### `models.py` — Data Types

Core types: `BookWord`, `WordHypothesis`, `ScoredWord`, `WordDiff`, `HarakaDiff`, `Confidence`, `DiffKind`.

### `config.py` — Settings

Model name, confidence thresholds, tracker window size, audio parameters.

### `arabic.py` — Arabic Text Utilities

Strip/compare/manipulate harakat, normalize Arabic text, detect last-letter position for i3rab operations.

## Interfaces

### CLI (`main.py`)

Phrase-by-phrase reading with mic input. Shows colored terminal output. Optional GPT-4o i3rab explanations.

### Web (`server.py` + `static/index.html`)

FastAPI backend. Browser records audio via MediaRecorder, sends to `/api/transcribe`. Parchment-styled UI with word cards showing color-coded results and confidence badges.

**Key endpoints**: `POST /api/transcribe` (evaluate audio), `POST /api/book/load` (load new book), `POST /api/explain` (GPT-4o grammar explanation).

## Performance

- **Latency**: ~500ms per phrase on M4 Pro (encoder: ~200ms, decode per hypothesis: ~5ms × ~7 × ~5 words)
- **Accuracy**: 100% on isolated word discrimination (acc/nom/gen). ~65% on full sentences with TTS (limited by TTS not articulating case endings). Expected higher with real human recitation.
- **Noise resilience**: Minimal accuracy drop up to SNR 20dB.

## Dependencies

**Required**: `transformers`, `torch`, `numpy`, `soundfile`, `scipy`, `av` (for webm audio decoding)

**Optional**: `catt-tashkeel` (text diacritization), `camel-tools` (morphological analysis), `openai` (GPT-4o explanations)
