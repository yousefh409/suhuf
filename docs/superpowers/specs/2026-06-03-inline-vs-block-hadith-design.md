# Inline-vs-block hadith structure (issue #14)

## Problem

`ingestion/parse.py` does not respect the source's inline-vs-newline layout
for hadith. The agreed format contract is:

> A block = one source line/paragraph. Sub-parts *within* a line are labeled
> spans, not separate blocks.

- A hadith on **one running source line** should be **one block** with
  `isnad` / `matn` / `takhrij` (and `quran`) as inline **spans**.
- A hadith laid out across **separate lines** should be **separate blocks**,
  one per line.

Today the parser does neither correctly for the inline case: when a `$RWY$`
paragraph contains an inline `@MATN@`, the marker is swallowed as a literal
token and the whole thing becomes a single `isnad` block. The separate-line
case already emits separate `isnad` / `matn` blocks.

Separately, most real OpenITI books carry **no** native `@MATN@` tags, so a
running-line hadith parses as one `prose` block and the Claude annotation pass
can only relabel the whole block to a single type — it cannot subdivide it
into isnad/matn/takhrij.

## Scope

Two paths, both in this work:

1. **Native parser path** — `parse.py` detects inline vs separate `@MATN@`
   and emits spans-or-blocks accordingly.
2. **Claude path** — `annotate.py` gains `isnad`/`matn`/`takhrij` as inline
   span labels so the model can structure running-line hadith in untagged
   books.

Out of scope: reader rendering (already pre-wired) and any new block type.

## Representation

The reader is already built to consume the inline shape. `web/src/lib/reader/
types.ts` lists `isnad`/`matn`/`takhrij` in both `BlockType` and `SpanLabel`;
`spanStyles.ts` marks them inline-styled (`reader-span-*`); `TokenText.tsx`
renders them and applies the transmission-verb accent inside inline isnad
spans. So:

- A running-line hadith → **one `prose` container block** carrying
  `isnad` / `matn` / `takhrij` / `quran` spans over token ranges.
- No new block type is introduced. (`hadith` was considered and rejected: it
  is absent from `BlockType` and would force a new renderer case for no gain.)

## Detection signal

In `parse.py`, one "source line/paragraph" equals one assembled `pending_text`
dispatch (after `~~` continuation lines are joined). That yields a clean rule:

- **Inline** — `@MATN@` appears in the *same dispatched paragraph* as the
  `$RWY$` opener → emit one `prose` block with spans.
- **Separate** — `@MATN@` arrives in a *later* dispatch while `in_hadith` is
  set → emit separate `isnad` / `matn` blocks (current behavior, preserved).

A `~~`-wrapped hadith stays one logical paragraph (continuations are joined
before dispatch), so it is correctly treated as inline.

## Changes

### `ingestion/parse.py`

Fix the `$RWY$` branch so that when its paragraph contains `@MATN@`:

- Strip the `@MATN@` marker (it never becomes a token).
- Build one `prose` block whose tokens are all the hadith words.
- Add spans over token ranges:
  - `isnad` — words before `@MATN@`.
  - `matn` — words after `@MATN@`, up to a takhrij boundary if present.
  - `takhrij` — from a leading takhrij keyword (`_TAKHRIJ_KEYWORDS`:
    رواه / أخرجه / …) found in the matn tail, to the end.
  - `quran` — via the existing `_extract_inline_quran` run on the matn
    portion, so embedded ayāt keep their citation-anchored spans.
- Carry the hadith `number`.

The separate-line path (the existing `@MATN@`-in-later-dispatch branch) is
unchanged.

### `ingestion/annotate.py`

- Add `isnad`, `matn`, `takhrij` to `SPAN_LABELS`.
- Define them in the system prompt, with guidance: for a running-line hadith,
  emit inline isnad/matn/takhrij **spans**; for a separate-line hadith,
  **relabel** the whole block — not both.
- Existing merge logic already keeps parse-emitted spans authoritative over
  model spans; no change there.

### `ingestion/models.py`

- Update the `Span.label` comment to include `isnad | matn | takhrij`
  (the field is a free `str`; documentation only).

## Testing

`ingestion/tests/`:

- Inline `@MATN@` hadith → one `prose` block; correct isnad + matn span
  ranges; `@MATN@` marker absent from tokens; `number` preserved.
- Inline with a takhrij keyword → additional `takhrij` span with correct
  boundary.
- Inline with an embedded `{ayah} [sura:ayah]` citation → `quran` span
  coexists with isnad/matn spans.
- Separate-line `@MATN@` → two blocks (`isnad`, `matn`) — regression guard.
- annotate: `SPAN_LABELS` includes the three; a stubbed model response with
  isnad/matn spans applies to a prose block; a parse-emitted span wins over an
  overlapping model span.

## Follow-on (separate execution, not this spec)

Clone the OpenITI RELEASE for the four target books, run real ingestion with
`--dump web/data --dry-run`, then run the precision/recall eval described in
`docs/superpowers/plans/2026-04-30-claude-annotation-pass.md`.
