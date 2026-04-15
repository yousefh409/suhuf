-- Enable RLS on waitlist tables.
-- All access goes through API routes using the service role key,
-- so we block direct access via the anon key entirely.

ALTER TABLE waitlist_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE feature_votes ENABLE ROW LEVEL SECURITY;
ALTER TABLE feature_suggestions ENABLE ROW LEVEL SECURITY;

-- Service role bypasses RLS automatically, so no explicit policies needed.
-- These tables are now invisible to the anon key.
