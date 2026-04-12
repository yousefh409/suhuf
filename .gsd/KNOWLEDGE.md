# Knowledge

## Naming

- Files: `snake_case.py` (e.g. `train_type_classifier.py`, `diagnostic_rules.py`)
- Classes: `PascalCase` (e.g. `RecitationEngine`, `StreamingSession`, `MixGoPScorer`)
- Functions: `snake_case` with `_leading_underscore` for private (e.g. `_lcs_ratio`, `_word_match`)
- Constants: `UPPER_CASE` (e.g. `FATHA`, `SAMPLE_RATE`, `FRAME_STRIDE`)
- Signal keys: short abbreviations (`eff`, `sf`, `pc`, `mg`, `pd_i3rab`, `tash_delta`, `gfm`, `gdm`)

## Testing

- **No formal test framework** — uses script-based validation with print output
- Batch eval: `evaluate.py` runs 78 recordings from `test_data/manifest.jsonl`
- Streaming: `test_streaming.py` uses TTS audio + WebSocket (requires running server)
- Mutations: `test_mutations.py` scores real audio against mutated reference text
- Diagnostics: 14+ `diagnostic_*.py` scripts for root cause analysis and threshold tuning
- Test data: `.webm` recordings with JSONL manifest, session dirs with `audio.raw` + `meta.json` + `scores.json`

## Error Detection Philosophy

- **False negatives > false positives** — better to miss an error than wrongly flag correct reading
- Conservative streaming thresholds, relaxed batch thresholds for final scoring
- Sukoon (pausal form) always acceptable: `effective_score = max(expected, sukoon_variant)`
- Signal priority ordering: first match wins (S0 through S6)
- GBM classifier only as fallback at low eff (< -1.5) where hand-tuned rules fail

## Patterns

- **Singleton engine**: `RecitationEngine` loaded once at startup, shared across requests (`server.py:176`)
- **Lazy loading**: Whisper downloaded on first WebSocket, GBM classifiers loaded on first call
- **Ring buffer**: 8s bounded audio window per streaming session prevents memory growth
- **High-water mark**: `StreamingSession._best_spoken` remembers word progress when old audio leaves buffer
- **Score locking**: After 3 consistent cycles, word states lock to prevent late-audio degradation
- **Dual thresholds**: Every signal has batch vs streaming threshold variants
- **Arabic fuzzy matching**: Short words (1-3 chars) require exact match, longer words use LCS > 60%
- **Module constants**: Diacritic Unicode values as frozensets for efficient membership tests (`arabic.py`)

## Error Handling

- Minimal try-except, only for optional model loading
- Guard clauses for invalid input (empty audio, missing passage)
- Graceful fallback: if Whisper match poor, don't trust output
- Sentinel pattern: `_error_classifier = None` (not loaded) vs `False` (tried, doesn't exist)
- RuntimeError for ffmpeg failures with stderr context

## Logging

- `print()` only — no logging library
- Development/research code style; verbose output during model loading and scoring

## Git

- Informal commit messages (lowercase, minimal descriptions)
- Single branch: `main`
- Large files excluded via `.gitignore` (models, recordings, TTS cache, venv)

## Arabic Domain

- **i3rab** (إعراب): Case endings — raf3 (damma), nasb (fatha), jarr (kasra), tanween, sukoon
- **tashkeel** (تشكيل): Internal vowels on non-final consonants
- **shadda** (شدة): Gemination marker
- Diacritics: `\u064E` fatha, `\u064F` damma, `\u0650` kasra, `\u0652` sukoon, `\u0651` shadda
- Passages: Classical texts (Ajrumiyyah, Daa-Dawa, Ihya) with phrase-level breakdown
