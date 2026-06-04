# Continuous Tagged Book Format Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan phase-by-phase. Steps use checkbox (`- [ ]`) syntax for tracking. Follow TDD: write the failing test first, watch it fail, implement, watch it pass, commit. Keep commits frequent and small.

**Goal:** Store each book as one continuous tagged document sliced into page rows, so a hadith (or any logical unit) is tagged whole by the AI, rendered whole by the reader across page breaks, and addressable for durable citation and sharing.

**Architecture:** Before the AI, content is plain page text. The AI tags unit-safe chunks with `<hadith>/<isnad>/<matn>/<quran>/<person>…` boundaries; a deterministic pass numbers the tags (`h2`, `p7`, `q5`); resolvers fill an `annotations` table keyed by tag id; the tagged document is sliced back into page rows (tags may cross), each carrying the open-tag stack at its start. The reader concatenates a page window and parses, so cross-page units rejoin automatically. Sharing anchors to the frozen plain text.

**Tech Stack:** Python ingestion (pydantic, pytest), Supabase Postgres, Next.js reader (TypeScript, vitest), Anthropic API for the structure pass.

**Spec:** `docs/superpowers/specs/2026-06-05-continuous-tagged-book-format-design.md`

**Reference example:** al-Arba'un al-Nawawiyya hadith #2 (Hadith of Jibril), stored today across pages 47, 49, 50. The end-to-end success test is that it tags, stores, renders, and cites as one unit.

---

## Phasing

Five phases, each shippable and testable on its own. Land them in order; each builds on the prior.

1. **Format core** — the slice/reconstruct round-trip primitive (pure functions).
2. **Ingestion** — assemble, chunk, AI-tag, number, resolve, slice, dump.
3. **Storage** — Supabase schema, upload, read path.
4. **Reader** — concat-and-parse reconstruction and rendering.
5. **Sharing** — plain-text-offset addresses for highlight, bookmark, note, share, citation.

Run the self-review at the bottom before starting Phase 1, and re-read it after each phase.

---

## Phase 1: Format core (slice / reconstruct)

**Goal:** Prove that a continuous tagged document with id-bearing tags can be sliced at arbitrary page-break positions (cutting mid-tag) and losslessly reconstructed, and that each page slice can record the tag stack open at its start.

**Shippable outcome:** A focused, well-tested `page_slice` module. The round-trip property holds on the real hadith #2 shape. Nothing downstream can be correct until this is.

**Files:**
- Create: `ingestion/page_slice.py`
- Create: `ingestion/tests/test_page_slice.py`
- Reuse: `ingestion/tags.py` (tag regex, `compile_tagged`), `ingestion/tagged_format.py` (`Span`)

**Decisions locked here:**
- A page slice stores its raw tagged fragment plus an `open_tags` list (tag name + id) describing the stack open at its start. Tags are left genuinely unclosed across slices; reconstruction is plain concatenation.
- Page-break positions are expressed as offsets into the plain text (tags stripped). v1 assumes no `&lt;/&gt;/&amp;` entities in the text, per the tag-grammar note that they effectively never occur, so plain offset equals raw offset.
- A helper makes a single fragment independently well-formed (prepend the open tags, append closers for tags still open at the end) so one page can be compiled and rendered in isolation for jump-to-page.

**Tasks:**
- [x] **Slice/reconstruct round-trip.** Test first: for several tagged documents and break sets, slicing then concatenating returns the original string. Implement the slicer that walks the tag stream, tracks the open-tag stack, and cuts the current fragment when the plain offset reaches a break. Cover breaks that land inside a tag's text, exactly on a tag boundary, and between two tags.
- [x] **Open-tag stack capture.** Test first: a break inside a `<matn>` inside a `<hadith id="h2">` yields a next-fragment `open_tags` of `[hadith#h2, matn]`. Implement the stack snapshot at each cut. Confirm tag `id` attributes are captured (extend the tag regex to read `id` if needed; keep it ignoring all other attributes).
- [x] **Fragment isolation + compile.** Test first: a mid-matn fragment, made well-formed by the helper, compiles (via `compile_tagged`) to plain text equal to that page's words and a `matn` span covering them. Implement the close-and-reopen helper.
- [x] **Hadith of Jibril fixture.** Test first: a fixture of the three-page hadith #2 split (page 47/49/50 fragments with the `<hadith id="h2">` and one `<matn>` spanning all three) reconstructs to the whole hadith, the matn is one span end to end, and each page's `open_tags` is correct. This is the canonical regression guard for the whole feature.

**Checkpoint:** All `test_page_slice.py` tests pass. Commit. The round-trip is the foundation; do not proceed until it is green on the hadith #2 fixture. **DONE 2026-06-05** — `ingestion/page_slice.py` + 15 tests (suite 277 green); commits `24aa62f`, `ca99a88`, `cdd3ed5`. Spec review ✅, code quality Approved (over-close now raises `TagError`).

---

## Phase 2: Ingestion (assemble, chunk, AI-tag, number, resolve, slice)

**Goal:** Replace per-page block detection with: assemble the book's plain text across page breaks, chunk it at unit boundaries, let the AI emit all structure, number the tags, resolve metadata, and slice the result into page rows. Output a new `.book.json` shape.

**Shippable outcome:** `python -m ingestion tagged 0676Nawawi.ArbacunaNawawiyya --dump web/data` produces a book whose hadith #2 is a single `<hadith id>` with one whole matn spanning pages 47/49/50, plus an annotations list.

**Files:**
- Create: `ingestion/chunk.py` (unit-safe chunking)
- Create: `ingestion/number_ids.py` (deterministic id assignment)
- Modify: `ingestion/pipeline_tagged.py` (new stage order; stop using `detect_hadith_structure` as the structure source)
- Modify: `ingestion/annotate_tagged.py` (AI now produces all structure from chunks, not just entities)
- Modify: `ingestion/resolve_tagged.py` (fill the `annotations` records: ayah ref, person ref, grading)
- Modify: `ingestion/__main__.py` (`run_tagged` dump shape: page rows with `tagged`/`open_tags`/`text`/`start_offset`, plus `annotations`)
- Repurpose: `ingestion/hadith.py` (its markers/`«…»` logic becomes hints fed to the AI and a verification check, not a structure producer)
- Tests: `ingestion/tests/test_chunk.py`, `ingestion/tests/test_number_ids.py`, `ingestion/tests/test_pipeline_tagged.py` (extend)

**Decisions locked here:**
- Assembly concatenates page plain text in document order and records each page's start offset in the book-global plain text. Page markers are retained only as those offsets.
- Chunking cuts only at source unit boundaries (printed hadith numbers, chapter and section headings), never at page markers, so a chunk always holds whole hadiths. Fallback for genres without numbering: coarsest available boundary (chapter, then heading, then paragraph). Each chunk carries its book-global start offset so the AI's spans map back to global positions.
- The AI emits boundary tags only, no attributes and no ids. It receives the source hints (hadith numbers, `«…»` presence) as context.
- Numbering is a single deterministic pass over the merged document in document order, assigning short per-label ids (`h2`, `p7`, `q5`). Per-chunk output is renumbered globally at merge so ids cannot collide.
- Verification compares AI structure against source signals (a matn should sit inside its `«…»` where one exists; a hadith chunk should contain a transmission marker). Mismatches are flagged on the block/annotation for later review, not auto-corrected.

**Tasks:**
- [ ] **Chunker.** Test first: a fixture with two numbered hadith and a chapter heading splits into chunks at the unit starts and never at the page markers that fall mid-hadith; each chunk reports its global start offset. Implement `chunk.py`. Add the fallback-boundary test for an unnumbered prose fixture.
- [ ] **Assembly.** Test first: assembling Nawawi pages yields continuous plain text and a correct page-offset table (page 49 and 50 offsets land mid-hadith-2). Implement assembly in the pipeline.
- [ ] **AI structure pass.** Test first (mocked AI): given a chunk of plain text, the pass returns boundary-tagged text whose tags are well-formed and within the chunk. Update `annotate_tagged.py` to request full structure from chunks. Keep the real API call behind the existing `--skip-annotate` flag for offline tests.
- [ ] **Id numbering.** Test first: a merged document with two hadith, three persons, one quran gets `h1,h2 / p1,p2,p3 / q1`, stable across re-runs and unaffected by chunk boundaries. Implement `number_ids.py`.
- [ ] **Metadata resolution into annotations.** Test first: a `<quran>` tag resolves to a `{sura, ayah}` annotation; a `<hadith>` carries its source number; an unresolved person yields an annotation with a null ref but a valid id. Update `resolve_tagged.py`.
- [ ] **Slice to page rows + dump.** Test first: the pipeline output for Nawawi has page rows whose concatenated `tagged` reconstructs the whole book, hadith #2 is one `<hadith id>` across pages 47/49/50 with one matn, and `annotations` contains `h2`. Wire Phase 1's slicer into the pipeline and update the dump shape.
- [ ] **Verification check.** Test first: a matn that does not sit inside an available `«…»` is flagged; a clean hadith #2 is not. Implement the check as a non-blocking flag.

**Checkpoint:** The Nawawi dump shows hadith #2 whole with a real annotations list. Run the ingestion test suite. Commit. This is the first end-to-end proof of the accuracy fix.

---

## Phase 3: Storage (Supabase schema, upload, read path)

**Goal:** Persist the new shape and read it back. Keep download by page.

**Shippable outcome:** Nawawi uploads to Supabase in the new shape; the reader's data layer fetches page rows and annotations and reconstructs a book object.

**Files:**
- Create: a timestamped migration in `supabase/migrations/` and mirror it in `web/supabase-schema.sql`
- Modify: `ingestion/upload_tagged.py` (write page rows + annotations)
- Modify: `web/src/lib/reader/queries.ts` (Supabase read path: page rows + annotations)
- Tests: `ingestion/tests/test_upload.py` (extend), `web/src/lib/reader/queries.test.ts` (extend)

**Decisions locked here:**
- The `pages` row carries the page's `tagged` fragment, its `open_tags`, the derived plain `text`, and its book-global `start_offset`. The old per-page `content_blocks` is removed.
- A new `annotations` table keyed by `(book_id, id)` holds `label`, optional plain-text `start`/`end`, and a JSONB `meta`. No metadata table existed before; this is additive.
- Download stays per page. Annotations for a book are small and fetched once up front.

**Tasks:**
- [ ] **Migration.** Test/verify first: write the migration (new `pages` columns, drop `content_blocks`, create `annotations`), apply it to a local Supabase, confirm the schema. Mirror it in `web/supabase-schema.sql`.
- [ ] **Upload.** Test first: uploading the Nawawi book writes the expected page rows and annotation rows; re-upload is idempotent. Update `upload_tagged.py`.
- [ ] **Read path.** Test first: the queries layer fetches a book's pages and annotations and returns the in-memory book object the reader expects. Update `queries.ts`. Keep the local-dump dev path working alongside the Supabase path.

**Checkpoint:** Round-trip a real book through Supabase and back. Commit.

---

## Phase 4: Reader (concat, parse, render)

**Goal:** Render the reconstructed document, with cross-page units whole and jump-to-page seeded by `open_tags`.

**Shippable outcome:** Opening Nawawi in the reader shows hadith #2 as one continuous hadith with correct isnad/matn styling across the 47/49/50 page boundaries; page markers still display; jump-to-page works.

**Files:**
- Modify: `web/src/lib/reader/types.ts` (page row shape; drop stored blocks/tokens)
- Modify: `web/src/lib/reader/newFormat.ts` (port Phase 1's concat + parse + fragment-isolation to TypeScript; reuse the same fixtures)
- Modify: `web/src/lib/reader/sentences.ts` (build the word/selection map from rendered text, not stored tokens)
- Modify: `web/src/components/reader/Block.tsx`, `TokenText.tsx`, `PageBoundary.tsx`, `PageMarkersToggle.tsx` (render the parsed tag tree; page markers from offsets)
- Tests: `web/src/lib/reader/newFormat.test.ts`, `sentences.test.ts` (extend, sharing the hadith #2 fixture)

**Decisions locked here:**
- The reader parses the concatenated window into the same span shape the renderer already consumes (isnad/matn/takhrij/person/quran styling stays as-is). Annotations attach by tag id.
- Jump-to-page renders from the target page's `open_tags` rather than from the chapter start.
- Word tap, highlight, and recitation key off a derived `{page or unit}:{wordIndex}` from the rendered word list, with no stored per-word tokens.

**Tasks:**
- [ ] **Port reconstruction.** Test first (reuse the hadith #2 fixture in vitest): concat + parse rebuilds the whole hadith and its spans. Implement in `newFormat.ts`.
- [ ] **Types.** Update `types.ts` to the page-row shape; fix the compile.
- [ ] **Render the tag tree.** Test/verify first: the block renderer shows hadith #2 continuous with isnad/matn styling across the seam. Update the components.
- [ ] **Page markers + jump.** Test/verify first: page markers render at the right offsets and jump-to-page lands correctly using `open_tags`.
- [ ] **Selection map.** Test first: the word/selection map is built from rendered text and matches what the user taps. Update `sentences.ts`.

**Checkpoint:** Reader shows hadith #2 whole. Run the web reader test suite and the dev loop (dump then open `/reader/0676Nawawi.ArbacunaNawawiyya`). Commit.

---

## Phase 5: Sharing and user data (plain-text-offset addresses)

**Goal:** Let a user highlight, bookmark, note, share, and cite any range, including across pages, with durable handles.

**Shippable outcome:** A user can select a quote that crosses a page seam, highlight it, and produce a share link and a citation string ("Sahih Muslim, Hadith of Jibril, Nawawi #2"). The link resolves after a re-ingest.

**Files:**
- Create: a timestamped migration in `supabase/migrations/` for the user-data address change; mirror in `web/supabase-schema.sql`
- Modify: the reader user-data layer in `web/src/lib/reader/` (selection to address, address to render position, citation string from annotations)
- Tests: the relevant `web/src/lib/reader/*.test.ts`

**Decisions locked here:**
- A share/user-data address is `{ book_id, start, end, anchor_text, in_id? }` over the book's frozen plain text. The single-`page_id` plus token-id anchoring is replaced. The page and the enclosing unit are derived, not stored.
- The citation string is built from the enclosing tag id's annotation `meta` (collection ref, title, number).
- `anchor_text` (~20 chars) provides fuzzy re-anchoring if anything ever shifts.

**Tasks:**
- [ ] **Address model + migration.** Test/verify first: write and apply the user-data schema change. Mirror in the schema file.
- [ ] **Selection to address.** Test first: a selection crossing the 49/50 seam yields a single `{start, end}` range with the right `in_id`. Implement.
- [ ] **Address to render.** Test first: an address resolves to the page and rendered position, with the highlight drawn across the seam. Implement.
- [ ] **Citation string.** Test first: an address inside hadith #2 produces the expected citation from annotations. Implement.

**Checkpoint:** Share and re-resolve a cross-page quote. Commit.

---

## Documentation sync

After Phase 4 (reader is the user-visible change) and again after Phase 5:
- [ ] Rewrite `docs/reader/book-format.md` to the new model (page-sliced tagged + annotations + plain-text-offset sharing). Remove the per-page-block and token-id descriptions.
- [ ] Update `docs/reader/ingestion-pipeline.md` for the assemble/chunk/AI/number/resolve/slice stages.
- [ ] Update `docs/reader/app.md` where it describes block/token rendering and user-data anchoring.
- [ ] Update the project memory note `project_reader_dev_loop` if the dump file shape or dev-loop command changes.

Keep docs succinct and direct, matching the existing style.

---

## Self-review (run before Phase 1, re-check after each phase)

**Spec coverage:** every spec section maps to a phase. Pipeline → Phase 2. Page-row storage and annotations table → Phase 3. Reader concat-and-parse → Phase 1 (logic) and Phase 4 (render). Sharing → Phase 5. The immutable-text and unit-safe-chunking decisions are encoded in Phases 1 and 2.

**No silent gaps:** the two open spec questions (starter-catalog verification and freezing; non-hadith unit boundaries) are not blockers for Nawawi. Address them when extending past hadith collections; note them at Phase 2's checkpoint.

**Sequencing risk:** Phase 1 is load-bearing; its round-trip must be green before Phase 2 wires it in. The TypeScript port in Phase 4 must reuse the exact Phase 1 fixtures so the two implementations cannot drift.

**Cost note:** the AI structure pass on large books (Bukhari, Siyar) is out of scope for this plan; validate it on Nawawi first. Chunking is built to make the large-book pass feasible later.
