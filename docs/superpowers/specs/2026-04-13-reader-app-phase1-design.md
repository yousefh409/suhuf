# Reader App Phase 1: Reading + Word Analysis

## Overview

Expo (TypeScript) iPad + iPhone app that downloads books from Supabase to local SQLite for offline reading. Users browse a library, read paginated Arabic text, and tap words for AI-powered grammar analysis, translation, and conversational chat via Supabase Edge Functions calling Claude Sonnet. Results cached locally in SQLite.

**Not in scope**: authentication, payments, onboarding flow, recitation, bidirectional sync, CAMeL Tools pre-computation, Supabase global i'rab cache, ingestion pipeline (developed separately).

## System Architecture

```
┌─────────────────────────────────────┐
│         Expo App (TypeScript)        │
│  Expo Router v6 · iPad + iPhone      │
├─────────────────────────────────────┤
│         Local SQLite                 │
│  Downloaded books · I'rab cache      │
├─────────────────────────────────────┤
│         Supabase                     │
│  Book catalog (already populated)    │
│  Edge Functions: i'rab / translate   │
│  / ask-ai (-> Claude Sonnet)         │
└─────────────────────────────────────┘
```

### Data Flow

1. App launches, fetches book catalog from Supabase, displays Library.
2. User taps a book. All pages download to local SQLite. Reading works offline from there.
3. User taps a word. App checks local SQLite i'rab cache. On miss, calls Supabase Edge Function which calls Claude Sonnet. Result cached locally.
4. No user accounts. No sync. No premium gating.

### Deliverables

- Expo app (all screens from Paper designs, pixel-faithful)
- 3 Supabase Edge Functions (i'rab, translate, ask-ai)
- Local SQLite schema + download/cache logic

## Navigation & Screen Map

```
Stack Navigator (Expo Router)
├── / (Library Main)
│   ├── /discover (Library Discover)
│   ├── /book/[id] (Reading Session)
│   │   └── Word Detail (bottom sheet overlay)
│   │       ├── Translation tab
│   │       ├── I'rab tab
│   │       └── Ask AI tab
│   ├── /profile (Profile -- read-only stats, no auth actions)
│   └── /settings (Settings)
```

Pure stack navigation. No tab bar. Library Main is the home screen.

## Screen Details

All screens are pixel-faithful reproductions of the Paper designs.

### Library Main

- **Header**: "Library" title (left), search icon + generic profile avatar (right)
- **Stats row**: 4 cards -- pages today, words learned this week, streak days, time read. All local-only data from SQLite.
- **Continue Reading**: Up to 3 book cards with cover thumbnail, title, author, category tags, progress bar + percentage. "Resume" button on the most recent.
- **Filtered tabs**: "In Progress", "Saved", "Completed" -- horizontal scroll of book cards below each tab.
- **"Full Library" button**: Navigates to Discover.
- **Recommended for You**: Grid of book cards (smaller thumbnails, no progress bars). Without auth, shows curated/popular books from Supabase rather than personalized recommendations.

### Library Discover

- **Header**: Back chevron + "Library", centered "Discover" title.
- **Search bar**: Full-width text input.
- **Category pills**: Nahw, Sarf, Hadith, Fiqh, Tafseer, Aqeedah, Balagha, Lugha, Sirah. Horizontal scroll with counts. Active state on selection.
- **Book grid**: 5 columns on iPad, responsive on iPhone. Cover cards with Arabic title, English name, author, level.
- **Sort button**: Top right of search bar.

### Reading Session

- **Header**: Back chevron + "Library", book title + chapter name (center), bookmark icon + settings icon (right).
- **Page content**: RTL Arabic text, paginated via horizontal FlatList with snap. Diacritized text at top section (larger, styled differently). Regular body text below.
- **Footer**: Page number ("3 / 14"), "Tashkeel" toggle button (shows/hides diacritics).
- **Word selection**: Tap a word to see an inline popup with "Grammar", "Translate", and copy icon. Tapping Grammar or Translate opens the Word Detail bottom sheet.

### Word Detail (bottom sheet)

Presented as a draggable bottom sheet overlay on the Reading Session.

**Translation tab**:
- Word header: Arabic word (large) + English meaning
- Tags row: dictionary definitions, grammatical labels
- "In this sentence" explanation card
- Related words from same root (4-6 entries)

**I'rab tab**:
- Word header: Arabic word (large) + English meaning
- Tags row: grammatical role, case
- "Why is it [case] here?" button that expands an explanation card with the grammar rule, examples, and case marker explanation

**Ask AI tab**:
- Suggested question buttons at top (contextual, e.g., "Why is it majrur here?")
- Chat message history
- Text input at bottom with send button
- AI responses include inline Arabic with grammar explanations

**Loading state**: Skeleton placeholders while waiting for Claude response.

**Error state**: Retry button if the Edge Function call fails.

### Settings

- Font size slider
- Arabic font picker (Amiri, Scheherazade New, Noto Naskh Arabic, others from Paper designs)
- AI assistant language (English / Arabic)
- Grammar detail level
- Notifications toggle
- Data & privacy section

### Profile

- Generic avatar (no auth)
- Local-only stats: hours read, books active, completed, words learned
- Read-only -- no subscription, account, or sign-out sections without auth

## Data Model

### Supabase Tables (pre-existing, populated by ingestion pipeline)

- `books` -- id, title_ar, title_en, author_ar, author_en, category, level, cover_url, page_count, content_hash
- `pages` -- id, book_id, page_number, blocks (JSON array of typed blocks with word tokens)
- `chapters` -- id, book_id, title, start_page

### Local SQLite Tables (created by the app)

```sql
-- Mirror of Supabase for downloaded books
CREATE TABLE books (
  id TEXT PRIMARY KEY,
  title_ar TEXT NOT NULL,
  title_en TEXT NOT NULL,
  author_ar TEXT,
  author_en TEXT,
  category TEXT,
  level TEXT,
  cover_url TEXT,
  page_count INTEGER,
  content_hash TEXT,
  downloaded_at TEXT,
  last_read_page INTEGER DEFAULT 1
);

CREATE TABLE pages (
  id TEXT PRIMARY KEY,
  book_id TEXT NOT NULL REFERENCES books(id),
  page_number INTEGER NOT NULL,
  blocks TEXT NOT NULL -- JSON array
);

CREATE TABLE chapters (
  id TEXT PRIMARY KEY,
  book_id TEXT NOT NULL REFERENCES books(id),
  title TEXT NOT NULL,
  start_page INTEGER NOT NULL
);

-- User data (local only, no sync)
CREATE TABLE reading_progress (
  book_id TEXT PRIMARY KEY REFERENCES books(id),
  current_page INTEGER NOT NULL,
  total_time_seconds INTEGER DEFAULT 0,
  pages_read_today INTEGER DEFAULT 0,
  last_opened TEXT
);

CREATE TABLE bookmarks (
  id TEXT PRIMARY KEY,
  book_id TEXT NOT NULL REFERENCES books(id),
  page_number INTEGER NOT NULL,
  token_id TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE highlights (
  id TEXT PRIMARY KEY,
  book_id TEXT NOT NULL REFERENCES books(id),
  token_id_start TEXT NOT NULL,
  token_id_end TEXT NOT NULL,
  color TEXT DEFAULT 'yellow',
  created_at TEXT NOT NULL
);

CREATE TABLE notes (
  id TEXT PRIMARY KEY,
  book_id TEXT NOT NULL REFERENCES books(id),
  token_id TEXT NOT NULL,
  text TEXT NOT NULL,
  created_at TEXT NOT NULL
);

-- AI response caches
CREATE TABLE irab_cache (
  word TEXT NOT NULL,
  sentence_hash TEXT NOT NULL,
  model_version TEXT NOT NULL,
  result_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (word, sentence_hash, model_version)
);

CREATE TABLE translation_cache (
  text_hash TEXT NOT NULL,
  model_version TEXT NOT NULL,
  result_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (text_hash, model_version)
);

-- Local stats
CREATE TABLE stats (
  date TEXT PRIMARY KEY,
  pages_read INTEGER DEFAULT 0,
  words_learned INTEGER DEFAULT 0,
  time_seconds INTEGER DEFAULT 0
);
```

## Edge Functions

### `irab`

**Input**:
```json
{
  "word": "طَرِيقٍ",
  "sentence": "بِكُلِّ طَرِيقٍ فَمَا يَزْدَادُ إِلَّا تَوَقُّدًا",
  "position": 1
}
```

**Claude prompt strategy**: Send the full sentence with the target word marked. Request structured JSON with: part of speech, grammatical role, case, case marker, why-this-case explanation, dictionary meaning.

**Output**:
```json
{
  "pos": "noun",
  "role": "mudaf_ilayh",
  "role_ar": "مضاف إليه",
  "case": "majrur",
  "case_ar": "مجرور",
  "marker": "tanween_kasra",
  "marker_ar": "تنوين كسر",
  "why": "طَرِيقٍ is مجرور because it's the مضاف إليه in an إضافة with كُلّ.",
  "meaning": "path, road, way, method"
}
```

**Cache key**: `(word, sentence_hash, model_version)`

### `translate`

**Input**:
```json
{
  "sentence": "بِكُلِّ طَرِيقٍ فَمَا يَزْدَادُ إِلَّا تَوَقُّدًا"
}
```

**Output**:
```json
{
  "translation": "By every path, it only increases in intensity",
  "related_words": [
    { "word": "طَرِيق", "root": "ط ر ق", "meaning": "path, road" },
    { "word": "طَرَقَ", "root": "ط ر ق", "meaning": "to knock, to come at night" },
    { "word": "مُطْرِق", "root": "ط ر ق", "meaning": "looking down, bowing the head" },
    { "word": "طَرِيقَة", "root": "ط ر ق", "meaning": "method, way, manner" }
  ]
}
```

**Cache key**: `(text_hash, model_version)`

### `ask-ai`

**Input**:
```json
{
  "word": "طَرِيقٍ",
  "sentence": "بِكُلِّ طَرِيقٍ فَمَا يَزْدَادُ إِلَّا تَوَقُّدًا",
  "question": "Why is it مجرور here?",
  "history": []
}
```

**Output**: Streaming text response. Supports conversational follow-ups via the `history` array.

**No caching** -- questions are unique and conversational.

## Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Framework | Expo SDK 54, TypeScript | Specified in technical spec |
| Router | Expo Router v6 | File-based routing, specified in spec |
| State management | Zustand | Lightweight, no boilerplate, good for offline state |
| SQLite | `expo-sqlite` | Built into Expo SDK 54, no native module issues |
| Bottom sheet | `@gorhom/bottom-sheet` | Industry standard, snap points, gesture handling |
| Arabic text | Custom `ArabicText` component | Handles RTL, diacritics, word-level tap targets |
| Pagination | Horizontal `FlatList` with snap | Paginated reading per designs |
| Image loading | `expo-image` | Fast, caching built in |
| Fonts | `expo-font` + Google Fonts | Amiri, Scheherazade New, Noto Naskh Arabic |
| HTTP | Supabase JS client | Direct connection to existing Supabase project |

## Fonts

From the Paper designs, the app uses:
- **Noto Naskh Arabic** -- Primary Arabic body text
- **Amiri** -- Alternative Arabic font option
- **Scheherazade New** -- Alternative Arabic font option
- **DM Sans** -- UI text (English labels, buttons, navigation)

## Color Palette

Extracted from Paper designs:
- **Background**: warm off-white (#F5F0EB or similar)
- **Cards**: white with subtle warm border
- **Primary accent**: dark brown/olive (#3D3526 or similar) for buttons and headers
- **Secondary accent**: gold/amber (#B8860B or similar) for highlights and active states
- **Text primary**: near-black, warm
- **Text secondary**: muted warm gray
- **Progress bars**: amber/gold
- **Book covers**: various muted earth tones (browns, olives, dark teals)

Exact values will be extracted from Paper using `get_computed_styles` during implementation.

## Key Gotchas

- **Arabic text rendering differs between simulator and real device.** Diacritic clipping and RTL layout bugs are common in React Native. Test on real iPad early.
- **Unicode normalization matters.** Arabic diacritic ordering (consonant + vowel + shadda) must use NFC normalization before hashing for cache keys.
- **Token IDs are deterministic**: `p{page}_b{block_index}_w{word_index}`. User data (bookmarks, highlights, notes) anchors to these, not character offsets.
- **Clitics stay attached**: Whitespace-only tokenization. "والكتاب" is one token, not three.
- **`sentence_hash` must capture the full sentence**: Same word in different sentences needs different cache entries because grammar is context-dependent.
- **`model_version` bump invalidates cache**: Any Claude prompt change requires a version bump.

## Future Phases

Phase 2 and beyond (separate spec cycles):
- Authentication (Apple Sign In + Supabase Auth)
- Onboarding flow (4 steps from designs)
- Subscription / paywall (RevenueCat)
- Three-tier i'rab cache (local -> Supabase global -> Claude)
- Bidirectional sync
- Recitation integration
- CAMeL Tools morphological pre-computation
- Search (within book and across library)
