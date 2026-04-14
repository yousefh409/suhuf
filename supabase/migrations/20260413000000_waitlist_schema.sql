-- Waitlist users
create table if not exists waitlist_users (
  id uuid primary key default gen_random_uuid(),
  email text unique not null,
  referral_code text unique not null,
  referred_by uuid references waitlist_users(id),
  position int not null,
  referral_count int default 0,
  signup_source text default 'hero',
  interest_areas text[] default '{}',
  feature_request text,
  utm_source text,
  utm_medium text,
  utm_campaign text,
  created_at timestamptz default now()
);

-- Feature votes
create table if not exists feature_votes (
  id uuid primary key default gen_random_uuid(),
  waitlist_user_id uuid not null references waitlist_users(id),
  feature_id text not null,
  created_at timestamptz default now(),
  unique(waitlist_user_id, feature_id)
);

-- Feature suggestions
create table if not exists feature_suggestions (
  id uuid primary key default gen_random_uuid(),
  waitlist_user_id uuid not null references waitlist_users(id),
  suggestion text not null,
  created_at timestamptz default now()
);

-- Referral count increment function
create or replace function increment_referral_count(user_id uuid)
returns void as $$
  update waitlist_users
  set referral_count = referral_count + 1
  where id = user_id;
$$ language sql;

-- Indexes
create index if not exists idx_waitlist_email on waitlist_users(email);
create index if not exists idx_waitlist_referral_code on waitlist_users(referral_code);
create index if not exists idx_feature_votes_feature on feature_votes(feature_id);
