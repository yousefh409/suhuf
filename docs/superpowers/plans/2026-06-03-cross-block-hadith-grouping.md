# Cross-block Hadith Grouping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect a hadith's isnad/matn/takhrij across the blocks it actually spans (stitching split matns and matn-fragment headings) and write the result back as per-block span pieces, so a hadith fragmented by the source is no longer truncated.

**Architecture:** Refactor the per-block detector into two halves — the tier logic returns *ranges* over a token list (`_detect_ranges`), and a new grouping step (`_group_hadith_units`) gathers consecutive blocks into a hadith unit, runs detection over the combined tokens, then projects the ranges back as per-block spans (`_project`). Matn-fragment `### |` headings absorbed into a unit are re-typed to prose and pruned from the chapter tree. No storage/schema change.

**Tech Stack:** Python 3, Pydantic, pytest.

**Spec:** `docs/superpowers/specs/2026-06-03-cross-block-hadith-grouping-design.md`

---

## File Structure

- **Modify** `ingestion/hadith.py` — refactor the four `_emit_from_*` tier functions into `_ranges_from_*` (return ranges, don't append); add `_detect_ranges`, `_group_hadith_units` + grouping predicates, `_project`; rewrite `detect_hadith_structure` to be unit-based.
- **Modify** `ingestion/tests/test_hadith.py` — grouping unit tests + cross-block integration tests; existing single-block tests are the regression guard.

The whole change lives in `hadith.py` (already the dedicated module) — no new files needed.

---

## Task 1: Refactor tiers to return ranges (behavior-preserving)

Convert each `_emit_from_*(block, toks, norm, …, stats)` (which appends spans) into `_ranges_from_*(toks, norm, …)` (which returns `(isnad, matn, takhrij, conf)` or `None`, each range an inclusive `(start, end)` or `None`). `detect_hadith_structure` keeps working via the existing per-block `_emit`. No test should change.

**Files:** Modify `ingestion/hadith.py`

- [ ] **Step 1: Add `_detect_ranges` + the four `_ranges_from_*` functions**

In `ingestion/hadith.py`, **add** these functions (place them just before `def _detect_block`):

```python
def _detect_ranges(toks, norm):
    """Compute (isnad, matn, takhrij, conf) ranges over a token list, or None.
    Ranges are inclusive (start, end) index pairs in `toks` coords, or None."""
    b = _find_prophetic_marker(norm)
    if b is not None:
        return _ranges_from_marker(toks, norm, b)
    return (_ranges_from_quote(toks, norm)
            or _ranges_from_narrator_qal(toks, norm)
            or _ranges_from_crossref(toks, norm))


def _ranges_from_marker(toks, norm, b):
    n = len(toks)
    takhrij_idx = next((j for j in range(b + 1, n) if norm[j] in TAKHRIJ_NORM), None)
    quote_close = None
    if any("«" in toks[k].text for k in range(b, n)):
        quote_close = next((k for k in range(b, n) if "»" in toks[k].text), None)
    cands = [n - 1]
    if takhrij_idx is not None:
        cands.append(takhrij_idx - 1)
    if quote_close is not None:
        cands.append(quote_close)
    matn_end = min(cands)
    if matn_end < b:
        return None
    conf = HIGH_CONF if (takhrij_idx is not None or quote_close is not None) else LOW_CONF
    isnad = (0, b - 1) if b > 0 else None
    takhrij = (takhrij_idx, _takhrij_end(toks, takhrij_idx, n)) if takhrij_idx is not None else None
    return (isnad, (b, matn_end), takhrij, conf)


def _ranges_from_quote(toks, norm):
    n = len(toks)
    q_open = next((k for k in range(n) if "«" in toks[k].text), None)
    if q_open is None:
        return None
    q_close = next((k for k in range(q_open, n) if "»" in toks[k].text), None)
    if q_close is None:
        return None
    if not any(norm[k] in _TRANSMISSIONS for k in range(q_open)):
        return None
    takhrij_idx = next((j for j in range(q_close + 1, n) if norm[j] in TAKHRIJ_NORM), None)
    isnad = (0, q_open - 1) if q_open > 0 else None
    takhrij = (takhrij_idx, _takhrij_end(toks, takhrij_idx, n)) if takhrij_idx is not None else None
    return (isnad, (q_open, q_close), takhrij, LOW_CONF)


def _ranges_from_narrator_qal(toks, norm):
    n = len(toks)
    if n < 3:
        return None
    first = next((x for x in norm if x), "")
    if first not in _TRANSMISSIONS:
        return None
    hinge = next((j for j in range(1, n)
                  if norm[j] in _QAL_HINGE or _deconj(norm[j]) in _QAL_HINGE
                  or toks[j].text.rstrip().endswith(":")), None)
    if hinge is None or hinge == 0:
        return None
    is_an = norm[hinge] in _AN_HINGE or _deconj(norm[hinge]) in _AN_HINGE
    matn_start = hinge if is_an else hinge + 1
    isnad_end = hinge - 1 if is_an else hinge
    if matn_start >= n or isnad_end < 0:
        return None
    takhrij_idx = next((j for j in range(matn_start + 1, n) if norm[j] in TAKHRIJ_NORM), None)
    matn_end = (takhrij_idx - 1) if takhrij_idx is not None else (n - 1)
    if matn_end < matn_start:
        return None
    takhrij = (takhrij_idx, _takhrij_end(toks, takhrij_idx, n)) if takhrij_idx is not None else None
    return ((0, isnad_end), (matn_start, matn_end), takhrij, LOW_CONF)


def _ranges_from_crossref(toks, norm):
    raw = " ".join(t.text for t in toks)
    if not (_CROSSREF_RE.match(raw) or any(x in _GRADING_VOCAB for x in norm)):
        return None
    n = len(toks)
    q_open = next((k for k in range(n) if "«" in toks[k].text), None)
    q_close = next((k for k in range(q_open, n) if "»" in toks[k].text), None) if q_open is not None else None
    if q_open is not None and q_close is not None and q_open > 0:
        return (None, (q_open, q_close), (0, q_open - 1), LOW_CONF)
    colon = next((k for k in range(n) if toks[k].text.rstrip().endswith(":")), None)
    if colon is not None and colon + 1 < n:
        rest0 = colon + 1
        rest_is_source = (norm[rest0] in _TRANSMISSIONS
                          or " ".join(t.text for t in toks[rest0:rest0 + 2]).startswith(("من حديث", "من رواية")))
        if not rest_is_source:
            tk = next((j for j in range(rest0, n) if norm[j] in TAKHRIJ_NORM), None)
            matn_end = (tk - 1) if tk is not None else (n - 1)
            if matn_end >= rest0:
                return (None, (rest0, matn_end), (0, colon), LOW_CONF)
    return (None, None, (0, n - 1), LOW_CONF)
```

- [ ] **Step 2: Point `_detect_block` at the new ranges + keep `_emit`**

In `ingestion/hadith.py`, REPLACE the body of `_detect_block` (and delete the now-unused `_emit_from_marker`, `_emit_from_quote`, `_emit_from_narrator_qal`, `_emit_from_crossref` functions) with:

```python
def _detect_block(block, stats: dict) -> None:
    toks = block.tokens
    ranges = _detect_ranges(toks, [_norm(t.text) for t in toks])
    if ranges is not None:
        isnad, matn, takhrij, conf = ranges
        _emit(block, toks, isnad, matn, takhrij, conf, stats)
```

Leave `_emit`, `_takhrij_end`, `_find_prophetic_marker`, `_is_prophetic_subject`, and all constants exactly as they are.

- [ ] **Step 3: Run the full hadith suite — nothing should change**

Run: `cd ingestion && python -m pytest tests/test_hadith.py -v`
Expected: PASS (all existing tests — this is a behavior-preserving refactor).

- [ ] **Step 4: Commit**

```bash
git add ingestion/hadith.py
git commit -m "refactor(hadith): tiers return ranges (_detect_ranges) — prep for cross-block"
```

---

## Task 2: Group consecutive blocks into hadith units

Add the grouping function and its predicates. Pure logic over a flat block list; unit-tested directly.

**Files:** Modify `ingestion/hadith.py`, `ingestion/tests/test_hadith.py`

- [ ] **Step 1: Write the failing tests**

Append to `ingestion/tests/test_hadith.py`:

```python
from ingestion.hadith import _group_hadith_units, _is_hadith_start, _is_real_chapter
from ingestion.models import Block, Token


def _blk(key, type, text, number=None):
    toks = [Token(id=f"p1_{key}_w{i}", text=w) for i, w in enumerate(text.split())]
    return Block(key=key, type=type, tokens=toks, number=number)


def test_group_absorbs_open_quote_fragment():
    # b3 opens « but never closes; b4 (a heading) closes it → same unit.
    b3 = _blk("b3", "prose", "وعن ابي سعيد قال قال رسول الله «ان", number="2")
    b4 = _blk("b4", "heading", "الماء طهور لا ينجسه شيء».")
    b5 = _blk("b5", "takhrij", "اخرجه الثلاثة")
    units = _group_hadith_units([(1, 0, b3), (1, 1, b4), (1, 2, b5)])
    assert len(units) == 1
    assert [t[2].key for t in units[0]] == ["b3", "b4", "b5"]


def test_real_chapter_heading_ends_unit():
    b1 = _blk("b1", "prose", "وعن انس قال قال رسول الله صلى الله عليه وسلم كذا", number="1")
    chap = _blk("b2", "heading", "كتاب الطهارة")
    b3 = _blk("b3", "prose", "وعن عمر قال قال رسول الله كذا", number="2")
    units = _group_hadith_units([(1, 0, b1), (1, 1, chap), (1, 2, b3)])
    assert len(units) == 2                 # chapter is not absorbed into either
    assert [t[2].key for t in units[0]] == ["b1"]
    assert [t[2].key for t in units[1]] == ["b3"]


def test_real_chapter_vs_fragment_heading():
    assert _is_real_chapter(_blk("b0", "heading", "كتاب الطهارة")) is True
    assert _is_real_chapter(_blk("b0", "heading", "الماء طهور لا ينجسه شيء».")) is False  # ends »
    assert _is_real_chapter(_blk("b0", "prose", "كتاب")) is False                         # not a heading
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ingestion && python -m pytest tests/test_hadith.py -k "group or real_chapter" -v`
Expected: FAIL — `_group_hadith_units`/`_is_real_chapter` not defined.

- [ ] **Step 3: Implement the grouping**

In `ingestion/hadith.py`, add (after `_detect_ranges`):

```python
_OPEN_DELIMS = {"«": "»", "{": "}", "﴿": "﴾"}


def _is_hadith_start(block) -> bool:
    """True if the block begins a new hadith/variant: a numbered item, a prose
    isnad-opener (transmission verb / prophetic marker), or a cross-ref variant."""
    if block.number:
        return True
    if block.type != "prose":
        return False
    norm = [_norm(t.text) for t in block.tokens]
    first = next((x for x in norm if x), "")
    if first in _TRANSMISSIONS or _find_prophetic_marker(norm) is not None:
        return True
    return bool(_CROSSREF_RE.match(" ".join(t.text for t in block.tokens)))


def _is_real_chapter(block) -> bool:
    """A `### |` heading that is a genuine section title, not a matn fragment."""
    if block.type != "heading":
        return False
    text = " ".join(t.text for t in block.tokens).strip()
    if not text or text[0] in (":", "«") or "«" in text or text.endswith("»"):
        return False
    return True


def _is_takhrij_continuation(block) -> bool:
    """A trailing takhrij-line or grading note that belongs to the prior hadith
    (but is not itself a cross-ref *variant* opener)."""
    if block.type == "takhrij":
        return True
    norm = [_norm(t.text) for t in block.tokens]
    first = next((x for x in norm if x), "")
    return first in TAKHRIJ_NORM or any(n in _GRADING_VOCAB for n in norm)


def _unit_open_delim(unit) -> bool:
    text = " ".join(t.text for _, _, b in unit for t in b.tokens)
    return any(text.count(o) > text.count(c) for o, c in _OPEN_DELIMS.items())


def _group_hadith_units(flat):
    """Group a document-ordered [(page_number, block_index, block), …] list into
    hadith units. Each unit is such a list. See spec."""
    units, cur = [], None
    for entry in flat:
        block = entry[2]
        if _is_real_chapter(block):
            if cur:
                units.append(cur); cur = None
            continue
        if _is_hadith_start(block):
            if cur:
                units.append(cur)
            cur = [entry]
            continue
        if cur is not None and (_unit_open_delim(cur)
                                or _is_takhrij_continuation(block)
                                or block.type == "heading"):
            cur.append(entry)
            continue
        if cur:
            units.append(cur); cur = None
    if cur:
        units.append(cur)
    return units
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ingestion && python -m pytest tests/test_hadith.py -k "group or real_chapter" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ingestion/hadith.py ingestion/tests/test_hadith.py
git commit -m "feat(hadith): group consecutive blocks into hadith units"
```

---

## Task 3: Cross-block detection + per-block span projection

Rewrite `detect_hadith_structure` to detect over each unit's combined tokens and project ranges back as per-block spans, re-typing absorbed fragment headings and pruning their chapters.

**Files:** Modify `ingestion/hadith.py`, `ingestion/tests/test_hadith.py`

- [ ] **Step 1: Write the failing tests**

Append to `ingestion/tests/test_hadith.py`:

```python
def test_split_matn_spans_both_blocks(tmp_path):
    # A hadith whose matn quote opens in one block and closes in the next, with
    # the tail pulled into a ### | heading — must produce a matn span in BOTH,
    # the heading re-typed to prose, and dropped from chapters.
    src = tmp_path / "split.mARkdown"
    src.write_text(
        "######OpenITI#\n#META#Header#End#\n# PageV01P001\n"
        "### | 1 - \n"
        "# وعن ابي سعيد الخدري رضي الله عنه قال قال رسول الله صلى الله عليه وسلم «ان\n"
        "### | الماء طهور لا ينجسه شيء».\n"
        "# اخرجه الثلاثة\n",
        encoding="utf-8",
    )
    from ingestion.parse import parse_file
    result = parse_file(src, "0100Test.Split")
    detect_hadith_structure(result)
    blocks = result.pages[0].content_blocks
    matn_blocks = [b for b in blocks if any(s.label == "matn" for s in b.spans)]
    assert len(matn_blocks) == 2                         # matn spans BOTH blocks
    frag = [b for b in blocks if "طهور" in " ".join(t.text for t in b.tokens)][0]
    assert frag.type == "prose"                          # re-typed from heading
    assert all("طهور" not in c.title for c in result.chapters)  # pruned from chapters


def test_single_block_hadith_unchanged(tmp_path):
    # Regression: a self-contained hadith still gets one isnad+matn+takhrij set.
    src = tmp_path / "one.mARkdown"
    src.write_text(
        "######OpenITI#\n#META#Header#End#\n# PageV01P001\n"
        "# وعن ابي هريرة رضي الله عنه قال قال رسول الله صلى الله عليه وسلم «انما الاعمال» رواه البخاري\n",
        encoding="utf-8",
    )
    from ingestion.parse import parse_file
    result = parse_file(src, "0100Test.One")
    detect_hadith_structure(result)
    b = result.pages[0].content_blocks[0]
    labels = {s.label for s in b.spans}
    assert {"isnad", "matn", "takhrij"} <= labels
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ingestion && python -m pytest tests/test_hadith.py -k "split_matn or single_block_hadith" -v`
Expected: FAIL — `detect_hadith_structure` is still per-block, so `split_matn` only tags one block and leaves the heading.

- [ ] **Step 3: Add `_project` and rewrite `detect_hadith_structure`**

In `ingestion/hadith.py`, add `_project` (after `_group_hadith_units`):

```python
def _project(origin, combined, ranges, stats: dict) -> None:
    """Append per-block spans for each range, splitting at block boundaries.
    origin[i] is the Block that combined[i] belongs to (same object identity)."""
    isnad, matn, takhrij, conf = ranges
    for label, rng in (("isnad", isnad), ("matn", matn), ("takhrij", takhrij)):
        if rng is None:
            continue
        s, e = rng
        i = s
        while i <= e:
            blk = origin[i]
            j = i
            while j + 1 <= e and origin[j + 1] is blk:
                j += 1
            blk.spans.append(Span(start_token_id=combined[i].id,
                                  end_token_id=combined[j].id,
                                  label=label, confidence=conf))
            stats[label] += 1
            i = j + 1
    stats["hadith"] += 1
    stats["high_conf" if conf >= HIGH_CONF else "low_conf"] += 1
```

Then REPLACE `detect_hadith_structure` with:

```python
def detect_hadith_structure(result: ParseResult) -> dict:
    """Group blocks into hadith units, detect structure across each unit, and
    write per-block isnad/matn/takhrij spans. Returns a stats dict."""
    stats = {"hadith": 0, "isnad": 0, "matn": 0, "takhrij": 0,
             "high_conf": 0, "low_conf": 0}
    flat = [(p.page_number, i, b)
            for p in result.pages for i, b in enumerate(p.content_blocks)]
    pruned: set[tuple[int, int]] = set()    # (page_number, block_index) fragment headings
    for unit in _group_hadith_units(flat):
        # Skip units already carrying structure (rare native @MATN@ path).
        if any(any(s.label in ("isnad", "matn", "takhrij") for s in b.spans)
               for _, _, b in unit):
            continue
        combined, origin = [], []
        for _, _, b in unit:
            for t in b.tokens:
                combined.append(t); origin.append(b)
        ranges = _detect_ranges(combined, [_norm(t.text) for t in combined])
        if ranges is None:
            continue
        _project(origin, combined, ranges, stats)
        # Re-type matn-fragment headings absorbed into the unit (not the opener).
        for pg, idx, b in unit[1:]:
            if b.type == "heading":
                b.type = "prose"
                pruned.add((pg, idx))
    if pruned:
        result.chapters = [c for c in result.chapters
                           if (c.page_number, c.block_index) not in pruned]
    return stats
```

Delete the now-unused `_detect_block` function (nothing references it after this rewrite).

- [ ] **Step 4: Run the full hadith suite**

Run: `cd ingestion && python -m pytest tests/test_hadith.py -v`
Expected: PASS — the new cross-block tests pass and every existing single-block test still passes (a lone hadith is a unit of one; `_project` over one block == the old `_emit`).

- [ ] **Step 5: Run the whole ingestion suite**

Run: `cd ingestion && python -m pytest -q`
Expected: PASS (no regressions in parse/annotate/etc.).

- [ ] **Step 6: Commit**

```bash
git add ingestion/hadith.py ingestion/tests/test_hadith.py
git commit -m "feat(hadith): cross-block detection — stitch fragmented hadith, project per-block spans"
```

---

## Task 4: Verify truncation drops on Bulugh

**Files:** none (verification).

- [ ] **Step 1: Re-parse Bulugh and measure matn truncations**

Run (from repo root, needs the `RELEASE` corpus):
```bash
python -m ingestion parse 0852IbnHajarCasqalani.BulughMaram --dump web/data --corpus-path ./RELEASE
python3 - <<'PY'
import json
d=json.load(open("web/data/0852IbnHajarCasqalani.BulughMaram.parsed.json"))
h=[b for p in d["pages"] for b in p["content_blocks"] if b.get("number")]
def seg(b,l):
    sp=[s for s in b.get("spans",[]) if s["label"]==l]
    if not sp: return ""
    ids=[t["id"] for t in b["tokens"]];tx={t["id"]:t["text"] for t in b["tokens"]}
    s=sp[0];i0=ids.index(s["start_token_id"]);i1=ids.index(s["end_token_id"])
    return " ".join(tx[ids[i]] for i in range(i0,i1+1))
trunc=sum(1 for b in h if "«" in seg(b,"matn") and "»" not in seg(b,"matn"))
cov=sum(1 for b in h if {s["label"] for s in b.get("spans",[])}&{"isnad","matn","takhrij"})
print(f"coverage {cov}/{len(h)} ({cov/len(h):.0%}) | matn truncated at an open « : {trunc}  (was ~133)")
PY
```
Expected: truncations drop sharply from ~133 toward single digits; coverage stays ~99%.

- [ ] **Step 2: Run suhuf verify**

Run: `./bin/suhuf verify --base origin/main`
Expected: `✓ verify passed`.

---

## Self-Review

- **Spec coverage:** grouping `_group_hadith_units` (Task 2) ✓; open-delimiter `« { ﴿` absorption (`_OPEN_DELIMS`, Task 2) ✓; real-chapter-vs-fragment heuristic (`_is_real_chapter`, Task 2) ✓; combined detection (`_detect_ranges`, Task 1) ✓; per-block projection (`_project`, Task 3) ✓; fragment re-typing + chapter pruning (Task 3) ✓; single-block regression (Task 3 test + existing suite) ✓; truncation drop (Task 4) ✓.
- **Placeholder scan:** none — every step has full code/commands.
- **Type consistency:** `_detect_ranges(toks, norm) -> (isnad, matn, takhrij, conf)`; `_ranges_from_*` same shape; `_group_hadith_units(flat)` takes/returns `(page_number, block_index, block)` tuples; `_project(origin, combined, ranges, stats)`; `_is_real_chapter`/`_is_hadith_start`/`_is_takhrij_continuation`/`_unit_open_delim` consistent. `Span`, `_norm`, `_takhrij_end`, `_CROSSREF_RE`, `_GRADING_VOCAB`, `_TRANSMISSIONS`, `_QAL_HINGE`, `_AN_HINGE`, `TAKHRIJ_NORM`, `HIGH_CONF`, `LOW_CONF` all already exist in `hadith.py`.
