-- Re-apply RLS policies after schema recreation in 20260414000000.

-- Catalog: public read
ALTER TABLE authors ENABLE ROW LEVEL SECURITY;
ALTER TABLE books ENABLE ROW LEVEL SECURITY;
ALTER TABLE pages ENABLE ROW LEVEL SECURITY;
ALTER TABLE chapters ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public read authors" ON authors FOR SELECT USING (true);
CREATE POLICY "Public read books" ON books FOR SELECT USING (true);
CREATE POLICY "Public read pages" ON pages FOR SELECT USING (true);
CREATE POLICY "Public read chapters" ON chapters FOR SELECT USING (true);

-- irab_cache: public read, service role write
ALTER TABLE irab_cache ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read irab_cache" ON irab_cache FOR SELECT USING (true);
CREATE POLICY "Service role insert irab_cache" ON irab_cache FOR INSERT WITH CHECK (auth.role() = 'service_role');
CREATE POLICY "Service role update irab_cache" ON irab_cache FOR UPDATE USING (auth.role() = 'service_role');

-- User tables: own rows only
ALTER TABLE user_library ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users manage own library" ON user_library FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

ALTER TABLE user_bookmarks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users manage own bookmarks" ON user_bookmarks FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

ALTER TABLE user_highlights ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users manage own highlights" ON user_highlights FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

ALTER TABLE user_notes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users manage own notes" ON user_notes FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

ALTER TABLE user_reading_positions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users manage own positions" ON user_reading_positions FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
