# Group D — Dashboard (Library + Reading Progress) Design

**Date:** 2026-06-03
**Branch / worktree:** `funny-euclid-7a0366`
**Status:** Approved, ready for implementation plan

## Goal

Build the authenticated dashboard from the Paper designs ("Library — Main" and
"Library — Discover"): a personalized home with reading stats, a Continue Reading
list, the user's library by status, and recommendations, plus a full-catalog
Discover/browse screen. Per-user data depends on Group 0 auth, so this iteration
builds the UI/layout against a typed data seam backed by mock fixtures; the seam
swaps to Supabase once auth and real data land.

## Decisions

- **Scope:** two screens — `/dashboard` (personalized home) and `/library`
  (Discover catalog browse). Both fully responsive (desktop 1024px + mobile 390px
  artboards).
- **Data:** a typed data-access seam with a mock/fixture implementation. Swapping
  to Supabase later is a single-file change.
- **Stats / recommendations:** mock now; the eventual table/query shape is
  documented in the seam, but no migrations are added in this iteration.
- **Cleanup:** the old dev book-list currently at `(app)/library` is deleted. The
  product Discover screen takes over `/library` and links into `/reader/{id}`.
- **Architecture:** RSC-first. Pages are server components that call the data
  module; only tabs, search, genre filter, and sort are small client islands.
- **Styling:** reuse the existing brand system — no new design tokens or fonts.

## Existing system this builds on

- Next.js app-router (`next@16`, React 19, Tailwind v4).
- `(app)/` route group with an auth gate in `web/src/app/(app)/layout.tsx`
  (redirects unauthenticated users to `/login`). Both new pages live inside it.
- Brand tokens in `web/src/app/globals.css`: `parchment`, `parchment-light`,
  `parchment-warm`, `ink`, `gold` (`#B47D3A`), `dark`, `cta-dark`. Fonts:
  Instrument Serif (display/serif), DM Sans (body/sans), Amiri (Arabic) — all
  already loaded in `web/src/app/layout.tsx`.
- `lucide-react` (icons), `motion` (animation), `@floating-ui/react` (popovers),
  `@supabase/ssr` server client at `web/src/lib/supabase/server.ts`.
- Reader pages live at `/reader/{openiti_id}`; book cards link there.

The Paper designs already match this brand system (Instrument Serif headers, gold
progress bars on parchment), so no visual reinterpretation is needed.

## Architecture

RSC-first with client islands. Each page is a server component that calls the
typed data module. Sections are presentational components. Only genuinely
interactive pieces are `"use client"` islands: the dashboard tab switcher, and the
Discover search input, genre chips, and sort control. This matches the existing
reader pages and keeps the eventual mock→Supabase swap confined to one module.

## Components and units

### Data-access seam — `web/src/lib/dashboard/`

The single swap-point for real data.

- `types.ts`
  - `DashboardStats` — `{ pagesToday, wordsLearnedThisWeek, streakDays, timeReadMinutes }`.
  - `ContinueReadingItem` — book identity + `progressPercent`, `lastOpenedAt`.
  - `LibraryEntry` — book identity + `status: "in_progress" | "saved" | "completed"`,
    `progressPercent`, `lastOpenedAt`.
  - `RecommendedBook`, `DiscoverBook` — book identity + author + genre + level.
  - `Genre` — `{ slug, label, count }`.
  - A shared `BookIdentity` — `{ openitiId, titleAr, titleLat?, titleEn?, authorName, coverUrl? }`.
- `data.ts` — async functions the server components call:
  `getStats()`, `getContinueReading()`, `getLibrary(status)`, `getRecommended()`,
  `getDiscover({ genre?, query?, sort? })`, `getGenres()`. Each currently delegates
  to `mock.ts` and carries a `// TODO(group0): swap to Supabase` note plus a short
  doc block naming the eventual source:
  - stats ← a future `reading_sessions` aggregate (streak/time/words/pages);
  - library ← `user_library` (status, last_opened_at) joined to `books`;
  - progress ← `user_reading_positions` page over `books.total_pages`;
  - recommendations ← future recommender (placeholder: curated list);
  - discover ← `books`/`authors` with genre + text search + sort.
- `mock.ts` — fixtures matching the Paper mockups (Al-Ajrumiyyah 42%,
  Al-Arba'in al-Nawawiyyah 67%, Al-Muwatta 18%, Riyad al-Salihin 31%, Bulugh
  al-Maram 8%, plus the recommended/discover sets). Genre counts mirror the
  Discover chips (Nahw 1,240, Sarf 840, Hadith 1,100, …).

### Presentational components — `web/src/components/dashboard/`

- `DashboardHeader` — Instrument-Serif "Library" title, search affordance, avatar.
- `StatsBar` + `StatCard` — 4-up stat row.
- `ContinueReadingList` + `ContinueReadingRow` — cover, title, `author · genre · level`,
  `ProgressBar`, Resume button (first/active row).
- `LibraryShelf` — wraps the `LibraryTabs` client island; renders a `BookCard` grid
  for the active status; "Full Library →" links to `/library`.
- `LibraryTabs` (client) — In Progress / Saved / Completed with counts; switches the
  visible shelf.
- `BookCard` — cover with optional `%` badge, title, `author`. Click → `/reader/{id}`.
- `RecommendedGrid` — grid of `BookCard`, "Based on your reading" caption.
- Discover: `DiscoverHeader` (back link + centered title), `DiscoverSearch` (client),
  `GenreChips` (client), `DiscoverGrid` (reuses `BookCard`).
- Shared: `ProgressBar` (gold fill + percent label), `BookCover` (graceful fallback
  when `coverUrl` is missing — initials/placeholder on a parchment tile).

### Pages

- `web/src/app/(app)/dashboard/page.tsx` — server component composing
  `DashboardHeader → StatsBar → ContinueReadingList → LibraryShelf → RecommendedGrid`.
- `web/src/app/(app)/library/page.tsx` — server component for Discover; reads
  `searchParams` (`genre`, `q`, `sort`) and calls `getDiscover(...)` so filtering is
  URL-driven and server-rendered. Client islands push state via the URL.

## Screen layouts

### Dashboard `/dashboard` (from "Library — Main")

Instrument-Serif "Library" header with search + avatar → 4-up `StatsBar`
(Today pages / Words learned this week / Streak days / Time read) → "Continue
Reading" list (first row gets a Resume button; gold progress bars) → tab bar
(In Progress / Saved / Completed with counts) with a "Full Library →" link to
`/library` → `BookCard` grid for the active tab → "Recommended for You" grid.
Cards sit on `parchment-warm`; progress uses `gold #B47D3A`.

### Discover `/library` (from "Library — Discover")

Back-to-dashboard link + centered "Discover" title → full-width search input
("Search N Arabic texts…") → horizontal `GenreChips` (Nahw / Sarf / Hadith / Fiqh /
Tafseer / Aqeedah / Balagha / Lugha / Sirah with counts; active chip = ink fill) →
"{genre} · N texts" caption → 5-column `BookCard` grid. Search, genre, and sort
write to the URL; the server re-queries the mock. Card click → `/reader/{id}`.

## Responsive behavior

Tailwind breakpoints only; one responsive implementation per page.

- **Desktop (≥1024px):** stats 4-up; library and discover grids 5-column.
- **Mobile (≤640px, per the 390px artboard):** stats 2×2; Continue Reading
  condensed (cover + title + compact progress); the In Progress shelf becomes a
  horizontal scroll row using the existing `.scrollbar-hide` utility; recommended
  and discover grids drop to 2-column.

## Error / empty states

- Empty library tab → quiet "Nothing here yet" line with a link to Discover.
- Missing book cover → `BookCover` fallback tile (no broken image).
- Discover search with no matches → "No texts match" with a clear-filters action.
- Data functions are pure/mock and cannot throw in this iteration; the eventual
  Supabase swap will add real error handling at the seam.

## Testing

- Vitest unit tests for the data layer: mock data shape, `getLibrary` status
  filtering, and `getDiscover` genre/query/sort filtering.
- A render smoke test per page (mounts with mock data, asserts key sections
  appear).
- No e2e — there is no auth or real data to exercise yet.

## Cleanup and docs

- Delete the old dev book-list `web/src/app/(app)/library/page.tsx`.
- Update `CLAUDE.md` and `docs/reader/dev-loop.md`: note that `/library` is now the
  product Discover screen and reader access in the dev loop is Discover →
  `/reader/{id}` (the standalone dev book-list is gone).

## Out of scope

- Real per-user data, auth wiring, and Supabase queries (Group 0 + a follow-up).
- Migrations for stats / reading-sessions / recommendations.
- A real recommendation engine (placeholder curated list only).
- Bookmarks, highlights, and notes surfaces.

## Coordination

- **Group 0 (auth/data):** owns `auth.users` and the Supabase session. This work
  consumes the existing `(app)/` auth gate and leaves a typed seam for Group 0 /
  a follow-up to back with real queries.
- **Ingestion/reader workflow:** the dev book-list at `/library` is removed; book
  navigation to `/reader/{id}` is preserved through Discover.
