-- Invite codes for gated signup.
--
-- Account creation requires a valid invite code. The signup form checks this
-- table (via the anon key) before calling auth.signUp(). Codes are shared
-- cohort codes: one code can be used by many signups. Add a code with an
-- INSERT; disable one by deleting its row.

CREATE TABLE IF NOT EXISTS invite_codes (
  code text PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- First cohort.
INSERT INTO invite_codes (code) VALUES ('CS153')
  ON CONFLICT (code) DO NOTHING;

-- Public read so the signup form (anon key) can validate a code.
-- Codes are shared cohort codes, not secrets; no insert/update/delete from
-- the client (those go through the service role / SQL).
ALTER TABLE invite_codes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public read access for invite_codes"
  ON invite_codes FOR SELECT
  USING (true);
