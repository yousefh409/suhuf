# Deterministic hadith-structure detection

## Problem

The Claude `annotate` pass is the only source of hadith structure
(isnad/matn/takhrij) on real OpenITI books, because the corpus carries no
native `$RWY$`/`@MATN@` tags (verified: zero across Bukhari, Muslim, Tirmidhi,
Bulugh — see [[project_openiti_not_semantically_tagged]]). Measured on Bulugh
(1,573 hadith):

- **Coverage is ~8%** — the LLM labels structure on 125 of 1,573 hadith. It is
  opportunistic (the prompt says "tag what you find"), it triages under a chunk
  output-token budget, and it has no deterministic pre-pass.
- **Precision wobbles** even when it labels — e.g. it tagged the lead-in
  `قال رسول الله ﷺ:` as `isnad` and missed the actual narrator.

Yet ~80% of hadith structure is mechanically detectable. We are paying an LLM to
do — badly and incompletely — something that is mostly deterministic.

## Goal

Near-100% **coverage** and exact **boundaries** on the structural layer
(isnad/matn/takhrij), generalising across hadith collections and across genres
(a hadith quoted inside a fiqh/tafsir book), at balanced corpus-scale cost. The
LLM keeps doing what it is uniquely good at (entities) and what rules cannot
(the irregular residual + verifying uncertain boundaries).

## Key evidence — markers vary, so anchor on the universal one

Marker prevalence across collections (counts):

| Collection | `«…»` | رواه/أخرجه | قال رسول/عن النبي | حدثنا |
|---|---|---|---|---|
| Bukhari | **0** | 135 | **2,561** | 18,641 |
| Muslim | 7,759 | 30 | **2,325** | 23,329 |
| Tirmidhi | **0** | 327 | **2,365** | 10,781 |
| Bulugh | 1,347 | 1,389 | 508 | 1 |

- **`«…»` matn-quote is edition-specific** — Bukhari and Tirmidhi have none. A
  "matn = «…»" rule would fail entirely on them.
- **`رواه` takhrij is a digest feature** — common in Bulugh (a digest that cites
  sources), rare in primary collections (which *are* the source).
- **The prophetic-speech marker is universal** — `قال رسول الله ﷺ` / `عن النبي
  ﷺ` / `أن رسول الله` appears in the thousands in every collection. It is the
  reliable isnad→matn boundary.

So: **anchor on the prophetic-speech marker; use `«…»` and `رواه` as bonus
precision where present.**

## Approach (chosen: deterministic structure + scoped/verifying LLM)

Two cooperating layers:

1. **Deterministic detector** — high coverage + exact boundaries on the
   confident cases, free.
2. **LLM (`annotate`)** — entities, the residual hadith with no marker, and
   verification of low-confidence deterministic spans. No new pass, no
   per-hadith call.

## Component 1 — `ingestion/hadith.py` (new, deterministic)

`detect_hadith_structure(result: ParseResult) -> dict` runs **right after parse**
(before tashkeel), mutating blocks in place. Returns stats (hadith detected,
spans emitted, by-confidence counts). Lives in its own module to keep
`parse.py` (already 769 lines) focused and to be testable in isolation.

Emits inline `isnad`/`matn`/`takhrij` **spans** on hadith blocks — the same
one-block-with-spans shape as #14. No new block types.

### Marker vocabularies (one documented place)

- `PROPHETIC_MARKERS` — `قال رسول الله`, `قال النبي`, `عن النبي`,
  `عن رسول الله`, `أن النبي`, `أن رسول الله`, `سمعت رسول الله`, `سمعت النبي`
  (matched tashkeel-insensitively; ﷺ / `صلى الله عليه وسلم` variants tolerated).
- `ISNAD_VERBS` — `حدثنا`, `حدثني`, `أخبرنا`, `أخبرني`, `أنبأنا`, `سمعت`, `عن`,
  `قال` (mirror of the reader's existing `web/src/lib/reader/spanStyles.ts`
  set; keep the two in sync).
- `TAKHRIJ_KEYWORDS` — reuse `parse._TAKHRIJ_KEYWORDS`
  (`رواه`/`أخرجه`/`أخرجها`/`رواها`/`متفق`).

### Per-block algorithm

1. **Hadith-likeness gate** (prevents false positives on fiqh/tafsir prose): the
   block must contain an isnad verb **or** a prophetic marker. A bare `«…»` or
   `رواه` alone does **not** qualify — that is how a fiqh definition-in-quotes or
   a Qur'an quote is kept out.
2. **Boundary** = the first token `b` of the matched prophetic-marker phrase:
   - `isnad` span = tokens `[0 .. b-1]` (the narrator chain), if non-empty.
   - `matn` span = `[b .. matn_end]`, where `matn_end` is the **earliest** of:
     the first `TAKHRIJ_KEYWORDS` token after `b`, the close token of a `«…»`
     quote opened at/after `b`, or the block end. This puts the
     `قال رسول الله ﷺ:` lead **inside** the matn (fixing the mislabel) while
     excluding a trailing takhrij or trailing editorial after a closing quote.
   - `takhrij` span = from the first `TAKHRIJ_KEYWORDS` token after the matn to
     the block end, if present.
3. **No prophetic marker but isnad verbs present** (e.g. a Companion's report):
   leave structure to the LLM residual — do not guess.
4. **Self-check** (free): matn non-empty and ordering isnad < matn < takhrij;
   on failure emit nothing (the block becomes residual).
5. **Confidence** on each span:
   - **high (≈0.95)** when ≥2 signals agree (marker + `«…»`, or marker + takhrij).
   - **low (≈0.7)** when only the prophetic marker fired (no quote, no takhrij).

## Component 2 — `annotate.py` changes (LLM rescope + verify)

- **Pipeline:** `__main__` calls `detect_hadith_structure(result)` after parse;
  the deterministic spans are present before `annotate` runs.
- **Serialization:** include each block's existing spans (label + confidence) in
  the payload sent to the model, so it sees what is already structured.
- **Prompt:** structure (isnad/matn/takhrij) is *pre-supplied*; the model should
  (a) add **entities** (person/place/date/book_ref/hadith_ref) and **flags**,
  (b) add structure **only** to blocks that have none (the residual), and
  (c) may correct a structural span **only if** it is marked low-confidence.
- **Merge rule (`_apply_block_annotation`):** today all parse spans are locked.
  Change to **confidence-gated authority**: spans with confidence ≥ a threshold
  (e.g. 0.9) stay locked (model overlaps dropped); spans below it are
  *proposals* a model span of the same structural label may replace.

## Generalization (verified against the table)

- Bukhari — full isnad + `قال رسول الله`, no quote/takhrij → boundary on the
  marker. ✅
- Muslim — `«…»` matn → marker + quote, high confidence. ✅
- Tirmidhi — `قال` + `رواه`, no quote → marker + takhrij. ✅
- Bulugh — `عن X` + `«…»` + `رواه` → all three signals, high confidence. ✅
- Hadith inside a fiqh/tafsir book — the marker appears inline; the gate lets it
  through and the structure is tagged in place. ✅
- A fiqh `«…»` definition or a Qur'an `«…»` quote with no isnad verb / prophetic
  marker — **gated out**, stays prose (Qur'an handled by its own span). ✅

## Out of scope

- Entity detection itself (stays in the LLM `annotate` pass — unchanged logic,
  just rescoped emphasis).
- The `@HUKM@` grading tag (separate, rare).
- Reader rendering (already consumes isnad/matn/takhrij spans).

## Testing (`ingestion/tests/test_hadith.py`)

Fixtures, one per shape above:
- Bukhari-style: full isnad, no quote, no takhrij → isnad+matn, boundary at the
  marker, no takhrij span.
- Muslim-style: `«…»` matn → matn tightened to quote bounds, high confidence.
- Tirmidhi-style: marker + `رواه` tail → isnad+matn+takhrij.
- Bulugh-style: `عن X` + `«…»` + `رواه` → all three, high confidence.
- Hadith-in-fiqh-block: marker mid-paragraph → structure tagged in place.
- **Negative:** a fiqh `«…»` definition with no isnad verb / marker → **no**
  hadith spans.
- Self-check failure (matn empty) → no spans emitted.
- annotate merge: a low-confidence matn span is overridable by the model; a
  high-confidence one is not.

Plus a coverage check: re-run Bulugh and assert structural coverage rises from
~8% toward ~80%.

## Results (Bulugh al-Maram, 1,573 numbered hadith)

Structural coverage rose **8% → 99.4%** deterministically, via four detection
tiers (each gated to generalise across collections and never fire on quote-less
editions or non-hadith prose):

1. **Prophetic-marker** (`قال/عن/نهى/كان/… + رسول الله/النبي`, incl. the
   `الله`-omitted `قال رسول ﷺ` form and ف/و-prefixed verbs) — high confidence.
2. **`«…»`-matn fallback** (transmission context + quote) — low confidence.
3. **Narrator-`قال:`/`أن`/colon hinge** (`عن X قال: [report]`) — low confidence.
4. **Cross-reference / source-attribution** (وللبيهقي: «…» → matn+takhrij;
   `وأصله…`/grading notes → takhrij) — low confidence.

Marker/hinge vocabularies are written in readable Arabic and **normalised
programmatically** (`_norm`/`_deconj`) to avoid silent match misses (a recurring
bug: `نهى`→`نهي`, `صلى`→`صلي`).

**Precision (LLM-judge, Sonnet):** the high-confidence marker tier has **~0%
incorrect** matn boundaries (remaining "partials" are a defensible convention —
the matn includes the `قال رسول الله ﷺ:` intro). The low-confidence fallback
tiers are ~70% precise and are emitted as **proposals the LLM-verify merge may
correct** (confidence-gated). The end-to-end hybrid preserves the deterministic
spans (verified) and layers entities (person/book_ref/qur'an) on top.

The irreducible residual (~10 blocks) is numbering artifacts (`و442`),
`«»`-wrapped book names, and non-hadith scholarly notes.
