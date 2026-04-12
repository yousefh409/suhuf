# Project

Suhoof (i3rab) — AI-powered Arabic recitation assessment with real-time error detection for diacritized text.

## Architecture

- `recitation/` — Python backend: FastAPI server + CTC scoring engine + streaming WebSocket
- `recitation/engine.py` — `RecitationEngine` (CTC model) + `StreamingSession` (WebSocket state)
- `recitation/server.py` — FastAPI app, REST + WS endpoints, classification rules
- `recitation/arabic.py` — Unicode diacritic utilities, i3rab/tashkeel alternative generation
- `recitation/scorer.py` — `MixGoPScorer` GMM-based diacritic scoring on frozen SSL layers
- `recitation/models/` — XLS-R v5 CTC (300M params), Whisper (lazy), GBM classifiers, GMMs (~14GB total)
- `recitation/static/` — `index.html` (live readalong UI), `record.html` (test recorder)
- `recitation/test_data/` — 78 recordings, manifest.jsonl, saved sessions, TTS cache
- `reader/` — Planned iPad app (Expo/TypeScript) — only `TECHNICAL_SPEC.md` exists

## Data Flow

```
[Browser] --WebSocket PCM float32--> server.py
  --> StreamingSession.score_cycle()
    --> Whisper transcribe (position tracking, 5s window)
    --> XLS-R CTC inference (log_probs)
    --> forced_align() (character-level alignment)
    --> assess_word() (score expected vs alternatives)
    --> classify_words() (multi-tier threshold rules + GBM fallback)
  <-- JSON: {words: [{status, error_type, debug}], matched_phrase_idx}
```

Batch mode: `POST /api/score` with webm file → ffmpeg → same pipeline → JSON response.

## Entry Points

- `recitation/server.py` — FastAPI app, run via `python -m uvicorn server:app --host 0.0.0.0 --port 8000`
- `recitation/static/index.html` — Browser UI served at `/`

## Core Models

- `recitation/engine.py:RecitationEngine` — CTC scoring, alignment, diacritic analysis
- `recitation/engine.py:StreamingSession` — Per-connection state, 8s ring buffer, position tracking
- `recitation/scorer.py:MixGoPScorer` — GMM diacritic scoring on XLS-R layers [14,16,18]

## ML Models

| Model | Path | Purpose |
|-------|------|---------|
| XLS-R v5 CTC | `models/ssl_xls_r_v5/` | Diacritized Arabic character scoring (58 tokens) |
| Whisper small | HuggingFace (lazy) | Position tracking (undiacritized transcription) |
| Error GBM | `models/error_classifier.pkl` | Binary error/correct fallback |
| Type GBM | `models/type_classifier.pkl` | Error type (i3rab/tashkeel/word) |
| MixGoP GMMs | `models/gmm/` | Per-diacritic scoring on SSL hidden states |

## Detection Signals (priority order)

1. S0 — Wrong word (consonant mismatch)
2. S-1 — Skipped word (frame-limited)
3. S1 — CTC i3rab (case ending delta)
4. S2 — CTC tashkeel (internal vowel delta)
5. S3 — Per-character diacritic confidence
6. S4-S6 — Shadda, greedy internal/final mismatch

## Scoring Thresholds (dual mode)

| Signal | Batch | Streaming |
|--------|-------|-----------|
| i3rab | 0.08 | 0.15 |
| tashkeel | 0.20 | 0.20 |
| shadda | 0.20 | 0.30 |
| pc_tier1_delta | -4.5 | -6.0 |

## Current Metrics

- Batch FP rate: 1.8% (target: <2%)
- Detection rate: 76% (4 misses on subtle sukoon/tanween)
- Streaming: 0% FP on correct readings, catches i3rab/tashkeel

## Infrastructure

- **Runtime**: Python 3.10+, PyTorch, FastAPI/Uvicorn
- **Audio**: ffmpeg (webm → PCM float32 @ 16kHz)
- **GPU**: Required for production (T4+), dev runs on CPU/MPS
- **No CI/CD, Docker, or cloud deployment yet**
- **Planned**: Supabase (auth, DB), RevenueCat (payments), Expo (iOS app)

## Passages

- `passage.json` — 3 diacritized texts: Ajrumiyyah (grammar), Daa-Dawa (spiritual), Ihya (theology)

## Docs

- `PRD.md` — Product requirements
- `GTM.md` — Go-to-market (4 phases)
- `Market-Analysis.md` — TAM/SAM/SOM, competitors
- `recitation/Architecture.md` — Technical architecture + metrics
- `recitation/CLAUDE.md` — Dev guidelines (error detection philosophy)
- `reader/TECHNICAL_SPEC.md` — Full iPad app spec (not yet built)
