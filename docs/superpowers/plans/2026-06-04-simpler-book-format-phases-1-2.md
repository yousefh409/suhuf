# Simpler book format: Phases 1-2 implementation plan

**Goal:** Replace the token plus token-ID-span block format with the tagged
format from the design doc, and rewrite the ingestion pipeline so the AI authors
boundary tags. Ends when Phase 2 is complete: books ingest into the tagged
format, the reader renders them at parity, and the accuracy eval reruns clean.

**Design:** `docs/superpowers/specs/2026-06-04-simpler-book-format.md`.

**Architecture:** One canonical `tagged` field per block; `text`, `spans`, and
`lines` are derived by a single compile step. Metadata (`conf`, `ref`, `sub`) is
a resolved span layer. The reader tokenizes at render. The deterministic hadith
logic already on this branch ports forward, emitting tags instead of token spans.

**Tech stack:** Python (ingestion, pytest), TypeScript/Next.js (reader, vitest).

Phase 3 (turath adapter) is tracked separately in issue #22 and is out of scope
here.

---

## Phase 1: Format core and reader parity

Goal: the new format exists end to end and the reader renders a migrated book at
parity, with no pipeline changes yet.

### Step 1: Tag compiler (`ingestion/tags.py`)

- `compile(tagged) -> (text, spans, lines)`: strict stack parser over the tag
  whitelist; strips tags to produce `text`; records each inline tag as a span
  with character offsets (end exclusive) and label only; records `verse` /
  `hemistich` structure as `lines`.
- `render(text, spans, lines) -> tagged`: inverse, re-emits canonical boundary
  tags from offsets. Used to serialize for the AI and to migrate old data.
- Decisions: whitelist is the design's tag set; unknown tag or bad nesting is an
  error; reserved characters `< > &` escape to entities; spans may nest;
  `render` orders overlapping tags by start then by widest-first so nesting is
  well-formed.
- Tests first: round-trip `compile(render(...))` and `render(compile(...))` on
  prose with nested spans, on poetry, on escaped characters, and on the error
  cases.

### Step 2: New models (`ingestion/models.py`)

- `Span`: `start: int`, `end: int`, `label`, optional `sub`, `ref`, `conf`.
- `Block`: `key`, `type` (prose|heading|poetry|quran), `tagged`, derived `text`,
  optional `text_raw`, `spans`, optional `lines`, plus `number`, `level`,
  `parser_type`, `flags`.
- `Page`: `blocks` (renamed from `content_blocks`), `footnotes` as block-shaped
  records.
- Decision: `Token` is removed from the block/page contract. Keep a thin internal
  token notion only inside an adapter if it needs one; it never reaches storage.
- Tests: model construction and JSON round-trip for each block type.

### Step 3: Migration aligner (`ingestion/migrate_format.py`)

- Input: an existing parsed book (tokens plus token-ID spans). Output: the new
  format.
- Steps: join a block's tokens into `text` using the same join the reader used;
  map every span's `start_token_id` / `end_token_id` to character offsets; carry
  `conf`/`sub`/`ref`; for poetry, fold hemistich tokens into `lines`; then
  `render` the canonical `tagged`.
- Decision: deterministic, no AI; this is also how we keep any existing dumped
  data usable.
- Tests: a fixture block with known token-ID spans migrates to the expected
  offsets and tagged string; poetry folds to `lines`.

### Step 4: Reader consumes the new format

- `web/src/lib/reader/types.ts`: mirror the new `Block`/`Span`/`Page`. Remove the
  stored `Token` type from the block union.
- `Block.tsx` / `TokenText.tsx`: tokenize `text` at render; apply spans by offset
  range to mark words; render poetry from `lines`.
- `sentences.ts`: `buildSelectionMap` works from the rendered word list; word
  identity is a derived `{blockKey}:{wordIndex}`.
- Recitation provider: key status on the derived word id.
- Decision: rendering output (visible text, span styling, tap targets) must match
  today; this is parity, not a redesign.
- Tests: the existing reader unit tests adapt to the new shape and pass.

### Step 5: Proof on one book

- Migrate Arba'un (smallest) to the new format, dump it, open the reader.
- Verify: visible text identical to the old render; isnad/matn/entity highlights
  land on the same words; tap and tashkeel toggle work.
- Decision: parity on Arba'un is the Phase 1 exit criterion.

---

## Phase 2: Pipeline emits boundary tags

Goal: ingestion produces the tagged format directly, the AI authors boundary
tags, and the accuracy eval reruns without the truncation and nesting failures.

### Step 1: Deterministic detector emits tags (`ingestion/hadith.py`)

- Port the existing detector to write `isnad`/`matn`/`takhrij` boundary tags into
  a block's `tagged`, with `conf` attached to the resulting span (the detector
  owns `conf`).
- Decision: the cross-block stitching and poetry re-typing logic stays; with one
  block able to hold a whole hadith, prefer emitting one tagged block over
  projecting across blocks where the adapter already keeps the hadith together.
- Tests: the current `test_hadith.py` cases assert on tags/spans in the new shape.

### Step 2: Annotate authors tags (`ingestion/annotate.py`)

- Serialize each block to the AI as its `tagged` boundary text. The model returns
  edited boundary tags. Parse back with `compile`; run the gated merge over the
  tagged boundaries (high-`conf` deterministic boundaries win on conflict).
- Decision: the model sees boundary tags only, never `conf`; the merge enforces
  the gate deterministically. Chunking shrinks because output is compact, which
  removes the 8192 truncation; nested entity tags remove the overlap-drop.
- Tests: gated merge keeps a high-conf isnad boundary against a conflicting model
  edit; a nested `person` inside `matn` survives; relabel of a mistyped poetry
  block still works.

### Step 3: Resolution passes own metadata

- Port quran ref resolution (`quran.py` / `resolve_spans`) to set `ref` on
  `quran` spans by offset. Add a minimal `person` `sub` classifier (lookup or a
  cheap rule set; the format only reserves the field).
- Decision: each field has one owner; passes are idempotent and keyed to span
  content so they survive a recompile.
- Tests: a cited ayah span gets the right `ref`; a known companion gets
  `sub: companion`.

### Step 4: Wire the pipeline and dump

- Pipeline order: adapter -> detector tags -> tashkeel (OpenITI only) -> annotate
  tags -> resolve metadata -> compile -> dump. The dumped files carry `tagged`
  plus derived `text`/`spans`/`lines`.
- Decision: keep the `--dump` dev loop and `--dry-run`; the reader reads the new
  dumped shape directly.

### Step 5: Re-run the accuracy eval

- Rerun the Sonnet hadith-precision judge and the poetry/over-relabel checks on
  the four books.
- Success: no output truncation; entity spans survive inside structural spans;
  low-confidence boundaries improve versus the 47% baseline; real poetry
  preserved.

---

## Success criteria

- Phase 1: Arba'un renders at parity from the migrated tagged format; tag
  compiler and aligner are covered by tests; full ingestion and reader test
  suites pass.
- Phase 2: the four books ingest into the tagged format and render; the accuracy
  eval reruns with the truncation and nesting failures gone and the low-confidence
  tier measurably improved.

## Risks

- The compiler is the load-bearing piece; offset and escaping bugs corrupt
  everything downstream. Mitigate with exhaustive round-trip tests before any
  pipeline change.
- Reader parity can regress subtly (spacing, span edges). Mitigate by diffing the
  rendered text against the old output on the proof book.
- The person `sub` classifier is open-ended; keep it minimal so it does not block
  the phase.
