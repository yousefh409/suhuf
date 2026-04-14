-- Migration: Drop old simplified schema and recreate with full spec.
-- The old 20260413100000 migration had a flat books table without authors.
-- This migration drops all old tables and recreates from the spec in
-- docs/reader/book-format.md.

-- Drop old tables (cascade handles FK deps)
DROP TABLE IF EXISTS user_reading_positions CASCADE;
DROP TABLE IF EXISTS user_notes CASCADE;
DROP TABLE IF EXISTS user_highlights CASCADE;
DROP TABLE IF EXISTS user_bookmarks CASCADE;
DROP TABLE IF EXISTS user_library CASCADE;
DROP TABLE IF EXISTS irab_cache CASCADE;
DROP TABLE IF EXISTS chapters CASCADE;
DROP TABLE IF EXISTS pages CASCADE;
DROP TABLE IF EXISTS books CASCADE;
DROP TABLE IF EXISTS authors CASCADE;

-----------------------------------------------------------------------
-- Authors
-----------------------------------------------------------------------
CREATE TABLE authors (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  openiti_id TEXT UNIQUE NOT NULL,

  shuhra_ar TEXT NOT NULL,
  shuhra_lat TEXT,
  ism_ar TEXT,
  nasab_ar TEXT,
  kunya_ar TEXT,
  laqab_ar TEXT,
  nisba_ar TEXT,
  full_name_ar TEXT,

  birth_ah INTEGER,
  death_ah INTEGER,

  birthplace TEXT,
  deathplace TEXT,
  places_visited TEXT[],
  places_resided TEXT[],

  teachers TEXT[] DEFAULT '{}',
  students TEXT[] DEFAULT '{}',

  wikidata_id TEXT,
  external_ids JSONB DEFAULT '{}',

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-----------------------------------------------------------------------
-- Books
-----------------------------------------------------------------------
CREATE TABLE books (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  openiti_id TEXT UNIQUE NOT NULL,
  author_id UUID NOT NULL REFERENCES authors(id) ON DELETE CASCADE,

  title_ar TEXT NOT NULL,
  title_lat TEXT,
  description TEXT,

  genres TEXT[] NOT NULL DEFAULT '{}',

  word_count INTEGER,
  char_count INTEGER,
  total_pages INTEGER,
  total_volumes INTEGER DEFAULT 1,

  version_status TEXT,
  source_edition_url TEXT,
  quality_issues TEXT[] DEFAULT '{}',
  language TEXT DEFAULT 'ara',
  composition_date_ah INTEGER,

  commentary_on TEXT,
  abridgement_of TEXT,

  is_starter BOOLEAN DEFAULT FALSE,
  has_tashkeel BOOLEAN DEFAULT FALSE,

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-----------------------------------------------------------------------
-- Pages
-----------------------------------------------------------------------
CREATE TABLE pages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  page_number INTEGER NOT NULL,
  volume INTEGER DEFAULT 1,
  content_blocks JSONB NOT NULL,
  content_plain TEXT NOT NULL,
  content_hash TEXT,
  UNIQUE(book_id, volume, page_number)
);

-----------------------------------------------------------------------
-- Chapters
-----------------------------------------------------------------------
CREATE TABLE chapters (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  level INTEGER NOT NULL,
  page_id UUID REFERENCES pages(id) ON DELETE SET NULL,
  parent_id UUID REFERENCES chapters(id),
  sort_order INTEGER NOT NULL,
  UNIQUE(book_id, sort_order)
);

-----------------------------------------------------------------------
-- I'rab cache
-----------------------------------------------------------------------
CREATE TABLE irab_cache (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  word TEXT NOT NULL,
  sentence_hash TEXT NOT NULL,
  model_version TEXT NOT NULL DEFAULT 'sonnet-1',
  result_json JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(word, sentence_hash, model_version)
);

-----------------------------------------------------------------------
-- User tables
-----------------------------------------------------------------------
CREATE TABLE user_library (
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'none',
  download_progress REAL DEFAULT 0,
  last_opened_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (user_id, book_id)
);

CREATE TABLE user_bookmarks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  page_id UUID NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  token_id TEXT,
  label TEXT,
  anchor_context TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  deleted_at TIMESTAMPTZ
);

CREATE TABLE user_highlights (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  page_id UUID NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  start_token_id TEXT NOT NULL,
  end_token_id TEXT NOT NULL,
  color TEXT DEFAULT 'yellow',
  note TEXT,
  anchor_context TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  deleted_at TIMESTAMPTZ
);

CREATE TABLE user_notes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  page_id UUID NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  token_id TEXT NOT NULL,
  content TEXT NOT NULL,
  anchor_context TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  deleted_at TIMESTAMPTZ
);

CREATE TABLE user_reading_positions (
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  page_id UUID NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (user_id, book_id)
);

-----------------------------------------------------------------------
-- Indexes
-----------------------------------------------------------------------
CREATE INDEX idx_authors_openiti_id ON authors(openiti_id);
CREATE INDEX idx_books_openiti_id ON books(openiti_id);
CREATE INDEX idx_books_author_id ON books(author_id);
CREATE INDEX idx_books_genres ON books USING GIN (genres);
CREATE INDEX idx_pages_book_volume_page ON pages(book_id, volume, page_number);
CREATE INDEX idx_chapters_book_sort ON chapters(book_id, sort_order);
CREATE INDEX idx_chapters_page_id ON chapters(page_id);
CREATE INDEX idx_user_bookmarks_user_book ON user_bookmarks(user_id, book_id);
CREATE INDEX idx_user_highlights_user_book ON user_highlights(user_id, book_id);
CREATE INDEX idx_user_notes_user_book ON user_notes(user_id, book_id);
