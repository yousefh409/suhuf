# Invite-code signup

Account creation is gated by an invite code. The signup form at `/login` reads
the entered code, normalizes it (trim + uppercase), and checks it against the
`invite_codes` table before calling `auth.signUp()`. No match means no account.

Codes are shared cohort codes: one code can be used by any number of signups.
The table and the seed code `CS153` are created by
[`supabase/migrations/20260604000000_invite_codes.sql`](../../supabase/migrations/20260604000000_invite_codes.sql).

This is a client-side gate. It stops ordinary signups without a code; it does
not defend against someone calling `auth.signUp()` directly with the anon key.
That tradeoff was chosen deliberately for simplicity.

## Managing codes

Codes are stored uppercase. Run SQL against the project (SQL editor or
`supabase db push` after editing a migration):

```sql
-- Add a code
insert into invite_codes (code) values ('SPRING26');

-- Disable a code
delete from invite_codes where code = 'CS153';

-- List codes
select * from invite_codes order by created_at;
```

## Applying the migration

The table must exist in the linked project for the gate to work:

```sh
supabase db push
```
