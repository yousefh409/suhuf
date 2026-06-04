# Continuous tagged book format (page-sliced)

## Problem

The stored book is **Page to Block**: one Supabase row per page, each holding a
self-contained array of typed blocks. A page is a hard container, but the
logical units of the text are not page-shaped. A hadith, a poem, or a long
Qur'an passage routinely crosses a page break, and the format fractures it.

Two concrete pains, both shown by a single hadith (al-Arba'un al-Nawawiyya #2,
the Hadith of Jibril, stored across pages 47, 49, 50):

- **Ingestion accuracy.** Structure detection runs per block on page-fragmented
  text. The matn of hadith #2 is one continuous `«...»` quote spanning five
  source paragraphs and three pages, but only the first two fragments carry a
  `matn` tag. The rest are bare prose. The detector severs the unit the moment a
  dialogue turn (`فقال رسول الله`) looks like a new hadith, three pages before
  the quote actually closes. The disambiguating `«...»` is split across pages, so
  no single block ever sees both ends.
- **Addressability.** "الحديث الثاني" is stored as a heading string. The hadith
  number is not captured as data, and the hadith itself is six prose blocks
  across three page rows with no shared identity. Nothing can point a citation,
  a highlight, a share link, or recitation at "hadith #2" as one thing.

The page being the storage and render container is the last place fragmentation
lives. The tagged format shipped earlier already collapses a whole hadith into
one block *within* a page; only the page-row boundary still cuts it.

## Goals

1. A logical unit (hadith, ayah, poem) is one thing the AI tags whole, the
   reader renders whole, and the user can address whole, even across pages.
2. Keep download by page. The page stays the storage and streaming chunk.
3. Keep the existing `<hadith>/<isnad>/<matn>` inline tag format. No new
   structure representation, no offset-span migration.
4. Durable citation and sharing at any grain (page, hadith, sentence, word),
   anchored so that re-tagging never breaks a shared link.

## Key insight: the book text is immutable

These are classical texts. The words never change. Only the annotations change
(structure tags, entity refs, gradings, tashkeel). That splits the format into a
frozen substrate and a regenerable layer on top, and it makes any address into
the frozen text durable forever.

## Core decisions

1. **The book is one continuous tagged document.** Pages are where that document
   is sliced for storage and download, nothing more. A tag may open on one page
   slice and close on a later one.
2. **All structure comes from the AI, after assembly.** Before the AI, content is
   plain page text. The AI reads the whole assembled book and emits every
   structural and entity tag. There is no deterministic pre-detection producing
   structure. Cheap reliable source signals (page markers, printed hadith
   numbers, `«...»`) are fed to the AI as hints and used to verify its output,
   not to pre-compute structure.
3. **Tags carry only a boundary and a stable `id`.** No rich attributes. All
   metadata (number, grading, ayah ref, person ref) lives in a separate `meta`
   map keyed by id. Resolvers own `meta`; the AI never authors it.
4. **The reader reconstructs by concatenate and parse.** It concatenates the
   loaded page slices in order and parses the tags. A cross-page hadith rejoins
   automatically because it is one tag tree.
5. **Sharing anchors to the plain text.** A share or citation is a character
   range into the book's frozen plain text (tags stripped), plus an anchor
   snippet and the enclosing tag id. Durable because plain text never moves.

## The format

### Pipeline

```
source pages
   │  strip to clean text, keep page breaks + printed hadith numbers as hints
   ▼
PRE-AI:   plain text, assembled across page breaks   (no structure)
   │  AI reads the whole book, emits <hadith>/<isnad>/<matn>/<quran>/<person>… + ids
   ▼
RESOLVE:  deterministic passes fill meta[id]  (ayah ref, person ref, grading…)
   │  verify against source signals (« » bounds, marker presence); flag mismatches
   ▼
SLICE:    cut the tagged document at page boundaries into page rows (tags may cross)
   ▼
storage (Supabase)  →  download by page  →  reader concat + parse
```

The book is tagged once and frozen. Because the text is immutable, this is a
one-time cost per book, including the AI pass.

### Storage: page rows

```jsonc
// pages
{
  "book_id": "…",
  "volume": 1,
  "page_number": 47,

  // canonical: this page's slice of the continuous tagged document.
  // tags may open here and close on a later page, or continue one opened earlier.
  "tagged": "<hadith id=\"h2\"><isnad>«عن <person id=\"p7\">عمر</person>… قال:</isnad> <matn>بينما نحن جلوس…",

  // the tag stack open at the START of this page. lets the reader render or jump
  // to this page without re-parsing from the chapter start.
  "open_tags": [],

  // derived: plain text for this page, tags stripped. powers search and the
  // plain-text offset space used by sharing.
  "text": "الحديث الثاني بينما نحن جلوس عند رسول الله…",

  // this page's start position in the book's whole plain-text offset line.
  "start_offset": 5120
}
```

Download is unchanged: fetch page rows, stream in batches. `open_tags` on a later
page (for example `["hadith#h2","matn"]`) is what lets "jump to page 49" render
correctly without loading page 47 first.

### Storage: metadata sidecar

One entry per tag id. Any shape, regenerable, queryable without parsing the
tagged text.

```jsonc
// annotations  (keyed by book_id + id)
{ "id": "h2", "label": "hadith", "meta": { "number": "2", "collection_ref": "muslim:8", "grade": "sahih", "title": "حديث جبريل" } }
{ "id": "p7", "label": "person", "meta": { "ref": "umar_ibn_al_khattab", "role": "companion" } }
{ "id": "q5", "label": "quran",  "meta": { "sura": 2, "ayah": 255 } }
```

The same rule covers hadith, ayah, person, place, and book reference: the tag
carries an id, `meta[id]` carries everything else. Re-running a resolver rewrites
only `meta`. The tagged text and the plain text never move, so nothing about
sharing or citation breaks.

### Reader reconstruction

```
load page window (by page) + the meta sidecar (small, up front)
  → concatenate the pages' `tagged` in order, seeding the parser with the
    first page's `open_tags`
  → parse the tags → one tag tree, hadith #2 whole across its pages
  → apply meta by id, render (isnad/matn styling, hadith card, ayah ref…)
```

Word tap, highlight, and recitation operate on the rendered plain-text word list,
keyed by plain-text offset. No stored per-word tokens.

### Sharing and citation

A selection becomes a smart plain-text address:

```jsonc
{
  "book_id": "…",
  "start": 1240,            // offset into the book's frozen plain text
  "end":   1268,
  "anchor": "بينما نحن جلوس", // ~20 chars, re-anchors if anything ever shifts
  "in": "h2"                // enclosing tag id, derived, for the citation string
}
```

- The offset resolves the exact words, stable forever because plain text is
  frozen. The page is derived (the page whose `[start_offset, start_offset+len)`
  contains the offset).
- `meta["h2"]` yields the human citation, for example "صحيح مسلم · حديث جبريل
  (النووي ٢)".
- Share a word, a sentence, or the whole hadith with the same mechanism by
  widening `start`/`end`.

User data (highlights, bookmarks, notes) uses the same anchor shape instead of a
single `page_id` plus token id, so a highlight can cross a page seam.

## Worked example: hadith #2

```
pages (canonical `tagged`, sliced at page boundaries):

 p47  <hadith id="h2"><isnad>«عن <person id="p7">عمر</person>… قال:</isnad>
      <matn>بينما نحن جلوس… الإسلام… الإيمان…              ← opens hadith + matn, not closed
 p49  قال: فأخبرني عن الساعة…                              ← bare continuation, still inside matn
      open_tags: ["hadith#h2","matn"]
 p50  ثم انطلق… دينكم»</matn>
      <takhrij>رواه <person id="p9">مسلم</person></takhrij></hadith>
      open_tags: ["hadith#h2","matn"]

reader: concat(p47,p49,p50) → one <hadith id="h2"> with one whole <matn> → render.

meta: { "h2": {number:"2", collection_ref:"muslim:8", grade:"sahih", title:"حديث جبريل"},
        "p7": {ref:"umar_ibn_al_khattab", role:"companion"},
        "p9": {ref:"muslim_ibn_hajjaj"} }
```

The matn is one tag, so the accuracy bug cannot occur: the split is purely
physical. The hadith has an id, so it is addressable, citable, and shareable.

## What changes, what stays

| | Today | New |
|---|---|---|
| Page storage | one row per page | unchanged (one row per page) |
| Download | by page | unchanged (by page) |
| Page content | self-contained typed blocks | a slice of one continuous tagged document; tags cross pages |
| Structure source | deterministic pre-detection + AI entities | AI tags the whole assembled book; source signals are hints + verification |
| Hadith identity | none (heading string) | a tag id, with `meta[id]` |
| Metadata | on derived spans | `meta` sidecar keyed by tag id |
| Reader | render per-page blocks | concat the page window, parse, render |
| Sharing | page id + token id | plain-text offset + anchor + enclosing id |

The stored format barely moves. The real new pieces are: assemble before the AI,
let the AI produce all structure, give tags ids with a `meta` sidecar, slice the
tagged document into page rows, and reconstruct on the reader.

## Migration

All current book data is dev data. Migration is a re-ingest through the new
pipeline. No production data depends on the old shape. A one-time converter from
today's per-page tagged blocks (concatenate across pages, re-slice, assign ids)
is possible if any existing dump is worth keeping, but re-ingest is the default.

## Out of scope

- A person or place knowledge base. The `meta` resolver can start as a simple
  lookup or classifier; the format only reserves the field.
- New tag labels beyond the current set.
- Recitation engine internals. The format provides a derived word handle; the
  exact handle the engine uses is confirmed during planning.
- The AI prompt and batching strategy. Those are planning concerns.

## Open questions

- **ID assignment.** Hadith use the printed number where present (`h2`). What
  assigns ids to non-numbered spans (a person, an unnumbered paragraph): document
  order, or a content hash. Stability across re-ingestion is the requirement.
- **Where `meta` lives.** A JSONB blob on the book versus an `annotations` table
  keyed by `(book_id, id)`. Decide on the largest book (Bukhari, Siyar) where the
  blob would be large and a table paginates and queries better.
- **AI cost on huge books.** Bukhari (~2,600 pp) and Siyar (~10,000 pp) need
  batching. The AI call can chunk by chapter while keeping book-global plain-text
  offsets. Confirm the chunking keeps tag nesting well-formed at chunk seams.
- **AI structure is not reproducible run to run.** For the starter catalog
  (~18 books, the ones users actually read and cite), spot-check the structure
  once and freeze it.
