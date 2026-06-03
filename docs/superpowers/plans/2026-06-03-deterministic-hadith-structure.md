# Deterministic Hadith-Structure Detection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect hadith isnad/matn/takhrij structure deterministically (anchored on the universal prophetic-speech marker), so hadith collections get near-complete structural coverage (~8% → ~80%) instead of relying on the LLM, with the LLM rescoped to entities + residual + verifying low-confidence boundaries.

**Architecture:** A new deterministic module `ingestion/hadith.py` runs right after parse and emits inline `isnad`/`matn`/`takhrij` spans (with confidence) on prose hadith blocks. `annotate.py` is told those spans exist; its merge becomes confidence-gated so the LLM can correct low-confidence boundaries but not clobber high-confidence ones.

**Tech Stack:** Python 3, Pydantic, pytest.

**Spec:** `docs/superpowers/specs/2026-06-03-deterministic-hadith-structure-design.md`

---

## File Structure

- **Create** `ingestion/hadith.py` — `_norm`, marker vocab, `_find_prophetic_marker`, `detect_hadith_structure`. One responsibility: deterministic hadith structure.
- **Create** `ingestion/tests/test_hadith.py` — unit + integration tests.
- **Modify** `ingestion/__main__.py` — call `detect_hadith_structure(result)` after parse in `_ingest_one` and `run_parse`.
- **Modify** `ingestion/annotate.py` — serialize existing spans into the payload, prompt note, confidence-gated merge in `_apply_block_annotation`.
- **Modify** `ingestion/tests/test_annotate.py` — merge-gating tests.

---

## Task 1: Normalization + prophetic-marker finder

**Files:**
- Create: `ingestion/hadith.py`
- Create: `ingestion/tests/test_hadith.py`

- [ ] **Step 1: Write the failing test**

Create `ingestion/tests/test_hadith.py`:

```python
"""Tests for deterministic hadith-structure detection."""
from pathlib import Path

from ingestion.hadith import _norm, _find_prophetic_marker, detect_hadith_structure
from ingestion.parse import parse_file


def test_norm_strips_tashkeel_and_normalizes_variants():
    assert _norm("قَالَ") == "قال"
    assert _norm("النَّبِيِّ") == "النبي"
    assert _norm("أنّ") == "ان"          # hamza-alef → bare alef
    assert _norm("الله:") == "الله"       # punctuation dropped


def test_find_marker_returns_phrase_start():
    norm = ["عن", "ابي", "هريره", "قال", "قال", "رسول", "الله"]
    # the SECOND "قال" starts "قال رسول الله"
    assert _find_prophetic_marker(norm) == 4


def test_find_marker_none_when_absent():
    assert _find_prophetic_marker(["عن", "ابي", "هريره", "قال", "كذا"]) is None


def test_find_marker_an_nabi_variant():
    norm = ["عن", "انس", "عن", "النبي", "انه", "قال"]
    assert _find_prophetic_marker(norm) == 2   # "عن النبي"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ingestion && python -m pytest tests/test_hadith.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ingestion.hadith'`.

- [ ] **Step 3: Implement the module skeleton + helpers**

Create `ingestion/hadith.py`:

```python
"""Deterministic hadith-structure detection.

Anchors on the universal prophetic-speech marker (قال رسول الله / عن النبي / …)
to split a prose hadith block into isnad / matn / takhrij inline spans, with a
confidence per span. Runs after parse, before tashkeel. See spec
docs/superpowers/specs/2026-06-03-deterministic-hadith-structure-design.md.
"""
from __future__ import annotations
import logging
import re

from ingestion.models import ParseResult, Span

logger = logging.getLogger(__name__)

HIGH_CONF = 0.95   # ≥2 signals agree (marker + quote or takhrij)
LOW_CONF = 0.70    # marker only

# Combining marks (harakat, sukun, dagger alef) + tatweel.
_TASHKEEL = re.compile(r"[ً-ْٰـ]")


def _norm(text: str) -> str:
    """Bare Arabic letters for marker matching: strip tashkeel, fold alef/ya/ta
    variants, drop non-letters (punctuation, «», digits, ﷺ)."""
    text = _TASHKEEL.sub("", text)
    text = text.translate(str.maketrans("أإآىة", "ااايه"))
    return "".join(c for c in text if "ء" <= c <= "ي")


# Prophetic-speech markers as normalized word tuples (the isnad→matn boundary).
PROPHETIC_MARKERS: tuple[tuple[str, ...], ...] = (
    ("قال", "رسول", "الله"),
    ("عن", "رسول", "الله"),
    ("ان", "رسول", "الله"),
    ("سمعت", "رسول", "الله"),
    ("قال", "النبي"),
    ("عن", "النبي"),
    ("ان", "النبي"),
    ("سمعت", "النبي"),
)

# Source-attribution keywords (normalized) that open a takhrij tail.
TAKHRIJ_NORM = {"رواه", "اخرجه", "اخرجها", "رواها", "متفق"}


def _find_prophetic_marker(norm_tokens: list[str]) -> int | None:
    """Return the index of the first token of the earliest prophetic marker
    phrase, or None if no marker is present."""
    for i in range(len(norm_tokens)):
        for phrase in PROPHETIC_MARKERS:
            if tuple(norm_tokens[i : i + len(phrase)]) == phrase:
                return i
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ingestion && python -m pytest tests/test_hadith.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add ingestion/hadith.py ingestion/tests/test_hadith.py
git commit -m "feat(hadith): normalization + prophetic-marker finder"
```

---

## Task 2: `detect_hadith_structure` — emit isnad/matn/takhrij spans

**Files:**
- Modify: `ingestion/hadith.py`
- Modify: `ingestion/tests/test_hadith.py`

- [ ] **Step 1: Write the failing tests**

Append to `ingestion/tests/test_hadith.py`:

```python
def _make_book(tmp_path, body: str) -> Path:
    src = tmp_path / "h.mARkdown"
    src.write_text(
        "######OpenITI#\n#META#Header#End#\n# PageV01P001\n" + body,
        encoding="utf-8",
    )
    return src


def _spans(block):
    return {s.label: s for s in block.spans}


def test_bukhari_shape_full_isnad_no_quote(tmp_path):
    # full isnad, no «…», no takhrij → isnad + matn, boundary at the marker
    body = "# حدثنا عبد الله عن نافع عن ابن عمر قال رسول الله صلى الله عليه وسلم بني الاسلام على خمس\n"
    block = parse_file(_make_book(tmp_path, body), "0100Test.Bukhari").pages[0].content_blocks[0]
    detect_hadith_structure(_one(block))
    sp = _spans(block)
    assert "isnad" in sp and "matn" in sp and "takhrij" not in sp
    texts = {t.id: t.text for t in block.tokens}
    assert texts[sp["isnad"].start_token_id] == "حدثنا"
    assert texts[sp["matn"].start_token_id] == "قال"          # marker is in matn
    assert sp["matn"].confidence == LOW_CONF                   # marker only


def test_bulugh_shape_quote_and_takhrij(tmp_path):
    body = "# وعن ابي هريرة رضي الله عنه قال قال رسول الله صلى الله عليه وسلم «هو الطهور ماؤه» رواه ابو داود\n"
    block = parse_file(_make_book(tmp_path, body), "0100Test.Bulugh").pages[0].content_blocks[0]
    detect_hadith_structure(_one(block))
    sp = _spans(block)
    assert {"isnad", "matn", "takhrij"} <= set(sp)
    texts = {t.id: t.text for t in block.tokens}
    assert texts[sp["takhrij"].start_token_id] == "رواه"
    assert "»" in texts[sp["matn"].end_token_id]               # matn ends at the quote close
    assert sp["matn"].confidence == HIGH_CONF                  # marker + quote + takhrij


def test_negative_fiqh_quote_without_marker_is_not_hadith(tmp_path):
    body = "# الماء «الطهور» هو الباقي على اصل خلقته وهذا مذهب الجمهور\n"
    block = parse_file(_make_book(tmp_path, body), "0100Test.Fiqh").pages[0].content_blocks[0]
    detect_hadith_structure(_one(block))
    assert all(s.label not in ("isnad", "matn", "takhrij") for s in block.spans)


def test_marker_at_start_no_isnad(tmp_path):
    body = "# قال رسول الله صلى الله عليه وسلم انما الاعمال بالنيات\n"
    block = parse_file(_make_book(tmp_path, body), "0100Test.NoIsnad").pages[0].content_blocks[0]
    detect_hadith_structure(_one(block))
    sp = _spans(block)
    assert "isnad" not in sp and "matn" in sp


def _one(block):
    """Wrap a single block in a minimal ParseResult for detect_hadith_structure."""
    from ingestion.models import BookMetadata, Page, ParseResult
    meta = BookMetadata(openiti_id="t.1", title_ar="x", author_openiti_id="a")
    return ParseResult(metadata=meta, pages=[Page(page_number=1, content_blocks=[block])])
```

Note: `_one` re-wraps the parsed block so `detect_hadith_structure` (which takes a `ParseResult`) can run on it; the block object is shared, so the spans land on the original.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ingestion && python -m pytest tests/test_hadith.py -v`
Expected: FAIL — `detect_hadith_structure` not defined.

- [ ] **Step 3: Implement `detect_hadith_structure`**

Append to `ingestion/hadith.py`:

```python
def detect_hadith_structure(result: ParseResult) -> dict:
    """Mutate prose hadith blocks in place, adding isnad/matn/takhrij spans.
    Returns a stats dict."""
    stats = {"hadith": 0, "isnad": 0, "matn": 0, "takhrij": 0,
             "high_conf": 0, "low_conf": 0}
    for page in result.pages:
        for block in page.content_blocks:
            if block.type != "prose":
                continue
            # Skip blocks already structured (e.g. the rare native @MATN@ path).
            if any(s.label in ("isnad", "matn", "takhrij") for s in block.spans):
                continue
            _detect_block(block, stats)
    return stats


def _detect_block(block, stats: dict) -> None:
    toks = block.tokens
    norm = [_norm(t.text) for t in toks]
    b = _find_prophetic_marker(norm)
    if b is None:
        return  # no reliable boundary — leave to the LLM residual
    n = len(toks)

    # takhrij tail = first attribution keyword after the marker.
    takhrij_idx = next((j for j in range(b + 1, n) if norm[j] in TAKHRIJ_NORM), None)

    # quote close = first "»" at/after the marker (only if a "«" opened at/after b).
    quote_close = None
    if any("«" in toks[k].text for k in range(b, n)):
        quote_close = next((k for k in range(b, n) if "»" in toks[k].text), None)

    candidates = [n - 1]
    if takhrij_idx is not None:
        candidates.append(takhrij_idx - 1)
    if quote_close is not None:
        candidates.append(quote_close)
    matn_end = min(candidates)
    if matn_end < b:
        return  # self-check: matn would be empty

    conf = HIGH_CONF if (takhrij_idx is not None or quote_close is not None) else LOW_CONF
    if b > 0:
        block.spans.append(Span(start_token_id=toks[0].id, end_token_id=toks[b - 1].id,
                                label="isnad", confidence=conf))
        stats["isnad"] += 1
    block.spans.append(Span(start_token_id=toks[b].id, end_token_id=toks[matn_end].id,
                            label="matn", confidence=conf))
    stats["matn"] += 1
    if takhrij_idx is not None:
        block.spans.append(Span(start_token_id=toks[takhrij_idx].id, end_token_id=toks[n - 1].id,
                                label="takhrij", confidence=conf))
        stats["takhrij"] += 1
    stats["hadith"] += 1
    stats["high_conf" if conf == HIGH_CONF else "low_conf"] += 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ingestion && python -m pytest tests/test_hadith.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add ingestion/hadith.py ingestion/tests/test_hadith.py
git commit -m "feat(hadith): detect_hadith_structure — isnad/matn/takhrij spans with confidence"
```

---

## Task 3: Wire into the pipeline (after parse)

**Files:**
- Modify: `ingestion/__main__.py` (in `_ingest_one`, after `parse_file`; and in `run_parse`)

- [ ] **Step 1: Write the failing test**

Append to `ingestion/tests/test_hadith.py`:

```python
def test_full_parse_then_detect_adds_structure(tmp_path):
    # Two hadith on separate lines; both should get matn spans after detect.
    body = (
        "# وعن ابي هريرة قال قال رسول الله صلى الله عليه وسلم «انما الاعمال بالنيات» رواه البخاري\n"
        "# وعن عائشة قالت قال رسول الله صلى الله عليه وسلم «من احدث في امرنا» متفق عليه\n"
    )
    result = parse_file(_make_book(tmp_path, body), "0100Test.Two")
    stats = detect_hadith_structure(result)
    assert stats["matn"] == 2 and stats["takhrij"] == 2
```

- [ ] **Step 2: Run test to verify it passes already (function-level)**

Run: `cd ingestion && python -m pytest tests/test_hadith.py::test_full_parse_then_detect_adds_structure -v`
Expected: PASS — the function works; this task only wires it into the CLI so dumped JSON includes the spans.

- [ ] **Step 3: Wire `detect_hadith_structure` into `_ingest_one`**

In `ingestion/__main__.py`, add the import near the other stage imports at the top:

```python
from ingestion.hadith import detect_hadith_structure
```

Then in `_ingest_one`, immediately AFTER:

```python
    result = parse_file(path, uri)
    logger.info(f"Parsed: {len(result.pages)} pages, {len(result.chapters)} chapters")
```

insert:

```python
    # Deterministic hadith-structure pass (isnad/matn/takhrij spans) — runs
    # before the parsed.json dump so the structure is part of the parse tier.
    hstats = detect_hadith_structure(result)
    logger.info(
        f"Hadith structure: {hstats['matn']} matn, {hstats['isnad']} isnad, "
        f"{hstats['takhrij']} takhrij ({hstats['high_conf']} high / {hstats['low_conf']} low conf)"
    )
```

- [ ] **Step 4: Wire into `run_parse` (parse-only command)**

In `ingestion/__main__.py` `run_parse`, immediately AFTER:

```python
    result = parse_file(path, uri)
    logger.info(f"Parsed: {len(result.pages)} pages, {len(result.chapters)} chapters")
```

insert:

```python
    detect_hadith_structure(result)
```

- [ ] **Step 5: Run the full suite**

Run: `cd ingestion && python -m pytest -q`
Expected: PASS (all green, including the new hadith tests).

- [ ] **Step 6: Commit**

```bash
git add ingestion/__main__.py ingestion/tests/test_hadith.py
git commit -m "feat(ingest): run deterministic hadith-structure pass after parse"
```

---

## Task 4: Tell `annotate` the structure exists (serialize spans + prompt)

**Files:**
- Modify: `ingestion/annotate.py` (`_serialize_block`, `_build_system_prompt`)

- [ ] **Step 1: Write the failing test**

Append to `ingestion/tests/test_annotate.py`:

```python
def test_serialize_block_includes_existing_spans():
    from ingestion.annotate import _serialize_block
    from ingestion.models import Block, Span, Token
    tokens = [Token(id=f"p1_b0_w{i}", text=f"w{i}") for i in range(4)]
    block = Block(key="b0", type="prose", tokens=tokens,
                  spans=[Span(start_token_id="p1_b0_w1", end_token_id="p1_b0_w2",
                              label="matn", confidence=0.7)])
    payload = _serialize_block(1, block)
    assert "spans" in payload
    assert payload["spans"] == [[1, 2, "matn", 0.7]]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ingestion && python -m pytest tests/test_annotate.py::test_serialize_block_includes_existing_spans -v`
Expected: FAIL — `_serialize_block` doesn't emit `spans`.

- [ ] **Step 3: Add spans to `_serialize_block`**

In `ingestion/annotate.py`, replace the `return` in `_serialize_block`:

```python
    return {
        "key": _global_key(page_number, block),
        "type": block.type,
        "tokens": [[i, t.text] for i, t in enumerate(flat)],
    }
```

with:

```python
    idmap = {t.id: i for i, t in enumerate(flat)}
    spans = []
    for s in block.spans:
        a, b = idmap.get(s.start_token_id), idmap.get(s.end_token_id)
        if a is not None and b is not None:
            spans.append([min(a, b), max(a, b), s.label, s.confidence])
    return {
        "key": _global_key(page_number, block),
        "type": block.type,
        "tokens": [[i, t.text] for i, t in enumerate(flat)],
        "spans": spans,
    }
```

- [ ] **Step 4: Update the system prompt**

In `ingestion/annotate.py` `_build_system_prompt`, find the line describing the `tokens` input:

```python
- "tokens": ordered list of tokens with positions, format [[i, "text"], ...]
```

and add AFTER it:

```python
- "spans": structural spans already detected, format [[start, end, label, confidence], ...]. isnad/matn/takhrij spans here are PRE-DETECTED — do NOT re-add them. For a block with NO structural spans you may add them. You MAY correct a structural span only if its confidence is below 0.9; never touch one at 0.9 or above. Always add entity spans (person/place/quran/book_ref/hadith_ref/date_hijri) regardless.
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd ingestion && python -m pytest tests/test_annotate.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ingestion/annotate.py ingestion/tests/test_annotate.py
git commit -m "feat(annotate): surface pre-detected structural spans to the model"
```

---

## Task 5: Confidence-gated merge (LLM may correct low-confidence spans)

**Files:**
- Modify: `ingestion/annotate.py` (`_apply_block_annotation` merge block)
- Modify: `ingestion/tests/test_annotate.py`

- [ ] **Step 1: Write the failing tests**

Append to `ingestion/tests/test_annotate.py`:

```python
def test_low_confidence_structural_span_is_overridable():
    block = _make_block(n_tokens=6)
    block.spans = [Span(start_token_id="p1_b0_w0", end_token_id="p1_b0_w2",
                        label="matn", confidence=0.7)]   # low-conf proposal
    ann = {"spans": [{"start": 0, "end": 3, "label": "matn", "confidence": 0.9}], "flags": []}
    _apply_block_annotation(block, ann)
    matn = [s for s in block.spans if s.label == "matn"]
    assert len(matn) == 1
    assert matn[0].end_token_id == "p1_b0_w3"          # the model's corrected span


def test_high_confidence_structural_span_is_locked():
    block = _make_block(n_tokens=6)
    block.spans = [Span(start_token_id="p1_b0_w0", end_token_id="p1_b0_w2",
                        label="matn", confidence=0.95)]  # locked
    ann = {"spans": [{"start": 0, "end": 3, "label": "matn", "confidence": 0.9}], "flags": []}
    _apply_block_annotation(block, ann)
    matn = [s for s in block.spans if s.label == "matn"]
    assert len(matn) == 1
    assert matn[0].end_token_id == "p1_b0_w2"           # original, model dropped


def test_different_label_model_span_coexists_with_soft_span():
    block = _make_block(n_tokens=6)
    block.spans = [Span(start_token_id="p1_b0_w0", end_token_id="p1_b0_w4",
                        label="matn", confidence=0.7)]
    ann = {"spans": [{"start": 1, "end": 1, "label": "person", "confidence": 0.9}], "flags": []}
    _apply_block_annotation(block, ann)
    labels = sorted(s.label for s in block.spans)
    assert labels == ["matn", "person"]                # person nests inside the soft matn
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ingestion && python -m pytest tests/test_annotate.py -k "confidence or coexist" -v`
Expected: FAIL — current merge locks ALL parse spans and drops every overlapping model span.

- [ ] **Step 3: Replace the merge block in `_apply_block_annotation`**

In `ingestion/annotate.py`, find this block in `_apply_block_annotation`:

```python
    preserved = list(block.spans)
    idmap = _token_index_map(block)
    preserved_ranges = [r for r in (_span_range(s, idmap) for s in preserved) if r]
    preserved_has_quran = any(s.label == "quran" for s in preserved)

    kept: list[Span] = []
    for cs in spans:
        rng = _span_range(cs, idmap)
        if rng and any(_ranges_overlap(rng, pr) for pr in preserved_ranges):
            continue
        if cs.label == "quran" and preserved_has_quran:
            continue
        kept.append(cs)

    block.spans = preserved + kept
    span_count = len(kept)
```

and replace it with:

```python
    LOCK_THRESHOLD = 0.9
    preserved = list(block.spans)
    idmap = _token_index_map(block)
    # Spans with no confidence, or confidence >= threshold, are authoritative
    # (citation qur'an, footnotes, high-confidence structure). Below-threshold
    # structural spans are PROPOSALS a same-label model span may replace.
    locked = [s for s in preserved if s.confidence is None or s.confidence >= LOCK_THRESHOLD]
    soft = [s for s in preserved if s.confidence is not None and s.confidence < LOCK_THRESHOLD]
    locked_ranges = [r for r in (_span_range(s, idmap) for s in locked) if r]
    locked_has_quran = any(s.label == "quran" for s in locked)

    kept: list[Span] = []
    overridden = set()  # ids of soft spans replaced by a same-label model span
    for cs in spans:
        rng = _span_range(cs, idmap)
        if rng and any(_ranges_overlap(rng, pr) for pr in locked_ranges):
            continue
        if cs.label == "quran" and locked_has_quran:
            continue
        if rng:
            for ss in soft:
                sr = _span_range(ss, idmap)
                if sr and _ranges_overlap(rng, sr) and cs.label == ss.label:
                    overridden.add(id(ss))
        kept.append(cs)

    surviving_soft = [s for s in soft if id(s) not in overridden]
    block.spans = locked + surviving_soft + kept
    span_count = len(kept)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ingestion && python -m pytest tests/test_annotate.py -v`
Expected: PASS (all annotate tests, including the three new ones and the existing parse-owns-spans tests — those spans have `confidence=None`, so they stay locked).

- [ ] **Step 5: Commit**

```bash
git add ingestion/annotate.py ingestion/tests/test_annotate.py
git commit -m "feat(annotate): confidence-gated merge — LLM may correct low-confidence structural spans"
```

---

## Task 6: Coverage verification on Bulugh

**Files:** none (verification step).

- [ ] **Step 1: Run the full suite + verify**

Run: `cd ingestion && python -m pytest -q` then `./bin/suhuf verify --base origin/main`
Expected: all green.

- [ ] **Step 2: Re-parse Bulugh and measure structural coverage**

Run (from repo root, requires the `RELEASE` corpus):
```bash
python -m ingestion parse 0852IbnHajarCasqalani.BulughMaram --dump web/data --corpus-path ./RELEASE
python3 - <<'PY'
import json, collections
d=json.load(open("web/data/0852IbnHajarCasqalani.BulughMaram.parsed.json"))
hadith=[b for p in d["pages"] for b in p["content_blocks"] if b.get("number")]
labeled=sum(1 for b in hadith if any(s["label"] in ("isnad","matn","takhrij") for s in b.get("spans",[])))
print(f"{labeled}/{len(hadith)} hadith now structured ({labeled/len(hadith):.0%})")
PY
```
Expected: coverage rises from ~8% to ~70-80% (deterministic, no API call). If materially lower, inspect which hadith lack a prophetic marker — that's the residual the LLM still owns; do not loosen the marker list to chase coverage (false positives are worse).

- [ ] **Step 3: Commit any doc note**

If the measured number differs from ~80%, record the actual figure in the spec's Problem section. Otherwise no commit.

---

## Self-Review

- **Spec coverage:** marker-anchored detection (Task 2) ✓; hadith-likeness via marker requirement + negative test (Task 2) ✓; matn end-boundary rule (Task 2 `_detect_block`) ✓; confidence high/low (Task 2) ✓; self-check (Task 2) ✓; pipeline wiring after parse (Task 3) ✓; LLM rescope serialization + prompt (Task 4) ✓; confidence-gated merge (Task 5) ✓; generalization fixtures Bukhari/Muslim-via-quote/Bulugh/marker-at-start/negative (Task 2) ✓; coverage check (Task 6) ✓.
- **Placeholder scan:** none — every step has real code/commands.
- **Type consistency:** `detect_hadith_structure(result)`, `_detect_block(block, stats)`, `_find_prophetic_marker(norm_tokens)`, `_norm(text)`, constants `HIGH_CONF`/`LOW_CONF`/`PROPHETIC_MARKERS`/`TAKHRIJ_NORM` used consistently across tasks; `Span.confidence` already exists in `models.py`.
- *Gap noted:* the Tirmidhi shape (marker + `رواه`, no quote) is covered by `test_bulugh_shape` logic (takhrij path) and `test_full_parse_then_detect` (متفق); a no-quote-with-takhrij case is exercised by `test_full_parse_then_detect`'s second hadith.
