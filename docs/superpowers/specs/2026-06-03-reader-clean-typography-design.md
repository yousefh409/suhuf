# Reader: Clean Edition typography pass

## Goal

Bring the internal reader (`/reader/[openiti_id]`) to production typeset-book
quality. The structure already exists — block types, themes, toggles, footnotes,
poetry. This effort is a **typography and rendering polish pass**, not a rewrite,
plus one format capability: honoring the source's inline-vs-newline layout.

Direction chosen: **Clean Edition** — hierarchy from space, size, and weight;
restrained accents; no decorative boxes or ornament. Readability is the first
constraint: no treatment may reduce legibility.

Tap-to-popup reference cards are out of scope (tracked in #11).

## Decisions

### Reading face
- Switch the Arabic face to **Scheherazade New**, loaded with real **400 and 700**
  weights. This replaces Amiri, which only loaded 400 and was being faux-bolded
  for headings and matn (muddy strokes). DM Sans stays for chrome, labels, and
  numerals; other site fonts are untouched.
- Body around 21px, line-height ~1.95, centered measure ~44rem, comfortable side
  margins. Tashkeel continues to fade via `opacity`, never alpha color.
- Muted and faint text stay above a legible contrast floor; "small" text
  (takhrij, footnotes) never drops below a comfortable reading size.

### Inline-vs-block layout (the core format rule)
The reader must mirror how the source laid text out, rather than forcing every
hadith part and ayah onto its own line.

> **A block = one source line/paragraph. Sub-parts within a line are spans, not
> separate blocks.**

- Two render paths, sharing the same visual styling:
  - **Display path** — separate blocks (e.g. an `isnad` block, a `matn` block)
    each render on their own line, as today.
  - **Inline path** — a single block carrying labeled spans renders as one
    flowing paragraph, with the sub-parts styled inline.
- `SpanLabel` gains `isnad`, `matn`, `takhrij` (joining the existing `quran`).
  The reader styles these labels consistently whether they appear as a display
  block or an inline span: gold transmission verbs, bold matn, faint takhrij,
  green ayah.
- The sample fixture is hand-authored to demonstrate both shapes: one inline
  hadith and one block hadith, plus an inline ayah and a block ayah.
- Producing this distinction from real OpenITI source line structure is the
  ingestion parser's job and is deferred to **#14**. This effort only builds the
  reader's ability to render both shapes and a sample that exercises them.

### Per-element treatment
- **Headings** — hierarchy by space, not ornament.
  - Level 1: centered, bold, larger, generous letter-spacing, a faint parent
    "kicker" above, a thin hairline rule under the block, large top margin.
  - Level 2: centered, bold, smaller than L1, modest spacing, no rule.
  - Level 3+: centered or inline, bold, near body size.
- **Hadith (display path)** — faint sans **margin numeral** (drop the inline
  "N -" hyphen); muted isnad with gold transmission verbs; true-bold matn as the
  visual anchor; small faint takhrij beneath.
- **Qur'an** — block ayahs: centered, deep green, slightly larger, framed by
  faint gold ﴿ ﴾ markers, with breathing room — **no filled box**. Inline ayahs:
  deep green text only, **no highlight box** (the current tint interrupts running
  prose); an optional hair-thin underline at most.
- **Poetry** — two hemistichs on a centered axis with a real gutter,
  baseline-aligned, a restrained center divider, consistent rhythm between
  couplets.
- **Footnotes** — at section bottom, above a thin rule; small but legible; gold
  marker; hanging marker alignment. Inline refs are small gold superscripts.
- **Prose** — the shared baseline measure and rhythm; dates and reference labels
  render plain (no chips, no inline decoration).

### Themes
All three themes (paper / sepia / night) carry the new type and treatments. Green
and gold accents already have per-theme values; new styling reuses the existing
`--reader-*` tokens.

## Scope

### In scope (reader, `web/`)
- Arabic font swap to Scheherazade New (400/700) in the font setup and reader
  CSS.
- Reader-mode CSS refinement across headings, hadith, Qur'an (block + inline),
  poetry, footnotes, prose, and global type/measure.
- Extend `SpanLabel` (`web/src/lib/reader/types.ts`) with `isnad` / `matn` /
  `takhrij` and render inline spans for them.
- Small JSX adjustments in the reader block/scroll components to support the
  inline path and the margin numeral.
- Hand-author the sample fixture to exercise inline and block shapes.

### Out of scope
- Inspector mode, and all existing toggles (tashkeel, themes, page markers,
  cards, recite) — behavior unchanged.
- `lib/reader/queries.ts` and the data pipeline.
- Ingestion parser inline-vs-block detection — deferred to **#14**.
- Tap-to-popup reference cards — **#11**.

## Components affected

- Font setup (`web/src/app/layout.tsx`) — swap Amiri → Scheherazade New, real
  weights.
- `web/src/app/globals.css` — reader type tokens and the `reader-*` styling.
- `web/src/lib/reader/types.ts` — `SpanLabel` additions.
- `web/src/components/reader/Block.tsx`, `TokenText.tsx`, `ChapterScroll.tsx` —
  inline-span styling, display vs inline paths, margin numeral.
- Sample fixture under `web/data/` (and its seed source) — demonstrate both
  shapes.

## Testing / verification

- Existing reader unit tests (`web/src/lib/reader/*.test.ts`) stay green; extend
  where span-label handling changes.
- Visual verification in all three themes via the seeded sample at
  `/reader/Sample.Taxonomy`: confirm inline hadith, block hadith, inline ayah,
  block ayah, headings by level, poetry, and footnotes all read cleanly and
  legibly.
- Run `./bin/suhuf verify` (lint / typecheck / vitest on the affected `web`
  package) before shipping.

## Success criteria

- The reader reads like a carefully typeset book, not a generic page, in every
  theme.
- A hadith or ayah that was inline in the source renders inline; one that was on
  its own line renders on its own line.
- No element is harder to read than it is today; the Qur'an highlight box is gone
  in favor of color + markers.
- Matn and headings use a real bold weight (no faux bold).
