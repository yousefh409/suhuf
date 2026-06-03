-- Display preferences are now stored locally (cookie) only; the cross-device
-- sync was removed. Drop the table and its owner-only policy (the policy is
-- dropped automatically with the table).

DROP TABLE IF EXISTS user_preferences;
