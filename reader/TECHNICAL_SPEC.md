# Suhuf Reader — Technical Spec

## Scope

This spec covers the **Reader foundation**: book ingestion, reading experience, i'rab analysis, user annotations, sync, and recitation integration. It does not yet cover the broader AI-Powered Review system or advanced note-taking workflows from the PRD — those will be separate specs when the reader foundation is stable.

---

## Stack

- **App:** Expo SDK 54, TypeScript, Expo Router v6
- **Backend:** Supabase (Auth, Postgres, Edge Functions)
- **Payments:** RevenueCat
- **I'rab:** Claude Sonnet via Supabase Edge Function
- **Book source:** OpenITI mARkdown → ingestion pipeline → Supabase
- **Tashkeel:** Open source engine (Mishkal or Shakkala) in ingestion pipeline
- **Recitation:** Python/FastAPI + WebSocket, GPU server (Whisper + XLS-R CTC models)

---

## Architecture

```
Ingestion pipeline (local Node script)    App (iPad)
──────────────────────────────────────    ──────────────────────────────
OpenITI mARkdown                          Supabase Auth (Apple Sign In)
  → parse structure (pages, chapters)     Browse book catalog
  → tashkeel engine (Mishkal/Shakkala)    Download book → local SQLite
  → AI annotate (hadith, quran, etc.)     Read offline from local SQLite
  → upload to Supabase Postgres           Tap word → Edge Fn → Claude
                                          Recitation → WebSocket → GPU server
                                          RevenueCat for subscriptions
                                          Sync user data ↔ Supabase

GPU Server (recitation)
───────────────────────
FastAPI + WebSocket
Whisper Small (500MB)  → position tracking ("where are they reading?")
XLS-R CTC v5 (300MB)  → error scoring (i'rab, tashkeel, wrong words)
Streams audio in, streams word-by-word feedback out
```

**Offline-first:** Books download fully to local SQLite. App works offline after download, except first-time i'rab lookups and live recitation.

---

## Supabase Schema

```sql
-- BOOK DATA (populated by ingestion pipeline)

books (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  openiti_id TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  author TEXT,
  category TEXT,
  total_pages INTEGER,
  has_tashkeel BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

pages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id UUID REFERENCES books(id),
  page_number INTEGER NOT NULL,
  volume INTEGER DEFAULT 1,
  content TEXT NOT NULL,          -- paragraphs separated by \n\n, poetry hemistichs by \t
  content_hash TEXT,              -- for detecting changes and re-anchoring
  UNIQUE(book_id, volume, page_number)
);

chapters (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id UUID REFERENCES books(id),
  title TEXT NOT NULL,
  level INTEGER NOT NULL,         -- 1 = chapter, 2 = section, 3 = subsection
  page_id UUID REFERENCES pages(id),
  parent_id UUID REFERENCES chapters(id),
  sort_order INTEGER NOT NULL
);

annotations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id UUID REFERENCES books(id),
  page_id UUID REFERENCES pages(id),
  start_offset INTEGER NOT NULL,  -- character offset within page content
  end_offset INTEGER NOT NULL,
  type TEXT NOT NULL,              -- hadith | isnad | matn | quran | poetry | biography
  metadata_json JSONB             -- type-specific: hadith number, surah/ayah, poet, etc.
);

-- GLOBAL I'RAB CACHE (shared across all users)

irab_cache (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  word TEXT NOT NULL,
  sentence_hash TEXT NOT NULL,
  model_version TEXT NOT NULL DEFAULT 'sonnet-1',  -- prompt/model version for cache invalidation
  result_json JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(word, sentence_hash, model_version)
);

-- USER DATA (synced from app)

user_bookmarks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id),
  book_id UUID REFERENCES books(id),
  page_id UUID REFERENCES pages(id),
  start_offset INTEGER,
  end_offset INTEGER,
  label TEXT,
  anchor_context TEXT,            -- ~30 chars for re-anchoring if content changes
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  deleted_at TIMESTAMPTZ           -- tombstone for sync (NULL = active)
);

user_highlights (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id),
  book_id UUID REFERENCES books(id),
  page_id UUID REFERENCES pages(id),
  start_offset INTEGER NOT NULL,
  end_offset INTEGER NOT NULL,
  color TEXT DEFAULT 'yellow',
  note TEXT,
  anchor_context TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  deleted_at TIMESTAMPTZ           -- tombstone for sync
);

user_notes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id),
  book_id UUID REFERENCES books(id),
  page_id UUID REFERENCES pages(id),
  anchor_offset INTEGER NOT NULL,
  content TEXT NOT NULL,
  anchor_context TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  deleted_at TIMESTAMPTZ           -- tombstone for sync
);

user_reading_positions (
  user_id UUID REFERENCES auth.users(id),
  book_id UUID REFERENCES books(id),
  page_id UUID REFERENCES pages(id),
  scroll_offset REAL DEFAULT 0,
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (user_id, book_id)
);

user_pencil_strokes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id),
  book_id UUID REFERENCES books(id),
  page_id UUID REFERENCES pages(id),
  drawing_data BYTEA NOT NULL,    -- serialized PKDrawing
  viewport_json JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Local SQLite Schema

Primary data store on device. Syncs to/from Supabase when online.

```sql
-- Downloaded book data (mirrors Supabase)
books (id TEXT PK, openiti_id, title, author, category, total_pages, downloaded_at INTEGER);
pages (id TEXT PK, book_id, page_number, volume, content, content_hash);
chapters (id TEXT PK, book_id, title, level, page_id, parent_id, sort_order);
annotations (id TEXT PK, book_id, page_id, start_offset, end_offset, type, metadata_json);

-- User data (local-first, syncs to Supabase)
bookmarks (id TEXT PK, book_id, page_id, start_offset, end_offset, label, anchor_context, created_at INTEGER, updated_at INTEGER, deleted_at INTEGER, synced INTEGER DEFAULT 0);
highlights (id TEXT PK, book_id, page_id, start_offset, end_offset, color, note, anchor_context, created_at INTEGER, updated_at INTEGER, deleted_at INTEGER, synced INTEGER DEFAULT 0);
text_notes (id TEXT PK, book_id, page_id, anchor_offset, content, anchor_context, created_at INTEGER, updated_at INTEGER, deleted_at INTEGER, synced INTEGER DEFAULT 0);
pencil_strokes (id TEXT PK, book_id, page_id, drawing_data BLOB, viewport_json TEXT, created_at INTEGER, updated_at INTEGER, synced INTEGER DEFAULT 0);
reading_positions (book_id TEXT PK, page_id TEXT, scroll_offset REAL, updated_at INTEGER);

-- I'rab cache (local copy of global cache + user's own lookups)
irab_cache (id TEXT PK, word TEXT, sentence_hash TEXT, model_version TEXT DEFAULT 'sonnet-1', result_json TEXT, UNIQUE(word, sentence_hash, model_version));

-- Preferences
user_prefs (key TEXT PK, value TEXT);
```

`synced` flag: 0 = needs sync, 1 = synced. On connectivity, push all `synced=0` rows to Supabase, then mark as synced.

---

## I'rab Flow

```
User taps word
  → check local irab_cache
  → if miss: call Supabase Edge Function
      → Edge Fn checks global irab_cache in Postgres
      → if miss: call Claude, store result in global cache
      → return result
  → store in local cache
  → show popover
```

Three-tier cache: local SQLite → Supabase Postgres → Claude API. Over time, most taps are instant with no API call.

**Edge Function responsibilities:**
1. Verify JWT (user is authenticated)
2. Check RevenueCat subscription (paid feature)
3. Check global i'rab cache
4. If cache miss: call Claude, store in global cache
5. Return result

---

## Annotation Types & Rendering

| Type | Rendering | Metadata |
|---|---|---|
| hadith | Card with save button | hadith_number, source_book, grade |
| isnad | Smaller, muted text | narrators[] |
| matn | Prominent, larger | — |
| quran | Special font, ornamental frame | surah, ayah |
| poetry | Centered, hemistich layout | meter, poet |
| biography | Collapsible section | person_name, birth_ah, death_ah |

---

## Ingestion Pipeline

Local Node.js script at `ingestion/`. Run manually to process books.

```
ingestion/
  parse.ts        — mARkdown → pages + chapters
  tashkeel.ts     — run Mishkal/Shakkala on unvocalized text
  annotate.ts     — Claude: identify hadith, quran, poetry boundaries
  upload.ts       — push processed data to Supabase
  ingest.ts       — orchestrator: parse → tashkeel → annotate → upload
```

### Page content format

After parsing, page `content` preserves minimal inline structure:
- Paragraphs separated by `\n\n`
- Poetry hemistichs separated by `\t`
- All mARkdown tags stripped (structure captured in chapters + annotations tables)
- `content_hash` stored for change detection / re-anchoring

### Tashkeel engine

**Choice: Open source (Mishkal or Shakkala)**
- Mishkal: rule-based Python, good for classical Arabic morphology
- Shakkala: deep learning, better on modern Arabic
- Need to benchmark both on a sample of OpenITI classical texts to pick
- Run as a subprocess from the Node script, or use a Python wrapper

---

## Sync Strategy

**Local-first, sync when online.**

| Data | Direction | Trigger |
|---|---|---|
| Book catalog | Supabase → local | On app open, check for new books |
| Book download | Supabase → local | User taps "Download" |
| Reading position | Local → Supabase | Debounced, on page change |
| Bookmarks/highlights/notes | Bidirectional | On change (local), on app open (pull remote) |
| Pencil strokes | Local → Supabase | Background sync (blobs can be large) |
| I'rab cache | Edge Fn → local | On each lookup |

**Conflict resolution:** Last-write-wins based on `updated_at` timestamp. Acceptable for V1 — a user won't edit the same highlight on two devices simultaneously.

**Deletes:** Soft-delete via `deleted_at` tombstone. Sync pushes tombstoned rows so other devices can remove them. Tombstones can be purged after 90 days.

---

## Monetization

**Free tier:** Read all books. Browse, download, search, bookmark.

**Premium (RevenueCat subscription):**
- Unlimited i'rab analysis (word tap → grammar breakdown)
- AI annotations (hadith detection, Quran highlighting, etc.)
- Cloud sync across devices
- Apple Pencil annotations (when available)

**Integration:**
```
App ←→ RevenueCat SDK (purchase, restore, entitlements)
              ↓ webhook
       Supabase (user subscription status flag)
              ↓ checked by
       Edge Functions (gate i'rab + premium features)
```

---

## User Preferences

Stored in local `user_prefs` table. Applied as style props at render time.

| Key | Values | Default |
|---|---|---|
| fontSize | 18, 20, 22, 24, 28, 32 | 22 |
| lineHeight | 1.8, 2.0, 2.2 | 2.0 |
| theme | light, sepia, dark | light |
| fontFamily | NotoNaskhArabic, Amiri, ScheherazadeNew | NotoNaskhArabic |

---

## Recitation Engine

Live read-aloud assessment. User reads Arabic text, app listens and highlights errors in real-time.

### How it works

```
App                              GPU Server
───                              ──────────
User reads aloud
  → capture mic audio (16kHz PCM)
  → stream via WebSocket ──────→ FastAPI receives binary frames
                                   → Whisper: "where in the text are they?"
                                   → XLS-R CTC: "did they say it correctly?"
  ← receive word feedback ◄──── JSON: word statuses (correct/wrong/i3rab error/tashkeel error)
  → highlight words on screen
  User says "done"
  ← final scored results ◄───── Batch thresholds applied, final JSON
```

### Error types detected

| Error | Example | UI |
|---|---|---|
| Correct | Said it right | Green |
| Wrong word | Different word, skipped, or added | Red strikethrough |
| I'rab error | Wrong case ending (ضمة instead of فتحة) | Blue underline |
| Tashkeel error | Wrong internal vowel | Orange underline |

### Server requirements

| Resource | Requirement |
|---|---|
| GPU | NVIDIA T4 or better, 8GB+ VRAM |
| RAM | 16GB+ |
| Models | Whisper Small (~500MB) + XLS-R CTC v5 (~300MB) |
| Latency | ~400ms per 5s audio chunk on GPU |
| Concurrency | ~2 simultaneous sessions per T4 |
| System deps | Python 3.10+, CUDA 11.8+, ffmpeg |

### Hosting options

| Option | Cost | Fits? |
|---|---|---|
| **GPU cloud (AWS g4dn.xlarge, GCP)** | ~$0.50-1.00/hr | Best for production |
| **Modal / Replicate** | Pay-per-second GPU | Good for early stage — no idle cost |
| **Self-hosted GPU** | Upfront hardware | Only if you have one |
| Serverless (Lambda) | — | No — cold start + model load too slow |
| On-device | — | No — models too large |

**Recommendation for V1:** Use Modal or Replicate (pay-per-second GPU). No idle cost, scale to zero when nobody's reading. Move to dedicated GPU instance when usage justifies it.

### Integration with the app

- App connects via WebSocket to the GPU server URL
- Auth: pass Supabase JWT in the WebSocket handshake, server verifies
- The passage text (what the user should be reading) is sent as the first message
- Audio streams as binary frames, feedback streams back as JSON
- Premium feature (gated by RevenueCat subscription)

### Existing code

The engine is already built at `../recitation/`:
- `server.py` — FastAPI + WebSocket server
- `engine.py` — position tracking + scoring logic
- `arabic.py` — Arabic text utilities
- `models/ssl_xls_r_v5/` — fine-tuned CTC model
- 78 test recordings with evaluation framework

Needs: containerization (Docker), deployment config, JWT auth middleware.

---

## Public Website

SEO-indexable public website where anyone can read books and Google can crawl/index every page.

### Stack

Next.js (SSR) → same Supabase Postgres as the app. Server-rendered HTML so Google indexes full Arabic text.

### URL structure

```
suhuf.com/                              → homepage
suhuf.com/library                       → all books (browsable, filterable)
suhuf.com/book/[openiti_id]             → book detail + TOC
suhuf.com/book/[openiti_id]/[page]      → individual page with full text
```

No custom search needed — Google indexes every page. Users find content via Google. In-app search within a book is just `WHERE content LIKE '%query%'` on local SQLite.

### SEO strategy

- Each page server-renders full Arabic text in the DOM (not client-side JS)
- `<meta>` tags with book title, author, chapter name in Arabic
- Structured data (JSON-LD) for each book: `Book` schema with author, datePublished, inLanguage
- `generateStaticParams` to pre-build high-traffic book pages, dynamic for the rest
- Sitemap generated from `books` + `pages` tables

### Translation (future ingestion pipeline step)

Sentence-by-sentence English translation, stored as `translation` column on `pages`. Toggleable in the app (show/hide English below each sentence). Enables English Google indexing. Cost: ~$2,400-6,000 one-time for full corpus with Claude Haiku/GPT-4o-mini. Not needed for V1.

### Shared data

Website reads from the exact same Supabase tables as the app. No duplication. The ingestion pipeline feeds both.

```
Ingestion pipeline → Supabase Postgres ← App (reads + writes user data)
                                       ← Website (reads book data, SSR)
```

### Conversion funnel

Website visitor reads a page → "Get the full experience on iPad" CTA → App Store link. The website is the top of the funnel, the app is the product.

---

## Folder Structure

```
reader/
  app/
    _layout.tsx
    index.tsx                    # Library
    reader/[bookId].tsx          # Reader
    settings.tsx                 # Prefs, account, subscription
  components/
    arabic/
      TappableText.tsx
      IrabPopover.tsx
      PageView.tsx
      AnnotatedSegment.tsx       # Renders hadith/quran/poetry differently
    library/
      BookCard.tsx
  hooks/
    useIrab.ts
    useReadingPosition.ts
    useBookPages.ts
    useAnnotations.ts
    useUserPrefs.ts
    useSync.ts                   # Bidirectional Supabase sync
  lib/
    db.ts                        # Local SQLite
    supabase.ts                  # Supabase client
    irab-api.ts                  # Edge Function caller
    arabic.ts
    download.ts                  # Book download + local storage
    constants.ts
  types/
    book.ts
    irab.ts
    annotations.ts

ingestion/
  parse.ts
  tashkeel.ts
  annotate.ts
  upload.ts
  ingest.ts
```
