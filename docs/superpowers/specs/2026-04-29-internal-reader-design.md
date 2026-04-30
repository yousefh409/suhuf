# Internal Web Reader & Inspector — Design

## Overview

A hidden Next.js route inside `web/` that reads ingested OpenITI books from Supabase. Two distinct modes share routing and rendering: a clean **Reader** for prototyping the eventual public reading experience, and an **Inspector** that overlays ingestion artifacts (block types, token IDs, tashkeel diff, raw JSON) so the ingestion pipeline can be refined against real output.

This is internal-only for now — URL obscurity, no public link, robots disallow. No auth, no public navigation entry.

**Not in scope**: search, bookmarks, highlights, accounts, real auth, mobile polish, flag-to-DB workflows, public marketing of the reader, RTL/font polish beyond a baseline that reads well.

## Goals

1. Read ingested books in Arabic with sensible RTL typography, with and without tashkeel.
2. Surface ingestion artifacts so parse and tashkeel issues are visible at a glance.
3. Lay foundation for the eventual public reader (data layer, routing, block rendering primitives).

## System Architecture

```
┌────────────────────────────────────────────┐
│  Next.js (web/)                            │
│  /internal/library                         │
│  /internal/reader/[openiti_id]/[ch]        │
│  /internal/inspector/[openiti_id]/[ch]     │
├────────────────────────────────────────────┤
│  web/src/lib/reader/queries.ts             │
│  web/src/lib/reader/types.ts               │
│  Server components → getSupabase()         │
├────────────────────────────────────────────┤
│  Supabase                                  │
│  authors / books / chapters / pages        │
│  (populated by `python -m ingestion`)      │
└────────────────────────────────────────────┘
```

## Routing

```
/internal/library                              # book index
/internal/reader/[openiti_id]                  # → redirects to first chapter
/internal/reader/[openiti_id]/[ch_index]       # reader: chapter scroll
/internal/inspector/[openiti_id]               # → redirects to first chapter
/internal/inspector/[openiti_id]/[ch_index]    # inspector: same chapter, overlays on
```

- `[openiti_id]` is the OpenITI URI (e.g. `0676Nawawi.ArbacunaNawawiyya`). URL-encode the dot as `%2E`. We pick `openiti_id` over UUID because it is human-typeable and stable across re-ingests.
- `[ch_index]` is the chapter's `sort_order` column (1-indexed integer).
- A header toggle on every page swaps Reader↔Inspector for the same `(openiti_id, ch_index)`. Scroll position is preserved via the URL hash (e.g. `#p42-b3`).
- The two modes share data fetching and block rendering primitives; only the rendering layer differs.

### Books with no chapters

Some OpenITI works ship without chapter markers. To keep one URL shape, the query layer **synthesizes fake chapters** when the `chapters` table is empty for that book — one synthetic chapter per volume, titled `Volume N`, with `page_number` set to that volume's first page and `sort_order` running 1..N. This is purely a query-time concern; no DB writes.

## Hiding it

URL obscurity only. No middleware gate, no auth check, no public link.

- Add `Disallow: /internal/` to `web/public/robots.txt`.
- Add `noindex` meta to all `/internal/*` pages.
- Layout adds a small `INTERNAL` badge so it is visually obvious you're in the dev surface.

When the project gains real users we revisit and add proper auth — out of scope here.

## Data Layer

### Types: `web/src/lib/reader/types.ts`

TypeScript mirrors of the ingestion Pydantic models. `Block` is a discriminated union on `type`.

```ts
type BlockType =
  | "prose" | "hadith" | "isnad" | "matn"
  | "poetry" | "biography" | "heading";

type Token = { id: string; text: string; text_raw?: string };

type Block =
  | { key: string; type: "poetry"; hemistichs: Token[][][]; metadata?: object | null }
  | { key: string; type: Exclude<BlockType, "poetry">; tokens: Token[]; metadata?: object | null };
```

`text_raw` is optional. It is populated only when tashkeel changed the token's text (see "Ingestion change" below).

### Queries: `web/src/lib/reader/queries.ts`

Server-only module, uses `getSupabase()`.

- `listBooks()` → `BookListItem[]` (joins authors): `{ openiti_id, title_ar, title_lat, author_name_ar, total_pages, total_volumes, has_tashkeel }`.
- `getBook(openiti_id)` → book row + author row.
- `getChapters(book_id)` → `Chapter[]`. If empty, returns synthesized per-volume entries by querying distinct `volume` values from `pages`.
- `getChapterPages(book_id, ch_index)` → `Page[]` covering the chapter's range:
  - Find `pages` rows with `(volume, page_number)` ≥ this chapter's start and `<` next chapter's start (or end of book).
  - Volume-aware: if a chapter spans volumes, pages are returned in volume-then-page order.

All queries are read-only and run server-side. No client-side Supabase access.

## Reader Mode

### Layout & typography

- `dir="rtl"` on the article element.
- Body font: **Amiri** via `next/font/google`. Fallback: system Arabic.
- Container: max-width readable column (~720px), generous line-height, white-on-near-white background.
- Sticky header: book title, chapter title, mode toggle (Reader|Inspector), tashkeel toggle.
- Sticky footer: prev/next chapter buttons + chapter list trigger.
- Chapter list: `<details>` drawer (no extra deps) listing all chapters with `sort_order` and indent by `level`.

### Block rendering

| Type        | Element                                | Notes                                          |
|-------------|----------------------------------------|------------------------------------------------|
| `heading`   | `<h2>`/`<h3>` sized by `level`         | Bold, generous top margin                      |
| `prose`     | `<p>` leading-relaxed                  | Default                                        |
| `hadith`    | `<div>` border-r-2                     | Catch-all for hadith content not split further |
| `isnad`     | `<div>` border-r-2 text-muted          | Chain of narrators, slightly muted             |
| `matn`      | `<div>` border-r-2 font-medium         | The hadith statement, slightly emphasized      |
| `poetry`    | `<div>` two-column grid                | Hemistichs centered; verse gap                 |
| `biography` | `<aside>` background-tinted            | Subtle tint, smaller spacing                   |

### Page boundaries

Faint horizontal rule with `V01P042` label, `text-xs text-muted-foreground`. Anchor target `id="v{vol}p{page}"` for hash navigation.

### Tashkeel toggle

- Header button: "Tashkeel: On/Off".
- Persisted in `localStorage` under `suhuf.reader.tashkeel`.
- When off: strip the eight diacritic codepoints (U+064B..U+0652) client-side via regex on rendered text. Implementation: a `useTashkeel()` hook that reads the toggle, plus a `<TokenText>` component that conditionally strips. No re-fetch.

## Inspector Mode

Inspector mode reuses Reader's components and layout, then layers overlays:

### (a) Block outlines

Each block renders inside a wrapper with:
- `data-block-type={type}` attribute.
- Thin border colored per type (palette in `web/src/lib/reader/colors.ts`).
- Corner badge: `prose · b3` (type · key).

### (b) Token IDs

Every token rendered as `<span data-token-id={id}>`. Native `title={id}` for hover tooltip. Click handler copies to clipboard via `navigator.clipboard.writeText`. Visual cue: dotted underline on hover.

### (c) Tashkeel diff

Header toggle: "Diff: On/Off". When on, every token whose `text_raw` differs from `text` renders the raw form in `text-zinc-400 line-through` directly above the diacritized form (small leading). Tokens without a `text_raw` (no tashkeel change) render unchanged.

### (d) Page boundaries

Same as reader, but more prominent: solid rule, label in a pill.

### (e) Raw JSON pane

Right-side drawer (slide-out). For each visible page: a `<details>` showing `JSON.stringify(content_blocks, null, 2)` in a styled `<pre>`. No syntax highlighting library — keep it dependency-free for v1.

## Ingestion Change

Inspector's tashkeel diff requires preserving the pre-tashkeel form. The only viable spot is the token level (page-level `content_plain` would lose alignment).

Change: add an optional `text_raw: str | None` field to `Token` in [ingestion/models.py](ingestion/models.py). [ingestion/tashkeel.py](ingestion/tashkeel.py) populates `text_raw` with the original `text` **only when** the diacritized form differs:

```python
new_tokens = [
    Token(id=t.id, text=w, text_raw=t.text if t.text != w else None)
    for t, w in zip(block.tokens, result_words)
]
```

Backwards compatibility: existing rows (without `text_raw`) render fine — diff just shows nothing for them. Re-ingesting a book populates `text_raw`. No migration needed.

## Schema Reconciliation

[web/supabase-schema.sql](web/supabase-schema.sql) currently only defines waitlist tables. The ingestion-target tables (`authors`, `books`, `chapters`, `pages`) live in Supabase but are not tracked in this repo.

As part of this work: add `create table if not exists` blocks for those four tables to `web/supabase-schema.sql`, derived from the columns ingestion actually upserts ([ingestion/upload.py](ingestion/upload.py)). Goals:

- Document the contract one source.
- Future schema changes have a place to live.
- Idempotent: if the tables already exist, the file is a no-op.

This is documentation-only — it does not change runtime behavior.

## File Layout

```
web/src/
  app/
    internal/
      layout.tsx                              # INTERNAL badge, noindex
      library/page.tsx                        # book index
      reader/
        [openiti_id]/
          page.tsx                            # → redirect to first chapter
          [ch_index]/page.tsx                 # reader chapter view
      inspector/
        [openiti_id]/
          page.tsx                            # → redirect to first chapter
          [ch_index]/page.tsx                 # inspector chapter view
  lib/
    reader/
      types.ts                                # shared TS types
      queries.ts                              # server-only Supabase queries
      colors.ts                               # block-type palette
  components/
    reader/
      ChapterScroll.tsx                       # the rendered article
      Block.tsx                               # block renderer (mode-aware)
      TokenText.tsx                           # token + tashkeel + ID overlay
      PageBoundary.tsx
      ChapterDrawer.tsx
      InspectorJsonDrawer.tsx
      ModeToggle.tsx
      TashkeelToggle.tsx
  public/
    robots.txt                                # add Disallow: /internal/
```

`Block.tsx` accepts a `mode: "reader" | "inspector"` prop and conditionally adds the overlays. This keeps the rendering logic in one place rather than duplicating per mode.

## Testing

- Unit tests for `queries.ts` synthesized-chapter logic (book with chapters → real chapters; book without → one chapter per volume).
- Unit tests for the diacritic-strip regex (idempotent, doesn't strip non-Arabic).
- A smoke test that renders one chapter against a fixture page payload and asserts block types render with the right elements/borders.
- No e2e — internal tool, manual verification is enough for v1.

## Out of Scope

- Search, bookmarks, highlights, annotations.
- User accounts, real authentication.
- Public navigation links to `/internal/*`.
- Mobile-specific polish (must not break, but desktop is primary).
- Flag-block-for-review workflows (deferred until inspector is used in anger).
- Word-level i'rab/translate features — those belong to the future public reader, separate spec.
- Re-ingestion driven by the inspector (e.g. a "fix and re-run" button).
- Multi-book diffing or comparison views.

## Open questions

None blocking. The tashkeel-diff requires re-ingesting any book whose tokens were tashkeeled before this change — that's fine; we'll re-run on the small starter set.
