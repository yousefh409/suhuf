-- Full Suhuf schema: authors, books, pages, chapters, irab_cache, and user tables.
-- Follows the spec in docs/reader/book-format.md.

-----------------------------------------------------------------------
-- Authors
-----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS authors (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  openiti_id TEXT UNIQUE NOT NULL,           -- e.g. '0748Dhahabi'

  -- Names
  shuhra_ar TEXT NOT NULL,                   -- Famous name in Arabic
  shuhra_lat TEXT,                           -- Famous name in Latin transliteration
  ism_ar TEXT,                               -- Given name (ism)
  nasab_ar TEXT,                             -- Patronymic chain (ibn/bin)
  kunya_ar TEXT,                             -- Honorific epithet (Abu...)
  laqab_ar TEXT,                             -- Title (Shams al-Din, etc.)
  nisba_ar TEXT,                             -- Geographic/professional affiliation
  full_name_ar TEXT,                         -- Composite: ism + nasab + kunya + laqab + nisba

  -- Dates
  birth_ah INTEGER,                          -- Hijri birth year
  death_ah INTEGER,                          -- Hijri death year

  -- Geography (from Althurayya URIs)
  birthplace TEXT,
  deathplace TEXT,
  places_visited TEXT[],
  places_resided TEXT[],

  -- Scholarly network (OpenITI author URIs)
  teachers TEXT[] DEFAULT '{}',
  students TEXT[] DEFAULT '{}',

  -- External IDs
  wikidata_id TEXT,                          -- e.g. 'Q293554'
  external_ids JSONB DEFAULT '{}',           -- VIAF, EI2, etc.

  -- System
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-----------------------------------------------------------------------
-- Books
-----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS books (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  openiti_id TEXT UNIQUE NOT NULL,
  author_id UUID NOT NULL REFERENCES authors(id) ON DELETE CASCADE,

  -- Title
  title_ar TEXT NOT NULL,                    -- Arabic title
  title_lat TEXT,                            -- Latin transliteration
  description TEXT,                          -- Book description / summary

  -- Classification
  genres TEXT[] NOT NULL DEFAULT '{}',       -- OpenITI genre tags: HADITH, FIQH, TARIKH, etc.

  -- Metrics
  word_count INTEGER,
  char_count INTEGER,
  total_pages INTEGER,                       -- Derived from page markers during ingestion
  total_volumes INTEGER DEFAULT 1,

  -- Source provenance
  version_status TEXT,                       -- 'pri' (primary) or 'sec' (secondary)
  source_edition_url TEXT,                   -- Worldcat permalink to print edition
  quality_issues TEXT[] DEFAULT '{}',        -- NO_MAJOR_ISSUES, MANY_TYPOS, etc.
  language TEXT DEFAULT 'ara',               -- ISO 639-2 language code
  composition_date_ah INTEGER,               -- Hijri year of composition

  -- Related works (OpenITI URIs)
  commentary_on TEXT,                        -- OpenITI URI of commented work
  abridgement_of TEXT,                       -- OpenITI URI of abridged work

  -- Starter catalog
  is_starter BOOLEAN DEFAULT FALSE,          -- shown in "Start here" for new users

  -- System
  has_tashkeel BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-----------------------------------------------------------------------
-- Pages
-----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  page_number INTEGER NOT NULL,
  volume INTEGER DEFAULT 1,
  content_blocks JSONB NOT NULL,             -- Block array with tokens (see Content Model)
  content_plain TEXT NOT NULL,               -- Flat text for future full-text search
  content_hash TEXT,                         -- Hash of content_plain for change detection
  UNIQUE(book_id, volume, page_number)
);

-----------------------------------------------------------------------
-- Chapters
-----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chapters (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  level INTEGER NOT NULL,                    -- 1 = chapter, 2 = section, 3 = subsection
  page_id UUID REFERENCES pages(id) ON DELETE SET NULL,
  parent_id UUID REFERENCES chapters(id),
  sort_order INTEGER NOT NULL,
  UNIQUE(book_id, sort_order)
);

-----------------------------------------------------------------------
-- I'rab cache (global, shared across all users)
-----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS irab_cache (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  word TEXT NOT NULL,
  sentence_hash TEXT NOT NULL,
  model_version TEXT NOT NULL DEFAULT 'sonnet-1',
  result_json JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(word, sentence_hash, model_version)
);

-----------------------------------------------------------------------
-- User library state
-----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_library (
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'none',       -- none | downloading | downloaded | reading | favorited
  download_progress REAL DEFAULT 0,          -- 0.0 to 1.0
  last_opened_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (user_id, book_id)
);

-----------------------------------------------------------------------
-- User bookmarks
-----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_bookmarks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  page_id UUID NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  token_id TEXT,                             -- Optional: specific word bookmarked
  label TEXT,
  anchor_context TEXT,                       -- ~30 chars for re-anchoring if content changes
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  deleted_at TIMESTAMPTZ                     -- Tombstone for sync (NULL = active)
);

-----------------------------------------------------------------------
-- User highlights
-----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_highlights (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  page_id UUID NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  start_token_id TEXT NOT NULL,              -- First token in highlight range
  end_token_id TEXT NOT NULL,                -- Last token in highlight range
  color TEXT DEFAULT 'yellow',
  note TEXT,
  anchor_context TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  deleted_at TIMESTAMPTZ
);

-----------------------------------------------------------------------
-- User notes
-----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_notes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  page_id UUID NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  token_id TEXT NOT NULL,                    -- Token the note is anchored to
  content TEXT NOT NULL,
  anchor_context TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  deleted_at TIMESTAMPTZ
);

-----------------------------------------------------------------------
-- User reading positions
-----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_reading_positions (
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  page_id UUID NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (user_id, book_id)
);

-----------------------------------------------------------------------
-- Indexes
-----------------------------------------------------------------------

-- Authors
CREATE INDEX IF NOT EXISTS idx_authors_openiti_id ON authors(openiti_id);

-- Books
CREATE INDEX IF NOT EXISTS idx_books_openiti_id ON books(openiti_id);
CREATE INDEX IF NOT EXISTS idx_books_author_id ON books(author_id);
CREATE INDEX IF NOT EXISTS idx_books_genres ON books USING GIN (genres);

-- Pages
CREATE INDEX IF NOT EXISTS idx_pages_book_volume_page ON pages(book_id, volume, page_number);

-- Chapters
CREATE INDEX IF NOT EXISTS idx_chapters_book_sort ON chapters(book_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_chapters_page_id ON chapters(page_id);

-- I'rab cache (unique constraint already covers the lookup)
-- No additional index needed beyond the UNIQUE constraint

-- User data
CREATE INDEX IF NOT EXISTS idx_user_bookmarks_user_book ON user_bookmarks(user_id, book_id);
CREATE INDEX IF NOT EXISTS idx_user_highlights_user_book ON user_highlights(user_id, book_id);
CREATE INDEX IF NOT EXISTS idx_user_notes_user_book ON user_notes(user_id, book_id);
