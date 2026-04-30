# Reader navigation: continuous scroll with anchored pages and chapters

**Status:** Approved
**Date:** 2026-04-30
**Supersedes:** the per-chapter slicing introduced earlier today
(`pagesInChapter` block-index slicing).

## Motivation

The internal reader currently routes per chapter
(`/internal/reader/<id>/<sort_order>`) and slices `content_blocks` so each
chapter view shows only its own hadith/section. That model breaks down when
a single physical page contains several chapter starts (e.g. four hadiths
on Nawawi40 page 57): we either drop content, duplicate it, or split a
page mid-flow.

More importantly, that "one chapter per route" model is non-standard for
classical-text readers. Sefaria, Apple Books, Quran.com, and modern
Islamic reader apps all converge on a different pattern: **one canonical
continuous-scroll view per work, with deep-linkable anchors for both
pages and chapters**. Citation by page is preserved (anchors are stable
URLs); chapter discovery happens through the drawer; reading flow is
uninterrupted.

This spec adopts that pattern.

## Reading model

There is exactly one reader view per book (or per volume for multi-volume
works). It renders the full body top-to-bottom. The user navigates by:

1. **Scrolling** — primary mode of reading.
2. **Anchor links** — clicking a chapter or page in the drawer scrolls
   to its anchor; the URL hash updates.
3. **Direct deep links** — `…/<id>#h-5` lands inside the scroll at
   chapter sort_order 5; `…/<id>#p-V01P054` lands at physical page 54.

There are no per-chapter or per-page sub-routes. There is no mode toggle.
The display always shows the same continuous flow.

## Routes

```
/internal/reader/<id>           ← canonical scroll (all volumes for now)
/internal/inspector/<id>        ← same flow + inspector chrome
/internal/library               ← unchanged
```

Removed:

```
/internal/reader/<id>/<sort_order>      ← deleted
/internal/inspector/<id>/<sort_order>   ← deleted
```

These were internal-only, so deletion is safe. (If we ever want a
"focus on one hadith" study view, that's a separate feature added on
top — out of scope here.)

Multi-volume support is not in this spec. Today every book in
`web/data/` is single-volume; when multi-volume arrives, we'll add
`/v/<n>` segment and per-volume scroll. The anchor scheme already
includes the volume (`p-V01P054`), so deep links survive.

## Anchors

Two anchor families, both rendered as `id` attributes inside the scroll:

- **Page anchor:** `id="p-V<vol2>P<page3>"` (zero-padded, matches the
  visible label e.g. `V01P054`). Lives on the `PageBoundary` element.
- **Chapter anchor:** `id="h-<sort_order>"`. Lives on the heading block
  that starts the chapter — identified by `(page_number, block_index)`
  from the chapter record.

Both anchor IDs are stable as long as the underlying book file doesn't
change structure. They are the primary citation primitives.

## Components

- `web/src/lib/reader/queries.ts`
  - `pagesInChapter` is **deleted** (no longer needed; the scroll renders
    every page).
  - `synthesizeChapters` stays — drawer still groups by volume for
    chapterless books.
  - New helper: `chapterAnchorMap(chapters)` → `Map<pageNumber, Map<block_index, sort_order>>`
    so the renderer can stamp anchor IDs onto heading blocks in O(1).
- `web/src/components/reader/ChapterScroll.tsx`
  - Accepts `chapters: Chapter[]` in addition to `pages`. Uses the
    anchor map to wrap chapter-starting heading blocks with
    `id="h-<sort_order>"`.
  - Otherwise unchanged: still iterates pages → blocks, still emits
    `PageBoundary` per page.
- `web/src/components/reader/PageBoundary.tsx`
  - `id` becomes `p-V<vol>P<page>` (matches label format). Existing `v1p54`
    callsites have none outside this file, so this is a clean rename.
- `web/src/components/reader/ChapterDrawer.tsx`
  - Two tabs: **Chapters** | **Pages**.
  - "Chapters" tab: same hierarchical list, links become anchor links
    (`#h-<sort_order>`) instead of route navigations.
  - "Pages" tab: flat list of pages (`V01P054`, `V01P055`, …) plus a
    page-number jump input. Anchor links (`#p-V01P054`).
  - Highlighting the "current" entry is best-effort: we use
    `IntersectionObserver` on anchor targets to track the topmost visible
    page and chapter, and bold the matching drawer entry. Optional polish;
    not blocking.
- `web/src/app/internal/reader/[openiti_id]/page.tsx`
  - Becomes the canonical reader page. Loads book + chapters + all pages
    via `getBook`, `getEffectiveChapters`, `getAllPagesForBook`. Renders
    `ChapterScroll` with the full set.
- `web/src/app/internal/inspector/[openiti_id]/page.tsx`
  - Same change for inspector.
- `web/src/app/internal/reader/[openiti_id]/[ch_index]/` and
  `web/src/app/internal/inspector/[openiti_id]/[ch_index]/`
  - **Deleted.**

## Data model

Keep `Chapter.block_index` (already added today). It is now the position
where we stamp the `h-<sort_order>` anchor on the heading block — still
useful, just for a different reason.

`pagesInChapter` and its tests are removed.

## Performance / virtualization

Nawawi40 is 38 pages and renders fine without optimization. For larger
works (multi-thousand-page Shamela texts) virtualization will be needed:

- Lazy-load page chunks as the scroll approaches them (pattern: Sefaria,
  React Window, or `IntersectionObserver` + manual chunk render).
- Server can stream page batches; component holds chunk windows.

Out of scope for this spec; called out so future work has a name.

## Migration

1. Delete `[ch_index]` route folders under reader/ and inspector/.
2. Delete `pagesInChapter` and its tests; remove the import from any
   page that used it.
3. Reader/inspector top-level pages render the full scroll with chapters
   passed through.
4. `ChapterDrawer` rewritten with two tabs and anchor links.
5. `PageBoundary` id format updated.
6. Tests: remove `pagesInChapter` cases, add `chapterAnchorMap` cases.
7. Verify in browser: `/internal/reader/<id>#h-7` lands on hadith 7;
   `/internal/reader/<id>#p-V01P054` lands on page 54; drawer
   navigation updates the hash and scrolls.

## Out of scope

- Multi-volume routing.
- Virtualization / lazy chunking.
- Per-book default mode (not needed — only one mode exists).
- "Single-hadith study view" (separate future feature).
- Public reader: this internal pattern will translate, but Supabase
  query path and SSR/streaming concerns get their own spec when we ship
  publicly.
