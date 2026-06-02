# Reader format taxonomy redesign

Date: 2026-06-02
Status: design, pending review

## Goal

Settle the content typology for the ingestion to reader format: which block
and inline types exist, what each means, and how the reader renders each.
Validated across three genres: hadith (Nawawi 40), classical poetry, and
general prose (tafsir). Data stays local in `web/data`.

This spec covers the format contract and the reader rendering rules. Updating
the ingestion pipeline to produce this format is the follow on work, ordered
after the reader is dialed in.

## Guiding principle: rich format, minimal reader

The format captures as much structure and reference data as ingestion can
detect. The reader renders almost none of it visually. References live in the
data for later tap to popup features; the reader shows them as plain text until
a feature needs them.

Rationale: the schema is the expensive thing to change and re-ingest. Backing
datasets (narrator bios, geography, glossary) can be wired in later without
re-ingesting. Over capturing in the format is cheap insurance. Visual restraint
keeps the reader calm and book like rather than looking like a research
database.

## Final taxonomy

### Block types (reader renders these distinctly)

| type | meaning | reader render |
|---|---|---|
| `heading` | section head, with `level` 1/2/3 (kitab / bab / fasl) | centered, size by level |
| `prose` | default paragraph | justified body |
| `poetry` | verse, each a pair of hemistichs | centered couplets |
| `isnad` | chain of narrators | muted |
| `matn` | prophetic body of a hadith | bold |
| `takhrij` | sourcing line (rawahu al-Bukhari...), grading folded in | small, muted |
| `quran` | standalone ayah or ayat | centered, green tint |

A hadith is not a single container block. It is the sequence `isnad`, `matn`,
`takhrij` as sibling blocks. This matched the user's mental model.

### Inline spans

One visible span, the rest captured but rendered as plain text.

| label | visible? | resolves to (ref) | sub_label |
|---|---|---|---|
| `quran` | yes, green ﴿﴾ | sura:ayah | none |
| `person` | no, plain | narrator / scholar entity | prophet, companion, tabii, scholar, caliph |
| `place` | no, plain | geo entity | city, region |
| `book_ref` | no, plain | our catalog (openiti_id) | none |
| `hadith_ref` | no, plain | another hadith (e.g. muttafaq alayh) | none |
| `date_hijri` | no, plain | computed Gregorian | none |

The `quran` inline span carries the end of ayah glyph (۝ + number) inside it.

### Structural elements

| element | render | notes |
|---|---|---|
| item / hadith numbering | faint number before the item | e.g. `١ -` |
| page + volume boundaries | not rendered in default reader | data only; powers a future "split by page" mode |
| footnotes | superscript marker in text, note text at bottom of section | classic book footnotes; source is the editor (muhaqqiq) |

## Cut

Removed from the format and the reader. Unrecognized source content that would
have mapped to these now falls back to `prose`.

- Block types: `biography`, `commentary`, `quoted_text`, `editor_note`,
  `hadith_grading` (text folds into `takhrij`), and the `hadith` container type.
- Inline spans: `honorific` (ﷺ, radiya allah anhu), `term` (technical
  vocabulary), `prophetic_quote` (the `matn` block already captures it).
- Poetry metadata (meter, poet, rhyme): not captured at all.
- Visible page markers in the default reading flow.

## Format / data model deltas

Current state is in `ingestion/models.py` and mirrored in
`web/src/lib/reader/types.ts`. Changes:

1. Block type set shrinks to the seven listed above. Remove the cut types.
2. Add `level: int | None` to `Block` for headings (currently `level` lives
   only on `Chapter`; the renderer always emits h2).
3. Add `number: str | None` to `Block` for item / hadith numbering as printed.
4. Add `quran` to the block type set.
5. Rename span labels to the final set: `qur_quote` to `quran`,
   `personal_name` to `person`, `place_name` to `place`, `book_title` to
   `book_ref`, `hadith_quote` to `hadith_ref`. Keep `date_hijri`. Keep
   `sub_label` (used by `person`).
6. Footnotes: add `footnotes: list[Footnote]` to `Page`, where a `Footnote` is
   `{ marker: str, tokens: list[Token] }`. The inline anchor is a `Span` with
   label `footnote` and `ref` set to the marker, so it reuses the existing span
   machinery. (Footnote is internal structure, not a tappable reference.)
7. Drop poetry `metadata` (meter / poet / rhyme).

Pydantic JSON serialization stays the contract between ingestion and the reader.
TS types mirror every change.

## Reader rendering rules

- Headings: centered; font size steps down by level (1 largest).
- Prose: justified, generous line height.
- Poetry: two hemistichs per line in a centered grid, faint divider between.
- Hadith: `isnad` muted, `matn` bold, `takhrij` small and muted on its own line.
- Quran block: centered, green tint, ayah number inside.
- Quran span: green ﴿﴾ inline; only styled inline element.
- person / place / book_ref / hadith_ref / date_hijri: no visual treatment in
  the reader. Present in the DOM (data attributes) for later interaction.
- Item numbering: faint, before the item.
- Footnotes: superscript marker inline; note list rendered at the bottom of the
  section.

## Ingestion implications (follow on work)

Ordered after the reader. Captured here so the format is producible.

- Parser (`ingestion/parse.py`): map OpenITI mARkdown tags to the reduced block
  set; carry heading `level`; extract item numbering; detect footnote markers
  and note text where the source encodes them.
- Enrichment (`ingestion/enrich.py` / annotate): Claude detects inline spans
  (`person`, `place`, `book_ref`, `hadith_ref`, `quran`, `date_hijri`) and
  resolves `ref` where possible (quran sura:ayah, book_ref to catalog
  openiti_id). Unresolved refs still carry the label.
- Whether OpenITI sources encode footnotes is an open question to resolve during
  the ingestion phase. If absent, footnotes are simply empty.

## Open modeling decisions (for review)

- Footnote anchor as a `Span` with label `footnote` versus a dedicated token
  field. Span reuse is proposed.
- `number` as a string (preserve printed form, e.g. Arabic-Indic digits) versus
  an int. String proposed to keep fidelity.
- Heading `level` on the block versus continuing to read it from `Chapter`.
  On the block proposed so the renderer stops hardcoding h2.

## Validation

The design is exercised against:
- Hadith: Nawawi 40, hadith 1 (isnad / matn / takhrij, numbering, person and
  book_ref spans).
- Poetry: Muallaqa of Imru al-Qais opening (hemistich pairs, place spans).
- Prose: a tafsir paragraph (heading levels, quran block and span, person and
  date_hijri spans, footnotes).

Acceptance: a test page rendering all three reads cleanly with only the
reader-visible set styled, and the JSON carries the full captured taxonomy.
