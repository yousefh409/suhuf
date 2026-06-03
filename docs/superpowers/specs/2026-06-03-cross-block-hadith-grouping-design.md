# Cross-block hadith grouping

## Problem

`detect_hadith_structure` runs **per block**, but the OpenITI source frequently
fragments one hadith across several blocks. Bulugh hadith #2 is one hadith in
four blocks:

```
b3 prose   ▸ وعن أبي سعيد… قال: قال رسول الله ﷺ: «إن        ← isnad + matn, cut at «إن
b4 HEADING ▸ الماء طهور لا ينجسه شيء».                       ← the REST of the matn quote
b5 takhrij ▸ أخرجه الثلاثة (1)
b6 prose   ▸ وصححه أحمد. (2)                                ← takhrij/grading
```

Because the detector sees only b3, the matn truncates at `«إن`, and b4 (a real
matn fragment the source pulled into a `### |` heading) is never considered — it
even pollutes the chapter tree. This is the single biggest source of
low-confidence matn errors.

## Goal

Detect a hadith's structure across the blocks it actually spans, and write the
result back as **per-block span pieces** — no schema change. This is a **book
reader**: the page-block JSON in `pages.content_blocks` stays as-is; a matn that
crosses b3→b4 simply gets a matn span in b3 *and* in b4. No `hadith` table.

## Approach

Group consecutive blocks into a **hadith unit**, detect structure over the
unit's combined token stream, then project the resulting spans back onto each
constituent block. This is the deterministic *prior*; a later AI review pass
(separate spec) refines it.

## Components

### 1. Hadith-unit grouping — `_group_hadith_units(blocks)`

Walk blocks in **document order across pages** (a hadith can span a page break).
Emit a list of units, each a list of `(page_number, block_index, block)`.

- A **unit opens** at a *hadith-start* block: one with a printed `number`, or a
  prose block whose first token is a transmission opener (`عن`/`وعن`/`حدثنا`…)
  or a prophetic marker.
- The open unit **absorbs the next block** as a continuation when either:
  - the unit currently has an **unclosed `«` quote** (a split matn — absorb
    regardless of the next block's type, including `heading`), or
  - the next block is a **takhrij/grading/source continuation** (a takhrij-line,
    or a short cross-ref/grading note) and is *not* itself a hadith-start.
- The unit **closes** at the next hadith-start, at a **real chapter heading**
  (a `### |` heading that is a genuine section title — see below), or when no
  continuation rule applies.

**Real chapter vs. matn-fragment heading.** A `### |` heading is a *fragment*
(absorbed + re-typed) when the open unit has an unclosed quote, or the heading
ends with `»` / contains `«…»` / opens with `:` or `«`. Otherwise it is a *real
chapter* and closes the unit.

### 2. Combined detection — refactor the tiers to return ranges

The existing tiers (prophetic-marker → `«…»` → narrator-`قال:` → cross-ref) move
from "append spans to a block" to "**compute isnad/matn/takhrij ranges over a
token list**": `_detect_ranges(toks, norm) -> (isnad, matn, takhrij, conf)` where
each is an inclusive `(start, end)` in combined-unit coordinates or `None`. The
per-block path becomes the one-block special case (a unit of length 1).

### 3. Span projection — `_project(unit, ranges, conf)`

For each non-None range, **split it at block boundaries** and append a span to
each block it overlaps, using that block's local token IDs. A matn range that
spans b3 (combined 0–10) and b4 (11–25) → a matn span in b3 over its tail and a
matn span in b4 over its head. Confidence is shared across the pieces.

### 4. Fragment re-typing + chapter pruning

A `### |` heading absorbed into a unit is re-typed `heading` → `prose` (so the
reader renders it as body, not a section title), and its entry is removed from
`result.chapters`. Token IDs are untouched (no re-keying, no `content_hash`
drift).

## Data flow

```
detect_hadith_structure(result):
  for unit in _group_hadith_units(all_blocks):
      toks  = concat(unit block tokens, tracking block origin)
      ranges = _detect_ranges(toks, [_norm(t) for t in toks])
      if ranges: _project(unit, ranges)   # per-block spans + retype fragments + prune chapters
```

Spans stay inside `pages.content_blocks` exactly as today; only their *grouping
logic* changes. The high-confidence marker tier is unchanged in behaviour for
single-block hadith (regression-guarded).

## Out of scope

- The AI structural-review pass over the whole book (its own spec — this is the
  deterministic prior it builds on).
- Any storage/schema/reader change (none needed).
- Entity spans (person/qur'an/…) — unchanged, stay in the annotate pass.

## Testing (`ingestion/tests/test_hadith.py`)

- **Split matn across two blocks**: `…«إن` then `الماء طهور…»` → one matn,
  emitted as a piece in each block, no truncation.
- **Matn pulled into a `### |` heading** → heading re-typed to `prose`, carries
  a matn span, removed from `result.chapters`.
- **Separate takhrij block** after the matn → takhrij span on it, in the same unit.
- **Real chapter heading** (`كتاب الطهارة`) between two hadith → NOT absorbed;
  it closes the unit and stays a heading/chapter.
- **Single-block hadith** (marker / quote / narrator / cross-ref) → unchanged
  (regression guard).
- **Coverage + truncation**: re-run Bulugh; assert the count of matn spans
  ending on an unclosed `«` (truncations) drops sharply.
