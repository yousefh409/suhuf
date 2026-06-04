-- Flow book format: the book is one continuous tagged document sliced into page
-- rows, plus an annotations layer keyed by tag id. See
-- docs/superpowers/specs/2026-06-05-continuous-tagged-book-format-design.md.
--
-- ADDITIVE migration: it keeps content_blocks (now nullable) so the legacy reader
-- path keeps working until it is migrated to the flow shape. The eventual drop of
-- content_blocks is a later cleanup, after the reader reads `tagged`.

-----------------------------------------------------------------------
-- Pages: carry a slice of the continuous tagged document
-----------------------------------------------------------------------
ALTER TABLE pages ADD COLUMN IF NOT EXISTS tagged TEXT;            -- this page's tagged fragment (tags may open here / close on a later page)
ALTER TABLE pages ADD COLUMN IF NOT EXISTS open_tags JSONB DEFAULT '[]'::jsonb;  -- tag stack open at this page's start: [{"name","id"}, ...]
ALTER TABLE pages ADD COLUMN IF NOT EXISTS start_offset INTEGER;  -- this page's start in the book's plain-text offset line

-- Flow pages carry `tagged` instead of content_blocks; relax NOT NULL so the two
-- shapes coexist during the migration. content_plain still holds the page text.
ALTER TABLE pages ALTER COLUMN content_blocks DROP NOT NULL;

-----------------------------------------------------------------------
-- Annotations: the resolved metadata layer, one row per tag id
-----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS annotations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  tag_id TEXT NOT NULL,            -- the in-text tag id: 'h2', 'p7', 'q5'
  label TEXT NOT NULL,             -- hadith | person | place | quran | book_ref | hadith_ref | date_hijri
  start_offset INTEGER,            -- plain-text char range of the span (convenience; `tagged` is canonical)
  end_offset INTEGER,
  meta JSONB DEFAULT '{}'::jsonb,  -- resolved metadata: {number}, {sura,ayah}, {ref,role}, ...
  UNIQUE(book_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_annotations_book ON annotations(book_id);
CREATE INDEX IF NOT EXISTS idx_annotations_book_label ON annotations(book_id, label);

-- Catalog data: public read (service role writes bypass RLS), matching pages/chapters.
ALTER TABLE annotations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read access for annotations"
  ON annotations FOR SELECT
  USING (true);
