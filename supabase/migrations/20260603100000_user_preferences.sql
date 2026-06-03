-- Per-user reading preferences, synced across devices. Owner-only (RLS).
-- Values are also kept in a browser cookie for anonymous users and as the
-- render source of truth on first paint; this table is the authoritative
-- cross-device store for signed-in users.

CREATE TABLE user_preferences (
  user_id     UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  theme       TEXT NOT NULL DEFAULT 'paper'
                CONSTRAINT user_preferences_theme_check
                  CHECK (theme IN ('paper', 'sepia', 'night')),
  text_size   TEXT NOT NULL DEFAULT 'm'
                CONSTRAINT user_preferences_text_size_check
                  CHECK (text_size IN ('s', 'm', 'l', 'xl')),
  arabic_font TEXT NOT NULL DEFAULT 'scheherazade'
                CONSTRAINT user_preferences_arabic_font_check
                  CHECK (arabic_font IN ('scheherazade', 'amiri', 'noto-naskh')),
  line_spacing TEXT NOT NULL DEFAULT 'comfortable'
                CONSTRAINT user_preferences_line_spacing_check
                  CHECK (line_spacing IN ('comfortable', 'compact')),
  tashkeel    BOOLEAN NOT NULL DEFAULT true,
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own preferences" ON user_preferences
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
