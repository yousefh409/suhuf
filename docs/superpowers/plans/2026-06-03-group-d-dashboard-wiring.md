# Group D — Dashboard Data Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Replace the dashboard's mock data seam with real Supabase queries (library, reading progress, stats), make the catalog public, and record reading activity — without owning book content/ingestion.

**Architecture:** Keep the existing typed accessor seam (`web/src/lib/dashboard/data.ts`); swap each function's body from mock to a Supabase query. Catalog reads (Discover) are public (anon RLS); per-user reads (dashboard) use the session. A new `reading_sessions` table backs the stats; a small gated write-path records sessions + positions from the reader.

**Tech Stack:** Next.js 16, Supabase (`@supabase/ssr`, `@supabase/supabase-js`), Postgres RLS, Tailwind v4, Vitest.

**Predecessor:** the mock-backed UI from `2026-06-03-group-d-dashboard.md` (already built + merged into this branch).

**Live DB state (probed):** 1 book, 1 author, 38 pages, 1 user (`yousefh409@gmail.com`, id `b1992f15-7535-4eea-ab17-b1a86fb09797`); `user_library` and `user_reading_positions` empty; `reading_sessions` does not exist.

---

## Decisions locked with the user

- **Public vs gated:** PUBLIC = Discover (`/library`) + Reader (`/reader/<id>`). GATED = Dashboard (`/dashboard`) + Inspector + `/api/agents/*` (AI).
- **Stats:** add a `reading_sessions` table and compute real stats from it.
- **Book join:** query the real `books`/`authors` tables for titles/authors; do NOT populate them (ingestion's job). Library/Discover show whatever is ingested.
- **Reader data source:** untouched (book content is out of scope). Only the reader's *route* moves out of the auth gate.
- **Env/verify:** `web/.env.local` (copied from the main checkout, gitignored) holds the hosted Supabase keys. Verify against the real DB after seeding the test user.

## Metric definitions (`reading_sessions` → `getStats`)

For the current user:
- `pagesToday` = Σ `pages_read` where `occurred_at` ≥ start of today (UTC).
- `wordsLearnedThisWeek` = Σ `words_learned` where `occurred_at` ≥ now()−7 days. (`words_learned` is written by the AI/word-tap feature later; column exists now, defaults 0.)
- `streakDays` = count of consecutive calendar days ending today (or yesterday) each with ≥1 session.
- `timeReadMinutes` = round(Σ `duration_seconds` today / 60).

These windows are deliberate and easy to adjust; documented here so the UI labels (TODAY / this week / days / TIME READ) stay honest.

## Routing change

Introduce a public route group with a non-gating layout and move the two public routes into it; keep the gate for the rest.

- Create `web/src/app/(catalog)/layout.tsx` — renders children with the parchment chrome but does NOT redirect (no `getUser` requirement). May read the session optionally for personalization, but never blocks.
- Move `(app)/library/` → `(catalog)/library/` and `(app)/reader/` → `(catalog)/reader/` (route-group parens don't change the URL; `/library` and `/reader/<id>` are unchanged).
- `(app)/` keeps its gating layout for `dashboard/` and `inspector/`.
- The reader's own files are moved verbatim (no code edits) — only their folder location changes.

## Supabase access

- Reuse `createClient()` from `web/src/lib/supabase/server.ts` (cookie-aware; anon role for logged-out catalog reads, user role for dashboard). RLS already allows public read on `books/authors/pages/chapters` and own-row access on user tables.
- Add a tiny typed query module per concern under `web/src/lib/dashboard/` so `data.ts` stays a thin dispatcher.

---

## Task 1: `reading_sessions` migration

**Files:** Create `supabase/migrations/2026060300000_reading_sessions.sql`

- [ ] Create table `reading_sessions`: `id uuid pk default gen_random_uuid()`, `user_id uuid not null references auth.users(id) on delete cascade`, `book_id uuid not null references books(id) on delete cascade`, `pages_read int not null default 0`, `words_learned int not null default 0`, `duration_seconds int not null default 0`, `occurred_at timestamptz not null default now()`, `created_at timestamptz default now()`.
- [ ] Index `idx_reading_sessions_user_time on reading_sessions(user_id, occurred_at desc)`.
- [ ] Enable RLS; policy `"Users manage own sessions" FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id)`.
- [ ] Apply to the hosted DB (psql/supabase) and confirm the table exists (re-probe count returns 0, not error).
- [ ] Commit (`feat(db): reading_sessions table for dashboard stats`).

## Task 2: Catalog query module (public) — Discover + genres

**Files:** Create `web/src/lib/dashboard/catalog.ts`; modify `web/src/lib/dashboard/data.ts`

- [ ] `catalog.ts`: `queryDiscover(query)` → select from `books` joined to `authors`, mapping to `DiscoverBook` (openitiId ← books.openiti_id, titleAr ← title_ar, titleLat ← title_lat, authorName ← author shuhra/full name, genre ← first of `genres[]`, level ← derived or "" , popularity ← word_count or 0). Apply genre filter (genres array contains), case-insensitive title/author search, and sort (title/popularity/relevance) — reuse the existing pure `selectDiscover` where convenient or push to SQL. `queryGenres()` → aggregate distinct `genres` with counts (SQL group-by or fetch + reduce).
- [ ] Point `getDiscover`/`getGenres` in `data.ts` at these. Remove their mock usage.
- [ ] Typecheck. Commit (`feat: discover/genres from books table`).

## Task 3: Library + continue-reading queries (gated)

**Files:** Create `web/src/lib/dashboard/library.ts`; modify `data.ts`

- [ ] `library.ts`: `queryLibrary(status)` → `user_library` (current user via session) where status=…, joined to `books`+`authors`, with progress from `user_reading_positions` (position page_number / books.total_pages × 100, 0 when none). `queryContinueReading()` → in-progress entries ordered by `last_opened_at desc`, limit 3, same progress calc. `queryRecommended()` → `books` not present in the user's `user_library`, limit 10 (order by created_at desc). Map all to the existing types.
- [ ] Point `getLibrary`/`getContinueReading`/`getRecommended` at these. Handle logged-out (no user) by returning `[]`.
- [ ] Typecheck. Commit (`feat: library/continue-reading/recommended from Supabase`).

## Task 4: Stats query (gated)

**Files:** Create `web/src/lib/dashboard/stats.ts`; modify `data.ts`

- [ ] `stats.ts`: `queryStats()` → fetch the current user's recent `reading_sessions` (e.g. last 60 days) and compute the four metrics per the definitions above in TS (single query + reduce; streak by grouping distinct days). Return zeros when logged-out or no rows.
- [ ] Point `getStats` at it. Remove mock stats from `data.ts`.
- [ ] Unit-test the pure metric computation (feed synthetic session rows → assert pagesToday/week/streak/time). Put pure logic in a testable helper (`computeStats(sessions, now)`).
- [ ] Typecheck + `vitest run`. Commit (`feat: dashboard stats from reading_sessions (+ tests)`).

## Task 5: Make Discover + Reader public

**Files:** Create `web/src/app/(catalog)/layout.tsx`; move `library/` and `reader/` folders from `(app)` to `(catalog)`

- [ ] Add the non-gating `(catalog)/layout.tsx` (parchment chrome, no redirect).
- [ ] `git mv` the `library` and `reader` route folders from `(app)` into `(catalog)` (URLs unchanged). Do not edit their contents beyond import paths if any break.
- [ ] Confirm `dashboard` + `inspector` remain under the gated `(app)` layout.
- [ ] Build; confirm `/library` and `/reader/<id>` render logged-out, `/dashboard` redirects to `/login` logged-out.
- [ ] Commit (`feat: make Discover + Reader public, keep Dashboard/Inspector gated`).

## Task 6: Reading-activity write path

**Files:** Create `web/src/app/api/reading/progress/route.ts` (gated) + a client `ReadingTracker` component wired into the reader; possibly an `addToLibrary` on open

- [ ] `POST /api/reading/progress` — authenticated; body `{ bookId, pageId?, pageNumber?, pagesRead?, durationSeconds? }`. Upserts `user_reading_positions` (user, book, page) and inserts a `reading_sessions` row. Upserts `user_library` (status `in_progress`, `last_opened_at = now()`) so opening a book adds it to the library. Returns 401 when logged-out (no-op for public readers).
- [ ] A small client component in the reader that, when a logged-in user reads, posts progress on page change / a short interval (debounced), sending elapsed time + current page. Logged-out → does nothing. Keep it isolated; minimal touch to the reader page.
- [ ] Manually verify a POST creates the rows for the test user.
- [ ] Commit (`feat: record reading sessions + positions from reader`).

## Task 7: Seed script for verification

**Files:** Create `web/scripts/seed-dashboard.mjs` (dev-only, not a migration)

- [ ] Using the service-role key, seed the test user (`b1992f15-…`): a `user_library` row for the existing book (status `in_progress`, last_opened_at now); a `user_reading_positions` row at some page; several `reading_sessions` rows across the last few days (varying pages_read/duration, some words_learned) so streak/time/words are non-zero.
- [ ] Run it; re-probe counts to confirm rows exist.
- [ ] Commit (`chore: dashboard seed script for local verification`).

## Task 8: Verify against real Supabase + visual pass

- [ ] `./bin/suhuf verify` (lint, tsc, vitest, build) green.
- [ ] Start the dev server with `web/.env.local`; log in as the test user (or seed a session) and load `/dashboard` — confirm stats, continue-reading, library tabs, recommended all reflect seeded DB rows. Load `/library` logged-out — confirm public Discover shows the real book(s). Screenshot both.
- [ ] Fix issues, then ship.

---

## Self-review

- **Coverage:** stats schema (T1), public Discover/genres (T2), library/progress/recommended (T3), stats compute + tests (T4), public routing (T5), write path (T6), seed+verify (T7–T8). All locked decisions mapped.
- **Out of scope:** book ingestion/content, the reader's data source, a real recommender (simple "not-in-library" query stands in), bookmarks/highlights/notes surfaces.
- **Risk:** T5 moves the reader route folder (another group's files) — verbatim move, no content edits, verified by rendering. T6 adds an isolated tracker to the reader — minimal touch. Flag to user if reader coupling is deeper than expected.
- **Cross-group note:** coordinate the reader route move + tracker with whoever owns the reader before merge.
