# Ingestion Pipeline

A Python pipeline (`python -m ingestion flow`) that transforms an OpenITI mARkdown source file into the continuous-tagged, page-sliced book format and writes it to `web/data/<uri>.flow.json` and/or Supabase. The pipeline is the only ingestion path; the `flow` command is the only CLI command.

## Pipeline Overview

```mermaid
flowchart LR
    A[mARkdown file] --> B[parse\nblocks + chapters]
    B --> C[tashkeel\ndiacritize blocks]
    C --> D[assemble\none plain-text string\npage offsets + boundaries]
    D --> E[chunk\nat unit boundaries]
    E --> F[AI structure pass\nboundary tags per chunk]
    F --> G[tag-transfer\nalign AI output to source]
    G --> H[number ids\nh2 p7 q5]
    H --> I[build annotations\nmetadata layer]
    I --> J[headings as standoff annotations]
    J --> K[slice at page offsets]
    K --> L[enrich\nbook + author metadata]
    L --> M[dump flow.json\nand/or upload]
```

Because structure is tagged on the assembled plain text BEFORE slicing, a hadith stored across pages stays one `<hadith>` with one `<matn>`. The page boundary cuts the tag tree, but the reader reconstructs the whole unit by concatenating page fragments in order.

## Stage 1: Parse (`parse.py`)

Converts the raw mARkdown file into typed blocks and a chapters tree. The parser reads only *structural* markup: page markers, headings, poetry hemistich dividers. Semantic hadith tags (`$RWY$`, `@MATN@`) are absent from essentially every real corpus file and are not depended on.

Block types emitted:
- `prose` -- default paragraph text
- `heading` -- chapter/section title (also stored in `chapters`)
- `poetry` -- verse with hemistich pairs
- `isnad` / `matn` / `takhrij` -- only when native `@MATN@` markers are present (rare)
- `quran` -- inline Qur'an quotation detected via `{ayah} [سورة: آية]` citation brackets

The parser emits one block per source paragraph. Raw-file heuristics handle common OpenITI oddities: ` ... ` hemistich separators in prose blocks, ordinal-only headings that are really item numbers, and `[ص: N]` print-sheet refs (dropped).

## Stage 2: Tashkeel (`tashkeel.py`)

Adds Arabic diacritical marks to the block token text before assembly. Engine choices:

| Engine | Type | Notes |
|---|---|---|
| `shakkala` | Deep learning | Default; falls back to `flan-t5` when Shakkala fails to load |
| `flan-t5` | Seq2seq | Fallback |
| `sadeed` | Rule-based | Alternative |
| `none` | -- | Skip diacritization |

Diacritizing before assembly means the assembled plain text (and everything the AI tags over it) carries tashkeel. Sets `has_tashkeel = true` on the book record.

## Stage 3: Assemble (`assemble.py`)

Concatenates each page's plain text (tokens joined by spaces, pages joined by a single space) into one book-global string. Returns:

- `text` -- the continuous plain text
- `page_offsets` -- `(page_number, volume, start_offset)` per page
- `boundaries` -- start offset of every heading block; these are the only allowed chunk cut points

Page offsets mark where each page's content begins in the continuous string. They may land mid-unit and are NOT cut points.

## Stage 4: Chunk (`chunk.py`)

Groups whole units into chunks under a character budget (default 8,000 chars). The hard rule: **cut only at `boundaries` (heading start offsets), never at page markers.** A single unit longer than the budget becomes its own oversized chunk; it is never split.

This guarantees every chunk holds whole hadiths and that no tag ever opens in one chunk and closes in another. Chunk outputs concatenate to a well-formed tagged document.

## Stage 5: AI Structure Pass (`annotate_flow.py`)

Sends each chunk as plain text to the Claude API (`anthropic/claude-sonnet-4.5` via OpenRouter, OpenAI-compatible endpoint) and receives back the same text with HTML-style boundary tags added. The model must not change, add, or remove any character -- the visible text with all tags stripped must be byte-identical to the input.

Tag vocabulary: `<hadith>`, `<isnad>`, `<matn>`, `<takhrij>`, `<person>`, `<place>`, `<quran>`, `<book_ref>`, `<hadith_ref>`, `<date_hijri>`. Tags carry no attributes at this stage; ids are assigned in the next pass.

Chunk calls fan out across a thread pool (up to 8 workers). Each chunk is validated:

1. Parse the tagged output to check for `TagError` (malformed or unknown tags, mismatched closes).
2. Strip tags from the output and compare to the input; they must be identical.
3. If the model drifted characters (commonly drops `«»` guillemets), try **tag-transfer** to align the AI structure onto the exact source text.
4. If transfer fails or the alignment similarity is too low, fall back to plain text (no tags) for that chunk and record a fallback in stats.

When `OPENROUTER_API_KEY` is absent the pass returns every chunk unchanged (no tags, no API calls).

## Stage 6: Tag-Transfer (`tag_transfer.py`)

When the AI output's plain text differs from the source chunk (character drift), `transfer_tags` aligns the AI-tagged text to the exact source string using sequence alignment and projects the tag boundaries onto the exact characters. Only genuinely garbled output (low alignment score) falls back to plain; minor drift (a dropped `«`) is recovered.

## Stage 7: Number Ids (`number_ids.py`)

Walks the merged continuous tagged document in document order and assigns a short sequential id to each id-bearing opening tag: first `<hadith>` gets `h1`, second `h2`; first `<person>` gets `p1`; etc. Id-bearing labels: `hadith` (prefix `h`), `person` (`p`), `place` (`pl`), `quran` (`q`), `book_ref` (`b`), `hadith_ref` (`hr`), `date_hijri` (`d`). Structural tags (`isnad`, `matn`, `takhrij`) get no ids. The pass is idempotent: tags that already have an `id` attribute are not renumbered.

## Stage 8: Build Annotations (`flow_format.py`)

Walks the numbered continuous document and emits one `Annotation` per id-bearing tag (close order, then sorted by start). Each annotation records `{id, label, start, end, meta}` where `start`/`end` are character offsets into the compiled plain text and `meta` is resolved per label:

- `quran`: exact match against the bundled ayah index; falls back to loose (Uthmani-tolerant) match
- `hadith`: `{number}` from the first printed item number whose offset falls inside the hadith's range
- all others: `{}` (resolver TBD)

## Stage 9: Headings as Standoff Annotations

Heading ranges (computed from the parse result via `heading_ranges`) are added to the annotation list as standoff `heading` entries with book-global plain-text offsets. The reader uses these to split each page's prose into `heading` and `prose` blocks without the AI needing to tag chapter text.

## Stage 10: Slice (`page_slice.py`)

Cuts the numbered continuous document at the interior page-start offsets from `page_offsets`. Each `PageSlice` stores its raw tagged fragment and the `open_tags` stack (the tags open at its start). Tags are genuinely unclosed at page boundaries; the reader reconstructs by plain concatenation.

## Stage 11: Catalog Enrichment (`enrich.py`)

Calls the Claude API (via OpenRouter) to produce book and author metadata: English title and description, genre tags, composition date, commentary/abridgement links, author biographical fields. Gracefully returns `{}` when the API key is absent, so `--skip-enrich` and offline runs still produce a valid dump.

## Storage: Upload (`upload_flow.py`)

Writes the flow book to Supabase in order:
1. `authors` upsert (keyed on `openiti_id`)
2. `books` upsert (keyed on `openiti_id`)
3. `pages` upsert in batches of 50 (keyed on `book_id, volume, page_number`): stores `tagged`, `open_tags`, `content_plain`, `content_hash`, `start_offset`; `content_blocks` is left NULL
4. `chapters` upsert (keyed on `book_id, sort_order`)
5. `annotations` upsert in batches of 50 (keyed on `book_id, tag_id`)

All upserts make re-ingestion idempotent.

## CLI Reference

```sh
python -m ingestion flow <openiti_id> \
  --corpus-path ./RELEASE \
  --dump web/data \
  [--skip-annotate] \
  [--skip-enrich] \
  [--tashkeel-engine shakkala|flan-t5|sadeed|none] \
  [--upload]
```

| Flag | Default | Description |
|---|---|---|
| `--corpus-path` | `./RELEASE` | Path to the OpenITI RELEASE directory |
| `--dump` | (required) | Output directory; writes `<uri>.flow.json` |
| `--skip-annotate` | off | Skip the Claude AI structure pass (no API calls) |
| `--skip-enrich` | off | Skip the Claude catalog enrichment (no API calls) |
| `--tashkeel-engine` | `shakkala` | Diacritization engine (`none` = skip) |
| `--upload` | off | Write to Supabase after dumping (`SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` required) |

## Key Files

| Path | Purpose |
|---|---|
| `ingestion/__main__.py` | CLI entry point (`python -m ingestion flow ...`) |
| `ingestion/cli.py` | Argument parser |
| `ingestion/pipeline_flow.py` | Orchestrator: calls all stages in order |
| `ingestion/parse.py` | mARkdown -> typed blocks + chapters |
| `ingestion/tashkeel.py` | Diacritize block tokens |
| `ingestion/assemble.py` | Concatenate pages into one plain-text string |
| `ingestion/chunk.py` | Split at unit boundaries under a char budget |
| `ingestion/annotate_flow.py` | AI structure pass over plain chunks |
| `ingestion/tag_transfer.py` | Align AI tags to exact source on character drift |
| `ingestion/number_ids.py` | Assign sequential ids to id-bearing tags |
| `ingestion/flow_format.py` | Pydantic models + `build_annotations` |
| `ingestion/page_slice.py` | Cut tagged document at page offsets |
| `ingestion/enrich.py` | AI catalog enrichment (book + author metadata) |
| `ingestion/upload_flow.py` | Write FlowBook to Supabase |

## Gotchas

**Tashkeel engine fallback.** `shakkala` silently falls back to `flan-t5` in the current environment (Shakkala load fails). The dump is still valid; diacritics come from flan-t5.

**AI cost scales with book size.** Each chunk is one API call. A 1,000-page book with a 8,000-char chunk budget produces roughly 30-100 chunks depending on unit sizes. Use `--skip-annotate` for parse-only dev work.

**Fallback chunks produce no structural tags.** When a chunk falls back to plain text (API error, tag validation failure, or transfer failure), that chunk's hadiths will not be tagged. The dump is still valid and renderable; it will just render as prose for those sections.

**Prefer higher-tier files for cleaner structure, not for tags.** `.mARkdown` > `.completed` > raw reflects how well the structural markup was vetted; none of the tiers carries `$RWY$`/`@MATN@` semantic tags. All semantic structure comes from the AI pass.

**Unicode normalization before hashing.** Apply NFC normalization to `content_plain` before computing `content_hash`. Arabic combining characters can appear in different orders, producing different byte sequences for visually identical text.

---

Related docs: [Book Format](book-format.md) -- [Reader App](app.md) -- [I'rab Agents](../agents/irab.md)
