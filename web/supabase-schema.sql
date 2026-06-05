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

-- ===== Reader/Ingestion tables =====
-- Populated by ingestion/upload.py. `create table if not exists` keeps this
-- file idempotent against the live database.

create table if not exists authors (
  id uuid primary key default gen_random_uuid(),
  openiti_id text unique not null,
  shuhra_ar text,
  shuhra_lat text,
  ism_ar text,
  nasab_ar text,
  kunya_ar text,
  laqab_ar text,
  nisba_ar text,
  full_name_ar text,
  birth_ah int,
  death_ah int,
  created_at timestamptz default now()
);

create table if not exists books (
  id uuid primary key default gen_random_uuid(),
  openiti_id text unique not null,
  author_id uuid references authors(id) on delete cascade,
  title_ar text not null,
  title_lat text,
  description text,
  genres text[] default '{}',
  word_count int,
  char_count int,
  total_pages int,
  total_volumes int,
  version_status text,
  language text default 'ara',
  has_tashkeel boolean default false,
  composition_date_ah int,
  commentary_on text,
  abridgement_of text,
  created_at timestamptz default now()
);

create table if not exists pages (
  id uuid primary key default gen_random_uuid(),
  book_id uuid not null references books(id) on delete cascade,
  page_number int not null,
  volume int not null default 1,
  content_plain text not null,                -- page plain text
  content_hash text,
  tagged text,                                -- flow: this page's slice of the continuous tagged document
  open_tags jsonb default '[]'::jsonb,        -- flow: tag stack open at this page's start
  start_offset int,                           -- flow: page start in the book's plain-text offset line
  created_at timestamptz default now(),
  unique (book_id, volume, page_number)
);

create index if not exists idx_pages_book on pages(book_id);

create table if not exists chapters (
  id uuid primary key default gen_random_uuid(),
  book_id uuid not null references books(id) on delete cascade,
  title text not null,
  level int not null,
  page_id uuid references pages(id),
  sort_order int not null,
  created_at timestamptz default now(),
  unique (book_id, sort_order)
);

create index if not exists idx_chapters_book on chapters(book_id);

-- Flow annotations: resolved metadata layer, one row per in-text tag id.
create table if not exists annotations (
  id uuid primary key default gen_random_uuid(),
  book_id uuid not null references books(id) on delete cascade,
  tag_id text not null,                       -- 'h2', 'p7', 'q5'
  label text not null,
  start_offset int,
  end_offset int,
  meta jsonb default '{}'::jsonb,
  unique (book_id, tag_id)
);

create index if not exists idx_annotations_book on annotations(book_id);
create index if not exists idx_annotations_book_label on annotations(book_id, label);
