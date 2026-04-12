# Suhoof (i3rab)

AI-powered Arabic recitation assessment — live error detection for diacritized text.

## Tech Stack

- **Backend**: Python 3.10+, FastAPI, Uvicorn, PyTorch, HuggingFace Transformers
- **ML Models**: XLS-R 300M CTC (fine-tuned), Whisper small (position tracking), GBM classifiers
- **Audio**: ffmpeg (webm → PCM float32 @ 16kHz)
- **Frontend**: Static HTML + WebSocket client (served by FastAPI)
- **Planned**: Expo/TypeScript iPad app, Supabase backend, RevenueCat

## Quick Start

```bash
cd recitation
python -m uvicorn server:app --host 0.0.0.0 --port 8000
# Open http://localhost:8000
```

## Project Structure

| Path | Purpose |
|------|---------|
| `recitation/engine.py` | Core CTC engine, alignment, streaming session |
| `recitation/server.py` | FastAPI app, endpoints, classification rules |
| `recitation/arabic.py` | Unicode diacritic utilities |
| `recitation/scorer.py` | MixGoP GMM diacritic scoring |
| `recitation/passage.json` | Diacritized passages (Ajrumiyyah, Daa-Dawa, Ihya) |
| `recitation/models/` | ML models (~14GB, gitignored) |
| `recitation/test_data/` | 78 recordings + manifest + sessions |
| `recitation/static/` | Browser UI (index.html, record.html) |
| `reader/` | iPad app (spec only, not built yet) |
| `.gsd/` | Project docs (PROJECT.md, RUNTIME.md, KNOWLEDGE.md) |

## Testing

```bash
cd recitation
python evaluate.py            # Batch eval on 78 recordings (FP rate + detection)
python test_streaming.py      # Streaming tests via TTS + WebSocket (needs running server)
python test_mutations.py      # Mutation testing for error detection
python measure_tashkeel.py    # TTS-based tashkeel measurement
```

No formal test framework — uses script-based evaluation with printed results.

## Conventions

- **Files**: `snake_case.py`
- **Classes**: `PascalCase`
- **Functions**: `snake_case`, `_private_leading_underscore`
- **Constants**: `UPPER_CASE`
- **Signal keys**: short abbreviations (`eff`, `sf`, `pc`, `mg`, `pd_i3rab`, `tash_delta`)

## Grounding Rules

1. **Read `recitation/CLAUDE.md`** for error detection philosophy and domain context
2. **Read `recitation/Architecture.md`** for technical details and current metrics
3. **False negatives > false positives** — never flag correct readings as wrong
4. **Sukoon is always acceptable** — pausal form on final letter
5. **Test against real recordings** before claiming any scoring change works
6. **Don't look at git history** — previous implementation was deleted, only XLS-R v5 model carried over

## Documentation

| Doc | Path | Purpose |
|-----|------|---------|
| Product spec | `PRD.md` | Core features and user stories |
| Go-to-market | `GTM.md` | 4-phase launch plan |
| Market analysis | `Market-Analysis.md` | TAM/SAM, competitors |
| Architecture | `recitation/Architecture.md` | Scoring signals, thresholds, metrics |
| Dev guidelines | `recitation/CLAUDE.md` | Error detection philosophy, edge cases |
| Experiments | `recitation/experiments.md` | Baseline metrics and iteration log |
| Reader spec | `reader/TECHNICAL_SPEC.md` | iPad app architecture (planned) |
| Project overview | `.gsd/PROJECT.md` | Architecture and data flow |
| Runtime context | `.gsd/RUNTIME.md` | Endpoints, startup, performance |
| Conventions | `.gsd/KNOWLEDGE.md` | Naming, patterns, domain knowledge |

## Pipeline Commands

- `/pipeline-init` — Initialize pipeline infrastructure (this setup)
- `/pipeline-build` — Build and validate
- `/pipeline-qa` — QA testing
- `/pipeline-doc-update` — Update documentation
- `/pipeline-test-setup` — Configure test strategy
