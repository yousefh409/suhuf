-- Books table: catalog of all available books
CREATE TABLE IF NOT EXISTS books (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  openiti_id TEXT UNIQUE NOT NULL,
  title_ar TEXT NOT NULL,
  title_en TEXT NOT NULL,
  author_ar TEXT,
  author_en TEXT,
  category TEXT NOT NULL,
  level TEXT NOT NULL CHECK (level IN ('Beginner', 'Intermediate', 'Advanced')),
  cover_color TEXT DEFAULT '#5C4B3A',
  page_count INTEGER NOT NULL DEFAULT 0,
  content_hash TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Pages table: each page is a JSON array of typed blocks
CREATE TABLE IF NOT EXISTS pages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  page_number INTEGER NOT NULL,
  blocks JSONB NOT NULL DEFAULT '[]',
  UNIQUE(book_id, page_number)
);

-- Chapters table: table of contents
CREATE TABLE IF NOT EXISTS chapters (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  start_page INTEGER NOT NULL
);

-- Indexes for common queries
CREATE INDEX idx_pages_book_id ON pages(book_id);
CREATE INDEX idx_pages_book_page ON pages(book_id, page_number);
CREATE INDEX idx_chapters_book_id ON chapters(book_id);
CREATE INDEX idx_books_category ON books(category);
CREATE INDEX idx_books_level ON books(level);
