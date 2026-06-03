# Simpler book format

## Problem

The stored book format is tokens plus token-ID spans. Every block is roughly 50
`{id, text}` objects, and structure (isnad/matn/takhrij) and entities
(person/place/quran) are flat spans addressed by `start_token_id` /
`end_token_id`. This format is the source of truth for the reader, but it is
also the format we force the AI to read and write, and that is where it hurts.

The accuracy eval on Bulugh al-Maram showed three failures that all trace back
to making the model speak this format:

- **Truncation.** Annotate chunks of 60 blocks average 7,999 output tokens
  against an 8,192 cap. Echoing `[index, "word"]` arrays plus index-addressed
  spans is so verbose that JSON output is cut off mid-stream and trailing blocks
  lose their annotations.
- **No nesting.** Spans are flat ranges, so the gated merge drops any model span
  that overlaps a locked one. A narrator name inside a high-confidence isnad is
  thrown away: across all of Bulugh, 1 person span survived inside structured
  blocks versus 12 in unstructured ones.
- **Boundary errors.** The model has to return integer token indices, which is
  exactly the counting task LLMs are weakest at. The low-confidence fallback
  tier scored 47% precision (versus 96% for the marker tier).

The token/span structure exists for good reasons on the reader side
(word-tap, highlighting, tashkeel diff). The mistake is making the AI produce
that same internal representation. A read of the reader code shows it does not
actually need stored tokens: `buildSelectionMap` derives every word-tap field by
splitting the ordered words, `indexSpans` uses token IDs only as a join key, and
recitation keys highlight state by an id that can be derived. So we can simplify
the storage format itself.

## Goals

1. Give the AI a format it produces reliably: mark boundaries, nothing else.
2. Keep a queryable structured representation for search and rendering.
3. Keep the reader whole (tap, highlight, tashkeel diff, recitation) with no
   stored per-word data.
4. Support more than one source: OpenITI today, turath.io next, same target
   format.

## Core decisions

1. **Canonical text is HTML-style boundary tags.** One authored field per block,
   `tagged`. The AI reads and writes only this. Tags carry no attributes.
2. **`text`, `spans`, and `lines` are derived** by a single `compile(tagged)`
   step, regenerated on every write, never hand-edited. One writer, so they
   cannot drift.
3. **No stored per-word tokens.** The reader tokenizes `text` at render time for
   tap, highlight, and recitation. The word-lookup cache is content-addressed,
   not keyed on positional ids.
4. **Metadata is a resolved span layer.** `sub`, `ref`, and `conf` live on the
   derived span, not in the tags. Resolution passes own each field and run
   idempotently. The AI never authors or reads metadata, including `conf`.
5. **Sources land here through adapters.** Each source (OpenITI, turath.io) has a
   thin adapter that emits the page/block skeleton; the shared pipeline does all
   annotation.

## The format

### Book

The top-level document, stored per book. Unchanged from today apart from block
contents.

```jsonc
{
  "metadata": {
    "openiti_id": "0852IbnHajarCasqalani.BulughMaram",
    "title_ar": "بلوغ المرام",
    "author_openiti_id": "0852IbnHajarCasqalani",
    "source": "openiti",                  // provenance: openiti | turath
    "source_id": "0852IbnHajarCasqalani.BulughMaram",
    "source_url": null
  },
  "pages":      [ /* Page */ ],
  "chapters":   [ /* Chapter */ ],
  "enrichment": { "book": { /* … */ }, "author": { /* … */ } },
  "author_data": { /* parsed source author record */ }
}
```

### Page

```jsonc
{
  "page_number": 3,
  "volume": 1,
  "blocks":    [ /* Block */ ],
  "footnotes": [ /* Footnote */ ]
}
```

### Block

The core change. One canonical `tagged` field, three derived fields.

```jsonc
{
  "key": "b43",
  "type": "prose",            // prose | heading | poetry | quran
  "number": "150",            // printed item number, optional
  "level": null,              // heading depth, optional
  "parser_type": null,        // set if a pass re-typed the block

  // CANONICAL: authored by the source adapter, then the tagging passes.
  "tagged": "<isnad>وعن <person>أبي هريرة</person> رضي الله عنه عن النبي ﷺ قال:</isnad> <matn>«سبعة يظلهم الله في ظله يوم لا ظل إلا ظله»</matn> <takhrij>متفق عليه</takhrij>",

  // DERIVED by compile(tagged). Never hand-edited.
  "text":     "وعن أبي هريرة رضي الله عنه عن النبي ﷺ قال: «سبعة يظلهم الله في ظله يوم لا ظل إلا ظله» متفق عليه",
  "text_raw": "وعن ابي هريره رضي الله عنه عن النبي صلى الله عليه وسلم قال: «سبعه يظلهم الله...»",
  "spans": [
    { "start": 3,  "end": 14, "label": "person",  "sub": "companion" },  // sub from resolution pass
    { "start": 0,  "end": 40, "label": "isnad",    "conf": 0.95 },
    { "start": 41, "end": 84, "label": "matn",     "conf": 0.95 },
    { "start": 85, "end": 95, "label": "takhrij",  "conf": 0.95 }
  ],
  "flags": []
}
```

Changes from today:

- No `tokens` array. The word objects collapse to one `text` string.
- `isnad` / `matn` / `takhrij` are no longer block types, only spans. Block types
  shrink to the four the renderer distinguishes. A whole hadith can live in one
  block as nested tags, which removes the need for cross-block stitching.
- Spans are character offsets into `text` (end exclusive) and nest freely.
- `text_raw` is the undiacritized text for the tashkeel diff, parallel to `text`,
  produced by the tashkeel stage, not by `compile`.

### Block, poetry variant

Poetry uses the same tag system. `lines` is a derived projection like `spans`.

```jsonc
{
  "key": "b12",
  "type": "poetry",
  "tagged": "<verse><hemistich>قِفا نَبكِ مِن ذِكرى حَبيبٍ ومَنزِلِ</hemistich><hemistich>بِسِقطِ اللِوى بَينَ الدَخولِ فَحَومَلِ</hemistich></verse>",
  "text":  "قفا نبك من ذكرى حبيب ومنزل بسقط اللوى بين الدخول فحومل",
  "lines": [ ["قِفا نَبكِ مِن ذِكرى حَبيبٍ ومَنزِلِ", "بِسِقطِ اللِوى بَينَ الدَخولِ فَحَومَلِ"] ],
  "spans": []
}
```

### Block, heading variant

```jsonc
{ "key": "b40", "type": "heading", "level": 1, "tagged": "باب صلاة التطوع", "text": "باب صلاة التطوع", "spans": [] }
```

### Span (derived)

```jsonc
{
  "start": 41, "end": 84,   // char offsets into the block text, end exclusive
  "label": "matn",          // isnad|matn|takhrij | person|place|quran|book_ref|hadith_ref|date_hijri|footnote
  "sub":  "companion",      // optional, resolution layer
  "ref":  "7:158",          // optional, resolution layer
  "conf": 0.95              // optional, set by the structural detector
}
```

### Footnote

Block-shaped, so it can carry tags too.

```jsonc
{ "marker": "1", "tagged": "أخرجه <book_ref>البخاري</book_ref> في صحيحه", "text": "أخرجه البخاري في صحيحه", "spans": [ /* … */ ] }
```

### Chapter

```jsonc
{ "id": "ch-12", "title": "باب صلاة التطوع", "level": 1, "page_number": 3, "sort_order": 12, "block_key": "b40" }
```

## Tag grammar

A strict subset, not full HTML. We own both writer and parser.

- Whitelisted tags only. Inline: `isnad matn takhrij person place quran book_ref
  hadith_ref date_hijri footnote`. Poetry structure: `verse hemistich`. An
  unknown tag is a compile error.
- Tags carry no attributes. All metadata (`sub`, `ref`, `conf`) lives on the
  derived span, set by resolution passes.
- Tags nest. The matn quote may contain a `person`, a `quran`, and so on.
- Reserved characters are `<`, `>`, `&`, escaped as `&lt; &gt; &amp;`. Classical
  Arabic text effectively never contains them, so escaping rarely fires.

## compile and the migration aligner

- `compile(tagged)` walks the tag tree and emits `text` (tags stripped), `spans`
  (inline tag offsets, label only), and `lines` (verse/hemistich offsets). It
  validates the tag whitelist and nesting.
- The reverse, `render(text, spans) -> tagged`, re-emits canonical boundary tags.
  This is used to serialize a block for the AI and to migrate existing data.
- A one-time **aligner** migrates today's token-ID spans onto offsets: join the
  token text into the block string, map each `start_token_id` / `end_token_id` to
  its character offset, drop the token objects. Deterministic and testable.

The metadata layer is preserved across a re-compile by re-running the resolution
passes, which key off span content, not position. Resolution passes are cheap or
deterministic (quran ref already exists), so a tagged edit followed by recompile
plus resolve is safe.

## Pipeline

The format layers the pipeline into three stages, each owning one slice.

```
source -> [adapter] -> Book skeleton -> tag boundaries -> resolve metadata -> compile -> reader / Supabase
```

1. **Adapter.** Source-specific. Emits blocks whose `tagged` is the cleanest text
   the source gives, plus any structure the source already marks (headings, item
   numbers, footnotes). No annotations yet.
2. **Tag boundaries.** Shared. The deterministic hadith detector emits
   `isnad`/`matn`/`takhrij` boundary tags. The AI annotate pass adds entity tags
   and corrects low-confidence boundaries. Output is boundary tags only, no
   attributes.
3. **Resolve metadata.** Shared. Each field has one owner that attaches it to the
   span: the detector owns `conf` (it knows the confidence of the boundary it
   found), the quran resolver owns `ref`, the person resolver owns `sub`. The tags
   stay attribute-free; metadata lives on the compiled span.
4. **Compile.** `tagged -> text + spans + lines`.

The confidence-gated merge stays deterministic and post-AI: the model re-tags
freely, and the merge keeps high-`conf` deterministic boundaries where they
conflict. The model does not need to see `conf`.

## Source adapters

The format is the common target. Adding a source is a new adapter plus the shared
pipeline.

### OpenITI

The current `parse.py` becomes the OpenITI adapter: mARkdown to blocks, emitting
`tagged` as clean text plus headings and item numbers. The poetry and ellipsis
heuristics it carries are conversion-artifact handling specific to mARkdown and
stay in this adapter.

### turath.io

A new adapter, and a cleaner starting point than OpenITI raw:

- It serves clean per-page text with volume and page numbers, so no mARkdown
  conversion artifacts and none of the `### $` or ellipsis misparses that caused
  the poetry bugs.
- It carries structured metadata (author, death year, title, categories) that
  feeds `metadata` and `enrichment` directly.
- Many turath books already mark headings and footnotes, which the adapter maps
  to `heading` blocks and footnotes, giving turath books structure before the AI
  runs.

Provenance is recorded in `metadata` (`source`, `source_id`, `source_url`) so
re-ingestion and dedup are sane.

## Reader and storage changes

- `web/src/lib/reader/types.ts`: Block becomes `{ type, tagged, text, text_raw?,
  spans, lines?, … }`. Token type is removed from storage; spans use numeric
  offsets.
- `Block.tsx` / `TokenText.tsx`: tokenize `text` at render, apply spans by offset
  range, key recitation and tap on a derived `{blockKey}:{wordIndex}`.
- `sentences.ts`: `buildSelectionMap` works from the rendered word list rather
  than stored tokens.
- The word-lookup cache key becomes a content hash of `(book_id, word, sentence)`
  using the diacritized forms.
- Supabase: the per-page `content_blocks` JSONB holds the new block shape. No new
  tables.

## Migration

All current book data is dev data, so migration is a re-ingest plus the one-time
aligner for any data we keep. No production data depends on the old shape.

## Out of scope

- Any reader feature beyond rendering parity with today.
- A person knowledge base. The `sub` resolver can start as a simple classifier or
  lookup; the format only reserves the field.
- New span labels beyond the current set.
- The recitation aligner internals. The format supports a derived word id; the
  exact handle the recitation engine uses is verified during planning.

## Open questions

- turath.io access: API key versus a dump, the exact page and metadata shape, and
  one sample book to validate the adapter against.
- Recitation: confirm the recitation aligner can key on a derived word id rather
  than a stored token id.
- Whether `lines` is the right derived shape for the poetry renderer or whether it
  should consume `spans` labeled `hemistich` directly.
