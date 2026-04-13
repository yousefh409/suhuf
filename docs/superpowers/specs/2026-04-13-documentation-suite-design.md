# Suhoof Documentation Suite -- Design Spec

## Goal

Produce 9 reference docs covering every major system in the Suhoof project. Each doc follows a uniform style and structure, cross-references related docs, and describes the system as it exists (or as designed, for systems not yet implemented).

## Doc Style

- Direct, declarative prose. Present tense, active voice, no filler.
- Tables for structured comparisons (file maps, service lists, schema columns).
- Inline code for anything that appears in source (`paths`, `functions`, `env vars`, `columns`).
- Mermaid diagrams inline for flows and relationships.
- **Bold** for key terms on first use.
- Double hyphens (`--`) instead of em dashes.
- Each doc opens with a 2-4 sentence overview, then H2/H3 sections that are self-contained enough to skim.
- Every doc ends with a **Key Files** table linking back to source and a **Gotchas** section capturing non-obvious traps.
- Cross-references link to related docs so nothing is orphaned.
- Docs describe what exists now -- no TODOs, no aspirational content, no auto-generated API dumps.
- For systems that exist only as designs (reader app, ingestion pipeline, agents), write declarative descriptions of the architecture. Do not use aspirational language ("we plan to", "will eventually"). Describe the design as fact.

---

## File Structure

```
docs/
  recitation/
    system.md
  reader/
    app.md
    book-format.md
    ingestion-pipeline.md
  agents/
    irab.md
    translation.md
  testing/
    reader-app.md
    irab-agents.md
    recitation-system.md
```

---

## Doc 1: `docs/recitation/system.md` -- Recitation System

### Overview (2-4 sentences)

Live Arabic readalong assessment system. Listens to a student read diacritized Arabic text aloud and flags errors in real time -- wrong words, wrong i'rab (case endings), wrong tashkeel (internal vowels). Uses a dual-model architecture: Whisper for position tracking, XLS-R CTC for error scoring. Conservative philosophy: false negatives are always preferable to false positives.

### Sections

**Architecture**
- Mermaid diagram: audio in --> Whisper (position tracking) + CTC (error scoring) --> classification rules --> WebSocket response
- Why two models: Whisper recognizes words well but has no diacritic tokens; CTC has 58 diacritized character tokens but unreliable greedy decode for position tracking
- CPU-only execution (MPS produces incorrect results for wav2vec2)

**Models**
- XLS-R CTC v5: Wav2Vec2ForCTC, 300M params, fine-tuned, 58 Arabic character tokens (consonants + all diacritics), 16kHz input, loaded from `models/ssl_xls_r_v5/`
- Whisper Small: 244M params, lazy-loaded on first streaming use, auto-downloads ~500MB, uses direct model API (not `pipeline()`)

**Streaming Pipeline**
- StreamingSession lifecycle: one instance per WebSocket connection
- State: `audio_ring` (8s sliding window), `cursor_phrase`, `scored_words`, `_best_spoken` (high-water mark), `_cached_whisper_words`
- `score_cycle(final=False)` -- the main loop, called every ~0.5-0.75s:
  - Phase 1: Position tracking (Whisper) -- transcribe last 5s, match against phrase candidates, count spoken words
  - Phase 2: CTC scoring -- log-probability matrix, Viterbi alignment, per-word assessment signals
  - Phase 3: Cursor advance -- +1 cap per cycle, guard check (best_idx == cursor_phrase)
- Mermaid sequence diagram showing the three phases
- Key mechanisms preventing cursor problems: 5s Whisper window, lookbehind candidates, +1 cap, best_idx guard, high-water mark

**Error Detection**
- Six detection signals table (S0 wrong word, S-1 skipped, S1 CTC i'rab, S2 CTC tashkeel, S3 per-char, S4+ shadda/greedy variants)
- Dual thresholds table: streaming (conservative) vs batch (tight) -- with actual threshold values
- Classification priority: first match wins
- Sukoon always acceptable (pausal/waqf form)
- Score locking: after 3 consistent cycles, word assessment locks

**Arabic Text Utilities** (`arabic.py`)
- Functions: `strip_diacritics`, `get_final_diacritic`, `replace_final_diacritic`, `make_sukoon_variant`, `generate_i3rab_alternatives`, `generate_tashkeel_alternatives`
- Unicode ordering note: consonant + vowel + shadda (not consonant + shadda + vowel)
- Tashkeel alternatives skip shadda'd consonants (CTC can't distinguish vowel quality through gemination)

**API Reference**
- REST endpoints table: `GET /`, `GET /record`, `GET /api/passages`, `POST /api/score`, `POST /api/save`, `GET /api/recordings`
- WebSocket protocol (`WS /ws/score`):
  1. Client sends JSON: `{"passage_id": "ajrumiyyah", "debug": true}`
  2. Client streams raw PCM float32 @ 16kHz as binary frames
  3. Server responds with JSON: `{"words": [...], "matched_phrase_idx": N}`
  4. Client sends text `"done"` --> server runs final scoring with batch thresholds
  5. Server responds with `{"words": [...], "final": true}`
- Per-word response format: idx, word, status, error_type, error_detail, debug signals

**Frontend** (`static/index.html`)
- Single-file HTML/CSS/JS (~600 lines)
- Audio capture via AudioWorklet (ScriptProcessorNode fallback)
- Color coding: green = correct, red = wrong word, blue = i'rab error, orange = tashkeel error
- Debug overlay on word tap (effective score, deltas, greedy decode)
- "Done" button triggers final scoring

**Current Metrics**
- Batch (evaluate.py, 78 recordings): 1.8% FP rate (12/652 words), 76% detection
- Streaming (test_streaming.py, 9/9 pass): 0% FP on correct, 1.2s to first scored response, no flicker

**Key Files**
| Path | Purpose |
|------|---------|
| `recitation/engine.py` | Core: both models, scoring logic, StreamingSession |
| `recitation/server.py` | FastAPI server: REST + WebSocket, error classification |
| `recitation/arabic.py` | Arabic text utilities: diacritics, alternatives |
| `recitation/passage.json` | 3 diacritized passages (ajrumiyyah, daa-dawa, ihya) |
| `recitation/models/ssl_xls_r_v5/` | Fine-tuned XLS-R 300M CTC model |
| `recitation/static/index.html` | Live readalong UI |
| `recitation/static/record.html` | Test data recorder |
| `recitation/Architecture.md` | Detailed technical architecture |
| `recitation/CLAUDE.md` | Project conventions and philosophy |

**Gotchas**
- Do not use MPS for wav2vec2 -- produces incorrect results on Apple Silicon. Force CPU.
- Do not use `pipeline("automatic-speech-recognition")` for Whisper -- imports `torchcodec` which has FFmpeg version conflicts. Use `WhisperForConditionalGeneration` + `WhisperProcessor` directly.
- Do not use exact word matching for phrase coverage -- Whisper garbles Arabic words. Fuzzy matching with `_word_match` (LCS > 0.6) is required.
- Cursor jumps > 1 must be prevented -- common Arabic words appear across many phrases.
- Test recordings have small imperfections (background noise, slight mispronunciations not noted). Treat as real-world data, not lab-perfect ground truth.

**Cross-references**: [Testing Recitation System](../testing/recitation-system.md), [Reader App](../reader/app.md) (recitation integration)

---

## Doc 2: `docs/reader/book-format.md` -- Book Format

### Overview (2-4 sentences)

Arabic text flows through multiple format stages: from OpenITI mARkdown source files, through ingestion transforms, into Supabase Postgres storage, and finally into local SQLite on the reader device. Each stage serves a different purpose -- source preservation, processing, cloud storage, and offline reading. The recitation engine uses a separate `passage.json` format for its test passages.

### Sections

**Format Lifecycle**
- Mermaid diagram: OpenITI mARkdown --> parse --> tashkeel --> annotate --> Supabase Postgres --> local SQLite mirror
- Separate path: `passage.json` (recitation engine only, hand-curated passages)

**Source Format: OpenITI mARkdown**
- What mARkdown is: a plain-text markup format used by the OpenITI project for digitized Arabic texts
- Structural tags: headers (levels map to chapter hierarchy), page breaks, poetry hemistichs
- How structural tags map to the books/pages/chapters schema
- What gets stripped vs preserved during parsing

**Recitation Format: `passage.json`**
- Structure: `{"passages": [{"id", "title", "text", "phrases", "source"}]}`
- 3 passages: ajrumiyyah (18 phrases), daa-dawa (14 phrases), ihya (44 phrases)
- Phrase segmentation: pre-segmented for streaming position tracking
- Used by the recitation engine only -- not part of the reader app book pipeline

**Storage Format: Supabase Schema**
- `books` table: id, openiti_id (unique), title, author, category, total_pages, has_tashkeel
- `pages` table: id, book_id, page_number, volume, content, content_hash. Unique on (book_id, volume, page_number)
- `chapters` table: id, book_id, title, level (1=chapter, 2=section, 3=subsection), page_id, parent_id, sort_order
- `annotations` table: id, book_id, page_id, start_offset, end_offset, type, metadata_json
- Page `content` format: paragraphs separated by `\n\n`, poetry hemistichs separated by `\t`, all mARkdown tags stripped
- `content_hash`: stored per page for detecting changes and re-anchoring user annotations

**Local Format: SQLite Mirror**
- Mirrors Supabase schema for book data (books, pages, chapters, annotations)
- Extra fields: `downloaded_at` on books
- User data tables are local-first with `synced` flag (0 = needs sync, 1 = synced)

**Annotation Types**
| Type | Rendering | Metadata Fields |
|------|-----------|----------------|
| hadith | Card with save button | hadith_number, source_book, grade |
| isnad | Smaller, muted text | narrators[] |
| matn | Prominent, larger | -- |
| quran | Special font, ornamental frame | surah, ayah |
| poetry | Centered, hemistich layout | meter, poet |
| biography | Collapsible section | person_name, birth_ah, death_ah |

**I'rab Cache Schema**
- `irab_cache` table: id, word, sentence_hash, model_version, result_json
- Unique on (word, sentence_hash, model_version)
- Global -- shared across all users
- Local SQLite mirrors the global cache + stores user's own lookups

**User Data Schema**
- `user_bookmarks`: id, user_id, book_id, page_id, start/end_offset, label, anchor_context, timestamps, deleted_at
- `user_highlights`: same pattern + color, note
- `user_notes`: anchor_offset, content
- `user_reading_positions`: (user_id, book_id) PK, page_id, scroll_offset
- `user_pencil_strokes`: drawing_data (BYTEA), viewport_json
- Tombstone pattern: `deleted_at` for soft deletes, synced to other devices, purged after 90 days
- `anchor_context`: ~30 chars of surrounding text for re-anchoring if content changes on re-ingestion

**Key Files**
| Path | Purpose |
|------|---------|
| `recitation/passage.json` | Recitation engine passages (3 texts, phrase-segmented) |
| `reader/TECHNICAL_SPEC.md` | Full schema DDL (lines 47-195) |

**Gotchas**
- Arabic diacritic Unicode ordering: consonant + vowel + shadda (not consonant + shadda + vowel). Code that manipulates diacritized text must respect this order.
- `content_hash` is critical for re-anchoring user annotations (bookmarks, highlights, notes) after a book is re-ingested with content changes. Without it, character offsets drift.
- Tombstone purge after 90 days means devices offline for > 90 days may not receive delete signals. Acceptable for V1.
- `passage.json` and the reader book format are entirely separate pipelines. They share no schema.

**Cross-references**: [Ingestion Pipeline](ingestion-pipeline.md), [I'irab Agents](../agents/irab.md), [Reader App](app.md)

---

## Doc 3: `docs/reader/ingestion-pipeline.md` -- Ingestion Pipeline

### Overview (2-4 sentences)

A local Node.js script that transforms OpenITI mARkdown source files into structured, diacritized, annotated book data in Supabase Postgres. Runs manually per book. Four stages: parse structure, add tashkeel, AI-annotate semantic boundaries, upload to Supabase.

### Sections

**Pipeline Flow**
- Mermaid diagram: `ingest.ts` orchestrator --> parse.ts --> tashkeel.ts --> annotate.ts --> upload.ts
- All stages run in sequence (each depends on previous output)

**Stage 1: Parse** (`parse.ts`)
- Input: path to an OpenITI mARkdown file
- Output: pages array (page_number, volume, content) + chapters tree (title, level, page reference, sort_order)
- How mARkdown structural tags map to schema: headers --> chapters with levels, page breaks --> page boundaries
- Page content format: stripped of mARkdown tags, paragraphs as `\n\n`, poetry hemistichs as `\t`

**Stage 2: Tashkeel** (`tashkeel.ts`)
- Adds diacritical marks to unvocalized source text
- Two candidate engines:
  - Mishkal: rule-based Python, strong on classical Arabic morphology
  - Shakkala: deep learning model, stronger on modern Arabic
- Runs as a Python subprocess from the Node script
- Sets `has_tashkeel = true` on the book record

**Stage 3: Annotate** (`annotate.ts`)
- Uses Claude to identify semantic boundaries within page content
- Annotation types: hadith, isnad, matn, quran, poetry, biography
- Output: annotations array with character offsets (start_offset, end_offset) within page content + type + metadata_json
- Metadata varies by type (hadith_number, surah/ayah, poet name, etc.)

**Stage 4: Upload** (`upload.ts`)
- Pushes processed data to Supabase Postgres
- Upsert strategy: idempotent re-runs (safe to re-ingest a book)
- Generates `content_hash` per page for change detection
- Inserts into: books, pages, chapters, annotations

**Orchestrator** (`ingest.ts`)
- CLI entry point: takes path to mARkdown file
- Runs stages in order: parse --> tashkeel --> annotate --> upload
- Error handling and progress reporting per stage

**Key Files**
| Path | Purpose |
|------|---------|
| `ingestion/ingest.ts` | Orchestrator CLI |
| `ingestion/parse.ts` | mARkdown --> pages + chapters |
| `ingestion/tashkeel.ts` | Add diacritical marks |
| `ingestion/annotate.ts` | Claude semantic annotation |
| `ingestion/upload.ts` | Push to Supabase |

**Gotchas**
- Tashkeel engine choice is not finalized -- needs benchmarking on classical Arabic samples from OpenITI. Mishkal likely better for classical texts; Shakkala for modern.
- Annotation offsets are character-level within page `content` (not byte offsets, not codepoint offsets). Arabic combining characters (diacritics) count as separate characters.
- Re-ingesting a book must not break existing user annotations. The `content_hash` field enables re-anchoring, but `anchor_context` on user data is the safety net.
- The annotate stage calls Claude per page -- cost scales linearly with book size. Large books (1000+ pages) require budgeting.

**Cross-references**: [Book Format](book-format.md), [I'irab Agents](../agents/irab.md), [Reader App](app.md)

---

## Doc 4: `docs/agents/irab.md` -- I'irab Agents

### Overview (2-4 sentences)

On-demand Arabic grammar analysis powered by Claude Sonnet. A user taps a word in the reader app, and a Supabase Edge Function resolves the grammatical role (i'rab) via a three-tier cache: local SQLite, Supabase Postgres, Claude API. Over time, most lookups are instant cache hits with no API call.

### Sections

**Request Flow**
- Mermaid sequence diagram:
  1. User taps word in reader
  2. `useIrab` hook checks local `irab_cache` in SQLite
  3. On miss: calls Supabase Edge Function
  4. Edge Function checks global `irab_cache` in Postgres
  5. On miss: calls Claude Sonnet with word + surrounding sentence
  6. Stores result in global cache
  7. Returns result to app
  8. App stores in local cache
  9. Shows i'rab popover

**Three-Tier Cache**
- Tier 1: Local SQLite `irab_cache` -- instant, no network
- Tier 2: Supabase Postgres `irab_cache` -- shared across all users, fast
- Tier 3: Claude API -- cold path, ~1-2s latency
- Cache key: `(word, sentence_hash, model_version)`
- Cache is global -- one user's lookup benefits all future users

**Edge Function**
- Responsibilities in order:
  1. Verify JWT (user is authenticated)
  2. Check RevenueCat subscription (premium feature)
  3. Check global `irab_cache` in Postgres
  4. On miss: call Claude Sonnet
  5. Store result in global cache
  6. Return result
- Request format: word + surrounding sentence context
- Response format: structured i'rab analysis JSON

**Claude Prompt Design**
- Input: the target word + surrounding sentence (enough context for disambiguation)
- Output: structured JSON stored in `result_json` -- grammatical role, case ending reason, parsing breakdown
- `model_version` tracks prompt/model version for cache invalidation
- Classical Arabic grammar terminology in the output

**Cache Invalidation**
- `model_version` column (e.g., `'sonnet-1'`)
- When prompt or model changes: bump version string
- Old cache entries are ignored (unique constraint includes model_version)
- No manual purge needed -- old entries are dead weight but harmless
- Fresh lookups populate the new version entries organically

**Subscription Gating**
- I'rab analysis is a premium feature
- Edge Function checks RevenueCat entitlements before processing
- Free users: app shows a paywall prompt on word tap
- RevenueCat webhook updates subscription status in Supabase

**Key Files**
| Path | Purpose |
|------|---------|
| `reader/TECHNICAL_SPEC.md` (lines 201-222) | I'rab flow design |
| `reader/hooks/useIrab.ts` (planned) | Client-side hook |
| `reader/lib/irab-api.ts` (planned) | Edge Function caller |
| Supabase Edge Function (planned) | Server-side i'rab logic |

**Gotchas**
- `sentence_hash` must capture enough surrounding context for disambiguation. The same word (e.g., "كتاب") has different i'rab depending on its role in the sentence. Hash the full sentence, not just adjacent words.
- `model_version` must be bumped on any prompt change, or cache serves stale/incorrect results from the old prompt.
- Edge Function cold start adds ~1-2s latency on the first call after idle. Subsequent calls are fast.
- Claude's Arabic grammar analysis is not perfect -- occasional errors on rare constructions. The cache means errors persist until model_version is bumped.

**Cross-references**: [Book Format](../reader/book-format.md) (cache schema), [Reader App](../reader/app.md) (UI integration), [Testing I'irab Agents](../testing/irab-agents.md)

---

## Doc 5: `docs/agents/translation.md` -- Translation Agents

### Overview (2-4 sentences)

On-demand Arabic-to-English translation powered by Claude via Supabase Edge Function. Users request translations while reading in the reader app; results are cached globally so repeated lookups across users are instant. Follows the same three-tier cache pattern as I'irab analysis.

### Sections

**Request Flow**
- Mermaid sequence diagram: User requests translation --> local cache check --> Edge Function --> global cache check --> Claude API --> cache write --> response
- Structurally parallel to the I'irab flow

**Translation Scope**
- Granularity: per-sentence or per-paragraph chunks (not individual words -- that is I'irab territory)
- Input: Arabic text segment from the current page
- Output: English translation preserving meaning and register of classical Arabic
- Not pre-computed -- generated on demand, cached for all future users

**Edge Function**
- Same pattern as I'irab: JWT verification, subscription check, cache lookup, Claude call on miss, cache write
- Separate Edge Function from I'irab (different prompt, different cache table, different input granularity)

**Cache Design**
- Cache key: `(text_hash, model_version)`
- Separate `translation_cache` table in Supabase Postgres (parallel structure to `irab_cache`)
- Same `model_version` invalidation strategy as I'irab
- Global -- one user's translation benefits all future users

**Prompt Design**
- Faithful translation of classical Arabic prose
- Preserves register and meaning -- not paraphrase
- Handles untranslatable terms: hadith terminology, proper names, Islamic concepts (transliterate + brief gloss)
- Output format: plain English text

**Subscription Gating**
- Premium feature, same RevenueCat pattern as I'irab
- Free users see paywall on translation request

**Key Files**
| Path | Purpose |
|------|---------|
| Supabase Edge Function (planned) | Server-side translation logic |
| `translation_cache` table (planned) | Global translation cache |
| Reader hook (planned) | Client-side translation request |

**Gotchas**
- Translation granularity matters -- too small (word-level) loses context and produces poor translations; too large (page-level) is slow, expensive, and hard to cache effectively. Sentence-level is the sweet spot.
- Classical Arabic has domain-specific vocabulary (fiqh terms, hadith sciences, Sufi concepts) that generic translation mishandles. The prompt must instruct Claude to transliterate and gloss rather than force-translate.
- Cache key must use `text_hash` (hash of the actual text), not positional offset. Content may shift when a book is re-ingested.
- Unlike I'irab (which caches per-word), translation caches per-text-segment. Cache hit rate depends on users reading the same passages.

**Cross-references**: [I'irab Agents](irab.md) (shared architectural patterns), [Reader App](../reader/app.md) (UI toggle), [Book Format](../reader/book-format.md)

---

## Doc 6: `docs/reader/app.md` -- Reader App

### Overview (2-4 sentences)

iPad app for reading classical Arabic and Islamic texts. Offline-first architecture with local SQLite as the primary data store, Supabase for cloud sync and AI features. Integrates I'irab analysis, translation, and live recitation feedback. Built with Expo SDK 54, TypeScript, and Expo Router v6.

### Sections

**Architecture**
- Mermaid diagram: App <--> local SQLite (offline-first), App <--> Supabase (sync + auth), App <--> Edge Functions (I'irab, translation), App <--> GPU server (recitation WebSocket)
- Offline-first: books download fully to local SQLite. App works offline after download, except first-time I'irab/translation lookups and live recitation.

**Stack**
| Component | Technology |
|-----------|-----------|
| Framework | Expo SDK 54 |
| Language | TypeScript |
| Routing | Expo Router v6 |
| Backend | Supabase (Auth, Postgres, Edge Functions) |
| Payments | RevenueCat |
| I'rab AI | Claude Sonnet via Edge Function |
| Translation AI | Claude via Edge Function |
| Recitation | Python/FastAPI + WebSocket (GPU server) |

**Screens**
- Library (`app/index.tsx`): browse book catalog, download books, search
- Reader (`app/reader/[bookId].tsx`): read pages, tap words for I'irab, view annotations, recitation mode
- Settings (`app/settings.tsx`): font size, line height, theme, font family, account, subscription management

**Data Model**
- Local SQLite as primary store (see Book Format doc for full schema)
- Book data mirrors Supabase: books, pages, chapters, annotations
- User data is local-first: bookmarks, highlights, notes, reading positions, pencil strokes
- `synced` flag (0 = needs sync, 1 = synced) on all user data tables

**Reading Experience**
- Rendering diacritized Arabic text with proper RTL layout
- User preferences stored in `user_prefs` SQLite table:
  - Font size: 18-32px (default 22)
  - Line height: 1.8-2.2 (default 2.0)
  - Theme: light, sepia, dark (default light)
  - Font family: NotoNaskhArabic, Amiri, ScheherazadeNew (default NotoNaskhArabic)
- Annotation rendering varies by type (hadith cards, quran frames, poetry hemistich layout, etc.)

**I'irab Integration**
- `useIrab` hook: manages tap --> cache check --> Edge Function --> popover display
- `IrabPopover` component: shows grammatical analysis on word tap
- Links to agents/irab.md for the full backend flow

**Translation Integration**
- Toggle English translation below Arabic text
- On-demand via Edge Function, cached locally
- Links to agents/translation.md

**Recitation Integration**
- WebSocket connection to GPU server
- Audio capture: 16kHz PCM via AudioWorklet
- Word-by-word highlighting (green/red/blue/orange) as reader progresses
- "Done" button for final scoring with batch thresholds
- Premium feature gated by RevenueCat
- Links to recitation/system.md for the full backend flow

**Sync Strategy**
| Data | Direction | Trigger |
|------|-----------|---------|
| Book catalog | Supabase --> local | On app open |
| Book download | Supabase --> local | User taps "Download" |
| Reading position | Local --> Supabase | Debounced, on page change |
| Bookmarks/highlights/notes | Bidirectional | On change (local), on app open (pull remote) |
| Pencil strokes | Local --> Supabase | Background sync (large blobs) |
| I'rab cache | Edge Fn --> local | On each lookup |

- Conflict resolution: last-write-wins based on `updated_at` timestamp
- Deletes: soft-delete via `deleted_at` tombstone, synced to other devices, purged after 90 days

**Monetization**
- Free tier: read all books, browse, download, search, bookmark
- Premium (RevenueCat subscription): unlimited I'irab analysis, AI annotations, translation, cloud sync, Apple Pencil annotations
- Integration flow: App <--> RevenueCat SDK (purchase, restore, entitlements) --> webhook --> Supabase (subscription status) --> Edge Functions (gate premium features)

**Folder Structure**
```
reader/
  app/                          # Expo Router screens
    _layout.tsx
    index.tsx                   # Library
    reader/[bookId].tsx         # Reader
    settings.tsx                # Prefs, account, subscription
  components/
    arabic/
      TappableText.tsx
      IrabPopover.tsx
      PageView.tsx
      AnnotatedSegment.tsx      # Renders hadith/quran/poetry differently
    library/
      BookCard.tsx
  hooks/
    useIrab.ts
    useReadingPosition.ts
    useBookPages.ts
    useAnnotations.ts
    useUserPrefs.ts
    useSync.ts                  # Bidirectional Supabase sync
  lib/
    db.ts                       # Local SQLite
    supabase.ts                 # Supabase client
    irab-api.ts                 # Edge Function caller
    arabic.ts
    download.ts                 # Book download + local storage
    constants.ts
  types/
    book.ts
    irab.ts
    annotations.ts
```

**Key Files**
| Path | Purpose |
|------|---------|
| `reader/TECHNICAL_SPEC.md` | Full technical specification (17KB) |

**Gotchas**
- Offline-first means local SQLite is the source of truth, not Supabase. The app must never block on network requests for core reading functionality.
- Apple Pencil strokes are serialized `PKDrawing` blobs -- potentially large. Sync in background, not on the critical path.
- `content_hash` re-anchoring is needed when books are re-ingested with content changes. User annotations reference character offsets that may drift.
- RTL layout in React Native has known quirks. Test on real devices, not just simulators.
- RevenueCat webhook delivery can lag -- Edge Functions must handle the case where subscription status is stale.

**Cross-references**: [Book Format](book-format.md), [Ingestion Pipeline](ingestion-pipeline.md), [I'irab Agents](../agents/irab.md), [Translation Agents](../agents/translation.md), [Recitation System](../recitation/system.md), [Testing Reader App](../testing/reader-app.md)

---

## Doc 7: `docs/testing/recitation-system.md` -- Testing Recitation System

### Overview (2-4 sentences)

The recitation system has three testing layers: batch evaluation on 78 real recordings, automated streaming tests via TTS + WebSocket, and a suite of diagnostic scripts for deep signal analysis. All test data is real-world recordings with intentional errors (wrong words, wrong i'rab, wrong tashkeel, pausal forms).

### Sections

**Test Architecture**
- Mermaid diagram showing three layers: batch eval (offline, CTC-only) | streaming tests (live server, Whisper+CTC) | diagnostics (signal analysis)
- Batch for regression/accuracy. Streaming for end-to-end correctness. Diagnostics for debugging specific failure modes.

**Batch Evaluation** (`evaluate.py`)
- Loads recordings from `test_data/manifest.jsonl`
- Runs CTC scoring pipeline (no Whisper -- batch mode)
- Compares results against expected errors noted in manifest
- Reports: FP rate, detection rate, per-recording breakdown
- Current: 1.8% FP (12/652 words), 76% detection (4 missed subtle sukoon/tanween)

**Test Data**
- `test_data/manifest.jsonl`: one JSON line per recording with `file`, `passage_id`, `phrase_idx`, `notes`, `timestamp`
- `test_data/recordings/`: .webm audio files
- `test_data/sessions/`: saved streaming sessions (`audio.raw` + `meta.json` + `scores.json`)
- 78 recordings: correct readings, intentional wrong words, i'rab errors, tashkeel errors, pausal forms, tanween omissions
- How to add new recordings: use `record.html` at `http://localhost:8000/record`, then add entry to manifest
- Data quality note: real-world recordings, not lab-perfect. Occasional background noise, slight mispronunciations not noted.

**Streaming Tests** (`test_streaming.py`)
- Synthesizes audio via edge-tts (TTS)
- Streams to running server via WebSocket
- Validates: position tracking, error detection, no false positives on correct readings, no flicker
- 9 test scenarios covering correct readings + various error types
- Requires running server on port 8000

**Mutation Tests** (`test_mutations.py`)
- Generates mutated versions of correct recordings to test error detection
- Mutation types: word substitution, i'rab swaps, tashkeel swaps
- Validates that mutations are detected as errors

**Tashkeel Measurement** (`measure_tashkeel.py`)
- TTS-based measurement of tashkeel detection accuracy
- Synthesizes audio with intentional tashkeel errors
- Measures detection rate per error type

**Diagnostic Scripts**
| Script | Purpose |
|--------|---------|
| `diagnostic_ctc.py` | CTC scoring signal analysis |
| `diagnostic_framescan.py` | Frame-level signal scanning |
| `diagnostic_local_pd.py` | Local phrase-differential analysis |
| `diagnostic_classifier.py` | GBM classifier signal analysis |
| `diagnostic_cv.py` | Cross-validation analysis |
| `diagnostic_rescored.py` | Windowed re-scoring analysis |
| `diagnostic_rules.py` | Classification rule analysis |
| `diagnostic_fp_fix.py` | False positive investigation |
| `analyze_misses.py` | Missed error investigation |
| `diagnose_tts.py` | TTS synthesis diagnostics |

**Threshold Tuning**
- `threshold_scan.py`: scans threshold parameter space, reports accuracy at each point
- `optimize_thresholds.py`: optimizes individual threshold values
- `optimize_rules.py`: optimizes decision tree classification rules
- Dual threshold system: streaming (conservative) vs batch (tight)
- Changes cascade -- improving one signal threshold can degrade another

**Key Files**
| Path | Purpose |
|------|---------|
| `recitation/evaluate.py` | Batch evaluation harness |
| `recitation/test_streaming.py` | Automated streaming tests |
| `recitation/test_mutations.py` | Mutation test generator |
| `recitation/measure_tashkeel.py` | Tashkeel detection measurement |
| `recitation/threshold_scan.py` | Threshold parameter scanning |
| `recitation/test_data/manifest.jsonl` | Recording metadata (78 entries) |
| `recitation/test_data/recordings/` | Audio recordings (.webm) |
| `recitation/test_data/sessions/` | Saved streaming sessions |

**Gotchas**
- Streaming tests require a running server (`python -m uvicorn server:app --port 8000`). They fail if the server is not up.
- `evaluate.py` is CTC-only -- it does not use Whisper. Streaming tests exercise both models.
- Threshold changes cascade: improving one signal's threshold can degrade detection on a different error type. Always run full evaluation after any threshold change.
- Test data has small imperfections. Do not treat manifest `notes` as perfect ground truth.
- edge-tts (used by streaming tests) requires network access to Microsoft's TTS service.

**Cross-references**: [Recitation System](../recitation/system.md)

---

## Doc 8: `docs/testing/irab-agents.md` -- Testing I'irab Agents

### Overview (2-4 sentences)

Testing strategy for the I'irab analysis system. Covers Edge Function correctness, three-tier cache behavior, Claude prompt quality evaluation, and subscription gating. Tests range from unit-level cache logic to end-to-end grammar accuracy checks.

### Sections

**Test Layers**
- Mermaid diagram: unit tests (cache logic, prompt formatting) --> integration tests (Edge Function end-to-end) --> quality tests (prompt output evaluation)

**Cache Testing**
- Local cache hit: verify lookup returns cached result without network call
- Global cache hit: verify Edge Function returns Postgres-cached result without Claude call
- Cold miss: verify full flow (Claude call, global cache write, local cache write)
- Cache key correctness: same word in different sentences produces different cache entries (sentence_hash disambiguation)
- Model version invalidation: bumping model_version causes cache miss on previously cached entries

**Edge Function Testing**
- Auth: valid JWT passes, invalid/expired JWT rejected
- Subscription: premium user gets analysis, free user gets paywall response
- Cache lookup: hit returns cached result, miss triggers Claude
- Claude API: correct prompt sent, response parsed into result_json
- Error handling: API timeout returns graceful error, malformed Claude response handled

**Prompt Quality**
- Regression test set: curated list of word+sentence pairs with known correct i'rab
- Evaluate Claude output against expected grammatical analysis
- Track accuracy over time as prompts evolve
- Requires Arabic grammar expertise to validate results

**Subscription Gating**
- Free user: receives paywall response (no i'rab data)
- Premium user: receives full analysis
- Expired subscription: handled gracefully (treated as free)
- RevenueCat webhook lag: Edge Function checks Supabase subscription status, not RevenueCat directly

**Key Files**
| Path | Purpose |
|------|---------|
| Supabase Edge Function (planned) | Server-side i'rab logic |
| Test fixtures (planned) | Word+sentence pairs with expected i'rab |

**Gotchas**
- I'rab is context-dependent. The same word has different grammatical roles in different sentences. Test fixtures must include the full sentence context, not just isolated words.
- Prompt quality testing requires Arabic grammar expertise. Automated tests can verify structure (JSON schema, required fields) but not grammatical correctness.
- Edge Function cold start adds latency on first call after idle period. Tests should account for this or warm up the function first.
- RevenueCat subscription status in Supabase can lag behind the actual subscription state. Tests should verify the Edge Function checks Supabase (not RevenueCat API directly).

**Cross-references**: [I'irab Agents](../agents/irab.md), [Testing Reader App](reader-app.md)

---

## Doc 9: `docs/testing/reader-app.md` -- Testing Reader App

### Overview (2-4 sentences)

Testing strategy for the Expo/TypeScript reader app. Covers unit tests for hooks and utilities, component tests for Arabic text rendering, integration tests for sync and download flows, and end-to-end tests on iOS Simulator. Arabic-specific testing challenges (RTL layout, diacritic rendering, font rendering) require targeted attention.

### Sections

**Test Layers**
- Mermaid diagram: unit --> component --> integration --> E2E
- Unit and component tests run in Jest. Integration and E2E tests run on iOS Simulator.

**Unit Tests**
- Hooks: `useIrab` (cache check, API call, popover state), `useSync` (push/pull logic, conflict resolution), `useBookPages` (pagination, content loading), `useReadingPosition` (debounce, persistence)
- Utilities: `arabic.ts` (diacritic handling), `db.ts` (SQLite queries, schema migrations), `download.ts` (book download, local storage)
- Framework: Jest + React Testing Library

**Component Tests**
- `TappableText`: word tap targets hit correctly, RTL layout renders properly, diacritics display above consonants
- `IrabPopover`: displays formatted grammatical analysis, handles loading/error states
- `AnnotatedSegment`: renders each annotation type correctly (hadith card, quran frame, poetry layout, etc.)
- `PageView`: scroll behavior, user preference application (font size, theme, line height)

**Integration Tests**
- Sync flow: local change --> push to Supabase --> pull on another device --> verify consistency
- Book download: browse catalog --> tap download --> verify local SQLite populated with book data
- Offline mode: disconnect network --> verify reading, bookmarking, highlighting all work
- I'rab flow: tap word --> verify cache check --> mock Edge Function --> verify popover content

**E2E Tests**
- Full user flows on iOS Simulator:
  - Browse library --> download book --> open reader --> read pages
  - Tap word --> see i'rab analysis popover
  - Create bookmark --> verify in bookmarks list
  - Change font size --> verify text re-renders
  - Recitation mode --> verify WebSocket connection and word highlighting
- MCP browser testing approach (AI-powered E2E as per recent commit)

**Arabic-Specific Testing**
- RTL layout correctness: text flows right-to-left, punctuation positioned correctly
- Diacritic rendering: harakat (vowel marks) display above/below consonants without clipping
- Font rendering: verify all four supported fonts (NotoNaskhArabic, Amiri, ScheherazadeNew) render correctly
- Long text performance: pages with 1000+ words render without lag
- Mixed-direction text: Arabic text with inline English or numbers

**Key Files**
| Path | Purpose |
|------|---------|
| Test directory (planned) | `reader/__tests__/` or `reader/tests/` |
| `reader/TECHNICAL_SPEC.md` | Component and hook specifications |

**Gotchas**
- Arabic text rendering differs between iOS Simulator and real devices. Always verify critical rendering on a physical iPad.
- RTL layout bugs are common in React Native/Expo. Flexbox `direction: 'rtl'` behaves differently than web CSS RTL.
- SQLite on iOS has behavioral differences from SQLite in Jest (different versions, different WAL behavior). Integration tests must run on simulator, not just in Jest mocks.
- Diacritic clipping is a common rendering issue -- tall diacritics (like shadda + damma) can be clipped by insufficient line height. Test with `lineHeight: 1.8` (minimum supported).
- Apple Pencil tests require a physical device or specialized simulator input. May need to be manual tests.

**Cross-references**: [Reader App](../reader/app.md), [Testing I'irab Agents](irab-agents.md), [Testing Recitation System](recitation-system.md)
