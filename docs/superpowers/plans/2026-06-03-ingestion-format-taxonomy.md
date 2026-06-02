# Ingestion Format Taxonomy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the ingestion pipeline emit the frozen reader taxonomy (seven block types with level/number/footnotes plus the frozen inline span set with resolved Quran refs), and prove it on three real OpenITI books across genres.

**Architecture:** Three producers in sequence. `parse.py` does structural-only conversion of OpenITI mARkdown into the seven block types. `annotate.py` does all Claude detection (block relabel + inline spans on the frozen vocabulary). `enrich.py` connects spans to data, starting with deterministic Quran sura:ayah resolution, and keeps the existing book/author metadata enrichment. The existing `python -m ingestion ingest` command orchestrates the stages in the right order (annotate before enrich).

**Tech Stack:** Python 3, Pydantic models (frozen in `ingestion/models.py`), pytest. No new runtime deps beyond a committed Quran data file. Anthropic SDK already wired via `ingestion/_client.py`.

**Conventions:** TDD per task (failing test first). Tests live in `ingestion/tests/`. New parser features use a dedicated fixture so existing count-based tests in `test_parse.py` stay green. Run a single test with `python -m pytest ingestion/tests/test_x.py::test_name -v`. Commit after each task. Do not edit `ingestion/models.py` or `web/src/lib/reader/types.ts` (format is frozen and already mirrored).

---

## File structure

- `ingestion/parse.py` — modified. Structural parse; adds level, number, takhrij, quran, footnote handling; removes biography branch.
- `ingestion/annotate.py` — modified. Frozen vocabulary; span detection decoupled from relabel skip.
- `ingestion/enrich.py` — modified. Adds Quran ref resolution; metadata enrichment unchanged.
- `ingestion/quran.py` — created. Loads the bundled Quran index and exposes a normalize + lookup helper. Kept separate so enrich.py stays focused and the index logic is unit-testable in isolation.
- `ingestion/data/quran.json` — created. Bundled Quran text by sura/ayah.
- `ingestion/__main__.py` — modified. Invoke Quran span resolution inside the enrich stage before the enriched dump.
- `ingestion/tests/fixtures/taxonomy_sample.mARkdown` — created. Exercises heading levels, numbering, takhrij, quran block, footnote marker.
- `ingestion/tests/test_parse_taxonomy.py` — created. Parser feature tests.
- `ingestion/tests/test_annotate.py` — created or extended. Vocabulary + skip-decoupling tests.
- `ingestion/tests/test_quran.py` — created. Normalizer + index lookup tests.
- `ingestion/tests/test_enrich.py` — extended. Quran span resolution tests.

---

## Task 1: Heading level on the block

**Files:**
- Modify: `ingestion/parse.py` (heading branch in `_dispatch`)
- Create: `ingestion/tests/fixtures/taxonomy_sample.mARkdown`
- Create: `ingestion/tests/test_parse_taxonomy.py`

- [ ] **Step 1: Create the taxonomy fixture.** Write a small mARkdown file with a valid header block, one page, a level-1 heading (`### |`), a level-2 heading (`### ||`), a `$RWY$` hadith line with `@MATN@`, a takhrij-style line after the matn (begins with `رواه`), a standalone Quran line wrapped in the ornate brackets `﴿ ... ﴾`, and a numbered item line (begins with an Arabic-Indic digit then a dash). This single fixture feeds Tasks 1-6.
- [ ] **Step 2: Write the failing test.** In `test_parse_taxonomy.py`, assert the level-1 heading block has `level == 1` and the level-2 heading block has `level == 2`.
- [ ] **Step 3: Run it, expect failure** (`level` is `None` today). Command: `python -m pytest ingestion/tests/test_parse_taxonomy.py -v`.
- [ ] **Step 4: Implement.** In the heading branch of `_dispatch`, set `level=level` on the `Block` it constructs (the value is already computed for the `Chapter`).
- [ ] **Step 5: Run the test, expect pass.**
- [ ] **Step 6: Run the full parse suite** (`python -m pytest ingestion/tests/test_parse.py -v`) to confirm no regression.
- [ ] **Step 7: Commit** (`feat(parse): set heading level on block`).

## Task 2: Item / hadith number extraction

**Files:**
- Modify: `ingestion/parse.py`
- Modify: `ingestion/tests/test_parse_taxonomy.py`

- [ ] **Step 1: Write the failing test.** Assert the numbered item block has `number == "١"` (the printed Arabic-Indic ordinal) and that the digit token is no longer the first token of the block.
- [ ] **Step 2: Run it, expect failure.**
- [ ] **Step 3: Implement.** Add a helper that, before tokenizing a content line that will become a block, detects a leading ordinal: a run of Arabic-Indic (`\u0660-\u0669`) or ASCII digits optionally followed by a separator (`-`, `.`, `)`, `،`). If found, strip it from the text and record it as the block's `number`. Apply to prose, isnad, matn, and quran block construction. Keep `number` as the raw string.
- [ ] **Step 4: Run the test, expect pass.**
- [ ] **Step 5: Full parse suite, no regression. Commit** (`feat(parse): extract printed item numbering`).

## Task 3: takhrij block detection

**Files:**
- Modify: `ingestion/parse.py`
- Modify: `ingestion/tests/test_parse_taxonomy.py`

- [ ] **Step 1: Write the failing test.** Assert the sourcing line after the matn (begins with `رواه`) parses to a block with `type == "takhrij"`.
- [ ] **Step 2: Run it, expect failure** (it is `prose` today).
- [ ] **Step 3: Implement.** Add a deterministic prefix rule in `_dispatch`: when a content line begins with a takhrij keyword from a small set (`رواه`, `أخرجه`, `أخرجها`, `رواها`, `متفق`), emit a `takhrij` block instead of `prose`. Document the keyword set in a module constant. Annotate can still relabel later.
- [ ] **Step 4: Run the test, expect pass.**
- [ ] **Step 5: Full parse suite, no regression. Commit** (`feat(parse): detect takhrij sourcing lines`).

## Task 4: quran block detection

**Files:**
- Modify: `ingestion/parse.py`
- Modify: `ingestion/tests/test_parse_taxonomy.py`

- [ ] **Step 1: Write the failing test.** Assert a standalone line wholly wrapped in the ornate brackets (`﴿` U+FD3E … `﴾` U+FD3F) parses to a block with `type == "quran"`, tokens preserved including the bracket glyphs.
- [ ] **Step 2: Run it, expect failure.**
- [ ] **Step 3: Implement.** In `_dispatch`, before the prose fallback, detect a line that starts with `﴿` and ends with `﴾` (after stripping whitespace) and emit a `quran` block. The bracket glyphs stay attached to their tokens (the reader renders them).
- [ ] **Step 4: Run the test, expect pass.**
- [ ] **Step 5: Full parse suite, no regression. Commit** (`feat(parse): detect standalone quran blocks`).

## Task 5: Drop the biography type

**Files:**
- Modify: `ingestion/parse.py`
- Modify: `ingestion/tests/test_parse_taxonomy.py`

- [ ] **Step 1: Write the failing test.** Add a `### $BIO_MAN$ ...` line to the fixture (or a focused inline fixture in the test) and assert it parses to `type == "prose"`, not `biography`.
- [ ] **Step 2: Run it, expect failure** (currently emits `biography`).
- [ ] **Step 3: Implement.** Remove the `_BIO_RE` branch from `_dispatch` so biography markers fall through to the prose path (strip the marker prefix, keep the text). Delete the now-unused `_BIO_RE` constant.
- [ ] **Step 4: Run the test, expect pass.**
- [ ] **Step 5: Full parse suite, no regression. Commit** (`refactor(parse): drop cut biography type, fall back to prose`).

## Task 6: Footnote best-effort extraction

**Files:**
- Modify: `ingestion/parse.py`
- Modify: `ingestion/tests/test_parse_taxonomy.py`

- [ ] **Step 1: Write the failing test.** Using a focused fixture that contains an inline footnote marker in body text plus a separated note line, assert: the page's `footnotes` list contains a `Footnote` with the matching `marker`, and the body block carries a `Span` with `label == "footnote"` and `ref` equal to the marker. If the source has no footnotes, `footnotes` is empty (assert this on the main taxonomy fixture).
- [ ] **Step 2: Run it, expect failure.**
- [ ] **Step 3: Implement.** Detect footnote markers only when the source clearly encodes them (a recognized marker convention; document the exact pattern chosen as a module constant). Populate `Page.footnotes` and attach the `footnote` span on the anchoring block. When no markers are present, leave `footnotes` empty. Keep this conservative; cleaned OpenITI strips footnotes, so empty is the expected common case.
- [ ] **Step 4: Run the test, expect pass.**
- [ ] **Step 5: Full parse suite, no regression. Commit** (`feat(parse): best-effort footnote extraction`).

## Task 7: Retarget annotate vocabulary to the frozen set

**Files:**
- Modify: `ingestion/annotate.py`
- Create: `ingestion/tests/test_annotate.py`

- [ ] **Step 1: Write the failing test.** Build a small `ParseResult`, mock the Anthropic client to return spans using the frozen labels (`person`, `quran`, `book_ref`) and a relabel to a frozen block type. Assert that applying the annotation accepts the frozen labels and stores them, and that an old-vocabulary label (`personal_name`) is rejected (not stored).
- [ ] **Step 2: Run it, expect failure** (old vocab still in `SPAN_LABELS` / `BLOCK_TYPES`).
- [ ] **Step 3: Implement.** Replace `SPAN_LABELS` with the frozen set `quran`, `person`, `place`, `book_ref`, `hadith_ref`, `date_hijri`. Replace `BLOCK_TYPES` with the seven frozen types. Update the system prompt text: span definitions and block definitions to the frozen taxonomy, dropping all cut types and old label names. Update `_has_native_tags` to count `isnad`/`matn` only (drop `biography`).
- [ ] **Step 4: Run the test, expect pass.**
- [ ] **Step 5: Commit** (`feat(annotate): frozen span and block vocabulary`).

## Task 8: Span detection runs even when relabel is skipped

**Files:**
- Modify: `ingestion/annotate.py`
- Modify: `ingestion/tests/test_annotate.py`

- [ ] **Step 1: Write the failing test.** Build a `ParseResult` with enough native `isnad`/`matn` blocks to trip the native-tags threshold. Mock the client to return spans. Call the annotate entry point and assert: block types are unchanged (relabel skipped) but spans are still attached.
- [ ] **Step 2: Run it, expect failure** (today the whole pass returns early on native tags, so no spans).
- [ ] **Step 3: Implement.** Restructure the entry point so the native-tags short-circuit only disables the relabel decision, not the span/flag pass. The cleanest split: keep one chunked Claude pass that always runs and always applies spans/flags; gate only the type reassignment behind the native-tags / confidence check. Preserve stats keys and the graceful-failure contract.
- [ ] **Step 4: Run the test, expect pass.**
- [ ] **Step 5: Re-run `test_annotate.py` and `test_parse.py`. Commit** (`fix(annotate): always detect spans, gate only relabel`).

## Task 9: Quran data file + index module

**Files:**
- Create: `ingestion/data/quran.json`
- Create: `ingestion/quran.py`
- Create: `ingestion/tests/test_quran.py`

- [ ] **Step 1: Add the data file.** Download a complete Uthmani Quran text keyed by sura and ayah from a well-established open dataset (verify it has all 114 suras / 6236 ayat). Commit it to `ingestion/data/quran.json`. Record the source and version in a short header comment field inside the JSON or alongside in the module docstring.
- [ ] **Step 2: Write the failing test.** In `test_quran.py`: assert `normalize(text)` strips tashkeel, ornate brackets, and normalizes alif/hamza/ya variants; assert `lookup(quote)` returns `(1, 2)` for a normalized fragment of al-Fatiha ayah 2 (`الحمد لله رب العالمين`), and returns `None` for a fragment that matches more than one ayah ambiguously or matches nothing.
- [ ] **Step 3: Run it, expect failure** (module does not exist).
- [ ] **Step 4: Implement `ingestion/quran.py`.** Load `data/quran.json` once at import. Provide `normalize(text)` (NFC, remove `\u064B-\u065F\u0670` diacritics, remove `﴿﴾` and surrounding punctuation, map `أإآ`→`ا`, `ى`→`ي`, collapse whitespace). Build a normalized ayah index. Provide `lookup(quote) -> tuple[int,int] | None`: normalize the quote, find ayat that contain it; return the sura:ayah only on a unique match, else `None`.
- [ ] **Step 5: Run the test, expect pass.**
- [ ] **Step 6: Commit** (`feat(quran): bundled ayah index and matcher`).

## Task 10: Quran span resolution in enrich + pipeline wiring

**Files:**
- Modify: `ingestion/enrich.py`
- Modify: `ingestion/__main__.py`
- Modify: `ingestion/tests/test_enrich.py`

- [ ] **Step 1: Write the failing test.** In `test_enrich.py`, build a `ParseResult` whose page has a `quran` block with a span labeled `quran` (ref unset or deliberately wrong) over tokens spelling a known ayah. Call a new `resolve_spans(result)` and assert the span's `ref` becomes the correct `"sura:ayah"`. Add a second test: a `person` span passes through with `ref` unchanged. Add a third: a quran span whose text matches no ayah keeps `ref` unresolved (and does not raise).
- [ ] **Step 2: Run it, expect failure** (`resolve_spans` does not exist).
- [ ] **Step 3: Implement `resolve_spans(result)` in enrich.py.** Walk every block (and poetry hemistichs), collect tokens, and for each span labeled `quran` reconstruct the quoted text from its token range, call `quran.lookup`, and set `ref` on a unique match (overwriting any prior value). Leave all other labels untouched. Pure and deterministic; no network, no client.
- [ ] **Step 4: Run the test, expect pass.**
- [ ] **Step 5: Wire it in.** In `__main__.py` enrich stage (3b), after metadata enrichment and before the enriched dump, call `resolve_spans(result)` so the mutated spans are serialized into `enriched.json`. Log a one-line count of resolved quran refs.
- [ ] **Step 6: Run `test_enrich.py` and the full `ingestion` suite. Commit** (`feat(enrich): resolve quran spans to sura:ayah`).

## Task 11: Source the validation books

**Files:**
- No source changes. Writes into `RELEASE/data/` (corpus, outside the repo tree).

- [ ] **Step 1: Identify century repos.** Ibn Kathir (d. 774) lives in `OpenITI/0800AH`; al-Mutanabbi (d. 354) in `OpenITI/0400AH`. Confirm the exact book directory names via `gh api repos/OpenITI/0800AH/contents/data/0774IbnKathir` and the equivalent for Mutanabbi.
- [ ] **Step 2: Fetch Ibn Kathir Tafsir.** Download the best-quality file (prefer `.mARkdown`) for `0774IbnKathir.TafsirQuran` into `RELEASE/data/0774IbnKathir/0774IbnKathir.TafsirQuran/`, plus the author `.yml`. Use `gh api .../download_url` or the raw URL.
- [ ] **Step 3: Fetch the Mutanabbi Diwan.** Download the diwan file into `RELEASE/data/<author>/<author.book>/` and grep it for `%~%` hemistich markers to confirm usable poetry tagging. If absent, pick another diwan from `0400AH` (or report back) and note the substitution.
- [ ] **Step 4: Sanity check.** `python -m ingestion parse <uri> --dump web/data` for each new book (parse-only, fast) and confirm it produces pages without error.
- [ ] **Step 5: Commit** any tracking note if needed (corpus files are gitignored; no repo commit expected). Otherwise skip.

## Task 12: Run the real pipeline and verify against the fixture

**Files:**
- No source changes (verification task). May produce small follow-up fixes looped back into earlier tasks.

- [ ] **Step 1: Run the full pipeline on all three** with `python -m ingestion ingest <uri> --dump web/data --dry-run --tashkeel-engine shakkala` for Nawawi 40, the Ibn Kathir slice, and the Mutanabbi diwan. (Requires `ANTHROPIC_API_KEY`. Ibn Kathir is large; if needed, ingest a bounded slice for the proof.)
- [ ] **Step 2: Shape check.** For each `web/data/<uri>.enriched.json`, confirm: only the seven block types appear; headings carry `level`; numbered items carry `number`; inline spans use only the frozen labels. Compare structure against `web/fixtures/Sample.Taxonomy.enriched.json`.
- [ ] **Step 3: Quran ref check.** In the Ibn Kathir output, confirm `quran` spans resolved to plausible `sura:ayah` refs.
- [ ] **Step 4: Render check.** Start the web dev server and load `/internal/library`, then `/internal/reader/<id>` and `/internal/inspector/<id>` for each book. Confirm clean rendering and that the inspector shows the expected block types and spans.
- [ ] **Step 5: Fix and loop.** Any mismatch (wrong block type, missing level/number, bad span) loops back to the relevant earlier task with a new failing test first. Do not patch in this task without a test.
- [ ] **Step 6: Update `docs/reader/book-format.md` and `docs/reader/dev-loop.md`** where they still describe the old block set or note the heading-level gap as open. Commit (`docs: sync book-format and dev-loop to frozen taxonomy`).

---

## Self-review notes

- Spec coverage: parse changes (Tasks 1-6), annotate vocabulary + skip fix (Tasks 7-8), enrich Quran resolution + bundled data (Tasks 9-10), validation across 3 genres + fixture parity + render (Tasks 11-12), docs sync (Task 12). Metadata enrichment intentionally untouched (stays in enrich.py). Out-of-scope span resolution left as pass-through (Task 10, Step 3).
- The `number` extraction (Task 2) and `takhrij`/`quran` detection (Tasks 3-4) use deterministic source heuristics; Claude can refine via annotate. Heuristic keyword/pattern sets are pinned in module constants so they are reviewable.
- Frozen contract is not edited: no changes to `ingestion/models.py` or `web/src/lib/reader/types.ts`.
