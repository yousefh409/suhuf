# Inline-vs-block Hadith Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `ingestion/parse.py` emit a running-line hadith as one `prose` block with `isnad`/`matn`/`takhrij`/`quran` spans (instead of swallowing `@MATN@`), keep the separate-line shape as separate blocks, and let the Claude annotation pass label inline isnad/matn/takhrij for untagged books.

**Architecture:** A running-line hadith (`$RWY$ … @MATN@ …` in one dispatched paragraph) becomes a single `prose` block whose token ranges carry spans. A separate-line hadith (`@MATN@` arriving in a later dispatch) keeps the existing separate-block path. The reader is already wired to render both shapes; no web changes.

**Tech Stack:** Python 3, Pydantic models, pytest.

**Spec:** `docs/superpowers/specs/2026-06-03-inline-vs-block-hadith-design.md`

---

## File Structure

- `ingestion/parse.py` — add `_emit_inline_hadith` helper; modify the `$RWY$` branch to detect inline `@MATN@`. (Separate-line `@MATN@` branch unchanged.)
- `ingestion/annotate.py` — add `isnad`/`matn`/`takhrij` to `SPAN_LABELS`; extend the system-prompt span-label definitions.
- `ingestion/models.py` — update the `Span.label` docstring/comment (doc only).
- `ingestion/tests/test_parse_hadith.py` — NEW: inline/separate hadith parsing tests.
- `ingestion/tests/test_annotate.py` — update the frozen-set assertion; add inline-span-label tests.

Two independent work-streams (disjoint files, run in parallel):
- **Stream A** — parse.py + test_parse_hadith.py (Tasks 1–3).
- **Stream B** — annotate.py + models.py + test_annotate.py (Task 4).

---

## Stream A — parse.py

### Task 1: Inline `@MATN@` → one prose block with isnad + matn spans

**Files:**
- Create: `ingestion/tests/test_parse_hadith.py`
- Modify: `ingestion/parse.py` (`$RWY$` branch ~lines 331-343; add helper after `_flush_hadith`)

- [ ] **Step 1: Write the failing test**

Create `ingestion/tests/test_parse_hadith.py`:

```python
"""Tests for inline-vs-block hadith parsing (issue #14)."""
from pathlib import Path

from ingestion.parse import parse_file


def _write(tmp_path, body: str) -> Path:
    src = tmp_path / "hadith.mARkdown"
    src.write_text(
        "######OpenITI#\n"
        "#META# 020.BookTITLE\t:: اختبار\n"
        "#META# 00#VERS#LENGTH###\t:: 5\n"
        "#META#Header#End#\n"
        "# PageV01P001\n"
        + body,
        encoding="utf-8",
    )
    return src


def _spans_by_label(block):
    return {s.label: s for s in block.spans}


def test_inline_matn_is_one_block_with_isnad_and_matn_spans(tmp_path):
    # $RWY$ isnad @MATN@ matn — all on one source line.
    src = _write(tmp_path, "# $RWY$ حدثنا عبد الله @MATN@ إنما الأعمال بالنيات\n")
    result = parse_file(src, "0100Test.HadithBook")
    blocks = result.pages[0].content_blocks

    # One block, not separate isnad/matn blocks.
    assert len(blocks) == 1
    block = blocks[0]
    assert block.type == "prose"

    # The @MATN@ marker is not a token.
    assert all("@MATN@" not in t.text for t in block.tokens)
    assert [t.text for t in block.tokens] == [
        "حدثنا", "عبد", "الله", "إنما", "الأعمال", "بالنيات",
    ]

    spans = _spans_by_label(block)
    assert "isnad" in spans and "matn" in spans

    texts = {t.id: t.text for t in block.tokens}
    # isnad span covers "حدثنا عبد الله"
    assert texts[spans["isnad"].start_token_id] == "حدثنا"
    assert texts[spans["isnad"].end_token_id] == "الله"
    # matn span covers "إنما الأعمال بالنيات"
    assert texts[spans["matn"].start_token_id] == "إنما"
    assert texts[spans["matn"].end_token_id] == "بالنيات"


def test_inline_matn_preserves_item_number(tmp_path):
    src = _write(tmp_path, "# $RWY$ ١ - حدثنا عبد الله @MATN@ إنما الأعمال\n")
    result = parse_file(src, "0100Test.HadithBook")
    block = result.pages[0].content_blocks[0]
    assert block.number == "١"
    assert all("@MATN@" not in t.text for t in block.tokens)
    assert "حدثنا" in [t.text for t in block.tokens]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ingestion && python -m pytest tests/test_parse_hadith.py -v`
Expected: FAIL — current parser emits a single `isnad` block containing the literal `@MATN@` token (no `prose` block, no `matn` span).

- [ ] **Step 3: Add the `_emit_inline_hadith` helper**

In `ingestion/parse.py`, immediately AFTER the `_flush_hadith` function definition (it ends near line 296, before `def _dispatch`), add this nested helper:

```python
    def _emit_inline_hadith(isnad_text: str, matn_text: str, number: str | None):
        """Emit ONE prose block for a running-line hadith.

        isnad/matn/takhrij live as inline spans over token ranges instead of
        separate blocks. An embedded ``{ayah} [sura:ayah]`` citation in the matn
        keeps its quran span. The ``@MATN@`` marker itself is never tokenized.
        """
        isnad_words = isnad_text.split()
        matn_words, quran_spans = _extract_inline_quran(matn_text.split())

        all_words = isnad_words + matn_words
        if not all_words:
            return
        block_idx = len(current_blocks)
        tokens = [
            Token(id=f"p{current_page_num}_b{block_idx}_w{i}", text=w)
            for i, w in enumerate(all_words)
        ]

        spans: list[Span] = []
        n_isnad = len(isnad_words)
        if n_isnad:
            spans.append(Span(
                start_token_id=tokens[0].id,
                end_token_id=tokens[n_isnad - 1].id,
                label="isnad",
            ))

        # An optional trailing takhrij begins at the first source-attribution
        # keyword inside the matn portion (mirrors the standalone-line rule).
        takhrij_local: int | None = None
        for j, w in enumerate(matn_words):
            if w in _TAKHRIJ_KEYWORDS:
                takhrij_local = j
                break

        if matn_words:
            matn_end_local = (
                takhrij_local - 1 if takhrij_local is not None else len(matn_words) - 1
            )
            if matn_end_local >= 0:
                spans.append(Span(
                    start_token_id=tokens[n_isnad].id,
                    end_token_id=tokens[n_isnad + matn_end_local].id,
                    label="matn",
                ))
            if takhrij_local is not None:
                spans.append(Span(
                    start_token_id=tokens[n_isnad + takhrij_local].id,
                    end_token_id=tokens[-1].id,
                    label="takhrij",
                ))

        # Quran spans sit inside the matn portion; append last so they win on
        # overlap with the matn span (reader: later span wins per token).
        for start, end, ref in quran_spans:
            spans.append(Span(
                start_token_id=tokens[n_isnad + start].id,
                end_token_id=tokens[n_isnad + end].id,
                label="quran",
                ref=ref,
            ))

        current_blocks.append(Block(
            key=f"b{block_idx}", type="prose", tokens=tokens, spans=spans, number=number,
        ))
```

- [ ] **Step 4: Modify the `$RWY$` branch to detect inline `@MATN@`**

In `ingestion/parse.py`, REPLACE the existing `$RWY$` branch:

```python
        # Hadith start ($RWY$)
        m = _HADITH_RE.match(line_text)
        if m:
            _flush_hadith()
            in_hadith = True
            hadith_words = []
            hadith_number = None
            remainder = m.group(1).strip()
            if remainder:
                hadith_number, remainder = _extract_leading_ordinal(remainder)
                if remainder:
                    hadith_words.extend(remainder.split())
            return
```

with:

```python
        # Hadith start ($RWY$)
        m = _HADITH_RE.match(line_text)
        if m:
            _flush_hadith()
            remainder = m.group(1).strip()
            hadith_number = None
            if remainder:
                hadith_number, remainder = _extract_leading_ordinal(remainder)
            # Inline hadith: isnad and matn share one source line, joined by
            # @MATN@. Emit one prose block with spans, not separate blocks.
            if remainder and "@MATN@" in remainder:
                before, _, after = remainder.partition("@MATN@")
                _emit_inline_hadith(before.strip(), after.strip(), hadith_number)
                in_hadith = False
                hadith_words = []
                hadith_number = None
                return
            # Separate-line hadith: accumulate isnad words; a later @MATN@
            # dispatch (or a flush) closes it as separate blocks.
            in_hadith = True
            hadith_words = []
            if remainder:
                hadith_words.extend(remainder.split())
            return
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd ingestion && python -m pytest tests/test_parse_hadith.py -v`
Expected: PASS (both tests).

- [ ] **Step 6: Commit**

```bash
git add ingestion/parse.py ingestion/tests/test_parse_hadith.py
git commit -m "feat(parse): inline @MATN@ hadith → one prose block with isnad/matn spans (#14)"
```

---

### Task 2: Inline takhrij boundary + quran coexistence

**Files:**
- Modify: `ingestion/tests/test_parse_hadith.py`

(The implementation from Task 1 already handles both; this task locks the behavior with tests.)

- [ ] **Step 1: Add the tests**

Append to `ingestion/tests/test_parse_hadith.py`:

```python
def test_inline_takhrij_keyword_becomes_takhrij_span(tmp_path):
    src = _write(
        tmp_path,
        "# $RWY$ حدثنا فلان @MATN@ إنما الأعمال بالنيات رواه البخاري ومسلم\n",
    )
    result = parse_file(src, "0100Test.HadithBook")
    block = result.pages[0].content_blocks[0]
    spans = _spans_by_label(block)
    assert {"isnad", "matn", "takhrij"} <= set(spans)
    texts = {t.id: t.text for t in block.tokens}
    # matn ends before the takhrij keyword …
    assert texts[spans["matn"].end_token_id] == "بالنيات"
    # … and takhrij runs from "رواه" to the end.
    assert texts[spans["takhrij"].start_token_id] == "رواه"
    assert texts[spans["takhrij"].end_token_id] == "ومسلم"


def test_inline_embedded_ayah_keeps_quran_span(tmp_path):
    src = _write(
        tmp_path,
        "# $RWY$ حدثنا فلان @MATN@ قال تعالى {إنما الأعمال بالنيات} [البقرة: 2]\n",
    )
    result = parse_file(src, "0100Test.HadithBook")
    block = result.pages[0].content_blocks[0]
    spans = _spans_by_label(block)
    assert "isnad" in spans and "matn" in spans and "quran" in spans
    # Braces stripped from the rendered tokens.
    assert all("{" not in t.text and "}" not in t.text for t in block.tokens)
    # The quran span carries the citation-derived ref.
    quran = [s for s in block.spans if s.label == "quran"]
    assert len(quran) == 1 and quran[0].ref == "2:2"
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd ingestion && python -m pytest tests/test_parse_hadith.py -v`
Expected: PASS. If `test_inline_embedded_ayah_keeps_quran_span` fails on the ref value, print the parsed spans and adjust the expected ref only if the citation table maps البقرة differently — do NOT loosen the structural assertions.

- [ ] **Step 3: Commit**

```bash
git add ingestion/tests/test_parse_hadith.py
git commit -m "test(parse): inline hadith takhrij boundary + quran coexistence (#14)"
```

---

### Task 3: Separate-line regression guard

**Files:**
- Modify: `ingestion/tests/test_parse_hadith.py`

- [ ] **Step 1: Add the test**

Append to `ingestion/tests/test_parse_hadith.py`:

```python
def test_separate_line_matn_stays_two_blocks(tmp_path):
    # $RWY$ on one line, @MATN@ on a later line → separate isnad + matn blocks.
    src = _write(
        tmp_path,
        "# $RWY$ حدثنا عبد الله عن نافع\n"
        "# @MATN@ إنما الأعمال بالنيات\n",
    )
    result = parse_file(src, "0100Test.HadithBook")
    types = [b.type for b in result.pages[0].content_blocks]
    assert types == ["isnad", "matn"]
    # No inline isnad/matn spans in the separate-line shape.
    for b in result.pages[0].content_blocks:
        assert all(s.label not in ("isnad", "matn") for s in b.spans)
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd ingestion && python -m pytest tests/test_parse_hadith.py -v`
Expected: PASS (separate-line path is unchanged).

- [ ] **Step 3: Run the full parse-side suite**

Run: `cd ingestion && python -m pytest tests/test_parse.py tests/test_parse_quran.py tests/test_parse_hadith.py -v`
Expected: PASS (no regression in existing parse tests).

- [ ] **Step 4: Commit**

```bash
git add ingestion/tests/test_parse_hadith.py
git commit -m "test(parse): separate-line @MATN@ stays two blocks — regression guard (#14)"
```

---

## Stream B — annotate.py + models.py

### Task 4: Add isnad/matn/takhrij inline span labels to the Claude pass

**Files:**
- Modify: `ingestion/annotate.py` (`SPAN_LABELS` ~lines 44-52; `_build_system_prompt` span-label definitions ~lines 99-105)
- Modify: `ingestion/models.py` (`Span.label` comment ~line 21)
- Modify: `ingestion/tests/test_annotate.py` (`test_span_labels_constant_is_frozen_set` ~line 28; add new tests)

- [ ] **Step 1: Update the frozen-set test + add new tests (failing)**

In `ingestion/tests/test_annotate.py`, REPLACE:

```python
def test_span_labels_constant_is_frozen_set():
    assert set(SPAN_LABELS) == {"quran", "person", "place", "book_ref", "hadith_ref", "date_hijri"}
```

with:

```python
def test_span_labels_constant_is_frozen_set():
    assert set(SPAN_LABELS) == {
        "quran", "person", "place", "book_ref", "hadith_ref", "date_hijri",
        "isnad", "matn", "takhrij",
    }


def test_apply_accepts_inline_hadith_span_labels():
    block = _make_block(n_tokens=6)
    ann = {
        "spans": [
            {"start": 0, "end": 2, "label": "isnad", "confidence": 0.9},
            {"start": 3, "end": 5, "label": "matn", "confidence": 0.9},
        ],
        "flags": [],
    }
    _apply_block_annotation(block, ann)
    labels = sorted(s.label for s in block.spans)
    assert labels == ["isnad", "matn"]


def test_parse_inline_hadith_span_wins_over_model_span():
    # Parse emitted an authoritative isnad span; an overlapping model span is dropped.
    block = _make_block(n_tokens=6)
    block.spans = [Span(start_token_id="p1_b0_w0", end_token_id="p1_b0_w2", label="isnad")]
    ann = {
        "spans": [
            {"start": 1, "end": 1, "label": "matn", "confidence": 0.9},
        ],
        "flags": [],
    }
    _apply_block_annotation(block, ann)
    # Overlapping model matn span dropped; only the parse isnad span remains.
    assert [s.label for s in block.spans] == ["isnad"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ingestion && python -m pytest tests/test_annotate.py -v`
Expected: FAIL — `SPAN_LABELS` does not yet contain isnad/matn/takhrij, so the frozen-set test fails and `_apply_block_annotation` filters the new labels out.

- [ ] **Step 3: Extend `SPAN_LABELS`**

In `ingestion/annotate.py`, REPLACE:

```python
# Span-label frozen vocabulary (6 labels).
SPAN_LABELS = [
    "quran",
    "person",
    "place",
    "book_ref",
    "hadith_ref",
    "date_hijri",
]
```

with:

```python
# Span-label frozen vocabulary. The last three structure a running-line hadith
# inline (one block, parts as spans) for books without native @MATN@ tags.
SPAN_LABELS = [
    "quran",
    "person",
    "place",
    "book_ref",
    "hadith_ref",
    "date_hijri",
    "isnad",
    "matn",
    "takhrij",
]
```

- [ ] **Step 4: Add prompt definitions for the new span labels**

In `ingestion/annotate.py`, inside `_build_system_prompt`, find the `- "date_hijri": explicit Hijri date in the text` line in the span-label definitions block and add AFTER it:

```python
- "isnad": the chain-of-transmission portion of a hadith that sits inline within a single running block (use this span, not a block relabel, when isnad and matn share one line/paragraph)
- "matn": the reported-text portion of a hadith that sits inline within a single running block
- "takhrij": the source-attribution tail (e.g. "رواه البخاري") of a hadith that sits inline within a single running block

For a hadith laid out across SEPARATE lines (separate blocks), prefer relabeling each block's "type" to isnad/matn/takhrij. For a hadith on ONE running line, emit these as spans on a single block — do not do both.
```

- [ ] **Step 5: Update the `Span.label` comment in models.py**

In `ingestion/models.py`, REPLACE the `label` line in `class Span`:

```python
    label: str                     # quran | person | place | book_ref | hadith_ref | date_hijri | footnote
```

with:

```python
    label: str                     # quran | person | place | book_ref | hadith_ref | date_hijri | footnote | isnad | matn | takhrij
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd ingestion && python -m pytest tests/test_annotate.py -v`
Expected: PASS (all annotate tests, including the new ones).

- [ ] **Step 7: Commit**

```bash
git add ingestion/annotate.py ingestion/models.py ingestion/tests/test_annotate.py
git commit -m "feat(annotate): isnad/matn/takhrij inline span labels for untagged hadith (#14)"
```

---

## Final verification

- [ ] **Run the full ingestion suite**

Run: `cd ingestion && python -m pytest -q`
Expected: all tests pass (was 172; now higher with the new tests).

- [ ] **Run suhuf verify on the affected package**

Run: `./bin/suhuf verify --base origin/main`
Expected: ingestion lint/compileall/pytest pass.

---

## Self-Review

- **Spec coverage:** parse.py inline detection (Tasks 1–2) ✓; separate-line preserved (Task 3) ✓; annotate.py span labels + prompt (Task 4) ✓; models.py comment (Task 4 Step 5) ✓; tests for inline/takhrij/quran/separate/annotate ✓.
- **Placeholder scan:** none — all steps carry real code and commands.
- **Type consistency:** `_emit_inline_hadith(isnad_text, matn_text, number)` signature is used consistently; `Span`, `Block`, `Token`, `_extract_inline_quran`, `_TAKHRIJ_KEYWORDS` all already exist in parse.py.

---

## Appendix — Follow-on (manual, not TDD): real ingestion + accuracy eval

These depend on an external OpenITI corpus and `ANTHROPIC_API_KEY`; run after #14 lands.

**Target books:**
- `0676Nawawi.ArbacunaNawawiyya` — al-Arba'un (short, `.mARkdown`)
- `0672IbnMalik.Alfiyya` — Alfiyyat Ibn Malik (poetry, exercises `%~%` / `%`-wrapped hemistichs)
- `0852IbnHajarCasqalani.BulughMaram` — Bulugh al-Maram
- al-Dāʾ wa al-Dawāʾ (Ibn al-Qayyim, d. 751) — resolve exact OpenITI URI from the corpus

**Ingestion:** fetch each book file into `RELEASE/data/<AuthorID>/<AuthorID>.<BookID>/…`, then:
`python -m ingestion ingest <uri> --dump web/data --dry-run --tashkeel-engine shakkala`
Inspect each `web/data/<uri>.enriched.json` and open `/inspector/<uri>` for block/span review.

**Accuracy eval** (per `docs/superpowers/plans/2026-04-30-claude-annotation-pass.md`): on a natively-tagged book, strip native tags, run the annotate v1 pass, compute precision/recall per label. Targets: ≥0.95 isnad/matn, ≥0.85 takhrij. Ship a label only if it clears its bar.
