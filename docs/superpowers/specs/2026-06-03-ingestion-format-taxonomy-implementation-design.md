# Ingestion: produce the frozen reader taxonomy

Date: 2026-06-03
Status: design, pending review

## Goal

Make the ingestion pipeline produce the frozen reader format end to end, then
prove it on three real OpenITI books across genres. The format contract is
already settled in `ingestion/models.py` and mirrored in
`web/src/lib/reader/types.ts`. This work updates the producers (parser, Claude
detection, data connection) to emit that contract and validates the output
against `web/fixtures/Sample.Taxonomy.enriched.json`.

Companion format spec: `2026-06-02-reader-format-taxonomy-design.md`.
Tag mapping and starter catalog: `docs/reader/book-format.md`.

## Pipeline shape

The existing `python -m ingestion ingest <uri>` command is the orchestrator.
Stage order stays as it is today; the detection stage must run before the
connection stage because connection resolves what detection produced.

```
parse  →  tashkeel  →  annotate (Claude: detect)  →  enrich (connect to data)  →  dump / upload
```

Responsibilities, after this change:

- **parse.py** — pure structural parse of OpenITI mARkdown into the seven
  frozen block types. No Claude. Deterministic and offline.
- **annotate.py** — all Claude detection. Relabels block types where confident
  and attaches inline spans using the frozen span vocabulary. May propose a
  ref, but is not the authority on exact refs.
- **enrich.py** — connects records to backing data. Two concerns live here:
  the existing book and author metadata enrichment (a Claude call, unchanged),
  and the new deterministic span ref resolution. For now ref resolution covers
  the `quran` span only. The other span types are stubbed for later.

The dev loop and dump suffixes (`parsed`, `tashkeeled`, `annotated`,
`enriched`) are unchanged. The reader keeps picking the highest tier present.

## The seven block types

`heading`, `prose`, `poetry`, `isnad`, `matn`, `takhrij`, `quran`. Any source
content that does not map to one of these falls back to `prose`. The cut types
(`biography`, `commentary`, `quoted_text`, `editor_note`, `hadith_grading`, and
the `hadith` container) are removed from every producer.

## parse.py changes

Structural only. No model knowledge, no network.

- Carry heading depth onto the block: set `level` (1/2/3) on `heading` blocks,
  not just on the `Chapter` entry. The reader stops hardcoding one heading
  level.
- Extract printed item or hadith numbering into `number`, kept as a string to
  preserve the source form (including Arabic-Indic digits).
- Emit `takhrij` for the sourcing line that follows a matn (the "rawahu
  al-Bukhari ..." attribution), and `quran` for standalone ayat delimited by
  the ornate brackets.
- Drop the `biography` branch. Such content now falls back to `prose`.
- Footnote extraction is best effort: detect markers and note text when the
  source encodes them, populating `Page.footnotes` and a `footnote` span anchor.
  Cleaned OpenITI text strips paratext, so expect this to be empty in practice;
  the structure exists for sources that retain footnotes.

## annotate.py changes

- Retarget the span vocabulary to the frozen set: `quran`, `person`, `place`,
  `book_ref`, `hadith_ref`, `date_hijri`. Retarget the block-type vocabulary to
  the seven valid types. Remove the cut labels from the prompt and the accept
  list.
- Decouple span detection from block relabeling in the auto-skip path. Today
  the entire pass skips when the parser already produced enough native
  structural blocks, which would leave a well-tagged book like Nawawi 40 with
  no spans at all. After the change, relabeling may skip on well-tagged
  sources, but span detection always runs.
- Keep the chunking, token-index to token-id resolution, in-place mutation,
  stats, and graceful failure behavior. Failure still means: log a warning,
  leave blocks untouched.

## enrich.py changes

- Book and author metadata enrichment stays exactly as it is.
- Add deterministic Quran ref resolution. Walk every block, find spans labeled
  `quran`, normalize the quoted token text (strip tashkeel and ornate brackets,
  normalize alif and hamza variants), and match against a normalized index of
  the Quran built from a bundled data file. On a unique match, set `ref` to
  `"sura:ayah"`, overwriting any value the model proposed. No match leaves the
  label in place with `ref` unresolved.
- Other span types (`person`, `place`, `book_ref`, `hadith_ref`, `date_hijri`)
  are passed through untouched, with a clear marker that their resolution is
  future work. Gregorian date computation is out of scope.

## Quran data

A Quran text file lives in `ingestion/data/`, committed to the repo (114 suras,
6236 ayat, plain Uthmani text, roughly one megabyte). `enrich.py` loads it once
and builds a normalized lookup at module load. Self contained, offline, and
deterministic. Sourced from a well established open Quran dataset.

## Failure and edge handling

- Missing `ANTHROPIC_API_KEY`: annotate and the metadata half of enrich fail
  gracefully and return empty, the dump still completes (existing behavior).
  Quran resolution is deterministic and runs regardless.
- Token-count drift during tashkeel leaves a block as is (existing behavior);
  spans still resolve against whatever token ids exist.
- Ambiguous or unmatched Quran quotes resolve to no ref rather than a wrong
  ref. Wrong refs are worse than missing refs for the one visible span.

## Validation

Source two more books into `RELEASE/data` from the OpenITI per-century GitHub
repos: Ibn Kathir Tafsir (`.mARkdown`, well tagged) for prose and tafsir, and
the al-Mutanabbi Diwan for poetry. Nawawi 40 is already present for hadith. If
the Mutanabbi file lacks clean hemistich tagging, fall back to another diwan and
note it.

Run the real pipeline on all three:

```
python -m ingestion ingest <uri> --dump web/data --dry-run --tashkeel-engine shakkala
```

Ibn Kathir is large; ingest a slice for the proof rather than the whole work.

Acceptance:

- The enriched JSON for each book carries only the seven block types, headings
  with `level`, items with `number`, and inline spans from the frozen
  vocabulary. Its shape matches `web/fixtures/Sample.Taxonomy.enriched.json`.
- `quran` spans in the tafsir book resolve to correct `sura:ayah` refs.
- Each book renders cleanly at `/internal/reader/<id>` and the inspector shows
  the expected block types and spans.

## Tests

Added under `ingestion/tests/`:

- parse: heading `level`, `number` extraction, `takhrij` and `quran` block
  emission, `biography` falling back to `prose`, footnote structure when
  present.
- annotate: new vocabulary is the only accepted set, span detection runs even
  when block relabeling is skipped on a well-tagged source.
- enrich: Quran resolver returns the correct `sura:ayah` for a known ayah,
  returns no ref for an unmatched quote, and overrides a wrong model-proposed
  ref.

## Out of scope

- Resolution of `person`, `place`, `book_ref`, `hadith_ref`, `date_hijri`.
- Gregorian conversion of Hijri dates.
- Supabase upload.
- Cloning the full starter catalog. Only the three validation books are sourced.
