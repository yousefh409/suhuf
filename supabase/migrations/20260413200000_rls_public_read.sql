-- Row Level Security policies for all tables.
--
-- Catalog data (authors, books, pages, chapters): public read for everyone.
-- irab_cache: public read, insert/update via service role only.
-- user_* tables: users read/write their own rows only.

-----------------------------------------------------------------------
-- Catalog tables: public read
-----------------------------------------------------------------------

ALTER TABLE authors ENABLE ROW LEVEL SECURITY;
ALTER TABLE books ENABLE ROW LEVEL SECURITY;
ALTER TABLE pages ENABLE ROW LEVEL SECURITY;
ALTER TABLE chapters ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public read access for authors"
  ON authors FOR SELECT
  USING (true);

CREATE POLICY "Public read access for books"
  ON books FOR SELECT
  USING (true);

CREATE POLICY "Public read access for pages"
  ON pages FOR SELECT
  USING (true);

CREATE POLICY "Public read access for chapters"
  ON chapters FOR SELECT
  USING (true);

-----------------------------------------------------------------------
-- I'rab cache: public read, service role write
-----------------------------------------------------------------------

ALTER TABLE irab_cache ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public read access for irab_cache"
  ON irab_cache FOR SELECT
  USING (true);

CREATE POLICY "Service role insert for irab_cache"
  ON irab_cache FOR INSERT
  WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "Service role update for irab_cache"
  ON irab_cache FOR UPDATE
  USING (auth.role() = 'service_role');

-----------------------------------------------------------------------
-- User library
-----------------------------------------------------------------------

ALTER TABLE user_library ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own library"
  ON user_library FOR ALL
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-----------------------------------------------------------------------
-- User bookmarks
-----------------------------------------------------------------------

ALTER TABLE user_bookmarks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own bookmarks"
  ON user_bookmarks FOR ALL
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-----------------------------------------------------------------------
-- User highlights
-----------------------------------------------------------------------

ALTER TABLE user_highlights ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own highlights"
  ON user_highlights FOR ALL
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-----------------------------------------------------------------------
-- User notes
-----------------------------------------------------------------------

ALTER TABLE user_notes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own notes"
  ON user_notes FOR ALL
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-----------------------------------------------------------------------
-- User reading positions
-----------------------------------------------------------------------

ALTER TABLE user_reading_positions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own reading positions"
  ON user_reading_positions FOR ALL
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);
