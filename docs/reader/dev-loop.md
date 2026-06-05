# Reader dev loop

Current focus: getting the ingestion pipeline, book format, and the
internal web reader to a state where they can support the public
reader. All three move together — when the format changes, ingestion
changes to write it, and the reader changes to render it.

## The loop

```
edit ingestion code  →  python -m ingestion ingest <uri>  \
  --dump web/data --dry-run --tashkeel-engine shakkala
                        ↓
                        web/data/<uri>.{parsed,tashkeeled,enriched}.json
                        ↓
                        open /reader/<openiti_id>  →  inspect rendering
                        (or /inspector/<openiti_id> for block borders + JSON)
```

There is no local-book index UI anymore: `/library` is the product
Discover screen (mock catalog browse, part of the dashboard). Open a
freshly-dumped book by navigating directly to its `openiti_id` URL.

Full pipeline runs: parse → tashkeel → Claude enrichment → JSON files.
`--dry-run` skips only the Supabase upload (transport, not data shape).

Files written, in pipeline order:
- `<uri>.parsed.json`     — after parse (no diacritics, no enrichment)
- `<uri>.tashkeeled.json` — after tashkeel
- `<uri>.enriched.json`   — after Claude enrichment (full output)

The reader picks the highest tier that exists:
**book > enriched > tashkeeled > parsed**.

`book.json` is the new tagged format (see below); the reader converts it to the
legacy in-memory shape at load and renders at parity.

### The tagged format (new)

`python -m ingestion tagged <uri> --dump web/data` writes `<uri>.book.json` in
the simpler tagged format: each block carries a canonical `tagged` field
(HTML-style boundary tags) with derived `text`/`spans`/`lines`. The pipeline is
parse -> detect -> align -> annotate(tagged) -> resolve; it reuses the legacy
parse and hadith stages via the aligner and moves only annotation onto tagged
text, so the AI authors compact boundary tags (entities nest inside structural
spans, no token-array truncation). Add `--skip-annotate` to skip the API.
Design: `docs/superpowers/specs/2026-06-04-simpler-book-format.md`.

`enriched.json` extends ParseResult with:
```jsonc
{
  "metadata": {...}, "pages": [...], "chapters": [...],
  "enrichment": {
    "book":   { title_en, description, genres, composition_date_ah, commentary_on, abridgement_of },
    "author": { full_name_en, bio_en, birth_ah, death_ah, primary_fields }
  },
  "author_data": { /* parsed OpenITI author yml */ }
}
```

All three suffixes live under `web/data/` (gitignored).

### Required env

- `OPENROUTER_API_KEY` — for Claude enrichment (routed through OpenRouter's
  Anthropic-compatible endpoint). Without it, enrichment fails gracefully
  (returns `{}`) and the dump still completes; the reader will just show the
  un-enriched book.

### Skipping stages for fast iteration

If you're iterating on parsing only and don't need tashkeel/enrichment:
- `python -m ingestion parse <uri> --dump web/data` (parse only)
- Or add `--tashkeel-engine none --skip-enrich` to skip the slow stages.

## Where things live

**Ingestion (Python)** — `ingestion/`
- `models.py` — Pydantic types: `Token`, `Block`, `Page`, `Chapter`,
  `BookMetadata`, `ParseResult`. Token has optional `text_raw` for
  pre-tashkeel diff support.
- `parse.py` — OpenITI mARkdown → blocks. Frozen block types:
  `prose | heading | poetry | isnad | matn | takhrij | quran`.
  Also detects inline `{ayah} [سورة: آية]` Qur'an quotations within prose:
  emits a `quran` span over the verse tokens and sets `ref` deterministically
  from the citation (sura-name table → `"sura:ayah"`), which is far more
  reliable than phrase-matching a standard-orthography quote against the
  Uthmani index. A hadith written as **one running source line** (`$RWY$ …
  @MATN@ …` in a single paragraph) is emitted as **one `prose` block** with
  `isnad`/`matn`/`takhrij`/`quran` **spans** rather than separate blocks; a
  hadith laid out across **separate lines** stays separate blocks (#14).
  Raw-file heuristics: a ` ... ` (ellipsis) hemistich separator → `poetry`
  (guarded by balance/standalone checks); an ordinal-only `### | N -` heading →
  an item `number` on the next block (not a chapter); `[ص: N]` print-sheet refs
  are dropped and `:`/`«`-prefixed headings become prose (mistagged body text in
  raw OpenITI files).
- `hadith.py` — deterministic hadith-structure detector, runs after parse:
  splits a prose hadith into `isnad`/`matn`/`takhrij` spans anchored on the
  universal prophetic-speech marker, with `«…»`/narrator-`قال:`/cross-ref
  fallbacks. Groups blocks into hadith units so a matn split across blocks is
  stitched (spans projected per-block); an open `«` quote keeps a unit open
  across a chapter-like heading. Also re-types **misclassified poetry**: a
  `### $` verse-tagged block that is really a hadith (isnad opener / prophetic
  marker / `«»` quote) is flipped `poetry → prose` (hemistichs flattened to
  tokens) so it can be structured — safe across the corpus's real verse.
  Lifts structural coverage from ~8% (LLM-only) to ~99% on Bulugh with 0 matn
  truncations; high precision on the marker tier; fallbacks are low-confidence
  proposals the annotate pass may correct.
- `quran.py` — bundled ayah index + sura-name table. `citation_to_ref`
  parses `"الأعراف: 158"` → `"7:158"`; `lookup_match` resolves a quote by
  exact/containment match.
- `annotate.py` — Claude span/relabel pass. Preserves parse-emitted spans
  (parse owns citation-anchored Qur'an); Claude fills the rest. Span vocab
  includes `isnad`/`matn`/`takhrij`, so the model can structure a running-line
  hadith inline (spans on one block) for books lacking native `@MATN@` tags.
  Poetry relabel is one-directional: the pass never relabels a block TO
  `poetry` (it can't reconstruct `hemistichs`), but it MAY relabel a `poetry`
  block to prose/isnad/matn/takhrij when confident it is not real verse —
  the hemistichs are flattened back to tokens automatically. This is the AI
  safety net behind `hadith.py`'s deterministic poetry re-typing.
- `tashkeel.py` — adds diacritics; engines: `shakkala`, `flan-t5`.
  Populates `text_raw` only when diacritization changed the token.
- `enrich.py` — Claude metadata enrichment + `resolve_spans` (Qur'an refs:
  exact match overrides, containment only fills a missing ref).
- `upload.py` — Supabase writes (skipped in dev loop).

**Reader (Next.js, web/)** — internal-only at `/internal/*`
- `web/src/lib/reader/types.ts` — TS mirrors of the Pydantic models.
- `web/src/lib/reader/queries.ts` — filesystem reads from
  `web/data/`. Pure helpers `synthesizeChapters` and `pagesInChapter`
  are unit-tested.
- `web/src/lib/reader/tashkeel.ts` — `stripTashkeel` regex util.
- `web/src/components/reader/` — block-rendering primitives shared
  by reader and inspector modes.
- reader/inspector routes (open a dumped book by its `openiti_id`):
  - `/reader/<openiti_id>` — clean reader
  - `/inspector/<openiti_id>` — block borders + type/key badges +
    token IDs + JSON drawer + tashkeel diff
  - (the standalone `web/data` book-index page was removed; `/library`
    is now the product Discover screen)

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
