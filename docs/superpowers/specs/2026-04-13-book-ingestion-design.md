# Book Ingestion Pipeline Design

## Overview

A Python CLI that transforms OpenITI mARkdown source files into structured block-based book data in Supabase Postgres. Runs locally per book. Three stages execute in sequence: parse structure into typed blocks with word tokens, add tashkeel (diacritics) to token text, upload to Supabase.

Test book: `0676Nawawi.ArbacunaNawawiyya` (al-Arba'un al-Nawawiyyah, ~15 pages).

## Decisions

| Decision | Choice |
|---|---|
| Language | Python |
| Location | `ingestion/` |
| Architecture | Monolithic pipeline, optional `--stage` flag |
| Tashkeel | Sadeed primary, Shakkala fallback, fill-gaps-only |
| Corpus source | Full OpenITI RELEASE clone |
| Runtime | Local CLI first, cloud-ready later |
| Schema | All tables (authors, books, pages, chapters, irab_cache, user_*) |
| Test book | Nawawi's Arba'un al-Nawawiyyah |

---

## Project Structure

```
ingestion/
  __main__.py          # CLI entry point (python -m ingestion ...)
  cli.py               # argparse setup
  parse.py             # Stage 1: mARkdown -> blocks + tokens
  tashkeel.py          # Stage 2: diacritize tokens (Sadeed -> Shakkala fallback)
  upload.py            # Stage 3: upsert to Supabase
  metadata.py          # OpenITI metadata header parser (author, title, genres)
  models.py            # Pydantic data classes (Book, Page, Chapter, Block, Token)
  corpus.py            # Locate files within the RELEASE corpus
  requirements.txt     # Dependencies
```

## CLI Interface

```bash
# Ingest a single book (all stages)
python -m ingestion ingest 0676Nawawi.ArbacunaNawawiyya

# Run a specific stage only
python -m ingestion parse 0676Nawawi.ArbacunaNawawiyya --dump output/
python -m ingestion tashkeel output/parsed.json
python -m ingestion upload output/tashkeeled.json

# Ingest all 18 starter books
python -m ingestion ingest --starter

# Options
--corpus-path ./RELEASE            # Path to cloned OpenITI RELEASE
--tashkeel-engine sadeed|shakkala  # Default: sadeed
--force-tashkeel                   # Re-diacritize even words that already have diacritics
--dump <dir>                       # Write intermediate JSON for debugging
--dry-run                          # Parse and tashkeel but don't upload
```

---

## Data Models

Pydantic models for validation and serialization. Passed between stages in memory.

```python
class Token:
    id: str          # "p42_b1_w0"
    text: str        # "حَدَّثَنَا"

class Block:
    key: str         # "b0", "b1", ...
    type: str        # prose | hadith | isnad | matn | poetry | biography | heading
    tokens: list[Token]                  # For all types except poetry
    hemistichs: list[list[list[Token]]]  # For poetry only
    metadata: dict | None                # Optional (poet, meter, birth/death years)

class Page:
    page_number: int
    volume: int
    content_blocks: list[Block]
    content_plain: str               # Derived: all token text joined by spaces
    content_hash: str                # SHA-256 of NFC-normalized content_plain

class Chapter:
    title: str
    level: int                       # 1-5
    page_number: int
    sort_order: int
    parent_index: int | None         # Index into chapters list for nesting

class BookMetadata:
    openiti_id: str                  # "0676Nawawi.ArbacunaNawawiyya"
    title_ar: str
    title_lat: str | None
    author_openiti_id: str           # "0676Nawawi"
    genres: list[str]
    word_count: int | None
    char_count: int | None
    version_status: str | None       # "pri" or "sec"
    language: str                    # default "ara"

class ParseResult:
    metadata: BookMetadata
    pages: list[Page]
    chapters: list[Chapter]
```

---

## Stage 1: Parse

Reads an OpenITI mARkdown file line by line. Two passes.

### Metadata pass

Read the `#META#` header block. Extract `openiti_id`, title, author ID, genres, word count, char count, composition date. Stop at `######OpenITI#`.

### Content pass

Read remaining lines sequentially. Maintain state: `current_volume`, `current_page_number`, `current_blocks`, `in_hadith`, `chapter_stack`.

**Line dispatch:**

| Pattern | Action |
|---|---|
| `PageV##P###` | Flush current page, start new page with extracted volume + page_number |
| `### \|EDITOR\|` | Skip (editorial content) |
| `### \|` through `### \|\|\|\|\|` | Create heading block, add to chapters tree. Level = pipe count (1-5) |
| `# $RWY$` | Enter hadith mode, start accumulating isnad tokens |
| `@MATN@` | Flush accumulated tokens as isnad block, start matn block |
| `### $BIO_MAN$` / `### $BIO_WOM$` / `### $` / `### $$` | Start biography block. Extract `@YB####`/`@YD####` into metadata |
| `%~%` | Poetry: split by `%~%` into hemistich pairs, tokenize each separately |
| `#META#` / `######OpenITI#` | Skip (handled in metadata pass) |
| Everything else | Append tokens to current block (hadith sub-block if in hadith mode, prose otherwise) |

### Tokenization

Split text by whitespace. Generate token IDs: `p{page}_b{block_idx}_w{word_idx}`. Clitics stay attached (whitespace-only splitting).

### Edge cases

- No `PageV##P###` markers: treat entire file as volume 1, page 1
- Hadith without `@MATN@`: entire block stays as type `hadith` (no isnad/matn split)
- Consecutive page markers with no content: skip empty pages
- Heading inside a hadith: heading takes priority, flush hadith

---

## Stage 2: Tashkeel

Adds Arabic diacritical marks to unvocalized token text.

### Engine protocol

```python
class TashkeelEngine:
    def diacritize(text: str) -> str

class SadeedEngine(TashkeelEngine):
    # Loads Sadeed 1.5B model from HuggingFace
    # Keeps model warm in memory

class ShakkalaEngine(TashkeelEngine):
    # Loads PyTorch Shakkala model
    # Fallback if Sadeed fails
```

### Processing flow

1. Load Sadeed. If it fails, fall back to Shakkala with a warning.
2. For each page, for each block:
   - Collect token texts into a single string (models work better on sentences)
   - Check diacritic ratio: count diacritic chars vs total chars. If ratio > 0.15, skip (already vocalized)
   - Send to engine
   - Split result back into tokens by whitespace, matching 1:1 with original
3. After all pages: regenerate `content_plain` from updated token text
4. Recompute `content_hash` (SHA-256 of NFC-normalized `content_plain`)

### Token alignment

If diacritized output has different word count than input:
- Try Shakkala as fallback for that block
- If both fail, keep original undiacritized text and log a warning

### Fill-gaps-only mode (default)

Only diacritize words/blocks where diacritic ratio < 0.15. Preserve existing diacritics from the source. `--force-tashkeel` overrides this to re-diacritize everything.

---

## Stage 3: Upload

Pushes parsed + tashkeeled data to Supabase. All operations are upserts for idempotent re-ingestion.

### Upload order (respects foreign keys)

1. **Upsert author** -- keyed on `openiti_id`
2. **Upsert book** -- keyed on `openiti_id`, references `author_id`. Sets `has_tashkeel`, `total_pages`, `total_volumes`.
3. **Upsert pages** -- keyed on `(book_id, volume, page_number)`. Batched in groups of 100.
4. **Upsert chapters** -- keyed on `(book_id, sort_order)`. Resolves `page_id` and `parent_id`.

### Change detection

On re-ingestion, `content_hash` determines if a page changed. If hash matches, skip the upsert. Logs skipped vs updated pages.

### Error handling

If a batch fails, retry once. If still fails, log and continue. Report failures at the end. Pipeline is idempotent so re-running fixes partial failures.

### Client

Uses `supabase-py` with service role key (admin operation). Reads `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` from environment.

---

## Metadata & Author Extraction

### Book metadata

Parsed from the `#META#` header in each `.mARkdown` file:
- `10#BOOK#TITLEA#AR` -> `title_ar`
- `00#VERS#LENGTH###` -> `word_count`
- `00#VERS#CLENGTH##` -> `char_count`
- `40#BOOK#GENRE####` -> `genres` (split by `::`)
- `30#BOOK#WROTE##AH` -> `composition_date_ah`

### Author extraction

Author ID is parsed from the OpenITI URI: `0676Nawawi.ArbacunaNawawiyya` -> `0676Nawawi`. The RELEASE corpus has author metadata YAML files with structured name fields, dates, and places.

### `corpus.py`

Given an OpenITI URI, locates the file in the RELEASE directory structure. Search order: `.mARkdown` > `.completed` > raw (prefer best quality). Directory pattern: `{century}AH/{authorURI}/{bookURI}/`.

---

## Supabase Migrations

All tables from the book-format.md spec, created as sequential migrations.

### Migration 1: `create_authors_table`

The `authors` table with all name fields (shuhra, ism, nasab, kunya, laqab, nisba), dates, geography, scholarly network, external IDs.

### Migration 2: `create_books_and_content_tables`

- `books` table with FK to authors
- `pages` table with FK to books, unique constraint on `(book_id, volume, page_number)`
- `chapters` table with FK to books and pages, self-referencing `parent_id`

### Migration 3: `create_irab_cache_table`

Global `irab_cache` table with unique constraint on `(word, sentence_hash, model_version)`.

### Migration 4: `create_user_tables`

- `user_library` (PK: user_id, book_id)
- `user_bookmarks` (tombstone pattern)
- `user_highlights` (tombstone pattern)
- `user_notes` (tombstone pattern)
- `user_reading_positions` (PK: user_id, book_id)

### Indexes

- `pages(book_id, volume, page_number)` -- unique constraint
- `chapters(book_id, sort_order)`
- `books(openiti_id)` -- unique
- `authors(openiti_id)` -- unique

### RLS Policies

- `authors`, `books`, `pages`, `chapters`: read-only for authenticated users
- `irab_cache`: read for authenticated, write via service role
- `user_*` tables: users read/write own rows only

---

## Validation Plan (Nawawi's Arba'un)

1. **Parse**: ~15 pages produced. Hadith blocks with isnad/matn splits. Heading blocks map to chapters. Token IDs follow pattern. `content_plain` matches tokens.
2. **Tashkeel**: Sadeed loads. Already-vocalized words preserved. Token counts unchanged. `content_hash` computed.
3. **Upload**: Author row for al-Nawawi. Book row with correct metadata. All pages upserted. Chapters tree reflects hadith headings. Re-run is idempotent.
4. **Success**: `python -m ingestion ingest 0676Nawawi.ArbacunaNawawiyya` runs end to end, data queryable in Supabase.

---

## Dependencies

```
# requirements.txt
supabase>=2.0.0
pydantic>=2.0.0
torch>=2.0.0
transformers>=4.30.0    # For Sadeed model loading
pyyaml>=6.0             # For OpenITI author metadata YAML
python-dotenv>=1.0.0
```

Shakkala PyTorch port installed separately if needed as fallback.

---

## Gotchas

- **Unicode diacritic ordering**: NFC normalize before hashing or comparing
- **Token IDs are position-based**: source edits that insert/remove words shift all downstream IDs
- **Not all OpenITI files have complete tagging**: unrecognized content defaults to `prose`
- **`content_plain` must stay in sync**: always derived from token text, never written independently
- **Sadeed is a 1.5B model**: needs decent GPU/MPS for reasonable speed (~50-100 tokens/sec)
- **Token alignment after diacritization**: models may merge/split words; fallback strategy handles this
