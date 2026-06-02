# Reader Format Taxonomy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the block/span taxonomy to the agreed set and render it in the internal reader on the "rich format, minimal reader" principle, validated against a hand-authored multi-genre fixture.

**Architecture:** The format contract is Pydantic models (`ingestion/models.py`) mirrored by TS types (`web/src/lib/reader/types.ts`). The reader reads local JSON from `web/data/<id>.{tier}.json` and renders blocks via `Block.tsx` / `TokenText.tsx` inside `ChapterScroll.tsx`. This plan changes the type definitions and the rendering only. Ingestion code that *produces* the format is a separate follow-on plan. Validation is visual via the preview server against a committed sample fixture, plus unit tests for the model and pure logic.

**Tech Stack:** Python 3 / Pydantic (pytest), Next.js 16 / React / TypeScript / Tailwind (vitest, tsc, eslint). The reader has no React component-test harness (vitest runs in node, pure functions only), so component rendering is verified through the preview server, not RTL tests.

**Scope notes:**
- `web/AGENTS.md` warns this is a non-standard Next.js 16; consult `node_modules/next/dist/docs/` before using framework APIs. This plan only edits client components and CSS, no framework APIs.
- Shipping is via `./bin/suhuf ship` (raw `git push` is blocked). Per-task commits stay local; do not push mid-plan.
- The dev server (`web`) and preview tool are bound to this worktree; start it with `preview_start` (name `web`).

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `ingestion/models.py` | Pydantic contract | add `Block.level`, `Block.number`, `Footnote`, `Page.footnotes` |
| `ingestion/tests/test_models.py` | model tests | add cases |
| `web/src/lib/reader/types.ts` | TS mirror | new `BlockType`, `SpanLabel`; `Block.level/number`; `Footnote`; `Page.footnotes` |
| `web/src/lib/reader/colors.ts` | inspector block colors | rewrite Records for new `BlockType` |
| `web/src/components/reader/TokenText.tsx` | token + span rendering | quran styled, references plain + data attrs, footnote superscript |
| `web/src/components/reader/Block.tsx` | block rendering | 7-type switch, quran block, heading level, item number |
| `web/src/components/reader/ChapterScroll.tsx` | page/section layout | drop dead `hadith` branch, render footnotes at section end |
| `web/src/app/globals.css` | reader span + footnote styles | keep only quran span styled, add footnote styles |
| `web/fixtures/Sample.Taxonomy.enriched.json` | committed sample (test page) | create |
| `web/scripts/seed-sample.mjs` + `web/package.json` | seed fixture into `web/data` | create + script entry |

---

## Task 1: Pydantic model — add level, number, Footnote, Page.footnotes

**Files:**
- Modify: `ingestion/models.py`
- Test: `ingestion/tests/test_models.py`

- [ ] **Step 1: Write failing tests**

Append to `ingestion/tests/test_models.py`:

```python
from ingestion.models import Block, Footnote, Page, Token


def test_block_accepts_level_and_number():
    b = Block(key="b0", type="heading", level=2, number="١")
    assert b.level == 2
    assert b.number == "١"


def test_block_level_and_number_default_none():
    b = Block(key="b1", type="prose")
    assert b.level is None
    assert b.number is None


def test_footnote_model_and_page_footnotes():
    fn = Footnote(marker="١", tokens=[Token(id="p1_fn1_w0", text="سقط")])
    page = Page(page_number=1, content_blocks=[], footnotes=[fn])
    assert page.footnotes[0].marker == "١"
    assert page.footnotes[0].tokens[0].text == "سقط"


def test_page_footnotes_default_empty():
    page = Page(page_number=2, content_blocks=[])
    assert page.footnotes == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/yousefh/Desktop/Cool Code/suhuf/.claude/worktrees/frosty-moore-7e2c9b" && python -m pytest ingestion/tests/test_models.py -q`
Expected: FAIL (`Footnote` import error / unexpected keyword `level`).

- [ ] **Step 3: Implement model changes**

In `ingestion/models.py`, add `level` and `number` to `Block`:

```python
class Block(BaseModel):
    key: str
    type: str
    tokens: list[Token] = []
    hemistichs: list[list[list[Token]]] = []
    metadata: dict | None = None
    parser_type: str | None = None
    spans: list[Span] = []
    flags: list[str] = []
    level: int | None = None      # heading depth 1/2/3; None for non-headings
    number: str | None = None     # printed item ordinal, e.g. "١" (string preserves fidelity)
```

Add a `Footnote` model above `Page`:

```python
class Footnote(BaseModel):
    marker: str               # the in-text marker, e.g. "١"
    tokens: list[Token] = []  # the note body, tokenized
```

Add `footnotes` to `Page`:

```python
class Page(BaseModel):
    page_number: int
    volume: int = 1
    content_blocks: list[Block] = []
    footnotes: list[Footnote] = []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest ingestion/tests/test_models.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ingestion/models.py ingestion/tests/test_models.py
git commit -m "feat(format): add heading level, item number, and footnotes to model"
```

---

## Task 2: Hand-authored multi-genre fixture + seed script

This is the "test page". It exercises hadith, poetry, and prose with every kept type. Authoring it first gives a visible baseline before the rendering changes.

**Files:**
- Create: `web/fixtures/Sample.Taxonomy.enriched.json`
- Create: `web/scripts/seed-sample.mjs`
- Modify: `web/package.json` (add `seed:sample` script)

- [ ] **Step 1: Create the fixture**

Create `web/fixtures/Sample.Taxonomy.enriched.json`. Token ids follow `p{page}_b{block}_w{word}`. Span labels and block types use the FINAL names.

```json
{
  "metadata": {
    "openiti_id": "Sample.Taxonomy",
    "title_ar": "نموذج التنسيق",
    "title_lat": "Namudhaj al-Tansiq",
    "author_openiti_id": "0000Sample",
    "genres": ["SAMPLE"],
    "language": "ara"
  },
  "chapters": [
    { "title": "كتاب الإيمان", "level": 1, "page_number": 1, "sort_order": 1, "block_index": 0 },
    { "title": "تفسير الفاتحة", "level": 1, "page_number": 1, "sort_order": 2, "block_index": 5 },
    { "title": "من معلقة امرئ القيس", "level": 1, "page_number": 1, "sort_order": 3, "block_index": 8 }
  ],
  "pages": [
    {
      "page_number": 1,
      "volume": 1,
      "content_blocks": [
        { "key": "b0", "type": "heading", "level": 1, "tokens": [
          { "id": "p1_b0_w0", "text": "كِتَابُ" }, { "id": "p1_b0_w1", "text": "الإِيمَان" } ] },
        { "key": "b1", "type": "heading", "level": 2, "tokens": [
          { "id": "p1_b1_w0", "text": "بَابُ" }, { "id": "p1_b1_w1", "text": "إِخْلَاصِ" }, { "id": "p1_b1_w2", "text": "النِّيَّة" } ] },
        { "key": "b2", "type": "isnad", "number": "١",
          "spans": [ { "start_token_id": "p1_b2_w1", "end_token_id": "p1_b2_w3", "label": "person", "sub_label": "companion" } ],
          "tokens": [
            { "id": "p1_b2_w0", "text": "عَنْ" }, { "id": "p1_b2_w1", "text": "عُمَرَ" }, { "id": "p1_b2_w2", "text": "بْنِ" }, { "id": "p1_b2_w3", "text": "الخَطَّابِ" },
            { "id": "p1_b2_w4", "text": "رَضِيَ" }, { "id": "p1_b2_w5", "text": "اللهُ" }, { "id": "p1_b2_w6", "text": "عَنْهُ" }, { "id": "p1_b2_w7", "text": "قَالَ" } ] },
        { "key": "b3", "type": "matn", "tokens": [
          { "id": "p1_b3_w0", "text": "«إِنَّمَا" }, { "id": "p1_b3_w1", "text": "الأَعْمَالُ" }, { "id": "p1_b3_w2", "text": "بِالنِّيَّاتِ»" } ] },
        { "key": "b4", "type": "takhrij",
          "spans": [
            { "start_token_id": "p1_b4_w1", "end_token_id": "p1_b4_w1", "label": "person" },
            { "start_token_id": "p1_b4_w3", "end_token_id": "p1_b4_w3", "label": "book_ref", "ref": "0261Muslim.Sahih" } ],
          "tokens": [
            { "id": "p1_b4_w0", "text": "رَوَاهُ" }, { "id": "p1_b4_w1", "text": "البُخَارِيُّ" }, { "id": "p1_b4_w2", "text": "فِي" }, { "id": "p1_b4_w3", "text": "صَحِيحِهِ" } ] },
        { "key": "b5", "type": "heading", "level": 1, "tokens": [
          { "id": "p1_b5_w0", "text": "تَفْسِيرُ" }, { "id": "p1_b5_w1", "text": "الفَاتِحَة" } ] },
        { "key": "b6", "type": "prose",
          "spans": [
            { "start_token_id": "p1_b6_w1", "end_token_id": "p1_b6_w2", "label": "person", "sub_label": "scholar" },
            { "start_token_id": "p1_b6_w8", "end_token_id": "p1_b6_w8", "label": "footnote", "ref": "١" },
            { "start_token_id": "p1_b6_w10", "end_token_id": "p1_b6_w12", "label": "date_hijri" } ],
          "tokens": [
            { "id": "p1_b6_w0", "text": "قَالَ" }, { "id": "p1_b6_w1", "text": "ابْنُ" }, { "id": "p1_b6_w2", "text": "كَثِيرٍ" },
            { "id": "p1_b6_w3", "text": "فِي" }, { "id": "p1_b6_w4", "text": "قَوْلِهِ" }, { "id": "p1_b6_w5", "text": "تَعَالَى:" },
            { "id": "p1_b6_w6", "text": "هَذَا" }, { "id": "p1_b6_w7", "text": "ثَنَاءٌ" }, { "id": "p1_b6_w8", "text": "عَظِيمٌ." },
            { "id": "p1_b6_w9", "text": "تُوُفِّيَ" }, { "id": "p1_b6_w10", "text": "سَنَةَ" }, { "id": "p1_b6_w11", "text": "٧٧٤" }, { "id": "p1_b6_w12", "text": "هـ" } ] },
        { "key": "b7", "type": "quran",
          "spans": [ { "start_token_id": "p1_b7_w0", "end_token_id": "p1_b7_w3", "label": "quran", "ref": "1:2" } ],
          "tokens": [
            { "id": "p1_b7_w0", "text": "﴿الحَمْدُ" }, { "id": "p1_b7_w1", "text": "لِلَّهِ" }, { "id": "p1_b7_w2", "text": "رَبِّ" }, { "id": "p1_b7_w3", "text": "العَالَمِينَ﴾" } ] },
        { "key": "b8", "type": "heading", "level": 1, "tokens": [
          { "id": "p1_b8_w0", "text": "مِنْ" }, { "id": "p1_b8_w1", "text": "مُعَلَّقَةِ" }, { "id": "p1_b8_w2", "text": "امْرِئِ" }, { "id": "p1_b8_w3", "text": "القَيْس" } ] },
        { "key": "b9", "type": "poetry",
          "spans": [ { "start_token_id": "p1_b9_w5", "end_token_id": "p1_b9_w5", "label": "place" } ],
          "hemistichs": [
            [
              [ { "id": "p1_b9_w0", "text": "قِفَا" }, { "id": "p1_b9_w1", "text": "نَبْكِ" }, { "id": "p1_b9_w2", "text": "مِنْ" }, { "id": "p1_b9_w3", "text": "ذِكْرَى" } ],
              [ { "id": "p1_b9_w4", "text": "بِسِقْطِ" }, { "id": "p1_b9_w5", "text": "اللِّوَى" }, { "id": "p1_b9_w6", "text": "بَيْنَ" }, { "id": "p1_b9_w7", "text": "الدَّخُولِ" } ]
            ]
          ] }
      ],
      "footnotes": [
        { "marker": "١", "tokens": [
          { "id": "p1_fn1_w0", "text": "سَقَطَ" }, { "id": "p1_fn1_w1", "text": "فِي" }, { "id": "p1_fn1_w2", "text": "نُسْخَةِ" }, { "id": "p1_fn1_w3", "text": "«أ»." } ] }
      ]
    }
  ]
}
```

- [ ] **Step 2: Create the seed script**

Create `web/scripts/seed-sample.mjs`:

```js
import { copyFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const dir = path.dirname(fileURLToPath(import.meta.url));
const src = path.join(dir, "..", "fixtures", "Sample.Taxonomy.enriched.json");
const destDir = path.join(dir, "..", "data");
await mkdir(destDir, { recursive: true });
await copyFile(src, path.join(destDir, "Sample.Taxonomy.enriched.json"));
console.log("seeded Sample.Taxonomy.enriched.json into web/data");
```

- [ ] **Step 3: Add the npm script**

In `web/package.json` `scripts`, add:

```json
"seed:sample": "node scripts/seed-sample.mjs"
```

- [ ] **Step 4: Seed and verify it loads**

Run: `cd web && npm run seed:sample`
Expected: prints "seeded ...". File exists at `web/data/Sample.Taxonomy.enriched.json`.

Then start the preview (`preview_start` name `web`) and load `/internal/library`.
Expected: a "نموذج التنسيق" entry appears. Open `/internal/reader/Sample.Taxonomy` — it renders with the OLD styling (headings all same size, all spans visibly decorated, `quran` block falls back to prose, footnotes absent). This is the baseline.

- [ ] **Step 5: Commit**

```bash
git add web/fixtures/Sample.Taxonomy.enriched.json web/scripts/seed-sample.mjs web/package.json
git commit -m "test(reader): add multi-genre taxonomy sample fixture and seed script"
```

---

## Task 3: Retype the block/span set (types + colors + Block + ChapterScroll)

This is one atomic change because the `BlockType` union, its exhaustive `colors.ts` Records, the `Block.tsx` switch, and the `ChapterScroll.tsx` `hadith` reference must all agree for `tsc` to pass. Steps edit one file each; the commit lands once everything compiles.

**Files:**
- Modify: `web/src/lib/reader/types.ts`
- Modify: `web/src/lib/reader/colors.ts`
- Modify: `web/src/components/reader/Block.tsx`
- Modify: `web/src/components/reader/ChapterScroll.tsx:49-54`

- [ ] **Step 1: Update `types.ts`**

Replace the `BlockType` and `SpanLabel` unions and extend `Block`/`Page`:

```ts
export type BlockType =
  | "prose"
  | "heading"
  | "poetry"
  | "isnad"
  | "matn"
  | "takhrij"
  | "quran";

export type SpanLabel =
  | "quran"
  | "person"
  | "place"
  | "book_ref"
  | "hadith_ref"
  | "date_hijri"
  | "footnote";
```

Add `level`, `number` to `BlockBase`:

```ts
type BlockBase = {
  key: string;
  metadata?: Record<string, unknown> | null;
  parser_type?: string | null;
  spans?: Span[];
  flags?: QualityFlag[];
  level?: number | null;
  number?: string | null;
};
```

Add a `Footnote` type and `footnotes` on `Page` (find the `Page` type in this file):

```ts
export type Footnote = {
  marker: string;
  tokens: Token[];
};
```
and add `footnotes?: Footnote[];` to the `Page` type.

- [ ] **Step 2: Rewrite `colors.ts`**

Replace both Records so keys exactly match the new `BlockType`:

```ts
import type { BlockType } from "./types";

export const BLOCK_BORDER: Record<BlockType, string> = {
  prose:   "border-zinc-300",
  heading: "border-amber-400",
  poetry:  "border-rose-400",
  isnad:   "border-sky-400",
  matn:    "border-violet-400",
  takhrij: "border-fuchsia-400",
  quran:   "border-emerald-500",
};

export const BLOCK_BADGE: Record<BlockType, string> = {
  prose:   "bg-zinc-100 text-zinc-700",
  heading: "bg-amber-100 text-amber-800",
  poetry:  "bg-rose-100 text-rose-800",
  isnad:   "bg-sky-100 text-sky-800",
  matn:    "bg-violet-100 text-violet-800",
  takhrij: "bg-fuchsia-100 text-fuchsia-800",
  quran:   "bg-emerald-100 text-emerald-800",
};
```

- [ ] **Step 3: Update `Block.tsx` switch**

In `renderInner`, replace the `switch (block.type)` body. Remove the `hadith_grading`, `biography`, `commentary`, `quoted_text`, `editor_note`, and `hadith` cases. Make `heading` size by `block.level`. Add a `quran` case. Keep `isnad`, `matn`, `takhrij` reader/inspector branches as they are today.

```tsx
  switch (block.type) {
    case "heading": {
      const lvl = block.level ?? 2;
      const sizeReader = lvl === 1 ? "text-[1.35em]" : lvl === 2 ? "text-[1.15em]" : "text-[1.02em]";
      return isReader ? (
        <h2 className={`font-bold ${sizeReader} leading-snug mt-8 mb-3 text-center`} style={{ color: "var(--reader-fg)" }}>
          {tokens}
        </h2>
      ) : (
        <h2 className="font-bold text-xl mt-6 mb-2">{tokens}</h2>
      );
    }
    case "isnad":
      return isReader ? (
        <p className="text-[0.92em] leading-[2] my-1" style={{ color: "var(--reader-fg-muted)" }}>{tokens}</p>
      ) : (
        <p className="text-zinc-600 leading-loose">{tokens}</p>
      );
    case "matn":
      return isReader ? (
        <p className="font-semibold leading-[2.05] my-2 text-[1.02em]">{tokens}</p>
      ) : (
        <p className="font-medium leading-loose">{tokens}</p>
      );
    case "takhrij":
      return isReader ? (
        <p className="text-[0.88em] leading-[1.85] my-1" style={{ color: "var(--reader-fg-muted)" }}>{tokens}</p>
      ) : (
        <p className="text-zinc-500 leading-loose">{tokens}</p>
      );
    case "quran":
      return isReader ? (
        <p className="reader-quran-block text-center leading-[2.2] my-4 text-[1.1em]">{tokens}</p>
      ) : (
        <p className="text-emerald-800 text-center leading-loose my-3">{tokens}</p>
      );
    case "prose":
    default:
      return <p className="leading-[2] my-2">{tokens}</p>;
  }
```

Then render the item `number` (faint, before the first token) for `isnad`/`heading`-led items. Add this just before the `switch`, replacing the plain `tokens` use where needed:

```tsx
  const numberPrefix =
    isReader && block.number ? (
      <span className="reader-item-number" aria-hidden>{block.number} - </span>
    ) : null;
```
and prepend `{numberPrefix}` inside the `isnad` and `heading` reader `<p>`/`<h2>` returns (before `{tokens}`).

- [ ] **Step 4: Remove the dead `hadith` branch in `ChapterScroll.tsx`**

Delete lines 49-54 (the `if (b.type === "hadith") { ... }` block) in `groupBlocks`. The `isnad`+`matn` grouping above it remains.

- [ ] **Step 5: Typecheck, lint, existing tests**

Run: `cd web && npx tsc --noEmit && npx eslint src/lib/reader src/components/reader && npx vitest run`
Expected: all pass (the `Page` fixture-shaped objects in `queries.test.ts` still satisfy the widened types; `footnotes` is optional).

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/reader/types.ts web/src/lib/reader/colors.ts web/src/components/reader/Block.tsx web/src/components/reader/ChapterScroll.tsx
git commit -m "feat(reader): reduce block taxonomy, size headings by level, add quran block + item number"
```

---

## Task 4: Span rendering — quran styled, references plain + tappable, footnote superscript

**Files:**
- Modify: `web/src/components/reader/TokenText.tsx`

- [ ] **Step 1: Add the span-category constants**

At the top of `TokenText.tsx` (after imports), add:

```tsx
// Only quran is visually styled inline. The rest are tagged in the DOM
// (data attributes) for later tap-to-popup, but render as plain text.
const STYLED_SPAN_LABELS = new Set<SpanLabel>(["quran"]);
```

- [ ] **Step 2: Rework the reader-mode return**

Replace the reader-mode branch (the `if (mode === "reader") { ... }` block) so that:
- a `quran` span still gets `reader-span reader-span-quran`,
- a `footnote` span renders the word followed by a superscript marker (the `spanRef`),
- other labels render plain text but carry `data-span-label` / `data-span-ref`.

```tsx
  if (mode === "reader") {
    const styled = spanLabel && STYLED_SPAN_LABELS.has(spanLabel);
    const styledSpanClass = styled ? `reader-span reader-span-${spanLabel}` : undefined;
    const className =
      [accentClass, styledSpanClass, recitationClass].filter(Boolean).join(" ") || undefined;

    const dataAttrs =
      spanLabel && !styled && spanLabel !== "footnote"
        ? { "data-span-label": spanLabel, "data-span-ref": spanRef ?? undefined }
        : {};

    if (spanLabel === "footnote") {
      return (
        <span>
          {display}
          <sup className="reader-footnote-ref" data-footnote-ref={spanRef ?? undefined}>{spanRef}</sup>{" "}
        </span>
      );
    }

    if (className || Object.keys(dataAttrs).length > 0) {
      return <span className={className} title={styled ? title : undefined} {...dataAttrs}>{display} </span>;
    }
    return <span>{display} </span>;
  }
```

(The inspector-mode branch below is unchanged; it keeps showing every span class for debugging.)

- [ ] **Step 3: Typecheck and lint**

Run: `cd web && npx tsc --noEmit && npx eslint src/components/reader/TokenText.tsx`
Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add web/src/components/reader/TokenText.tsx
git commit -m "feat(reader): style only quran inline, render references plain with data attrs, footnote superscript"
```

---

## Task 5: Footnotes at the bottom of each section

**Files:**
- Modify: `web/src/components/reader/ChapterScroll.tsx`

- [ ] **Step 1: Render the footnote list per page section**

Inside the `pages.map(...)` `<section>` in `ChapterScroll`, after the `{items.map(...)}` block and before `</section>`, add (reader mode only):

```tsx
            {mode === "reader" && page.footnotes && page.footnotes.length > 0 && (
              <div className="reader-footnotes">
                {page.footnotes.map((fn) => (
                  <p key={fn.marker} className="reader-footnote">
                    <span className="reader-footnote-marker">{fn.marker}</span>{" "}
                    {fn.tokens.map((t) => (
                      <TokenText
                        key={t.id}
                        token={t}
                        mode={mode}
                        showTashkeel={showTashkeel}
                        showDiff={showDiff}
                      />
                    ))}
                  </p>
                ))}
              </div>
            )}
```

Add `TokenText` to the imports at the top: `import { TokenText } from "./TokenText";`.

- [ ] **Step 2: Typecheck and lint**

Run: `cd web && npx tsc --noEmit && npx eslint src/components/reader/ChapterScroll.tsx`
Expected: pass.

- [ ] **Step 3: Commit**

```bash
git add web/src/components/reader/ChapterScroll.tsx
git commit -m "feat(reader): render page footnotes at the bottom of each section"
```

---

## Task 6: Reader CSS — quran span, footnote, item number, quran block

**Files:**
- Modify: `web/src/app/globals.css`

- [ ] **Step 1: Replace the span label styles**

Replace the span-label block (the `.reader-span-qur_quote` ... `.reader-span-date_hijri` rules, lines ~148-176) with only the quran span plus the new structural styles. Keep `.reader-span` base.

```css
.reader-span-quran {
  background: rgba(26, 122, 70, 0.10);
  box-shadow: 0 1px 0 0 rgba(26, 122, 70, 0.35);
  color: var(--reader-quran, #1a6b46);
}
[data-reader-theme="night"] .reader-span-quran {
  background: rgba(80, 200, 140, 0.10);
  box-shadow: 0 1px 0 0 rgba(80, 200, 140, 0.30);
}

/* Standalone ayah block. */
.reader-quran-block {
  color: var(--reader-quran, #1a6b46);
}
[data-reader-theme="night"] .reader-quran-block { color: #6fd6a0; }

/* Faint printed item ordinal before a hadith/heading. */
.reader-item-number {
  color: var(--reader-fg-faint);
  font-family: var(--font-sans), system-ui, sans-serif;
  font-size: 0.8em;
}

/* Footnote superscript marker in running text. */
.reader-footnote-ref {
  color: var(--reader-accent);
  font-size: 0.62em;
  cursor: default;
}

/* Footnote list at the bottom of a section. */
.reader-footnotes {
  margin-top: 1.5rem;
  padding-top: 0.6rem;
  border-top: 1px solid var(--reader-rule);
}
.reader-footnote {
  font-size: 0.82em;
  line-height: 1.9;
  color: var(--reader-fg-muted);
  margin: 0.2rem 0;
}
.reader-footnote-marker { color: var(--reader-accent); }
```

- [ ] **Step 2: Verify the build picks up CSS (lint only, CSS has no test)**

Run: `cd web && npx eslint src --max-warnings=0 || true`
(ESLint does not lint CSS; this just confirms no JS regressions. CSS is verified visually in Task 7.)

- [ ] **Step 3: Commit**

```bash
git add web/src/app/globals.css
git commit -m "style(reader): quran-only inline tint, quran block, item number, footnote styles"
```

---

## Task 7: Cross-genre visual verification

No code; this is the acceptance gate. The reader has no component-test harness, so verify rendering through the preview.

**Files:** none (uses the seeded fixture from Task 2).

- [ ] **Step 1: Ensure fixture is seeded and server running**

Run: `cd web && npm run seed:sample`
Start/reuse the preview (`preview_start` name `web`).

- [ ] **Step 2: Verify the reader page**

Open `/internal/reader/Sample.Taxonomy`. Use `preview_snapshot` and `preview_screenshot` and confirm:
- Headings render at three distinct sizes (L1 > L2 > L3).
- Hadith: `isnad` muted, `matn` bold, `takhrij` small/muted; item number `١ -` faint before the isnad.
- The `quran` block is centered and green; the inline `quran` span (in prose) is the only tinted inline text.
- Narrator names, book title, and the hijri date in prose render as **plain text** (no underline/decoration). Confirm via `preview_inspect` that they carry `data-span-label`.
- Footnote: superscript `١` after "عَظِيمٌ"; the note text appears at the bottom of the section.
- Poetry: two hemistichs per line, centered, with the divider.

- [ ] **Step 3: Verify the inspector still shows everything**

Open `/internal/inspector/Sample.Taxonomy`. Confirm block badges show the new types (incl. `quran`) and that all spans remain visibly decorated in inspector mode (debugging affordance preserved).

- [ ] **Step 4: Full affected-package verify**

Run: `cd "/Users/yousefh/Desktop/Cool Code/suhuf/.claude/worktrees/frosty-moore-7e2c9b" && ./bin/suhuf verify --base origin/main`
Expected: web (lint, tsc, vitest, build) and ingestion (compileall, pytest) pass.

- [ ] **Step 5: Commit any verification fixups**

If Step 2 surfaced rendering bugs, fix the relevant component/CSS, re-verify, and commit with a `fix(reader): ...` message. Otherwise nothing to commit.

---

## Self-Review

**Spec coverage:**
- Block types reduced to the 7 reader-visible (heading/prose/poetry/isnad/matn/takhrij/quran): Task 3. ✓
- Heading carries `level`: model Task 1, type/render Task 3. ✓
- Item numbering (`number`): model Task 1, render Task 3 + CSS Task 6. ✓
- quran block + inline quran span (only styled inline): Task 3 (block), Task 4 (span), Task 6 (CSS). ✓
- References captured but plain (person/place/book_ref/hadith_ref/date_hijri): Task 4 (plain + data attrs), Task 6 (removed styles). ✓
- Footnotes (superscript → bottom of section): model Task 1, inline Task 4, list Task 5, CSS Task 6. ✓
- Cut types (biography/commentary/quoted_text/editor_note/hadith_grading/hadith/honorific/term/prophetic_quote): removed from union and switch Task 3; honorific/term/prophetic_quote simply absent from `SpanLabel`. ✓
- Page/volume boundaries kept in data, not newly rendered: unchanged (existing `PageBoundary` + `Page.page_number/volume`); no task needed. ✓
- Poetry metadata dropped: not added anywhere; fixture carries none. ✓
- Validation across hadith/poetry/prose: fixture Task 2, verification Task 7. ✓

**Placeholder scan:** No TBD/TODO; every code step shows full content. ✓

**Type consistency:** `BlockType`/`SpanLabel` defined in Task 3 are used consistently in `colors.ts`, `Block.tsx`, `TokenText.tsx` (`STYLED_SPAN_LABELS`), and the fixture. `Footnote` shape (`marker`, `tokens`) matches between Pydantic (Task 1), TS (Task 3), fixture (Task 2), and render (Task 5). Span label `footnote` with `ref` = marker is consistent across fixture, `TokenText`, and the `Page.footnotes` list. ✓

**Out of scope (follow-on ingestion plan):** parser/enrichment producing these types, `ref` resolution to the catalog/Qur'an, tap-to-popup interactions, the page-split reading mode.
