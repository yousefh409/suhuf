# Reader dev loop

Current focus: getting the ingestion pipeline, book format, and the
internal web reader to a state where they can support the public
reader. All three move together — when the format changes, ingestion
changes to write it, and the reader changes to render it.

## The loop

```
edit ingestion code  →  python -m ingestion ingest <uri>  \
  --dump web/data --dry-run --skip-enrich --tashkeel-engine shakkala
                        ↓
                        web/data/<uri>.{parsed,tashkeeled}.json
                        ↓
                        refresh /internal/library  →  inspect rendering
```

No DB in the dev loop. No Claude API calls (`--skip-enrich`). No upload
(`--dry-run`). Just: parse → tashkeel → JSON file → render.

The reader prefers `*.tashkeeled.json` over `*.parsed.json` for the
same `openiti_id`. Both live under `web/data/` (gitignored).

## Where things live

**Ingestion (Python)** — `ingestion/`
- `models.py` — Pydantic types: `Token`, `Block`, `Page`, `Chapter`,
  `BookMetadata`, `ParseResult`. Token has optional `text_raw` for
  pre-tashkeel diff support.
- `parse.py` — OpenITI mARkdown → blocks. Block types:
  `prose | hadith | isnad | matn | poetry | biography | heading`.
- `tashkeel.py` — adds diacritics; engines: `shakkala`, `flan-t5`.
  Populates `text_raw` only when diacritization changed the token.
- `enrich.py` — Claude metadata enrichment (skipped in dev loop).
- `upload.py` — Supabase writes (skipped in dev loop).

**Reader (Next.js, web/)** — internal-only at `/internal/*`
- `web/src/lib/reader/types.ts` — TS mirrors of the Pydantic models.
- `web/src/lib/reader/queries.ts` — filesystem reads from
  `web/data/`. Pure helpers `synthesizeChapters` and `pagesInChapter`
  are unit-tested.
- `web/src/lib/reader/tashkeel.ts` — `stripTashkeel` regex util.
- `web/src/components/reader/` — block-rendering primitives shared
  by reader and inspector modes.
- `web/src/app/internal/` — routes:
  - `/internal/library` — book index from `web/data/*.json`
  - `/internal/reader/[openiti_id]/[ch_index]` — clean reader
  - `/internal/inspector/[openiti_id]/[ch_index]` — block borders +
    type/key badges + token IDs + JSON drawer + tashkeel diff
  - `/internal/layout.tsx` — INTERNAL badge, `noindex`, robots disallow

**Specs / plans**
- `docs/superpowers/specs/2026-04-29-internal-reader-design.md`
- `docs/superpowers/plans/2026-04-29-internal-reader.md`

## Open questions / known gaps

- Shakkala silently falls back to FLAN-T5 in our env (Shakkala load
  fails). Worth investigating, then switching the default engine
  accordingly.
- Token count mismatches happen during tashkeel (block kept as-is).
  Inspector shows the type/key — easy to find and inspect raw JSON.
- Real chapters across multiple volumes not yet supported in
  `pagesInChapter` — cuts at the volume boundary. Synthesized
  per-volume chapters work fine.
- No author display in local mode (no author yml parser yet).
- Heading blocks don't carry `level` today (parser drops it onto the
  chapter entry). Block renderer always emits `<h2>`.

## When changing the format

Anything that adds/changes a `Block`/`Token`/`Page` field needs:
1. `ingestion/models.py` — add the field
2. `ingestion/parse.py` and/or `tashkeel.py` — populate it
3. New tests in `ingestion/tests/`
4. `web/src/lib/reader/types.ts` — mirror the field
5. Affected component(s) — render or surface it
6. Re-dump and refresh

The Pydantic JSON serialization is the contract between the two sides.

## Public reader (later)

The public reader will need its own data path back to Supabase. The
shape of `lib/reader/queries.ts` (four async functions returning the
TS types) was chosen so the implementation can swap without changing
routes or components — but that's a future task. For now, focus on
making the format and rendering right.
