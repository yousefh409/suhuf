# Internal Web Reader & Inspector — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a hidden Next.js route inside `web/` that reads ingested OpenITI books from Supabase, with a clean Reader mode and an Inspector mode that overlays ingestion artifacts (block types, token IDs, tashkeel diff, raw JSON).

**Architecture:** Server components fetch from Supabase via the existing `getSupabase()` helper. A `lib/reader/` module houses types, pure helpers (chapter synthesis, page slicing, tashkeel strip), and queries. A `components/reader/` module houses block-rendering primitives shared by both modes. Two route trees (`/internal/reader` and `/internal/inspector`) reuse the same components, passing a `mode` prop that conditionally renders inspector overlays. A small ingestion change adds an optional `text_raw` field to `Token`, populated by the tashkeel step only when diacritization changed the token.

**Tech Stack:** Next.js 16.2 (app router), React 19, TypeScript, Tailwind v4, `@supabase/supabase-js`, Vitest (new dev dep). Python ingestion uses Pydantic + pytest. Project ships via `./bin/suhuf ship` (raw `git push` is blocked by a hook).

**Spec:** [docs/superpowers/specs/2026-04-29-internal-reader-design.md](../specs/2026-04-29-internal-reader-design.md)

---

## ⚠️ Before you start

This Next.js codebase is unconventional ([web/AGENTS.md](../../../web/AGENTS.md)): "This is NOT the Next.js you know" — version 16.2.3, React 19. APIs in your training data may be wrong. In particular:

- Route handlers and pages receive `params` as a `Promise` you must `await`. See [web/src/app/r/[code]/route.ts](../../../web/src/app/r/[code]/route.ts) for an example.
- Read the relevant guide in `web/node_modules/next/dist/docs/` before writing app-router code if anything looks off.

The project has shipping guardrails ([CLAUDE.md](../../../CLAUDE.md)):

- Never run raw `git push` — blocked by a PreToolUse hook.
- All shipping goes through `./bin/suhuf ship`.
- Local verify: `./bin/suhuf verify` (lint + tsc + test + build for web; pytest collection for ingestion).
- `pytest --co` is collection-only in CI for ingestion. Run actual `pytest` locally before shipping ingestion changes.

---

## File Layout

### Created
```
docs/superpowers/plans/2026-04-29-internal-reader.md  (this file)

# Ingestion
ingestion/tests/test_text_raw.py

# Web - infrastructure
web/vitest.config.ts
web/src/lib/reader/types.ts
web/src/lib/reader/queries.ts
web/src/lib/reader/queries.test.ts
web/src/lib/reader/tashkeel.ts
web/src/lib/reader/tashkeel.test.ts
web/src/lib/reader/colors.ts

# Web - components
web/src/components/reader/TokenText.tsx
web/src/components/reader/Block.tsx
web/src/components/reader/PageBoundary.tsx
web/src/components/reader/ChapterScroll.tsx
web/src/components/reader/ModeToggle.tsx
web/src/components/reader/TashkeelToggle.tsx
web/src/components/reader/ChapterDrawer.tsx
web/src/components/reader/InspectorJsonDrawer.tsx
web/src/components/reader/DiffToggle.tsx

# Web - routes
web/src/app/internal/layout.tsx
web/src/app/internal/library/page.tsx
web/src/app/internal/reader/[openiti_id]/page.tsx
web/src/app/internal/reader/[openiti_id]/[ch_index]/page.tsx
web/src/app/internal/inspector/[openiti_id]/page.tsx
web/src/app/internal/inspector/[openiti_id]/[ch_index]/page.tsx

# Web - misc
web/public/robots.txt
```

### Modified
```
ingestion/models.py
ingestion/tashkeel.py
web/supabase-schema.sql
web/package.json
scripts/suhuf/src/lib/packages.mjs
```

---

## Phase A — Ingestion change

### Task 1: Add `text_raw` to Token model and populate during tashkeel

**Files:**
- Modify: `ingestion/models.py`
- Modify: `ingestion/tashkeel.py`
- Create: `ingestion/tests/test_text_raw.py`

- [ ] **Step 1: Write the failing tests**

Create `ingestion/tests/test_text_raw.py`:

```python
from ingestion.models import Token, Block, Page
from ingestion.tashkeel import diacritize_blocks


def test_token_text_raw_defaults_to_none():
    t = Token(id="p1_b0_w0", text="حدثنا")
    assert t.text_raw is None


def test_token_text_raw_set_explicitly():
    t = Token(id="p1_b0_w0", text="حَدَّثَنَا", text_raw="حدثنا")
    assert t.text_raw == "حدثنا"


def test_diacritize_populates_text_raw_when_changed():
    tokens = [
        Token(id="p1_b0_w0", text="حدثنا"),
        Token(id="p1_b0_w1", text="عبد"),
    ]
    block = Block(key="b0", type="prose", tokens=tokens)
    page = Page(page_number=1, volume=1, content_blocks=[block])

    class MockEngine:
        def diacritize(self, text: str) -> str:
            return "حَدَّثَنَا عَبْدُ"

    result = diacritize_blocks([page], engine=MockEngine())
    out = result[0].content_blocks[0].tokens
    assert out[0].text == "حَدَّثَنَا"
    assert out[0].text_raw == "حدثنا"
    assert out[1].text == "عَبْدُ"
    assert out[1].text_raw == "عبد"


def test_diacritize_does_not_set_text_raw_when_unchanged():
    tokens = [Token(id="p1_b0_w0", text="عبد")]
    block = Block(key="b0", type="prose", tokens=tokens)
    page = Page(page_number=1, volume=1, content_blocks=[block])

    class IdentityEngine:
        def diacritize(self, text: str) -> str:
            return text

    result = diacritize_blocks([page], engine=IdentityEngine())
    assert result[0].content_blocks[0].tokens[0].text_raw is None


def test_diacritize_populates_text_raw_in_poetry():
    h1 = [Token(id="p1_b0_w0", text="قفا"), Token(id="p1_b0_w1", text="نبك")]
    block = Block(key="b0", type="poetry", hemistichs=[[h1]])
    page = Page(page_number=1, volume=1, content_blocks=[block])

    class MockEngine:
        def diacritize(self, text: str) -> str:
            return "قِفَا نَبْكِ"

    result = diacritize_blocks([page], engine=MockEngine())
    out_h = result[0].content_blocks[0].hemistichs[0][0]
    assert out_h[0].text == "قِفَا"
    assert out_h[0].text_raw == "قفا"
    assert out_h[1].text == "نَبْكِ"
    assert out_h[1].text_raw == "نبك"
```

- [ ] **Step 2: Run the new tests to confirm they fail**

```bash
cd "/Users/yousefh/Desktop/Cool Code/suhuf/.claude/worktrees/gracious-agnesi-dde2e8" && python -m pytest ingestion/tests/test_text_raw.py -v
```

Expected: FAIL — `Token.text_raw` does not exist; tests error or assertion-fail on the four new fields.

- [ ] **Step 3: Add the field to `Token` in `ingestion/models.py`**

Replace the `Token` class:

```python
class Token(BaseModel):
    id: str          # "p42_b1_w0"
    text: str        # "حَدَّثَنَا"
    text_raw: str | None = None  # original pre-tashkeel form, set only when diacritization changed text
```

- [ ] **Step 4: Populate `text_raw` in `_diacritize_block` (non-poetry branch)**

In `ingestion/tashkeel.py`, replace the existing line near line 90:

```python
new_tokens = [Token(id=t.id, text=w) for t, w in zip(block.tokens, result_words)]
```

with:

```python
new_tokens = [
    Token(id=t.id, text=w, text_raw=t.text if t.text != w else None)
    for t, w in zip(block.tokens, result_words)
]
```

- [ ] **Step 5: Populate `text_raw` in `_diacritize_block` (poetry branch)**

In the same file, the inner loop currently reads:

```python
for token in hemistich:
    new_h.append(Token(id=token.id, text=result_words[idx]))
    idx += 1
```

Replace with:

```python
for token in hemistich:
    w = result_words[idx]
    new_h.append(Token(
        id=token.id,
        text=w,
        text_raw=token.text if token.text != w else None,
    ))
    idx += 1
```

- [ ] **Step 6: Run the new tests to confirm they pass**

```bash
cd "/Users/yousefh/Desktop/Cool Code/suhuf/.claude/worktrees/gracious-agnesi-dde2e8" && python -m pytest ingestion/tests/test_text_raw.py -v
```

Expected: PASS — all 5 tests green.

- [ ] **Step 7: Run the full ingestion test suite to confirm no regressions**

```bash
python -m pytest ingestion/ -v
```

Expected: PASS — all existing tests still green. The optional field defaults to `None`, so no existing assertions break.

- [ ] **Step 8: Commit**

```bash
git add ingestion/models.py ingestion/tashkeel.py ingestion/tests/test_text_raw.py
git commit -m "ingestion: add Token.text_raw, populate during tashkeel when changed"
```

---

## Phase B — Schema reconciliation

### Task 2: Add `authors / books / pages / chapters` tables to web schema

**Files:**
- Modify: `web/supabase-schema.sql`

These tables already exist in the live Supabase (created by ingestion uploads). This task documents the contract in-repo.

- [ ] **Step 1: Append to `web/supabase-schema.sql`**

Below the existing waitlist content, append:

```sql

-- ===== Reader/Ingestion tables =====
-- Populated by ingestion/upload.py. `create table if not exists` keeps this
-- file idempotent against the live database.

create table if not exists authors (
  id uuid primary key default gen_random_uuid(),
  openiti_id text unique not null,
  shuhra_ar text,
  shuhra_lat text,
  ism_ar text,
  nasab_ar text,
  kunya_ar text,
  laqab_ar text,
  nisba_ar text,
  full_name_ar text,
  birth_ah int,
  death_ah int,
  created_at timestamptz default now()
);

create table if not exists books (
  id uuid primary key default gen_random_uuid(),
  openiti_id text unique not null,
  author_id uuid references authors(id) on delete cascade,
  title_ar text not null,
  title_lat text,
  description text,
  genres text[] default '{}',
  word_count int,
  char_count int,
  total_pages int,
  total_volumes int,
  version_status text,
  language text default 'ara',
  has_tashkeel boolean default false,
  composition_date_ah int,
  commentary_on text,
  abridgement_of text,
  created_at timestamptz default now()
);

create table if not exists pages (
  id uuid primary key default gen_random_uuid(),
  book_id uuid not null references books(id) on delete cascade,
  page_number int not null,
  volume int not null default 1,
  content_blocks jsonb not null,
  content_plain text not null,
  content_hash text not null,
  created_at timestamptz default now(),
  unique (book_id, volume, page_number)
);

create index if not exists idx_pages_book on pages(book_id);

create table if not exists chapters (
  id uuid primary key default gen_random_uuid(),
  book_id uuid not null references books(id) on delete cascade,
  title text not null,
  level int not null,
  page_id uuid references pages(id),
  sort_order int not null,
  created_at timestamptz default now(),
  unique (book_id, sort_order)
);

create index if not exists idx_chapters_book on chapters(book_id);
```

- [ ] **Step 2: Cross-check against `ingestion/upload.py`**

Open [ingestion/upload.py](../../../ingestion/upload.py). For each `client.table(...).upsert(...)` call, confirm every column in the upsert dict appears in the SQL above. Specifically:
- `authors` row keys: openiti_id, shuhra_ar, shuhra_lat, ism_ar, nasab_ar, kunya_ar, laqab_ar, nisba_ar, birth_ah, death_ah, full_name_ar.
- `books` row keys: openiti_id, author_id, title_ar, title_lat, description, genres, word_count, char_count, total_pages, total_volumes, version_status, language, has_tashkeel, composition_date_ah, commentary_on, abridgement_of.
- `pages` row keys: book_id, page_number, volume, content_blocks, content_plain, content_hash.
- `chapters` row keys: book_id, title, level, page_id, sort_order.

Fix any missing column before continuing.

- [ ] **Step 3: Commit**

```bash
git add web/supabase-schema.sql
git commit -m "web: document authors/books/pages/chapters schema"
```

---

## Phase C — Web test setup

### Task 3: Add Vitest to `web/`

**Files:**
- Modify: `web/package.json`
- Create: `web/vitest.config.ts`
- Modify: `scripts/suhuf/src/lib/packages.mjs`

`web/` has no test runner today. Vitest lets us unit-test pure modules (queries helpers, tashkeel-strip).

- [ ] **Step 1: Install Vitest as a dev dependency**

```bash
cd web && npm install --save-dev vitest
```

Expected: `package.json` gains `"vitest": "..."` under `devDependencies`. `package-lock.json` updates.

- [ ] **Step 2: Add `test` scripts to `web/package.json`**

In the `scripts` block, add:

```json
"test": "vitest run --passWithNoTests",
"test:watch": "vitest"
```

Final `scripts` should be (preserving existing entries):

```json
"scripts": {
  "dev": "next dev",
  "build": "next build",
  "start": "next start",
  "lint": "eslint",
  "test": "vitest run --passWithNoTests",
  "test:watch": "vitest",
  "deploy": "opennextjs-cloudflare build && opennextjs-cloudflare deploy",
  "preview": "opennextjs-cloudflare build && opennextjs-cloudflare preview"
}
```

- [ ] **Step 3: Create `web/vitest.config.ts`**

```ts
import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
});
```

- [ ] **Step 4: Smoke test the runner**

Create a temporary `web/src/lib/_smoke.test.ts`:

```ts
import { describe, it, expect } from "vitest";

describe("smoke", () => {
  it("runs", () => expect(1 + 1).toBe(2));
});
```

Run:

```bash
cd web && npm test
```

Expected: PASS — 1 test passes.

- [ ] **Step 5: Delete the smoke file**

```bash
rm web/src/lib/_smoke.test.ts
```

- [ ] **Step 6: Hook the test step into suhuf verify**

In `scripts/suhuf/src/lib/packages.mjs`, replace the `web` package block:

```js
{
  name: "web",
  path: "web",
  prefix: "web/",
  kind: "node",
  steps: [
    { kind: "lint",      cmd: "npm run lint" },
    { kind: "typecheck", cmd: "npx tsc --noEmit" },
    { kind: "test",      cmd: "npm test" },
    { kind: "build",     cmd: "npm run build" },
  ],
},
```

- [ ] **Step 7: Run suhuf verify on the web package**

```bash
./bin/suhuf verify --all
```

Expected: web pkg passes all four steps (test passes with zero collected — `--passWithNoTests` keeps exit 0).

- [ ] **Step 8: Commit**

```bash
git add web/package.json web/package-lock.json web/vitest.config.ts scripts/suhuf/src/lib/packages.mjs
git commit -m "web: add vitest, wire into suhuf verify"
```

---

## Phase D — Foundation: types, queries, pure helpers

### Task 4: Add reader types module

**Files:**
- Create: `web/src/lib/reader/types.ts`

- [ ] **Step 1: Create `web/src/lib/reader/types.ts`**

```ts
// TypeScript mirrors of the ingestion Pydantic models.
// Block is a discriminated union on `type`.

export type BlockType =
  | "prose"
  | "hadith"
  | "isnad"
  | "matn"
  | "poetry"
  | "biography"
  | "heading";

export type Token = {
  id: string;
  text: string;
  text_raw?: string | null;
};

type BlockBase = {
  key: string;
  metadata?: Record<string, unknown> | null;
};

export type ProseLikeBlock = BlockBase & {
  type: Exclude<BlockType, "poetry">;
  tokens: Token[];
};

export type PoetryBlock = BlockBase & {
  type: "poetry";
  hemistichs: Token[][][];
};

export type Block = ProseLikeBlock | PoetryBlock;

export type Page = {
  page_number: number;
  volume: number;
  content_blocks: Block[];
};

export type Chapter = {
  id?: string;
  title: string;
  level: number;
  page_number: number;
  volume: number;
  sort_order: number;
  synthesized?: boolean;
};

export type Author = {
  id: string;
  openiti_id: string;
  full_name_ar?: string | null;
  shuhra_ar?: string | null;
};

export type Book = {
  id: string;
  openiti_id: string;
  title_ar: string;
  title_lat?: string | null;
  description?: string | null;
  genres?: string[] | null;
  total_pages?: number | null;
  total_volumes?: number | null;
  has_tashkeel?: boolean | null;
  language?: string | null;
  author_id: string;
};

export type BookListItem = Pick<
  Book,
  "openiti_id" | "title_ar" | "title_lat" | "total_pages" | "total_volumes" | "has_tashkeel"
> & {
  author_name_ar: string | null;
};

export type ReaderMode = "reader" | "inspector";
```

- [ ] **Step 2: Confirm typecheck passes**

```bash
cd web && npx tsc --noEmit
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add web/src/lib/reader/types.ts
git commit -m "web: add reader types module"
```

---

### Task 5: Add tashkeel-strip util with tests

**Files:**
- Create: `web/src/lib/reader/tashkeel.ts`
- Create: `web/src/lib/reader/tashkeel.test.ts`

- [ ] **Step 1: Write failing tests**

Create `web/src/lib/reader/tashkeel.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { stripTashkeel } from "./tashkeel";

describe("stripTashkeel", () => {
  it("removes fatha, kasra, damma, sukun, shadda, tanween marks", () => {
    expect(stripTashkeel("حَدَّثَنَا")).toBe("حدثنا");
  });

  it("is idempotent on text without diacritics", () => {
    expect(stripTashkeel("حدثنا")).toBe("حدثنا");
  });

  it("does not touch non-Arabic text", () => {
    expect(stripTashkeel("hello")).toBe("hello");
  });

  it("handles empty string", () => {
    expect(stripTashkeel("")).toBe("");
  });

  it("preserves spaces and punctuation", () => {
    expect(stripTashkeel("بِسْمِ اللَّهِ، الرَّحْمَنِ.")).toBe("بسم الله، الرحمن.");
  });
});
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
cd web && npm test -- tashkeel
```

Expected: FAIL — `stripTashkeel` not found.

- [ ] **Step 3: Implement `stripTashkeel`**

Create `web/src/lib/reader/tashkeel.ts`:

```ts
// Strip the eight Arabic diacritic codepoints (U+064B..U+0652).
// Used in Reader mode when the tashkeel toggle is OFF.

const DIACRITICS = /[\u064B-\u0652]/g;

export function stripTashkeel(text: string): string {
  return text.replace(DIACRITICS, "");
}
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
cd web && npm test -- tashkeel
```

Expected: PASS — all 5 tests green.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/reader/tashkeel.ts web/src/lib/reader/tashkeel.test.ts
git commit -m "web: add stripTashkeel util"
```

---

### Task 6: Add chapter synthesis + page slicing helpers with tests

**Files:**
- Create: `web/src/lib/reader/queries.test.ts` (helpers section first; queries added in Task 7)
- Create part of: `web/src/lib/reader/queries.ts` (helpers only)

We isolate the two pure helpers — `synthesizeChapters` and `pagesInChapter` — with thorough tests. The DB-touching parts of `queries.ts` come in Task 7.

- [ ] **Step 1: Write failing tests**

Create `web/src/lib/reader/queries.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { synthesizeChapters, pagesInChapter } from "./queries";
import type { Chapter, Page } from "./types";

describe("synthesizeChapters", () => {
  it("returns real chapters unchanged when present", () => {
    const real: Chapter[] = [
      { title: "باب", level: 1, page_number: 1, volume: 1, sort_order: 1 },
      { title: "فصل", level: 2, page_number: 5, volume: 1, sort_order: 2 },
    ];
    const result = synthesizeChapters(real, [
      { volume: 1, page_number: 1 },
      { volume: 1, page_number: 2 },
    ]);
    expect(result).toEqual(real);
    expect(result[0].synthesized).toBeUndefined();
  });

  it("synthesizes one chapter per volume when chapters are empty", () => {
    const result = synthesizeChapters([], [
      { volume: 1, page_number: 1 },
      { volume: 1, page_number: 2 },
      { volume: 2, page_number: 1 },
      { volume: 2, page_number: 2 },
      { volume: 3, page_number: 1 },
    ]);
    expect(result).toHaveLength(3);
    expect(result[0]).toMatchObject({
      title: "Volume 1",
      level: 0,
      page_number: 1,
      volume: 1,
      sort_order: 1,
      synthesized: true,
    });
    expect(result[1].volume).toBe(2);
    expect(result[2].sort_order).toBe(3);
  });

  it("uses each volume's earliest page_number", () => {
    const result = synthesizeChapters([], [
      { volume: 1, page_number: 5 },
      { volume: 1, page_number: 6 },
      { volume: 2, page_number: 3 },
    ]);
    expect(result[0].page_number).toBe(5);
    expect(result[1].page_number).toBe(3);
  });

  it("returns empty when no chapters and no pages", () => {
    expect(synthesizeChapters([], [])).toEqual([]);
  });
});

describe("pagesInChapter", () => {
  const mkPage = (volume: number, page_number: number): Page => ({
    volume,
    page_number,
    content_blocks: [],
  });

  it("returns only the volume's pages for a synthesized chapter", () => {
    const all = [mkPage(1, 1), mkPage(1, 2), mkPage(2, 1), mkPage(2, 2)];
    const ch: Chapter = {
      title: "Volume 2",
      level: 0,
      page_number: 1,
      volume: 2,
      sort_order: 2,
      synthesized: true,
    };
    const next: Chapter = {
      title: "Volume 3",
      level: 0,
      page_number: 1,
      volume: 3,
      sort_order: 3,
      synthesized: true,
    };
    expect(pagesInChapter(all, ch, next)).toEqual([mkPage(2, 1), mkPage(2, 2)]);
  });

  it("slices real chapter by [start, next.start) on the same volume", () => {
    const all = [mkPage(1, 1), mkPage(1, 2), mkPage(1, 3), mkPage(1, 4)];
    const ch: Chapter = { title: "A", level: 1, page_number: 1, volume: 1, sort_order: 1 };
    const next: Chapter = { title: "B", level: 1, page_number: 3, volume: 1, sort_order: 2 };
    expect(pagesInChapter(all, ch, next)).toEqual([mkPage(1, 1), mkPage(1, 2)]);
  });

  it("returns all pages from start to end when nextChapter is null", () => {
    const all = [mkPage(1, 1), mkPage(1, 2), mkPage(1, 3)];
    const ch: Chapter = { title: "A", level: 1, page_number: 2, volume: 1, sort_order: 1 };
    expect(pagesInChapter(all, ch, null)).toEqual([mkPage(1, 2), mkPage(1, 3)]);
  });

  it("respects volume boundary on real chapter — does not bleed into next volume", () => {
    const all = [mkPage(1, 1), mkPage(1, 2), mkPage(2, 1)];
    const ch: Chapter = { title: "A", level: 1, page_number: 1, volume: 1, sort_order: 1 };
    expect(pagesInChapter(all, ch, null)).toEqual([mkPage(1, 1), mkPage(1, 2)]);
  });
});
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
cd web && npm test -- queries
```

Expected: FAIL — `queries.ts` doesn't exist or doesn't export the helpers.

- [ ] **Step 3: Implement helpers in `web/src/lib/reader/queries.ts`**

Create the file with helpers only (DB queries land in Task 7):

```ts
import "server-only";
import type { Chapter, Page } from "./types";

type PageRange = { volume: number; page_number: number };

/** If real chapters exist, return them. Otherwise generate one synthetic
 *  chapter per distinct volume, titled "Volume N", at that volume's earliest
 *  page_number. */
export function synthesizeChapters(
  real: Chapter[],
  pageRanges: PageRange[],
): Chapter[] {
  if (real.length > 0) return real;
  if (pageRanges.length === 0) return [];

  const earliestByVolume = new Map<number, number>();
  for (const { volume, page_number } of pageRanges) {
    const cur = earliestByVolume.get(volume);
    if (cur === undefined || page_number < cur) {
      earliestByVolume.set(volume, page_number);
    }
  }

  return [...earliestByVolume.entries()]
    .sort(([a], [b]) => a - b)
    .map(([volume, firstPage], i) => ({
      title: `Volume ${volume}`,
      level: 0,
      page_number: firstPage,
      volume,
      sort_order: i + 1,
      synthesized: true,
    }));
}

/** Filter all pages of a book to those that belong to the given chapter.
 *  - Synthesized chapter: one volume == one chapter, return all of that volume.
 *  - Real chapter: return same-volume pages with page_number in
 *    [chapter.page_number, nextChapter.page_number) on the same volume.
 *    If nextChapter is null, return through end of that volume.
 *    Real chapters spanning volumes are out of scope for v1; we cut at the
 *    volume boundary. */
export function pagesInChapter(
  allPages: Page[],
  chapter: Chapter,
  nextChapter: Chapter | null,
): Page[] {
  if (chapter.synthesized) {
    return allPages.filter((p) => p.volume === chapter.volume);
  }
  return allPages.filter((p) => {
    if (p.volume !== chapter.volume) return false;
    if (p.page_number < chapter.page_number) return false;
    if (
      nextChapter &&
      nextChapter.volume === chapter.volume &&
      p.page_number >= nextChapter.page_number
    ) {
      return false;
    }
    return true;
  });
}
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
cd web && npm test -- queries
```

Expected: PASS — all 8 tests green.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/reader/queries.ts web/src/lib/reader/queries.test.ts
git commit -m "web: add chapter synthesis + page slicing helpers"
```

---

### Task 7: Add Supabase queries to `queries.ts`

**Files:**
- Modify: `web/src/lib/reader/queries.ts`

We append the four DB-touching async functions. They are not unit-tested (they hit Supabase) — manual verification covers them in Task 17.

- [ ] **Step 1: Append to `queries.ts`**

Below the existing pure helpers, add the imports and async functions. Note: the existing `import type { Chapter, Page } from "./types";` from Task 6 stays — extend it (or add a second import line) to also bring in `Author`, `Book`, `BookListItem`.

```ts
import { getSupabase } from "@/lib/supabase";
import type { Author, Book, BookListItem } from "./types";  // merge with existing types import

export async function listBooks(): Promise<BookListItem[]> {
  const sb = getSupabase();
  const { data, error } = await sb
    .from("books")
    .select(
      "openiti_id,title_ar,title_lat,total_pages,total_volumes,has_tashkeel,authors:author_id(shuhra_ar,full_name_ar)",
    )
    .order("openiti_id");
  if (error) throw error;
  return (data ?? []).map((b: Record<string, unknown>) => {
    const author = b.authors as { shuhra_ar?: string; full_name_ar?: string } | null;
    return {
      openiti_id: b.openiti_id as string,
      title_ar: b.title_ar as string,
      title_lat: (b.title_lat as string | null) ?? null,
      total_pages: (b.total_pages as number | null) ?? null,
      total_volumes: (b.total_volumes as number | null) ?? null,
      has_tashkeel: (b.has_tashkeel as boolean | null) ?? null,
      author_name_ar: author?.full_name_ar ?? author?.shuhra_ar ?? null,
    };
  });
}

export async function getBook(
  openitiId: string,
): Promise<{ book: Book; author: Author | null } | null> {
  const sb = getSupabase();
  const { data, error } = await sb
    .from("books")
    .select("*,authors:author_id(*)")
    .eq("openiti_id", openitiId)
    .maybeSingle();
  if (error) throw error;
  if (!data) return null;
  const { authors: authorRow, ...bookFields } = data as Record<string, unknown> & {
    authors?: Author | null;
  };
  return { book: bookFields as unknown as Book, author: authorRow ?? null };
}

export async function getEffectiveChapters(bookId: string): Promise<Chapter[]> {
  const sb = getSupabase();
  const [chapRes, pageRes] = await Promise.all([
    sb
      .from("chapters")
      .select("id,title,level,sort_order,pages:page_id(page_number,volume)")
      .eq("book_id", bookId)
      .order("sort_order"),
    sb
      .from("pages")
      .select("volume,page_number")
      .eq("book_id", bookId),
  ]);
  if (chapRes.error) throw chapRes.error;
  if (pageRes.error) throw pageRes.error;

  const real: Chapter[] = (chapRes.data ?? []).map((c: Record<string, unknown>) => {
    const pageJoin = c.pages as { page_number?: number; volume?: number } | null;
    return {
      id: c.id as string,
      title: c.title as string,
      level: c.level as number,
      sort_order: c.sort_order as number,
      page_number: pageJoin?.page_number ?? 0,
      volume: pageJoin?.volume ?? 1,
    };
  });

  return synthesizeChapters(real, pageRes.data as PageRange[] ?? []);
}

export async function getAllPagesForBook(bookId: string): Promise<Page[]> {
  const sb = getSupabase();
  const { data, error } = await sb
    .from("pages")
    .select("page_number,volume,content_blocks")
    .eq("book_id", bookId)
    .order("volume")
    .order("page_number");
  if (error) throw error;
  return (data ?? []) as Page[];
}
```

- [ ] **Step 2: Confirm typecheck and existing tests still pass**

```bash
cd web && npx tsc --noEmit && npm test
```

Expected: PASS (typecheck clean; helper tests still green).

- [ ] **Step 3: Commit**

```bash
git add web/src/lib/reader/queries.ts
git commit -m "web: add Supabase query functions"
```

---

### Task 8: Add block-type color palette

**Files:**
- Create: `web/src/lib/reader/colors.ts`

- [ ] **Step 1: Create the colors module**

```ts
import type { BlockType } from "./types";

// Tailwind classes for inspector mode block borders + badges.
// Pick distinct hues per block type to make boundaries scannable.
export const BLOCK_BORDER: Record<BlockType, string> = {
  prose:     "border-zinc-300",
  heading:   "border-amber-400",
  hadith:    "border-emerald-400",
  isnad:     "border-sky-400",
  matn:      "border-violet-400",
  poetry:    "border-rose-400",
  biography: "border-teal-400",
};

export const BLOCK_BADGE: Record<BlockType, string> = {
  prose:     "bg-zinc-100 text-zinc-700",
  heading:   "bg-amber-100 text-amber-800",
  hadith:    "bg-emerald-100 text-emerald-800",
  isnad:     "bg-sky-100 text-sky-800",
  matn:      "bg-violet-100 text-violet-800",
  poetry:    "bg-rose-100 text-rose-800",
  biography: "bg-teal-100 text-teal-800",
};
```

- [ ] **Step 2: Confirm typecheck**

```bash
cd web && npx tsc --noEmit
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add web/src/lib/reader/colors.ts
git commit -m "web: add block-type color palette"
```

---

## Phase E — Block rendering primitives

These components are visual; we rely on tsc + manual verification rather than render tests. Keep each component small and single-purpose.

### Task 9: `TokenText` component

**Files:**
- Create: `web/src/components/reader/TokenText.tsx`

Renders a single token. Reader mode: just text (with optional tashkeel strip). Inspector mode: dotted underline, `data-token-id`, click-to-copy, optional pre-tashkeel diff above.

- [ ] **Step 1: Create the component**

```tsx
"use client";

import type { Token, ReaderMode } from "@/lib/reader/types";
import { stripTashkeel } from "@/lib/reader/tashkeel";

type Props = {
  token: Token;
  mode: ReaderMode;
  showTashkeel: boolean;   // reader toggle
  showDiff: boolean;       // inspector-only diff toggle
};

export function TokenText({ token, mode, showTashkeel, showDiff }: Props) {
  const display = showTashkeel ? token.text : stripTashkeel(token.text);
  const raw = token.text_raw ?? null;
  const showRawAbove = mode === "inspector" && showDiff && raw && raw !== token.text;

  if (mode === "reader") {
    return <span>{display} </span>;
  }

  const onClick = () => {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(token.id).catch(() => undefined);
    }
  };

  return (
    <span
      data-token-id={token.id}
      title={token.id}
      onClick={onClick}
      className="cursor-pointer underline decoration-dotted underline-offset-4 decoration-zinc-300 hover:decoration-zinc-600"
    >
      {showRawAbove ? (
        <ruby>
          {display}
          <rt className="text-zinc-400 line-through text-[0.6em]">{raw}</rt>
        </ruby>
      ) : (
        display
      )}{" "}
    </span>
  );
}
```

- [ ] **Step 2: Typecheck**

```bash
cd web && npx tsc --noEmit
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add web/src/components/reader/TokenText.tsx
git commit -m "web: add TokenText component"
```

---

### Task 10: `Block` component

**Files:**
- Create: `web/src/components/reader/Block.tsx`

Renders a single block by type. Inspector mode adds a colored border + corner badge.

- [ ] **Step 1: Create the component**

```tsx
import type { Block as BlockT, ReaderMode } from "@/lib/reader/types";
import { BLOCK_BORDER, BLOCK_BADGE } from "@/lib/reader/colors";
import { TokenText } from "./TokenText";

type Props = {
  block: BlockT;
  pageNumber: number;
  mode: ReaderMode;
  showTashkeel: boolean;
  showDiff: boolean;
};

export function Block({ block, pageNumber, mode, showTashkeel, showDiff }: Props) {
  const inner = renderInner(block, mode, showTashkeel, showDiff);

  if (mode === "reader") {
    return <div data-block-key={block.key}>{inner}</div>;
  }

  // Inspector: add bordered wrapper + badge
  return (
    <div
      data-block-key={block.key}
      data-block-type={block.type}
      className={`relative my-3 border-r-2 pr-3 ${BLOCK_BORDER[block.type]}`}
    >
      <span
        className={`absolute -left-2 -top-3 px-1.5 py-0.5 rounded text-[10px] font-mono ${BLOCK_BADGE[block.type]}`}
      >
        {block.type} · {block.key} · p{pageNumber}
      </span>
      {inner}
    </div>
  );
}

function renderInner(
  block: BlockT,
  mode: ReaderMode,
  showTashkeel: boolean,
  showDiff: boolean,
) {
  if (block.type === "poetry") {
    return (
      <div className="my-4 space-y-2">
        {block.hemistichs.map((verse, vi) => (
          <div key={vi} className="grid grid-cols-2 gap-x-8 text-center">
            {verse.map((hemistich, hi) => (
              <div key={hi}>
                {hemistich.map((t) => (
                  <TokenText
                    key={t.id}
                    token={t}
                    mode={mode}
                    showTashkeel={showTashkeel}
                    showDiff={showDiff}
                  />
                ))}
              </div>
            ))}
          </div>
        ))}
      </div>
    );
  }

  const tokens = block.tokens.map((t) => (
    <TokenText
      key={t.id}
      token={t}
      mode={mode}
      showTashkeel={showTashkeel}
      showDiff={showDiff}
    />
  ));

  switch (block.type) {
    case "heading":
      // Heading blocks don't carry a level today (parser drops it onto the chapter
      // entry instead). Render uniformly as h2; revisit if/when blocks gain a level.
      return <h2 className="font-bold text-xl mt-6 mb-2">{tokens}</h2>;
    case "isnad":
      return <p className="text-zinc-600 leading-loose">{tokens}</p>;
    case "matn":
      return <p className="font-medium leading-loose">{tokens}</p>;
    case "biography":
      return (
        <aside className="bg-zinc-50 rounded p-3 my-3 italic leading-relaxed">
          {tokens}
        </aside>
      );
    case "hadith":
    case "prose":
    default:
      return <p className="leading-loose my-2">{tokens}</p>;
  }
}
```

- [ ] **Step 2: Typecheck**

```bash
cd web && npx tsc --noEmit
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add web/src/components/reader/Block.tsx
git commit -m "web: add Block renderer (mode-aware)"
```

---

### Task 11: `PageBoundary` component

**Files:**
- Create: `web/src/components/reader/PageBoundary.tsx`

- [ ] **Step 1: Create the component**

```tsx
import type { ReaderMode } from "@/lib/reader/types";

type Props = {
  volume: number;
  pageNumber: number;
  mode: ReaderMode;
};

export function PageBoundary({ volume, pageNumber, mode }: Props) {
  const id = `v${volume}p${pageNumber}`;
  const label = `V${String(volume).padStart(2, "0")}P${String(pageNumber).padStart(3, "0")}`;

  if (mode === "reader") {
    return (
      <div id={id} className="flex items-center gap-2 my-6 text-xs text-zinc-400" dir="ltr">
        <hr className="flex-1 border-zinc-200" />
        <span>{label}</span>
        <hr className="flex-1 border-zinc-200" />
      </div>
    );
  }

  return (
    <div id={id} className="flex items-center gap-2 my-6" dir="ltr">
      <hr className="flex-1 border-zinc-300" />
      <span className="px-2 py-0.5 rounded-full bg-zinc-200 text-zinc-700 text-xs font-mono">
        {label}
      </span>
      <hr className="flex-1 border-zinc-300" />
    </div>
  );
}
```

- [ ] **Step 2: Typecheck and commit**

```bash
cd web && npx tsc --noEmit
git add web/src/components/reader/PageBoundary.tsx
git commit -m "web: add PageBoundary component"
```

Expected: typecheck PASS.

---

### Task 12: `ChapterScroll` component

**Files:**
- Create: `web/src/components/reader/ChapterScroll.tsx`

Composes pages, blocks, and boundaries into the rendered article.

- [ ] **Step 1: Create the component**

```tsx
"use client";

import { useEffect, useState } from "react";
import type { Page, ReaderMode } from "@/lib/reader/types";
import { Block } from "./Block";
import { PageBoundary } from "./PageBoundary";

type Props = {
  pages: Page[];
  mode: ReaderMode;
};

const TASHKEEL_KEY = "suhuf.reader.tashkeel";
const DIFF_KEY = "suhuf.reader.diff";

export function ChapterScroll({ pages, mode }: Props) {
  const [showTashkeel, setShowTashkeel] = useState(true);
  const [showDiff, setShowDiff] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const t = window.localStorage.getItem(TASHKEEL_KEY);
    if (t !== null) setShowTashkeel(t === "1");
    const d = window.localStorage.getItem(DIFF_KEY);
    if (d !== null) setShowDiff(d === "1");

    const onStorage = (e: StorageEvent) => {
      if (e.key === TASHKEEL_KEY && e.newValue !== null) setShowTashkeel(e.newValue === "1");
      if (e.key === DIFF_KEY && e.newValue !== null) setShowDiff(e.newValue === "1");
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  return (
    <article dir="rtl" className="font-[Amiri,serif] text-lg leading-loose text-zinc-900 max-w-[720px] mx-auto px-4 py-8">
      {pages.map((page) => (
        <section key={`${page.volume}-${page.page_number}`}>
          <PageBoundary volume={page.volume} pageNumber={page.page_number} mode={mode} />
          {page.content_blocks.map((block) => (
            <Block
              key={block.key}
              block={block}
              pageNumber={page.page_number}
              mode={mode}
              showTashkeel={showTashkeel}
              showDiff={showDiff}
            />
          ))}
        </section>
      ))}
    </article>
  );
}
```

- [ ] **Step 2: Typecheck and commit**

```bash
cd web && npx tsc --noEmit
git add web/src/components/reader/ChapterScroll.tsx
git commit -m "web: add ChapterScroll composition component"
```

Expected: typecheck PASS.

---

### Task 13: Toggle components (`ModeToggle`, `TashkeelToggle`, `DiffToggle`)

**Files:**
- Create: `web/src/components/reader/ModeToggle.tsx`
- Create: `web/src/components/reader/TashkeelToggle.tsx`
- Create: `web/src/components/reader/DiffToggle.tsx`

- [ ] **Step 1: Create `ModeToggle.tsx`**

Switches between `/internal/reader/...` and `/internal/inspector/...` for the same `(openiti_id, ch_index)`. The active mode renders as a styled `<span>`; the inactive mode is a `<Link>` pointing to the swapped path.

```tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type Props = { mode: "reader" | "inspector" };

export function ModeToggle({ mode }: Props) {
  const pathname = usePathname();
  const other = mode === "reader" ? "inspector" : "reader";
  const target = pathname.replace(/^\/internal\/(reader|inspector)/, `/internal/${other}`);

  const ActiveChip = (
    <span className="px-2 py-1 rounded bg-zinc-900 text-white">
      {mode === "reader" ? "Reader" : "Inspector"}
    </span>
  );
  const InactiveLink = (
    <Link
      href={target}
      className="px-2 py-1 rounded bg-zinc-100 text-zinc-600 hover:bg-zinc-200"
    >
      {mode === "reader" ? "Inspector" : "Reader"}
    </Link>
  );

  return (
    <div className="flex gap-1 text-xs font-mono">
      {/* Order: Reader first, Inspector second */}
      {mode === "reader" ? ActiveChip : InactiveLink}
      {mode === "inspector" ? ActiveChip : InactiveLink}
    </div>
  );
}
```

- [ ] **Step 2: Create `TashkeelToggle.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";

const KEY = "suhuf.reader.tashkeel";

export function TashkeelToggle() {
  const [on, setOn] = useState(true);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const v = window.localStorage.getItem(KEY);
    if (v !== null) setOn(v === "1");
  }, []);

  const flip = () => {
    const next = !on;
    setOn(next);
    window.localStorage.setItem(KEY, next ? "1" : "0");
    window.dispatchEvent(new StorageEvent("storage", { key: KEY, newValue: next ? "1" : "0" }));
  };

  return (
    <button
      type="button"
      onClick={flip}
      className="text-xs font-mono px-2 py-1 rounded bg-zinc-100 hover:bg-zinc-200"
    >
      Tashkeel: {on ? "On" : "Off"}
    </button>
  );
}
```

- [ ] **Step 3: Create `DiffToggle.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";

const KEY = "suhuf.reader.diff";

export function DiffToggle() {
  const [on, setOn] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const v = window.localStorage.getItem(KEY);
    if (v !== null) setOn(v === "1");
  }, []);

  const flip = () => {
    const next = !on;
    setOn(next);
    window.localStorage.setItem(KEY, next ? "1" : "0");
    window.dispatchEvent(new StorageEvent("storage", { key: KEY, newValue: next ? "1" : "0" }));
  };

  return (
    <button
      type="button"
      onClick={flip}
      className="text-xs font-mono px-2 py-1 rounded bg-zinc-100 hover:bg-zinc-200"
    >
      Diff: {on ? "On" : "Off"}
    </button>
  );
}
```

- [ ] **Step 4: Typecheck**

```bash
cd web && npx tsc --noEmit
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/reader/ModeToggle.tsx web/src/components/reader/TashkeelToggle.tsx web/src/components/reader/DiffToggle.tsx
git commit -m "web: add reader/tashkeel/diff toggle components"
```

---

### Task 14: `ChapterDrawer` and `InspectorJsonDrawer`

**Files:**
- Create: `web/src/components/reader/ChapterDrawer.tsx`
- Create: `web/src/components/reader/InspectorJsonDrawer.tsx`

- [ ] **Step 1: Create `ChapterDrawer.tsx`**

Native `<details>` element so we don't drag in a UI library.

```tsx
import Link from "next/link";
import type { Chapter, ReaderMode } from "@/lib/reader/types";

type Props = {
  chapters: Chapter[];
  currentSortOrder: number;
  openitiId: string;
  mode: ReaderMode;
};

export function ChapterDrawer({ chapters, currentSortOrder, openitiId, mode }: Props) {
  const base = `/internal/${mode}/${encodeURIComponent(openitiId)}`;
  return (
    <details className="text-sm">
      <summary className="cursor-pointer font-mono px-2 py-1 rounded bg-zinc-100 hover:bg-zinc-200">
        Chapters ({chapters.length})
      </summary>
      <ul className="mt-2 max-h-96 overflow-y-auto border border-zinc-200 rounded bg-white p-2 absolute z-10">
        {chapters.map((c) => (
          <li
            key={c.sort_order}
            style={{ paddingInlineStart: `${(c.level ?? 0) * 12}px` }}
            className={c.sort_order === currentSortOrder ? "font-bold" : ""}
          >
            <Link href={`${base}/${c.sort_order}`} className="block py-0.5 hover:bg-zinc-50">
              {c.synthesized ? (
                <span className="text-zinc-500">{c.title}</span>
              ) : (
                c.title
              )}
            </Link>
          </li>
        ))}
      </ul>
    </details>
  );
}
```

- [ ] **Step 2: Create `InspectorJsonDrawer.tsx`**

```tsx
"use client";

import { useState } from "react";
import type { Page } from "@/lib/reader/types";

type Props = { pages: Page[] };

export function InspectorJsonDrawer({ pages }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <div className="fixed top-0 right-0 h-full z-20 flex" dir="ltr">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="self-center bg-zinc-900 text-white text-xs font-mono px-2 py-3 rounded-l"
      >
        {open ? "▶" : "◀"} JSON
      </button>
      {open && (
        <aside className="w-[480px] max-w-[40vw] h-full bg-white border-l border-zinc-200 overflow-y-auto p-3">
          {pages.map((p) => (
            <details key={`${p.volume}-${p.page_number}`} className="mb-3 text-xs font-mono">
              <summary className="cursor-pointer text-zinc-700">
                V{p.volume} P{p.page_number} ({p.content_blocks.length} blocks)
              </summary>
              <pre className="mt-2 bg-zinc-50 p-2 rounded overflow-x-auto whitespace-pre">
{JSON.stringify(p.content_blocks, null, 2)}
              </pre>
            </details>
          ))}
        </aside>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Typecheck and commit**

```bash
cd web && npx tsc --noEmit
git add web/src/components/reader/ChapterDrawer.tsx web/src/components/reader/InspectorJsonDrawer.tsx
git commit -m "web: add chapter drawer and inspector JSON drawer"
```

Expected: typecheck PASS.

---

## Phase F — Internal layout & robots

### Task 15: `/internal/layout.tsx` and `robots.txt`

**Files:**
- Create: `web/src/app/internal/layout.tsx`
- Create: `web/public/robots.txt`

- [ ] **Step 1: Create the layout**

```tsx
import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  robots: { index: false, follow: false, nocache: true },
  title: "Internal — Suhuf",
};

export const viewport: Viewport = { themeColor: "#fafafa" };

export default function InternalLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-white text-zinc-900">
      <div className="border-b border-amber-300 bg-amber-50 px-3 py-1 text-xs font-mono text-amber-900">
        INTERNAL · not for public access
      </div>
      {children}
    </div>
  );
}
```

- [ ] **Step 2: Create `robots.txt`**

`web/public/robots.txt`:

```
User-agent: *
Disallow: /internal/
```

- [ ] **Step 3: Typecheck and commit**

```bash
cd web && npx tsc --noEmit
git add web/src/app/internal/layout.tsx web/public/robots.txt
git commit -m "web: add internal layout (noindex, INTERNAL badge) + robots disallow"
```

Expected: typecheck PASS.

---

## Phase G — Library index

### Task 16: `/internal/library/page.tsx`

**Files:**
- Create: `web/src/app/internal/library/page.tsx`

- [ ] **Step 1: Create the page**

```tsx
import Link from "next/link";
import { listBooks } from "@/lib/reader/queries";

export const dynamic = "force-dynamic";

export default async function LibraryPage() {
  const books = await listBooks();

  return (
    <main className="max-w-3xl mx-auto px-4 py-8">
      <h1 className="text-xl font-bold mb-1">Library</h1>
      <p className="text-sm text-zinc-500 mb-6">{books.length} ingested book{books.length === 1 ? "" : "s"}</p>

      {books.length === 0 ? (
        <p className="text-zinc-500">
          No books ingested yet. Run <code>python -m ingestion ingest &lt;uri&gt;</code>.
        </p>
      ) : (
        <ul className="space-y-3">
          {books.map((b) => {
            const id = encodeURIComponent(b.openiti_id);
            return (
              <li key={b.openiti_id} className="border border-zinc-200 rounded p-3">
                <div className="flex items-baseline justify-between gap-3">
                  <div dir="rtl" className="text-lg font-[Amiri,serif]">{b.title_ar}</div>
                  <div className="text-xs font-mono text-zinc-500">{b.openiti_id}</div>
                </div>
                {b.title_lat && <div className="text-sm text-zinc-700">{b.title_lat}</div>}
                <div className="text-xs text-zinc-500 mt-1">
                  {b.author_name_ar ?? "—"} · {b.total_pages ?? "?"} pages
                  {b.total_volumes && b.total_volumes > 1 ? ` · ${b.total_volumes} volumes` : ""}
                  {b.has_tashkeel ? " · tashkeeled" : ""}
                </div>
                <div className="mt-2 flex gap-2 text-xs font-mono">
                  <Link href={`/internal/reader/${id}`} className="px-2 py-1 rounded bg-zinc-100 hover:bg-zinc-200">
                    Reader
                  </Link>
                  <Link href={`/internal/inspector/${id}`} className="px-2 py-1 rounded bg-zinc-100 hover:bg-zinc-200">
                    Inspector
                  </Link>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}
```

- [ ] **Step 2: Typecheck and commit**

```bash
cd web && npx tsc --noEmit
git add web/src/app/internal/library/page.tsx
git commit -m "web: add internal library index"
```

Expected: typecheck PASS.

---

## Phase H — Reader route

### Task 17: Reader redirect + chapter view

**Files:**
- Create: `web/src/app/internal/reader/[openiti_id]/page.tsx`
- Create: `web/src/app/internal/reader/[openiti_id]/[ch_index]/page.tsx`

- [ ] **Step 1: Create the redirect page**

`web/src/app/internal/reader/[openiti_id]/page.tsx`:

```tsx
import { redirect, notFound } from "next/navigation";
import { getBook, getEffectiveChapters } from "@/lib/reader/queries";

export default async function ReaderRedirect({
  params,
}: {
  params: Promise<{ openiti_id: string }>;
}) {
  const { openiti_id } = await params;
  const decoded = decodeURIComponent(openiti_id);
  const result = await getBook(decoded);
  if (!result) notFound();
  const chapters = await getEffectiveChapters(result.book.id);
  if (chapters.length === 0) notFound();
  redirect(`/internal/reader/${openiti_id}/${chapters[0].sort_order}`);
}
```

- [ ] **Step 2: Create the chapter view**

`web/src/app/internal/reader/[openiti_id]/[ch_index]/page.tsx`:

```tsx
import Link from "next/link";
import { notFound } from "next/navigation";
import {
  getBook,
  getEffectiveChapters,
  getAllPagesForBook,
  pagesInChapter,
} from "@/lib/reader/queries";
import { ChapterScroll } from "@/components/reader/ChapterScroll";
import { ChapterDrawer } from "@/components/reader/ChapterDrawer";
import { ModeToggle } from "@/components/reader/ModeToggle";
import { TashkeelToggle } from "@/components/reader/TashkeelToggle";

export const dynamic = "force-dynamic";

export default async function ReaderChapter({
  params,
}: {
  params: Promise<{ openiti_id: string; ch_index: string }>;
}) {
  const { openiti_id, ch_index } = await params;
  const decoded = decodeURIComponent(openiti_id);
  const chIdx = parseInt(ch_index, 10);
  if (Number.isNaN(chIdx)) notFound();

  const result = await getBook(decoded);
  if (!result) notFound();
  const chapters = await getEffectiveChapters(result.book.id);
  const idx = chapters.findIndex((c) => c.sort_order === chIdx);
  if (idx === -1) notFound();

  const chapter = chapters[idx];
  const next = chapters[idx + 1] ?? null;
  const allPages = await getAllPagesForBook(result.book.id);
  const pages = pagesInChapter(allPages, chapter, next);

  const id = encodeURIComponent(decoded);
  const prev = chapters[idx - 1] ?? null;

  return (
    <>
      <header className="sticky top-0 z-10 bg-white/90 backdrop-blur border-b border-zinc-200 px-4 py-2 flex items-center gap-3 flex-wrap">
        <Link href="/internal/library" className="text-xs font-mono text-zinc-600 hover:text-zinc-900">
          ← library
        </Link>
        <div className="text-sm" dir="rtl">{result.book.title_ar}</div>
        <div className="text-xs text-zinc-500">— {chapter.title}</div>
        <div className="flex-1" />
        <ChapterDrawer chapters={chapters} currentSortOrder={chIdx} openitiId={decoded} mode="reader" />
        <TashkeelToggle />
        <ModeToggle mode="reader" />
      </header>

      <ChapterScroll pages={pages} mode="reader" />

      <footer className="sticky bottom-0 bg-white/90 backdrop-blur border-t border-zinc-200 px-4 py-2 flex items-center justify-between text-xs font-mono">
        {prev ? (
          <Link href={`/internal/reader/${id}/${prev.sort_order}`} className="px-2 py-1 rounded bg-zinc-100 hover:bg-zinc-200">
            ← {prev.title}
          </Link>
        ) : <span />}
        <span className="text-zinc-500">{idx + 1} / {chapters.length}</span>
        {next ? (
          <Link href={`/internal/reader/${id}/${next.sort_order}`} className="px-2 py-1 rounded bg-zinc-100 hover:bg-zinc-200">
            {next.title} →
          </Link>
        ) : <span />}
      </footer>
    </>
  );
}
```

- [ ] **Step 3: Typecheck**

```bash
cd web && npx tsc --noEmit
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add web/src/app/internal/reader/
git commit -m "web: add internal reader route"
```

---

## Phase I — Inspector route

### Task 18: Inspector redirect + chapter view

**Files:**
- Create: `web/src/app/internal/inspector/[openiti_id]/page.tsx`
- Create: `web/src/app/internal/inspector/[openiti_id]/[ch_index]/page.tsx`

The inspector page reuses the same data fetch, swaps `mode="inspector"`, and adds the JSON drawer + diff toggle.

- [ ] **Step 1: Create the redirect**

`web/src/app/internal/inspector/[openiti_id]/page.tsx`:

```tsx
import { redirect, notFound } from "next/navigation";
import { getBook, getEffectiveChapters } from "@/lib/reader/queries";

export default async function InspectorRedirect({
  params,
}: {
  params: Promise<{ openiti_id: string }>;
}) {
  const { openiti_id } = await params;
  const decoded = decodeURIComponent(openiti_id);
  const result = await getBook(decoded);
  if (!result) notFound();
  const chapters = await getEffectiveChapters(result.book.id);
  if (chapters.length === 0) notFound();
  redirect(`/internal/inspector/${openiti_id}/${chapters[0].sort_order}`);
}
```

- [ ] **Step 2: Create the chapter view**

`web/src/app/internal/inspector/[openiti_id]/[ch_index]/page.tsx`:

```tsx
import Link from "next/link";
import { notFound } from "next/navigation";
import {
  getBook,
  getEffectiveChapters,
  getAllPagesForBook,
  pagesInChapter,
} from "@/lib/reader/queries";
import { ChapterScroll } from "@/components/reader/ChapterScroll";
import { ChapterDrawer } from "@/components/reader/ChapterDrawer";
import { ModeToggle } from "@/components/reader/ModeToggle";
import { TashkeelToggle } from "@/components/reader/TashkeelToggle";
import { DiffToggle } from "@/components/reader/DiffToggle";
import { InspectorJsonDrawer } from "@/components/reader/InspectorJsonDrawer";

export const dynamic = "force-dynamic";

export default async function InspectorChapter({
  params,
}: {
  params: Promise<{ openiti_id: string; ch_index: string }>;
}) {
  const { openiti_id, ch_index } = await params;
  const decoded = decodeURIComponent(openiti_id);
  const chIdx = parseInt(ch_index, 10);
  if (Number.isNaN(chIdx)) notFound();

  const result = await getBook(decoded);
  if (!result) notFound();
  const chapters = await getEffectiveChapters(result.book.id);
  const idx = chapters.findIndex((c) => c.sort_order === chIdx);
  if (idx === -1) notFound();

  const chapter = chapters[idx];
  const next = chapters[idx + 1] ?? null;
  const prev = chapters[idx - 1] ?? null;
  const allPages = await getAllPagesForBook(result.book.id);
  const pages = pagesInChapter(allPages, chapter, next);

  const id = encodeURIComponent(decoded);

  return (
    <>
      <header className="sticky top-0 z-10 bg-white/90 backdrop-blur border-b border-zinc-200 px-4 py-2 flex items-center gap-3 flex-wrap">
        <Link href="/internal/library" className="text-xs font-mono text-zinc-600 hover:text-zinc-900">
          ← library
        </Link>
        <div className="text-sm" dir="rtl">{result.book.title_ar}</div>
        <div className="text-xs text-zinc-500">— {chapter.title}</div>
        <div className="flex-1" />
        <ChapterDrawer chapters={chapters} currentSortOrder={chIdx} openitiId={decoded} mode="inspector" />
        <TashkeelToggle />
        <DiffToggle />
        <ModeToggle mode="inspector" />
      </header>

      <ChapterScroll pages={pages} mode="inspector" />
      <InspectorJsonDrawer pages={pages} />

      <footer className="sticky bottom-0 bg-white/90 backdrop-blur border-t border-zinc-200 px-4 py-2 flex items-center justify-between text-xs font-mono">
        {prev ? (
          <Link href={`/internal/inspector/${id}/${prev.sort_order}`} className="px-2 py-1 rounded bg-zinc-100 hover:bg-zinc-200">
            ← {prev.title}
          </Link>
        ) : <span />}
        <span className="text-zinc-500">{idx + 1} / {chapters.length}</span>
        {next ? (
          <Link href={`/internal/inspector/${id}/${next.sort_order}`} className="px-2 py-1 rounded bg-zinc-100 hover:bg-zinc-200">
            {next.title} →
          </Link>
        ) : <span />}
      </footer>
    </>
  );
}
```

- [ ] **Step 3: Typecheck**

```bash
cd web && npx tsc --noEmit
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add web/src/app/internal/inspector/
git commit -m "web: add internal inspector route"
```

---

## Phase J — Verify and ship

### Task 19: Manual verification + ship

**Files:** none modified.

- [ ] **Step 1: Run full local verify**

```bash
./bin/suhuf verify --all
```

Expected: every package green (web: lint + tsc + test + build; ingestion: syntax + collected tests).

- [ ] **Step 2: Run actual pytest for ingestion**

```bash
python -m pytest ingestion/ -v
```

Expected: PASS — including the 5 new `test_text_raw.py` tests.

- [ ] **Step 3: Manual smoke in dev server**

Start the dev server:

```bash
cd web && npm run dev
```

Visit each in a browser:
- `http://localhost:3000/internal/library` — book list renders, INTERNAL badge visible at top.
- `http://localhost:3000/internal/reader/<some-openiti-id>` — redirects to chapter 1, RTL text renders, Tashkeel toggle flips diacritics on/off.
- `http://localhost:3000/internal/inspector/<some-openiti-id>/1` — block borders + corner badges visible, hovering a token shows its ID, JSON drawer toggles, Diff toggle (if you've re-ingested a book since Task 1) shows pre-tashkeel forms above tokens.
- `http://localhost:3000/robots.txt` — contains `Disallow: /internal/`.

If you see no books in the library, ingest one:

```bash
python -m ingestion ingest 0676Nawawi.ArbacunaNawawiyya --tashkeel-engine shakkala
```

(requires a populated `RELEASE/` clone and Supabase env vars).

Note any issues, fix them, re-run verify.

- [ ] **Step 4: Confirm working tree is committed**

```bash
git status
```

Expected: `nothing to commit, working tree clean`. If anything is staged or modified from the manual smoke, commit it.

- [ ] **Step 5: Ship**

Per project policy, NEVER raw `git push` — it's hook-blocked.

```bash
./bin/suhuf ship
```

Expected: rebases onto origin/main, runs verify, force-pushes with lease.

- [ ] **Step 6: Open PR**

```bash
gh pr create --fill
```

Wait for CI. Report status to the user.

---

## Self-review notes

Coverage check vs spec:
- ✅ Routing (`/internal/library`, `/internal/reader/[id]/[ch]`, `/internal/inspector/[id]/[ch]`) — Tasks 16, 17, 18.
- ✅ Two modes share rendering primitives — Tasks 9–14.
- ✅ Block rendering per type (heading/prose/hadith/isnad/matn/poetry/biography) — Task 10.
- ✅ Tashkeel toggle, persisted in localStorage — Task 13 (`TashkeelToggle`), Task 12 (`ChapterScroll` listens via storage event).
- ✅ Tashkeel diff via `text_raw` — Task 1 (ingestion), Task 9 (`TokenText` ruby), Task 13 (`DiffToggle`).
- ✅ Page boundaries with V/P labels — Task 11.
- ✅ Block outlines + token IDs + raw JSON in inspector — Tasks 9, 10, 14.
- ✅ Synthesized chapters for books without chapter markers — Task 6.
- ✅ Chapter list drawer — Task 14.
- ✅ INTERNAL badge + noindex + robots disallow — Task 15.
- ✅ Schema reconciliation — Task 2.
- ✅ Vitest setup + tests for the two pure helpers (synthesizeChapters, pagesInChapter, stripTashkeel) — Tasks 3, 5, 6.
- ✅ Ship via suhuf — Task 19.

Out-of-scope items (deliberately not in the plan): search, bookmarks, accounts, real auth, public links, mobile polish, flag-block-for-review, multi-book diffing.
