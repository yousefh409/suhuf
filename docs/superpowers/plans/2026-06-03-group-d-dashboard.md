# Group D — Dashboard (Library + Reading Progress) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the authenticated `/dashboard` (stats + Continue Reading + library-by-status + recommendations) and `/library` (Discover catalog browse) screens from the Paper designs, against a typed data seam backed by mock fixtures.

**Architecture:** RSC-first. Pages are server components that call a typed data module (`lib/dashboard/`); presentational section components render the layout; only tab switching, Discover search, genre filter, and sort are small client islands. The data module delegates to mock fixtures today and swaps to Supabase in one place once Group 0 auth lands.

**Tech Stack:** Next.js 16 (app-router), React 19, Tailwind v4, TypeScript, Vitest, lucide-react. Existing brand tokens (`parchment`, `ink`, `gold #B47D3A`) and fonts (Instrument Serif / DM Sans / Amiri) are reused — no new design system.

**Spec:** `docs/superpowers/specs/2026-06-03-group-d-dashboard-design.md`

---

## Notes for the implementer

- **Read the bundled Next.js docs first.** `web/AGENTS.md` warns this Next.js has breaking changes vs. training data. Before writing routes/pages, skim the relevant guide in `web/node_modules/next/dist/docs/` (routing, server components, `searchParams`). Heed deprecation notices.
- **Test environment is `node`** (`web/vitest.config.ts`), so full React DOM rendering is not available without adding jsdom. Decision: TDD covers the **pure** logic (data module + a pure discover filter/sort helper); the rendered pages and components are verified visually with the preview tools, not React render tests. Do not add jsdom/testing-library.
- **Verify visually with preview tools** (`preview_start`, `preview_snapshot`, `preview_screenshot`, `preview_resize`) at desktop (≥1024px) and mobile (≤640px) against the Paper artboards "Library — Main", "Library Main — Mobile", and "Library — Discover".
- **Shipping:** commit per task. When the whole plan is done, follow the suhuf ship protocol (`./bin/suhuf ship`), do not raw `git push`.
- Tests live co-located as `*.test.ts`; follow the style in `web/src/lib/reader/queries.test.ts` (vitest `describe`/`it`/`expect`).

## File structure

Created:
- `web/src/lib/dashboard/types.ts` — all dashboard/discover TypeScript types.
- `web/src/lib/dashboard/mock.ts` — fixture data matching the Paper mockups.
- `web/src/lib/dashboard/select.ts` — pure helpers: library status filter, discover filter+sort. (Kept separate from `data.ts` so it is importable in a `node` test without `server-only`.)
- `web/src/lib/dashboard/data.ts` — `server-only` async accessors the pages call; delegates to `mock.ts` + `select.ts`; carries `TODO(group0)` swap notes.
- `web/src/lib/dashboard/select.test.ts` — unit tests for `select.ts`.
- `web/src/components/dashboard/ProgressBar.tsx`
- `web/src/components/dashboard/BookCover.tsx`
- `web/src/components/dashboard/BookCard.tsx`
- `web/src/components/dashboard/DashboardHeader.tsx`
- `web/src/components/dashboard/StatsBar.tsx` (includes `StatCard`)
- `web/src/components/dashboard/ContinueReading.tsx` (list + row)
- `web/src/components/dashboard/LibraryShelf.tsx`
- `web/src/components/dashboard/LibraryTabs.tsx` (`"use client"`)
- `web/src/components/dashboard/RecommendedGrid.tsx`
- `web/src/components/dashboard/discover/DiscoverHeader.tsx`
- `web/src/components/dashboard/discover/DiscoverSearch.tsx` (`"use client"`)
- `web/src/components/dashboard/discover/GenreChips.tsx` (`"use client"`)
- `web/src/components/dashboard/discover/DiscoverGrid.tsx`

Modified:
- `web/src/app/(app)/dashboard/page.tsx` — replace stub with composed dashboard.
- `web/src/app/(app)/library/page.tsx` — replace dev book-list with Discover.
- `CLAUDE.md`, `docs/reader/dev-loop.md` — update `/library` references.

Removed:
- The dev book-list body of `web/src/app/(app)/library/page.tsx` (replaced, not a separate file).

---

## Task 1: Dashboard types

**Files:** Create `web/src/lib/dashboard/types.ts`

- [ ] **Step 1:** Define and export the types from the spec: `BookIdentity` (openitiId, titleAr, titleLat?, titleEn?, authorName, coverUrl?), `LibraryStatus` union (`"in_progress" | "saved" | "completed"`), `DashboardStats`, `ContinueReadingItem`, `LibraryEntry`, `RecommendedBook`, `DiscoverBook`, `Genre`, and a `DiscoverQuery` (`{ genre?, query?, sort? }`) plus a `DiscoverSort` union (e.g. `"relevance" | "title" | "popularity"`). Keep field names exactly as referenced by later tasks.
- [ ] **Step 2:** Typecheck: `cd web && npx tsc --noEmit`. Expected: passes.
- [ ] **Step 3:** Commit (`feat: dashboard data types`).

## Task 2: Mock fixtures

**Files:** Create `web/src/lib/dashboard/mock.ts`

- [ ] **Step 1:** Export typed fixtures matching the Paper mockups: `mockStats` (47 pages today, 128 words/week, 12-day streak, 204 min), `mockContinueReading` (Al-Ajrumiyyah 42%, Al-Arba'in al-Nawawiyyah 67%, Al-Muwatta 18%), `mockLibrary` (entries across the three statuses; In Progress includes the five cards from the design — Al-Ajrumiyyah, Al-Arba'in, Al-Muwatta, Riyad al-Salihin 31%, Bulugh al-Maram 8%), `mockRecommended` (the 10 books in the design), `mockGenres` (Nahw 1240, Sarf 840, Hadith 1100, Fiqh 2300, Tafseer 890, Aqeedah 560, Balagha 320, Lugha 610, Sirah 280), and `mockDiscover` (the Discover grid books, each with author + genre slug + level). Use real `openiti_id` values where known so `/reader/{id}` links resolve when data exists; otherwise placeholder ids are fine. `coverUrl` omitted (fallback covers).
- [ ] **Step 2:** Typecheck: `cd web && npx tsc --noEmit`. Expected: passes.
- [ ] **Step 3:** Commit (`feat: dashboard mock fixtures`).

## Task 3: Pure select helpers (TDD)

**Files:** Create `web/src/lib/dashboard/select.ts`, `web/src/lib/dashboard/select.test.ts`

- [ ] **Step 1:** Write failing tests in `select.test.ts` covering: `selectLibrary(entries, status)` returns only entries of that status; `selectDiscover(books, query)` filters by genre slug, filters by case-insensitive substring match on title/author when `query` set, and sorts by the `sort` field (title alphabetical; popularity/relevance stable). Include an empty-result case.
- [ ] **Step 2:** Run `cd web && npx vitest run src/lib/dashboard/select.test.ts`. Expected: FAIL (functions undefined).
- [ ] **Step 3:** Implement `selectLibrary` and `selectDiscover` in `select.ts` as pure functions over arrays (no `server-only` import).
- [ ] **Step 4:** Run the test again. Expected: PASS.
- [ ] **Step 5:** Commit (`feat: dashboard select helpers + tests`).

## Task 4: Data accessors (the seam)

**Files:** Create `web/src/lib/dashboard/data.ts`

- [ ] **Step 1:** Add `import "server-only"`. Export async accessors: `getStats()`, `getContinueReading()`, `getLibrary(status)`, `getRecommended()`, `getGenres()`, `getDiscover(query)`. Each returns the corresponding mock (using `select.ts` for `getLibrary`/`getDiscover`). Above each accessor add a short comment naming the eventual Supabase source per the spec (stats ← reading_sessions aggregate; library ← user_library⋈books; progress ← user_reading_positions; discover ← books/authors) prefixed `TODO(group0): swap to Supabase`.
- [ ] **Step 2:** Typecheck: `cd web && npx tsc --noEmit`. Expected: passes.
- [ ] **Step 3:** Commit (`feat: dashboard data accessors (mock-backed seam)`).

## Task 5: Shared presentational components

**Files:** Create `ProgressBar.tsx`, `BookCover.tsx`, `BookCard.tsx` under `web/src/components/dashboard/`

- [ ] **Step 1:** `ProgressBar` — props `{ percent }`; renders a gold (`#B47D3A` / `gold` token) fill on a faint track with a right-aligned percent label, matching the design.
- [ ] **Step 2:** `BookCover` — props `BookIdentity` subset; renders the cover image when `coverUrl` present, otherwise a parchment-tile fallback showing the Arabic title (Amiri) — never a broken image.
- [ ] **Step 3:** `BookCard` — props `{ book, percentBadge? }`; cover (via `BookCover`) with optional `%` badge, title, author; wraps the whole card in a link to `/reader/${encodeURIComponent(book.openitiId)}`.
- [ ] **Step 4:** Typecheck: `cd web && npx tsc --noEmit`. Expected: passes.
- [ ] **Step 5:** Commit (`feat: dashboard shared components (progress, cover, card)`).

## Task 6: Dashboard sections

**Files:** Create `DashboardHeader.tsx`, `StatsBar.tsx`, `ContinueReading.tsx`, `RecommendedGrid.tsx` under `web/src/components/dashboard/`

- [ ] **Step 1:** `DashboardHeader` — Instrument-Serif "Library" title, a search affordance (lucide `Search`), and an avatar chip (initials). Server component.
- [ ] **Step 2:** `StatsBar` + `StatCard` — 4-up row of cards on `parchment-warm`; each card shows a small caps label and a large value with unit (Today/pages, Words learned/this week, Streak/days, Time read). Server component; takes `DashboardStats`.
- [ ] **Step 3:** `ContinueReading` (list + row) — "Continue Reading" heading with "Last opened" caption; each row: `BookCover`, title, `author · genre · level` meta, `ProgressBar`; the first/active row also renders a "Resume" button linking to `/reader/{id}`. Takes `ContinueReadingItem[]`.
- [ ] **Step 4:** `RecommendedGrid` — "Recommended for You" heading + "Based on your reading" caption; grid of `BookCard`. Takes `RecommendedBook[]`.
- [ ] **Step 5:** Typecheck: `cd web && npx tsc --noEmit`. Expected: passes.
- [ ] **Step 6:** Commit (`feat: dashboard sections (header, stats, continue reading, recommended)`).

## Task 7: Library shelf + tabs island

**Files:** Create `LibraryShelf.tsx`, `LibraryTabs.tsx` (`"use client"`) under `web/src/components/dashboard/`

- [ ] **Step 1:** `LibraryTabs` (client) — renders the In Progress / Saved / Completed tabs with counts; holds the active-status state; renders the provided grid for the active status. Receives the three already-fetched entry lists as props (server fetches once, client only toggles visibility) plus the "Full Library →" link to `/library`.
- [ ] **Step 2:** `LibraryShelf` (server) — fetches the three status lists via `getLibrary(...)`, builds `BookCard` grids, passes them to `LibraryTabs`. Empty status → quiet "Nothing here yet" with a link to `/library`.
- [ ] **Step 3:** Typecheck: `cd web && npx tsc --noEmit`. Expected: passes.
- [ ] **Step 4:** Commit (`feat: dashboard library shelf with status tabs`).

## Task 8: Dashboard page composition

**Files:** Modify `web/src/app/(app)/dashboard/page.tsx`

- [ ] **Step 1:** Replace the stub. Server component composing `DashboardHeader → StatsBar(getStats) → ContinueReading(getContinueReading) → LibraryShelf → RecommendedGrid(getRecommended)` inside a centered max-width container on parchment. Keep the existing `(app)` auth gate (no change to layout).
- [ ] **Step 2:** Typecheck + lint: `cd web && npx tsc --noEmit && npx eslint src/app/(app)/dashboard/page.tsx`. Expected: passes.
- [ ] **Step 3:** Visual verify: `preview_start`, navigate to `/dashboard`, `preview_snapshot` + `preview_screenshot` at desktop, then `preview_resize` to 390px and screenshot. Compare against "Library — Main" and "Library Main — Mobile". Fix layout gaps.
- [ ] **Step 4:** Commit (`feat: dashboard page`).

## Task 9: Discover header, search, genre chips, grid

**Files:** Create under `web/src/components/dashboard/discover/`: `DiscoverHeader.tsx`, `DiscoverSearch.tsx` (`"use client"`), `GenreChips.tsx` (`"use client"`), `DiscoverGrid.tsx`

- [ ] **Step 1:** `DiscoverHeader` (server) — back link to `/dashboard` (lucide `ChevronLeft` + "Library") and a centered "Discover" title.
- [ ] **Step 2:** `DiscoverSearch` (client) — full-width search input ("Search N Arabic texts…", N = total count prop); on submit/debounced-change, updates the URL `q` param via `useRouter().replace` (preserving other params). Include a Sort control writing the `sort` param.
- [ ] **Step 3:** `GenreChips` (client) — horizontal, scrollable chip row from `Genre[]`; active chip (ink fill) reflects the current `genre` param; clicking sets/clears the `genre` param in the URL. Use `.scrollbar-hide`.
- [ ] **Step 4:** `DiscoverGrid` (server) — 5-col `BookCard` grid; renders "No texts match" + a clear-filters link when empty.
- [ ] **Step 5:** Typecheck: `cd web && npx tsc --noEmit`. Expected: passes.
- [ ] **Step 6:** Commit (`feat: discover components`).

## Task 10: Discover page (replaces dev book-list)

**Files:** Modify `web/src/app/(app)/library/page.tsx`

- [ ] **Step 1:** Replace the dev book-list entirely. Server component that reads `searchParams` (`genre`, `q`, `sort`), calls `getGenres()` and `getDiscover({ genre, query, sort })`, and renders `DiscoverHeader → DiscoverSearch → GenreChips → "{genre} · N texts" caption → DiscoverGrid`. Follow the Next 16 `searchParams` contract from the bundled docs (it may be async).
- [ ] **Step 2:** Typecheck + lint. Expected: passes.
- [ ] **Step 3:** Visual verify at `/library`: snapshot + screenshot desktop and mobile; test that clicking a genre chip and typing a query update the grid (URL-driven). Compare against "Library — Discover".
- [ ] **Step 4:** Commit (`feat: discover page at /library`).

## Task 11: Cross-links and nav

**Files:** Verify links across `dashboard/page.tsx`, `LibraryShelf`, `DiscoverHeader`, `BookCard`

- [ ] **Step 1:** Confirm: "Full Library →" → `/library`; Discover back link → `/dashboard`; every `BookCard`/Resume → `/reader/{id}`. Fix any mismatch.
- [ ] **Step 2:** Commit if changed (`fix: dashboard/discover cross-links`).

## Task 12: Docs + cleanup

**Files:** Modify `CLAUDE.md`, `docs/reader/dev-loop.md`

- [ ] **Step 1:** Update both docs: `/library` is now the product Discover screen; the standalone dev book-list is gone; in the dev loop, open a book via Discover → `/reader/{id}` (and `/inspector/{id}` directly by URL if needed).
- [ ] **Step 2:** Grep for stale references: `rg -n "internal/library|dev.*library" docs CLAUDE.md`. Resolve any remaining.
- [ ] **Step 3:** Commit (`docs: point dev loop at Discover for /library`).

## Task 13: Full verify

- [ ] **Step 1:** Run `./bin/suhuf verify` (affected: `web` → lint, tsc, vitest, build). Expected: passes. Fix failures.
- [ ] **Step 2:** Final visual pass: `/dashboard` and `/library` at desktop + mobile; screenshot both for the PR.
- [ ] **Step 3:** Confirm with the user, then `./bin/suhuf ship` and open a PR.

---

## Self-review

- **Spec coverage:** data seam (T1–T4), dashboard screen incl. stats/continue-reading/library-tabs/recommended (T5–T8), Discover screen incl. search/genre/sort (T9–T10), responsive verify (T8/T10), empty/cover/no-match states (T5/T7/T9), docs+cleanup/delete dev tool (T10/T12), testing (T3 pure logic; pages via preview), coordination notes (header). All mapped.
- **Deliberate spec refinement:** the spec's "render smoke test per page" is replaced by preview-based visual verification because the Vitest env is `node` and adding jsdom for two pages is unjustified. Pure logic is still unit-tested (T3). Flag to user if they want jsdom render tests instead.
- **Type consistency:** `LibraryStatus`, `DiscoverQuery`/`DiscoverSort`, `BookIdentity`, and accessor names (`getStats`, `getContinueReading`, `getLibrary`, `getRecommended`, `getGenres`, `getDiscover`) are defined in T1/T4 and reused verbatim in T5–T10.
- **Placeholder scan:** none — every task names exact files, commands, and expected outcomes.
