# Reader dev loop

Current focus: getting the ingestion pipeline, book format, and the
internal web reader to a state where they can support the public
reader. All three move together -- when the format changes, ingestion
changes to write it, and the reader changes to render it.

## The loop

```
edit ingestion code  ->  python -m ingestion flow <uri>  \
  --corpus-path <RELEASE> --dump web/data
                         |
                         web/data/<uri>.flow.json
                         |
                         open /reader/<openiti_id>  ->  inspect rendering
                         (or /inspector/<openiti_id> for block borders + JSON)
```

There is no local-book index UI: `/library` is the product Discover
screen (mock catalog browse, part of the dashboard). Open a freshly-dumped
book by navigating directly to its `openiti_id` URL.

`--skip-annotate` skips the Claude AI structure pass (no API).
`--skip-enrich` skips the Claude catalog enrichment (no API).
`--upload` writes to Supabase after dumping.
`--dry-run` is not a flag; use `--dump` without `--upload` to skip upload.

Full pipeline when both passes run:
parse -> tashkeel -> assemble -> chunk -> AI structure -> tag-transfer ->
number ids -> build annotations -> headings as standoff -> slice ->
enrich -> dump `<uri>.flow.json`.

### Required env

- `OPENROUTER_API_KEY` -- for the AI structure pass and catalog
  enrichment (routed through OpenRouter's Anthropic-compatible endpoint).
  Without it, both passes return empty results gracefully; the dump
  still completes and the reader shows the book without structure tags.

### Skipping stages for fast iteration

```sh
# Parse + tashkeel only, no API calls
python -m ingestion flow <uri> --corpus-path <RELEASE> --dump web/data \
  --skip-annotate --skip-enrich

# Full pipeline including upload
python -m ingestion flow <uri> --corpus-path <RELEASE> --dump web/data \
  --tashkeel-engine shakkala --upload
```

## The flow format

`<uri>.flow.json` is the continuous-tagged, page-sliced book. The full
schema is in [docs/reader/book-format.md](book-format.md). Key shape:

```jsonc
{
  "metadata": { "openiti_id": "...", "title_ar": "...", ... },
  "pages": [
    {
      "page_number": 47,
      "volume": 1,
      "tagged": "<hadith id=\"h2\"><isnad>...",
      "open_tags": [],
      "text": "plain text of this page",
      "start_offset": 5120
    },
    {
      "page_number": 49,
      "tagged": "continuation of hadith text...",
      "open_tags": [{"name": "hadith", "id": "h2"}, {"name": "matn", "id": null}],
      "start_offset": 5890
    }
  ],
  "chapters": [...],
  "annotations": [
    {"id": "h2", "label": "hadith", "start": 5120, "end": 6210, "meta": {"number": "2"}},
    {"id": "p7", "label": "person", "start": 5135, "end": 5145, "meta": {}},
    {"id": "hd1", "label": "heading", "start": 5115, "end": 5120, "meta": {}}
  ],
  "enrichment": {
    "book":   { "title_en": "...", "description": "...", "genres": [...] },
    "author": { "full_name_en": "...", "bio_en": "...", "birth_ah": 631, "death_ah": 676 }
  },
  "author_data": { "shuhra_lat": "...", ... }
}
```

The reader (`flowFormat.ts`) converts this to the renderer's shape:
each page is parsed (with its `open_tags` seed) into a `text` + `spans`
pair, then split at heading annotation ranges into `heading` and
`prose` blocks. `convertNewBook` normalizes to the legacy in-memory
shape so the rest of the reader layer is unchanged.

## Where things live

**Ingestion (Python)** -- `ingestion/`
- `__main__.py` -- entry point: `python -m ingestion flow ...`
- `cli.py` -- argument parser for the `flow` command
- `pipeline_flow.py` -- orchestrator: calls all stages in order
- `parse.py` -- OpenITI mARkdown -> typed blocks (prose/heading/poetry/isnad/matn/quran).
  Reads structural markup only; reads `{ayah} [سورة: آية]` citation brackets for Qur'an refs.
- `tashkeel.py` -- diacritize block tokens; engines: `shakkala` (default, falls back to
  `flan-t5`), `flan-t5`, `sadeed`, `none`.
- `assemble.py` -- concatenate pages into one plain-text string; record page offsets and
  heading block offsets (the only allowed chunk cut points).
- `chunk.py` -- split at heading offsets under an 8,000-char budget; never splits a unit.
- `annotate_flow.py` -- AI structure pass: sends each plain chunk to Claude (via OpenRouter),
  receives back the same text with boundary tags. Validates output; falls back to plain on
  failure; uses `tag_transfer` to recover from minor character drift.
- `tag_transfer.py` -- aligns AI-tagged output to the exact source via sequence alignment,
  recovering structure when the model dropped a `«»` or similar.
- `number_ids.py` -- assigns sequential per-label ids (`h1`, `h2`, `p1`, ...) to
  id-bearing tags in document order.
- `flow_format.py` -- `FlowBook`/`FlowPage`/`Annotation` Pydantic models;
  `build_annotations` parses the numbered document and resolves metadata.
- `page_slice.py` -- slice the tagged document at page offsets; record `open_tags` per slice.
- `enrich.py` -- AI catalog enrichment (book + author metadata via OpenRouter).
- `upload_flow.py` -- write `FlowBook` to Supabase (authors -> books -> pages -> chapters
  -> annotations).
- `quran.py` -- bundled ayah index; `lookup_match` and `loose_lookup` resolve Qur'an spans.

**Reader (Next.js)** -- `web/src/`
- `lib/reader/flowFormat.ts` -- `parseFlowPage` (seeds open-tag stack, parses fragment,
  emits text + spans); `pageToBlocks` (splits at heading ranges); `flowToNewBook` (maps
  a `FlowBook` to the `NewBook` shape).
- `lib/reader/queries.ts` -- `_loadBookFile` (reads `<id>.flow.json` locally or queries
  Supabase flow rows); public API: `listBooks`, `getBook`, `getEffectiveChapters`,
  `getAllPagesForBook`. `synthesizeChapters` generates synthetic Volume N chapters when
  real chapters are absent.
- `components/reader/` -- block-rendering primitives shared by reader and inspector.
- Routes (open by `openiti_id`):
  - `/reader/<openiti_id>` -- clean reader
  - `/inspector/<openiti_id>` -- block borders + type/key badges + JSON drawer

**Specs / plans**
- `docs/superpowers/specs/2026-06-05-continuous-tagged-book-format-design.md` -- the
  format design (canonical reference for the page-sliced tagged model)

## Open questions / known gaps

- Shakkala silently falls back to flan-t5 in the current environment. Worth
  investigating; switch the default engine if flan-t5 is consistently better here.
- Fallback chunks (AI structure pass failures) render as unstyled prose. The inspector
  shows which chunks fell back; the `annotate` stats in the logs report fallback count.
- Chapter volumes: ingestion's `Chapter` doesn't carry volume; all chapters currently
  use volume=1. Multi-volume chapter support is a follow-up.
- No author display in local mode unless the corpus yml is present and parsed.

## When changing the format

Anything that adds/changes a field in `FlowPage`, `FlowBook`, or `Annotation` needs:
1. `ingestion/flow_format.py` -- update the Pydantic model
2. `ingestion/pipeline_flow.py` and/or related stage -- populate the field
3. New tests in `ingestion/tests/`
4. `web/src/lib/reader/flowFormat.ts` -- mirror the type
5. `web/src/lib/reader/queries.ts` -- update any field reads
6. Affected components -- render or surface it
7. Re-dump and refresh

The Pydantic JSON serialization (`flow.json`) is the contract between the two sides.

## Public reader (later)

The public reader will need its own data path to Supabase. The shape of
`lib/reader/queries.ts` (four async functions returning TS types) was chosen so
the implementation can swap without changing routes or components -- but that is
a future task. For now, focus on making the format and rendering right.
