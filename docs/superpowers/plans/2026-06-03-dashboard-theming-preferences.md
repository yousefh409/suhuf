# Dashboard polish + app-wide theming and preferences — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish the dashboard and Discover screens, and ship an app-wide theming and reading-preferences system controlled from a new Settings page and the avatar menu.

**Architecture:** A single typed preferences object is the source of truth. It is read server-side from a cookie in the root layout so the theme applies with no flash, mirrored to a Supabase `user_preferences` table for cross-device sync, and exposed to client components through a provider. The reader's existing localStorage theming is retired and folded into this one system.

**Tech Stack:** Next.js 16.2.x (App Router, server components, `next/headers` cookies, `next/font`), Tailwind v4 (CSS-variable tokens), Supabase (Postgres + RLS), vitest.

**Spec:** `docs/superpowers/specs/2026-06-03-dashboard-theming-preferences-design.md`

---

## Conventions and guardrails (read before starting)

- **Non-standard Next.js.** `web/AGENTS.md` requires reading the relevant guide in `web/node_modules/next/dist/docs/` before writing cookie, server-component, route-handler, font, or middleware code. Do not assume training-data APIs.
- **Shipping.** Commit freely on this branch. Do not run raw `git push`; the project uses `./bin/suhuf ship`. Run `./bin/suhuf verify` (affected packages: lint, tsc, vitest, build) before declaring a phase done.
- **DB conventions** (from `supabase/migrations/20260603000000_reading_sessions.sql`): `user_*` table, `user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE`, `ENABLE ROW LEVEL SECURITY`, owner-only policy `USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id)`. Migration filenames are timestamp-prefixed in `supabase/migrations/`.
- **Gating lives in two places**: a route under the `(app)` group AND its prefix in `web/src/lib/proxy-paths.ts` `PROTECTED_PREFIXES`.
- **Design taste:** parchment/ink palette, Scheherazade New as the default Arabic face, readability over ornament. Keep all new chrome on the token system, never raw zinc/grey.
- **Verify visually** with the preview tools after UI changes (the `web` launch config exists). Do not claim visual work done without a screenshot.

## File structure

Created:
- `web/src/lib/preferences/types.ts` — `Preferences` type, allowed values, `DEFAULT_PREFERENCES`.
- `web/src/lib/preferences/serialize.ts` — parse/serialize cookie JSON; validate and fill defaults.
- `web/src/lib/preferences/attributes.ts` — map a `Preferences` to the set of `html` data-attributes and the active Arabic-font CSS value.
- `web/src/lib/preferences/cookie.ts` — cookie name constant; server reader (`next/headers`) and client writer.
- `web/src/lib/preferences/server.ts` — Supabase read/upsert of the user's row.
- `web/src/lib/preferences/merge.ts` — the DB-wins-or-seed reconciliation rule.
- `web/src/components/preferences/PreferencesProvider.tsx` — client context, `usePreferences()` hook, write-through logic.
- `web/src/app/api/preferences/route.ts` — GET/PUT sync endpoint for the signed-in user.
- `web/src/components/dashboard/ProfileMenu.tsx` — avatar dropdown.
- `web/src/components/dashboard/discover/SortMenu.tsx` — sort icon button + dropdown.
- `web/src/app/(app)/settings/page.tsx` — Settings page.
- `web/src/components/settings/*` — appearance and reading controls, account section.
- `supabase/migrations/20260603100000_user_preferences.sql` — the table + RLS.

Modified:
- `web/src/app/layout.tsx` — read cookie, stamp `html`, load fonts, wrap in provider.
- `web/src/app/globals.css` — theme blocks and size/spacing/font variable blocks; repoint reader selectors.
- `web/src/components/dashboard/DashboardHeader.tsx` — greeting, remove search, host `ProfileMenu`.
- `web/src/components/dashboard/discover/DiscoverSearch.tsx` — use `SortMenu`.
- `web/src/components/reader/ReaderThemeShell.tsx`, `ThemeToggle.tsx`, `ChapterScroll.tsx`, `TashkeelToggle.tsx` — unify onto the global system.
- `web/src/lib/proxy-paths.ts` — add `/settings` to `PROTECTED_PREFIXES`.

---

## Phase 1 — Visual polish (independent, ships without the prefs system)

### Task 1.1: Library sort becomes a sort-icon dropdown

**Files:** Create `web/src/components/dashboard/discover/SortMenu.tsx`; Modify `web/src/components/dashboard/discover/DiscoverSearch.tsx`.

- [ ] **Step 1:** Build `SortMenu` as a client component: a compact icon button using a real sort glyph from lucide-react (`ArrowUpDown`), styled to match the parchment pill (`bg-parchment-warm`, `border-ink/10`, `rounded-xl`). Clicking opens a small dropdown listing the three sort options; the active one is marked. Close on outside-click and Escape. Selection calls back with the chosen `DiscoverSort`.
- [ ] **Step 2:** Replace the `SlidersHorizontal` + native `<select>` block in `DiscoverSearch` with `SortMenu`, keeping the existing URL-param behavior (`sort` param, `relevance` clears it). Keep the `SORT_OPTIONS` list as the single source.
- [ ] **Step 3:** Verify in preview on `/library`: the control reads as a sort icon, opens, selects, updates the URL, and closes on outside-click. Screenshot.
- [ ] **Step 4:** Commit: `feat(discover): replace sort select with sort-icon dropdown`.

### Task 1.2: Remove the dead dashboard search icon

**Files:** Modify `web/src/components/dashboard/DashboardHeader.tsx`.

- [ ] **Step 1:** Remove the search `<button>` and the now-unused `Search` import.
- [ ] **Step 2:** Verify the header still lays out correctly with only the avatar on the right. Screenshot.
- [ ] **Step 3:** Commit: `chore(dashboard): remove non-functional search icon`.

### Task 1.3: Dashboard greeting header

**Files:** Modify `web/src/components/dashboard/DashboardHeader.tsx`; Modify `web/src/app/(app)/dashboard/page.tsx` (pass any name/email needed).

- [ ] **Step 1:** Replace the flat "Library" title with a greeting. Use a time-of-day greeting line plus a name derived from the user (use the email local-part when no display name exists). Keep the serif scale and the existing layout slot. Pass whatever is needed from the page (it already loads `user`).
- [ ] **Step 2:** Verify in preview; confirm it reads well and does not overflow on small widths. Screenshot.
- [ ] **Step 3:** Commit: `feat(dashboard): greeting header in place of static title`.

### Task 1.4: Hover/focus/transition polish pass

**Files:** Modify the dashboard/discover components that render interactive chrome: `DashboardHeader.tsx`, `discover/DiscoverHeader.tsx`, `discover/GenreChips.tsx`, `BookCard.tsx`, `LibraryTabs.tsx`, `ContinueReading.tsx` resume link, `SortMenu.tsx`.

- [ ] **Step 1:** Add consistent, subtle states: `hover:` background/opacity shifts on buttons, chips, tabs, and cards; visible `focus-visible:` rings for keyboard users; short `transition` on color/opacity/transform. Keep everything on palette and restrained.
- [ ] **Step 2:** Verify with preview: hover and keyboard-tab through the header, chips, tabs, and a book card. Screenshot a couple of states.
- [ ] **Step 3:** Commit: `style(dashboard): consistent hover and focus states`.

- [ ] **Phase 1 gate:** run `./bin/suhuf verify`; confirm lint/tsc/vitest/build pass for `web`.

---

## Phase 2 — Preferences foundation (cookie + provider + html attrs + CSS)

### Task 2.1: Preferences model and serialization (TDD)

**Files:** Create `web/src/lib/preferences/types.ts`, `web/src/lib/preferences/serialize.ts`; Test alongside in `web/src/lib/preferences/__tests__/serialize.test.ts` (match existing vitest layout).

- [ ] **Step 1 (test first):** Specify, as failing tests: parsing valid cookie JSON returns the object; unknown/invalid field values fall back to the per-field default; missing fields are filled from `DEFAULT_PREFERENCES`; malformed JSON returns full defaults; serialize→parse round-trips. Defaults: theme `paper`, textSize `m`, arabicFont `scheherazade`, lineSpacing `comfortable`, tashkeel `true`.
- [ ] **Step 2:** Run the tests, confirm they fail.
- [ ] **Step 3:** Define the `Preferences` type and allowed-value sets in `types.ts`; implement parse/serialize with validation in `serialize.ts`.
- [ ] **Step 4:** Run tests, confirm pass.
- [ ] **Step 5:** Commit: `feat(prefs): preferences model and validated serialization`.

### Task 2.2: Preferences → html attributes mapping (TDD)

**Files:** Create `web/src/lib/preferences/attributes.ts`; Test `web/src/lib/preferences/__tests__/attributes.test.ts`.

- [ ] **Step 1 (test first):** Failing tests asserting a `Preferences` maps to the expected attribute bag: `data-app-theme`, `data-text-size`, `data-line-spacing`, `data-arabic-font`. Assert every theme/size/spacing/font value produces the matching attribute string.
- [ ] **Step 2:** Run, confirm fail.
- [ ] **Step 3:** Implement the pure mapping function.
- [ ] **Step 4:** Run, confirm pass.
- [ ] **Step 5:** Commit: `feat(prefs): map preferences to html data attributes`.

### Task 2.3: Cookie helpers

**Files:** Create `web/src/lib/preferences/cookie.ts`.

- [ ] **Step 1:** Read the Next.js cookies guide under `web/node_modules/next/dist/docs/`. Define the cookie name constant. Implement a server-side reader (via `next/headers`) returning a validated `Preferences` (defaults when absent) and a client-side writer that sets the cookie with a long max-age and `path=/`.
- [ ] **Step 2:** Confirm types compile (`tsc`).
- [ ] **Step 3:** Commit: `feat(prefs): cookie read/write helpers`.

### Task 2.4: CSS theme and reading-variable blocks

**Files:** Modify `web/src/app/globals.css`.

- [ ] **Step 1:** Add `[data-app-theme="paper"|"sepia"|"night"]` blocks that override the base `--color-*` tokens (parchment family, ink, gold, cta-dark, dark) so existing utility classes restyle automatically. Reuse the reader's existing sepia/night values as the reference palette. Within the same blocks, also set the reader `--reader-*` tokens (so the reader inherits the same theme from the global attribute).
- [ ] **Step 2:** Add `[data-text-size]` blocks setting a `--reading-size` variable (s/m/l/xl) and `[data-line-spacing]` blocks setting `--reading-leading` (comfortable/compact). Add `[data-arabic-font]` blocks setting `--font-arabic` to the chosen family variable.
- [ ] **Step 3:** Keep `paper` defaults equal to today's values so nothing changes until a non-default theme is selected.
- [ ] **Step 4:** Commit: `feat(theme): app-wide theme and reading-variable css blocks`.

### Task 2.5: Root layout reads cookie, stamps html, loads fonts

**Files:** Modify `web/src/app/layout.tsx`.

- [ ] **Step 1:** Read the Next.js font and metadata guides under `web/node_modules/next/dist/docs/`. Load Amiri and Noto Naskh Arabic via `next/font/google` next to Scheherazade, each exposing its own CSS variable. Add the new variables to the `html` className alongside the existing three.
- [ ] **Step 2:** In the (server) layout, read the preferences cookie and apply the attribute bag from Task 2.2 to the `html` element so first paint is themed. Wrap `children` in `PreferencesProvider` (Task 2.6), passing the server-read preferences as the initial value.
- [ ] **Step 3:** Verify with preview that the default (paper) renders unchanged and the `html` element carries the data attributes (inspect the DOM). Screenshot.
- [ ] **Step 4:** Commit: `feat(theme): apply preferences at the root layout with no flash`.

### Task 2.6: PreferencesProvider and hook

**Files:** Create `web/src/components/preferences/PreferencesProvider.tsx`.

- [ ] **Step 1:** Build a client provider seeded from the server-read preferences. Expose `prefs` and `setPref(key, value)`. On change: update state, rewrite the cookie (Task 2.3), and update the `html` data attributes immediately for instant apply. (DB sync is added in Phase 4; leave a single call-site seam for it.) Export `usePreferences()`.
- [ ] **Step 2:** Temporarily exercise it from a throwaway control or the existing reader toggle to confirm theme flips live without reload. Verify in preview, then remove any scaffolding.
- [ ] **Step 3:** Commit: `feat(prefs): client provider and usePreferences hook`.

- [ ] **Phase 2 gate:** `./bin/suhuf verify` green; manual check that switching the cookie value and reloading shows the theme with no flash.

---

## Phase 3 — Reader unification

### Task 3.1: Reader inherits the global theme

**Files:** Modify `web/src/app/globals.css` (reader selectors), `web/src/components/reader/ReaderThemeShell.tsx`.

- [ ] **Step 1:** Repoint the reader's `[data-reader-theme="x"]` selectors to the global `[data-app-theme="x"]` attribute (the variable definitions already moved into the app-theme blocks in Task 2.4). Remove the dead duplicates.
- [ ] **Step 2:** Strip the localStorage theme read and `StorageEvent` syncing from `ReaderThemeShell`; it no longer owns theme. Keep any non-theme responsibilities it has; if it becomes empty, remove it and its usage.
- [ ] **Step 3:** Verify the reader renders correctly in all three themes by toggling the cookie. Screenshot night + sepia in the reader.
- [ ] **Step 4:** Commit: `refactor(reader): inherit theme from the global preference`.

### Task 3.2: Reader theme toggle writes the global preference

**Files:** Modify `web/src/components/reader/ThemeToggle.tsx`.

- [ ] **Step 1:** Replace the localStorage cycle with `usePreferences().setPref("theme", ...)`, cycling paper→sepia→night. Keep the glyph display reading from the current pref. Remove the now-unused `THEME_KEY` reference here (leave the constant if other code still imports it; otherwise remove from `storageKeys.ts`).
- [ ] **Step 2:** Verify in the reader that cycling the toggle restyles immediately and persists across reload (cookie).
- [ ] **Step 3:** Commit: `feat(reader): theme toggle drives the global preference`.

### Task 3.3: Reader respects size, spacing, and diacritics defaults

**Files:** Modify `web/src/components/reader/ChapterScroll.tsx` (line ~100), `web/src/components/reader/TashkeelToggle.tsx`.

- [ ] **Step 1:** Replace the hard-coded `text-[21px] leading-[1.95]` on the reader article with the `--reading-size` / `--reading-leading` variables (via an inline style or matching utility). Confirm `m`/`comfortable` reproduce today's look.
- [ ] **Step 2:** Make the in-reader tashkeel toggle initialize from `usePreferences().prefs.tashkeel` while keeping its live per-read override behavior. Do not change page-markers/hadith-card/diff toggles.
- [ ] **Step 3:** Verify in preview: changing the cookie's textSize/lineSpacing/tashkeel changes the reader; the in-reader tashkeel toggle still overrides for the session.
- [ ] **Step 4:** Commit: `feat(reader): size, spacing, and tashkeel from preferences`.

- [ ] **Phase 3 gate:** `./bin/suhuf verify` green; reader verified across all three themes and all size/spacing values.

---

## Phase 4 — Supabase cross-device sync

### Task 4.1: user_preferences table and RLS

**Files:** Create `supabase/migrations/20260603100000_user_preferences.sql`.

- [ ] **Step 1:** Define a `user_preferences` table: `user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE`, one column per pref (theme, text_size, arabic_font, line_spacing, tashkeel) with sane defaults matching `DEFAULT_PREFERENCES`, plus `updated_at TIMESTAMPTZ DEFAULT NOW()`. Enable RLS; add the owner-only `FOR ALL` policy. (A jsonb `prefs` column is an acceptable alternative; pick columns for queryability and match the existing style.)
- [ ] **Step 2:** Apply locally and confirm it matches the convention of the reading_sessions migration. Note in the commit how migrations are applied in this project.
- [ ] **Step 3:** Commit: `feat(db): user_preferences table with owner-only rls`.

### Task 4.2: Server read/upsert and sync endpoint

**Files:** Create `web/src/lib/preferences/server.ts`, `web/src/lib/preferences/merge.ts` (+ test), `web/src/app/api/preferences/route.ts`.

- [ ] **Step 1 (test first for merge):** Failing tests for the reconciliation rule in `merge.ts`: when a DB row exists it wins over the cookie; when no DB row exists, the cookie value is returned to seed the DB; field-level fill from defaults for any missing column.
- [ ] **Step 2:** Run, confirm fail; implement `merge.ts`; run, confirm pass.
- [ ] **Step 3:** In `server.ts`, implement `readUserPreferences()` and `upsertUserPreferences()` using the server Supabase client. Read the Next.js route-handler guide under `web/node_modules/next/dist/docs/`, then implement `api/preferences/route.ts`: GET returns the signed-in user's row (or 401 when anonymous); PUT upserts and returns the stored value.
- [ ] **Step 4:** Commit: `feat(prefs): server read/upsert and sync endpoint`.

### Task 4.3: Provider hydration and write-through

**Files:** Modify `web/src/components/preferences/PreferencesProvider.tsx`; the dashboard/settings entry can pass the server-read DB value.

- [ ] **Step 1:** On mount for signed-in users, apply the merge rule: if the server provided a DB row, adopt it and write it back to the cookie + html attributes; if none, seed the DB from the current cookie via the endpoint. Prefer passing the DB row from a server component (dashboard/settings/layout) over a client fetch where possible, to avoid an extra round trip and any flash.
- [ ] **Step 2:** On every `setPref`, in addition to cookie + attributes, debounce a PUT to the sync endpoint when signed in. Anonymous users skip the DB write.
- [ ] **Step 3:** Verify: change a pref while signed in, reload in a different browser/profile pointed at the same account, confirm it syncs; confirm anonymous still works via cookie only.
- [ ] **Step 4:** Commit: `feat(prefs): hydrate from and sync to supabase`.

- [ ] **Phase 4 gate:** `./bin/suhuf verify` green; cross-device sync and anonymous-cookie paths both verified.

---

## Phase 5 — Profile menu and Settings page

### Task 5.1: Profile dropdown

**Files:** Create `web/src/components/dashboard/ProfileMenu.tsx`; remove/absorb `web/src/app/(app)/dashboard/SignOutButton.tsx`.

- [ ] **Step 1:** Build a client dropdown anchored to the avatar: a header showing the signed-in email, a three-swatch quick theme switch wired to `setPref("theme", …)`, a link to `/settings`, and a sign-out action (reuse the existing sign-out logic; restyle on palette, drop the zinc). Close on outside-click and Escape; keyboard accessible.
- [ ] **Step 2:** Remove the standalone `SignOutButton` if fully absorbed.
- [ ] **Step 3:** Verify in preview: menu opens from the avatar, swatches restyle the app live, Settings link navigates, sign out works. Screenshot.
- [ ] **Step 4:** Commit: `feat(dashboard): working avatar profile menu`.

### Task 5.2: Dashboard header hosts the profile menu

**Files:** Modify `web/src/components/dashboard/DashboardHeader.tsx`, `web/src/app/(app)/dashboard/page.tsx`.

- [ ] **Step 1:** Replace the static avatar div with `ProfileMenu`, passing the email/initials already available on the page.
- [ ] **Step 2:** Verify the header renders the greeting (Task 1.3) on the left and the working avatar menu on the right. Screenshot.
- [ ] **Step 3:** Commit: `feat(dashboard): mount profile menu in header`.

### Task 5.3: Settings page and controls

**Files:** Create `web/src/app/(app)/settings/page.tsx`, `web/src/components/settings/*`; Modify `web/src/lib/proxy-paths.ts`.

- [ ] **Step 1:** Add `/settings` to `PROTECTED_PREFIXES`. Confirm the `(app)` group already enforces auth in its layout (gating in two places).
- [ ] **Step 2:** Build the Settings page with three sections. Appearance: theme swatches, text-size control, line-spacing control, Arabic-font picker (each wired to `setPref`, showing the active value, with a small Arabic preview line for the font picker). Reading: diacritics-default toggle. Account: email display and sign out (identity folded in here, per spec).
- [ ] **Step 3:** Verify in preview at `/settings`: each control updates the live app and persists across reload; the page is gated when signed out (redirects to login).
- [ ] **Step 4:** Commit: `feat(settings): preferences control center`.

### Task 5.4: Cross-theme verification and the two open questions

**Files:** none (verification); small follow-up edits if needed.

- [ ] **Step 1:** Walk dashboard, Discover/library, reader, and settings in all three themes via preview. Fix any element that bypasses the token system (e.g. stray emerald dot, white mockup surfaces) so themed surfaces look intentional. Screenshot night + sepia of each.
- [ ] **Step 2:** Check the marketing landing (`/`) in sepia and night. If a non-default theme looks wrong there, scope theming away from the landing (render it fixed-paper) rather than restyling it; record the decision in the spec.
- [ ] **Step 3:** Check the font payload impact of Amiri + Noto Naskh (network panel / build output). If unacceptable, reduce to one extra face and note it.
- [ ] **Step 4:** Commit any fixes: `fix(theme): tidy non-tokenized surfaces across themes`.

- [ ] **Phase 5 gate:** `./bin/suhuf verify` green; full visual pass captured; spec updated if the landing scope changed.

---

## Self-review notes (coverage check against the spec)

- Sort icon, search removal, greeting, hover polish → Phase 1. ✓
- Five-pref model, cookie no-flash, CSS strategy → Phase 2. ✓
- Reader unification (theme, size, spacing, tashkeel default) → Phase 3. ✓
- Supabase table + sync with DB-wins-or-seed rule → Phase 4. ✓
- Profile menu, Settings page with Account folded in, gating → Phase 5. ✓
- Fonts (Amiri, Noto Naskh) → Task 2.5; payload check → Task 5.4. ✓
- "Verify not assume" (landing theming, font payload) → Task 5.4. ✓
- Diacritics default is `true` (matches current reader behavior) → Task 2.1 defaults. ✓
