-- Reading activity log backing the dashboard stats (pages today, words
-- learned this week, streak, time read). Owner-only, like the other user_* tables.

CREATE TABLE reading_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  pages_read INTEGER NOT NULL DEFAULT 0,
  words_learned INTEGER NOT NULL DEFAULT 0,
  duration_seconds INTEGER NOT NULL DEFAULT 0,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_reading_sessions_user_time
  ON reading_sessions(user_id, occurred_at DESC);

ALTER TABLE reading_sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users manage own sessions" ON reading_sessions
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
