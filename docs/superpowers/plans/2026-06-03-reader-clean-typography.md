# Reader Clean Edition Typography — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the internal reader to production typeset-book quality (Clean Edition direction) and make it honor the source's inline-vs-newline layout.

**Architecture:** Reader-mode CSS + small component tweaks on top of the existing block-rendering pipeline. The format rule is "one block = one source line; sub-parts within a line are labeled spans." A new render path styles `isnad`/`matn`/`takhrij`/`quran` spans inline; the existing block-type path still renders display blocks on their own lines. No data-pipeline or inspector changes.

**Tech Stack:** Next.js (web/), Tailwind v4 + `globals.css`, `next/font/google`, Vitest. Arabic face: Scheherazade New.

**Spec:** `docs/superpowers/specs/2026-06-03-reader-clean-typography-design.md`

**Plan-style note:** Per project convention this plan describes steps, file paths, names, and test commands rather than pasting code bodies. Keep names exactly as written so later tasks line up with earlier ones.

**Conventions used throughout:**
- All work is in `web/`. Run commands from `web/` unless noted.
- Visual verification uses the seeded sample at `/reader/Sample.Taxonomy`. Because `/reader` is auth-gated and local dev has no Supabase, viewing requires a temporary local-only bypass (see Task 0). That bypass is reverted in the final task and must never be committed.
- Use only Scheherazade New weights **400** and **700**. Never use `font-semibold` (600) on Arabic — it has no 600 and the browser will synthesize it.

---

### Task 0: Local viewing harness (temporary, never committed)

**Files:**
- Create: `web/.env.local` (gitignored)
- Modify (temporary): `web/src/lib/proxy-paths.ts`, `web/src/app/(app)/layout.tsx`

- [ ] **Step 1: Add placeholder Supabase env**

Create `web/.env.local` with `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` set to any non-empty placeholder values. This stops the proxy from throwing on `createServerClient`. `.env.local` is gitignored.

- [ ] **Step 2: Temporarily open the reader route**

In `web/src/lib/proxy-paths.ts`, comment out `"/reader"` in `PROTECTED_PREFIXES` with a `// TEMP(local-screenshot): REVERT` marker. In `web/src/app/(app)/layout.tsx`, neutralize the `if (!user) redirect("/login")` line with the same marker.

- [ ] **Step 3: Seed and start**

Run: `npm run seed:sample` then start the dev server. Confirm `/reader/Sample.Taxonomy` returns 200 and renders the sample.
Expected: the reader page renders (current styling).

> These two source edits are reverted in Task 10. Do not commit them.

---

### Task 1: Swap Arabic face to Scheherazade New (real 400/700)

**Files:**
- Modify: `web/src/app/layout.tsx:2,20-26,40`
- Modify: `web/src/app/globals.css:14` (`--font-arabic`) and `:120-122` (`.reader-article`)
- Modify: `web/src/components/reader/ChapterScroll.tsx:98-101`

- [ ] **Step 1: Load the font**

In `layout.tsx`, replace the `Amiri` import from `next/font/google` with `Scheherazade_New`. Configure it with `weight: ["400","700"]`, `subsets: ["arabic"]`, `display: "swap"`, `variable: "--font-scheherazade"`. Remove the now-unused `amiri` constant and add `${scheherazade.variable}` to the `<html>` className (replacing the amiri variable).

- [ ] **Step 2: Point the Arabic token at it**

In `globals.css`, change `--font-arabic` (line 14) to reference `var(--font-scheherazade)`. In `.reader-article` add `font-family: var(--font-arabic), serif;` so reader text uses the variable rather than a hardcoded family.

- [ ] **Step 3: Replace the hardcoded family in ChapterScroll**

In `ChapterScroll.tsx`, the `articleClass` strings use `font-[Amiri,serif]` for both reader and inspector. Replace with a class that resolves to `var(--font-arabic)` (e.g. an arbitrary Tailwind value referencing the CSS var, or rely on `.reader-article`'s `font-family` for reader mode and set the inspector branch's family the same way). No `Amiri` literal should remain.

- [ ] **Step 4: Verify no Amiri references remain**

Run: `grep -rn "Amiri\|font-amiri" src` (expect: no matches, or only in comments you then remove).

- [ ] **Step 5: Typecheck + visual**

Run: `npx tsc --noEmit` (expect: clean). Reload `/reader/Sample.Taxonomy`; confirm the Arabic renders in Scheherazade New and the matn/headings show true bold (heavier, even strokes), not synthesized bold.

- [ ] **Step 6: Commit**

`git add` the three files; commit `feat(reader): switch Arabic face to Scheherazade New with real 400/700`.

---

### Task 2: Inline span-label styling helper (TDD)

Introduce a pure helper so inline `isnad`/`matn`/`takhrij`/`quran` spans get the same visual language as their display-block counterparts. This is the one genuinely unit-testable piece.

**Files:**
- Create: `web/src/lib/reader/spanStyles.ts`
- Test: `web/src/lib/reader/spanStyles.test.ts`
- Modify: `web/src/lib/reader/types.ts:13-20` (`SpanLabel`)

- [ ] **Step 1: Extend the type**

In `types.ts`, add `"isnad" | "matn" | "takhrij"` to the `SpanLabel` union (alongside existing `quran`, `person`, etc.).

- [ ] **Step 2: Write the failing test**

In `spanStyles.test.ts`, test an exported function `inlineSpanClass(label: SpanLabel): string | undefined` that returns: `"reader-span-isnad"` for `isnad`, `"reader-span-matn"` for `matn`, `"reader-span-takhrij"` for `takhrij`, `"reader-span-quran"` for `quran`, and `undefined` for labels that are not visually styled inline (e.g. `person`, `place`, `book_ref`, `hadith_ref`, `date_hijri`, `footnote`). Cover at least one styled and one unstyled case plus all four styled labels.

- [ ] **Step 3: Run test — verify it fails**

Run: `npx vitest run src/lib/reader/spanStyles.test.ts` (expect: FAIL — module/function not found).

- [ ] **Step 4: Implement**

Create `spanStyles.ts` exporting `inlineSpanClass`. Back it with an exported `INLINE_STYLED_LABELS` set containing exactly `isnad`, `matn`, `takhrij`, `quran`. Return the `reader-span-<label>` class for members, `undefined` otherwise.

- [ ] **Step 5: Run test — verify it passes**

Run: `npx vitest run src/lib/reader/spanStyles.test.ts` (expect: PASS).

- [ ] **Step 6: Commit**

`git add` types.ts, spanStyles.ts, spanStyles.test.ts; commit `feat(reader): inline span-style helper for isnad/matn/takhrij/quran`.

---

### Task 3: Render inline spans in TokenText + CSS

Wire the helper into the component and add the inline styles. This is what makes an inline hadith flow as one paragraph with correct emphasis.

**Files:**
- Modify: `web/src/components/reader/TokenText.tsx:12,35-68`
- Modify: `web/src/components/reader/Block.tsx:20-36,168-187` (share verb-accent logic)
- Modify: `web/src/app/globals.css` (add inline span rules near the existing `.reader-span-quran` block, ~145-164)

- [ ] **Step 1: Use the helper in TokenText**

Replace the local `STYLED_SPAN_LABELS` set in `TokenText.tsx` with `inlineSpanClass` from `spanStyles.ts`. In reader mode, when a token's `spanLabel` resolves to a class, apply `reader-span` + that class. Keep the existing `footnote` superscript branch and the plain-data-attribute branch for unstyled labels.

- [ ] **Step 2: Apply transmission-verb accent inside inline isnad spans**

Export `isTransmissionVerb` (and the `ISNAD_VERBS` set) from a shared spot so both `Block.tsx` and `TokenText.tsx` can use it — move them into `spanStyles.ts` (or a sibling `isnad.ts`) and import in both files. In `TokenText.tsx`, when the token is inside an `isnad` span and is a transmission verb, add the existing `reader-isnad-verb` class. Update `Block.tsx` to import from the new location (no behavior change for display blocks).

- [ ] **Step 3: Add inline CSS**

In `globals.css` add: `.reader-span-isnad { color: var(--reader-fg-muted); }`, `.reader-span-matn { font-weight: 700; }`, `.reader-span-takhrij { color: var(--reader-fg-faint); font-size: 0.9em; }`. Do not set backgrounds. (The `quran` inline rule is changed in Task 6.)

- [ ] **Step 4: Typecheck**

Run: `npx tsc --noEmit` (expect: clean). Run `npx vitest run src/lib/reader` (expect: existing tests + spanStyles green).

- [ ] **Step 5: Commit**

Commit `feat(reader): render isnad/matn/takhrij/quran as inline spans`.

> Visual confirmation happens in Task 9 once the fixture has an inline hadith.

---

### Task 4: Heading hierarchy by level

**Files:**
- Modify: `web/src/components/reader/Block.tsx:195-205` (heading case)
- Modify: `web/src/app/globals.css` (add heading rules)

- [ ] **Step 1: Level-driven classes**

In the reader branch of the heading case, emit a level class (`reader-h1`/`reader-h2`/`reader-h3`, clamping level >=3 to h3) instead of the inline size ternary. Keep `numberPrefix` handling. Keep the existing `<h2>` element/semantics.

- [ ] **Step 2: Heading CSS**

In `globals.css`: `.reader-h1` centered, weight 700, ~1.5em, letter-spacing ~0.01em, large top margin, and a thin bottom hairline rule using `border-bottom: 1px solid var(--reader-rule)` on an inline-block inner or padding-bottom on the heading. `.reader-h2` centered, 700, ~1.22em, moderate top margin, no rule. `.reader-h3` centered, 700, ~1.05em. Use 700 only.

> Note: the parent-title "kicker" from the mockup is intentionally NOT implemented per-heading — repeating the book title above every L1 chapter reads wrong; that belongs to a running-head/chrome treatment, out of scope here. Hierarchy comes from size/weight/space/rule.

- [ ] **Step 3: Typecheck + visual**

Run: `npx tsc --noEmit` (expect: clean). Reload and confirm L1 vs L2 are clearly differentiated (after Task 8 sets sub-section headings to L2).

- [ ] **Step 4: Commit**

Commit `feat(reader): size headings by level with hairline rule on L1`.

---

### Task 5: Hadith margin numeral (display path)

**Files:**
- Modify: `web/src/components/reader/Block.tsx:189-192` (numberPrefix)
- Modify: `web/src/app/globals.css:166-171` (`.reader-item-number`)

- [ ] **Step 1: Position the numeral in the margin**

Change `numberPrefix` so the ordinal is a positioned element (e.g. an absolutely-positioned span) hanging in the start (right, RTL) margin of the block rather than an inline `"N - "` prefix. The hosting block needs `position: relative` and a small inline-start padding so text doesn't overlap the numeral. Drop the ` - ` hyphen.

- [ ] **Step 2: Numeral CSS**

Update `.reader-item-number`: DM Sans, `var(--reader-fg-faint)`, ~0.72em, weight 500, positioned in the margin (e.g. `position:absolute; inset-inline-start:0; top:~0.2em`). Add the wrapper padding/relative rule (a `.reader-numbered` class on the block, or reuse the block wrapper).

- [ ] **Step 3: Typecheck + visual**

Run: `npx tsc --noEmit`. Reload; confirm the `١` sits as a faint margin numeral beside the first hadith, no hyphen, text not overlapping.

- [ ] **Step 4: Commit**

Commit `feat(reader): hang hadith ordinal in the margin`.

---

### Task 6: De-box the Qur'an (block + inline) — key readability fix

The current "green box" is the inline `.reader-span-quran` background+shadow applied to every token inside the `quran` block. Remove the fill everywhere; keep color.

**Files:**
- Modify: `web/src/app/globals.css:150-164` (`.reader-span-quran`, night override, `.reader-quran-block`)
- Modify: `web/src/components/reader/Block.tsx:224-229` (quran block class)

- [ ] **Step 1: Strip the inline fill**

In `.reader-span-quran` remove `background` and `box-shadow`; keep `color: var(--reader-quran, …)`. Optionally add a hair-thin underline via `border-bottom: 1px solid` in a low-opacity green. Remove/redo the night-theme `.reader-span-quran` background override to match (color/underline only).

- [ ] **Step 2: Block ayah spacing**

Ensure `.reader-quran-block` is centered, deep green, slightly larger (~1.2em), with generous `margin` above/below and comfortable `line-height`. No background. Leave the ﴿ ﴾ glyphs in the ayah color (gold-marker styling needs the glyphs as separate tokens — deferred, noted in spec).

- [ ] **Step 3: Visual across themes**

Reload; in paper/sepia/night confirm: inline ayah in running prose is green text with no highlight box and reads cleanly; block ayah is centered green with breathing room and no box.

- [ ] **Step 4: Commit**

Commit `feat(reader): remove Qur'an highlight box in favor of color + markers`.

---

### Task 7: Global measure, poetry, footnotes, prose rhythm

**Files:**
- Modify: `web/src/components/reader/ChapterScroll.tsx:98-101` (reader `articleClass`)
- Modify: `web/src/components/reader/Block.tsx:115-164` (poetry)
- Modify: `web/src/app/globals.css` (poetry/footnote/prose tweaks)

- [ ] **Step 1: Reading measure**

In the reader `articleClass`, set body to ~21px, line-height ~1.95, `max-w-[44rem]`, comfortable horizontal padding. (Inspector branch unchanged.)

- [ ] **Step 2: Poetry rhythm**

In the poetry render, keep the two-column centered-axis grid; set a real gutter (~2em), baseline alignment, consistent vertical margin between abyat, and a restrained center divider in `var(--reader-rule)`/accent at reduced opacity.

- [ ] **Step 3: Footnote + prose polish**

Confirm `.reader-footnotes`/`.reader-footnote` sit under a thin rule with a gold marker and legible size (>=~0.8em of the larger body, i.e. comfortably readable); set footnote marker as hanging where simple. Ensure prose paragraphs use the shared measure/rhythm; dates/refs stay plain.

- [ ] **Step 4: Typecheck + visual**

Run: `npx tsc --noEmit`. Reload; confirm overall page rhythm, poetry alignment, and footnotes read like a typeset book in all three themes.

- [ ] **Step 5: Commit**

Commit `feat(reader): tune measure, poetry axis, and footnote rhythm`.

---

### Task 8: Sample fixture demonstrates inline + block shapes

**Files:**
- Modify: `web/fixtures/Sample.Taxonomy.enriched.json`

- [ ] **Step 1: Add an inline hadith block**

Add a new `prose`-type block (with a fresh key, unique token ids) containing a full short hadith on one line, with `spans` labeling the ranges: an `isnad` span over the chain (so its transmission verbs accent), a `matn` span over the quoted text, and a `takhrij` span over the attribution. Give it a `number` so it shows a margin ordinal. This demonstrates the inline path. Keep the existing separate `isnad`/`matn`/`takhrij` blocks (b2–b4) as the block-path demo.

- [ ] **Step 2: Add an inline ayah**

In the existing prose block `b6`, add a `quran` span over an ayah phrase embedded in the running text (insert the tokens + a `quran` span with a `ref`), so an inline ayah renders green-in-prose with no box.

- [ ] **Step 3: Show heading hierarchy**

Change sub-section headings `b5` (تفسير الفاتحة) and `b8` (من معلقة) from `level: 1` to `level: 2`, and update the matching entries in the `chapters` array to `level: 2`, so L1 vs L2 styling is visible. (Top heading `b0` كتاب الإيمان stays L1.)

- [ ] **Step 4: Re-seed and verify JSON**

Run: `npm run seed:sample` (expect: "seeded …"). Run `node -e "JSON.parse(require('fs').readFileSync('fixtures/Sample.Taxonomy.enriched.json'))"` (expect: no error) to confirm valid JSON.

- [ ] **Step 5: Commit**

Commit `test(reader): sample fixture demonstrates inline and block shapes`.

---

### Task 9: Full visual verification across shapes and themes

**Files:** none (verification only)

- [ ] **Step 1: Reload the seeded sample**

Reload `/reader/Sample.Taxonomy`.

- [ ] **Step 2: Confirm all shapes**

Verify, in paper / sepia / night:
- L1 heading with hairline rule; L2 sub-section headings clearly smaller.
- Block hadith: separate lines, faint margin numeral, muted isnad with gold verbs, bold matn, faint takhrij.
- Inline hadith: one flowing paragraph with the same emphasis applied inline.
- Inline ayah: green text in prose, no highlight box.
- Block ayah: centered green, no box, breathing room.
- Poetry: centered axis, aligned, even rhythm.
- Footnotes: under a thin rule, gold marker, legible.
- Everything reads comfortably — no element less legible than before.

- [ ] **Step 3: Capture proof**

Take screenshots of paper and night for the record / PR.

---

### Task 10: Revert local bypass, run full verify

**Files:**
- Modify (revert): `web/src/lib/proxy-paths.ts`, `web/src/app/(app)/layout.tsx`

- [ ] **Step 1: Restore auth gating**

Revert the Task 0 edits: `"/reader"` back in `PROTECTED_PREFIXES`; `if (!user) redirect("/login")` restored. Leave `.env.local` (gitignored, not committed).

- [ ] **Step 2: Confirm clean tree of temp edits**

Run: `git status` and `grep -rn "TEMP(local-screenshot)" src` (expect: no matches).

- [ ] **Step 3: Full verify**

Run: `npx tsc --noEmit`, `npx vitest run src/lib/reader`, then from repo root `./bin/suhuf verify` (lint/typecheck/test on the affected `web` package). Expect: all green.

- [ ] **Step 4: Final commit (if any cleanup remained)**

Commit any residual cleanup; otherwise proceed to ship.

---

## Self-Review

**Spec coverage:**
- Scheherazade New 400/700 → Task 1. ✓
- Body size/line-height/measure → Task 7. ✓
- Inline-vs-block rule + `SpanLabel` additions + inline rendering → Tasks 2, 3; fixture demo → Task 8. ✓
- Headings by level → Task 4 (kicker intentionally dropped, noted). 
- Hadith margin numeral / isnad-verbs / bold matn / faint takhrij → Tasks 5, 3. ✓
- Qur'an block + inline de-box → Task 6. ✓
- Poetry → Task 7. ✓
- Footnotes / prose → Task 7. ✓
- Themes carry → verified in Tasks 6, 7, 9. ✓
- Inspector + toggles + queries untouched → no task modifies them. ✓
- Tests green + verify → Tasks 2, 10. ✓

**Placeholder scan:** No TBD/TODO; each step names exact files, identifiers, and commands. Code bodies omitted by project convention, but names (`inlineSpanClass`, `INLINE_STYLED_LABELS`, `reader-span-*`, `reader-h1/2/3`) are concrete and consistent across tasks.

**Type consistency:** `inlineSpanClass`/`INLINE_STYLED_LABELS` defined in Task 2, consumed in Task 3. `SpanLabel` extended in Task 2, used everywhere after. Class names `reader-span-isnad/matn/takhrij/quran` consistent between Task 3 CSS and Task 2 helper. `reader-h1/h2/h3` consistent between Task 4 component and CSS.

**Deviation from spec:** per-heading parent "kicker" dropped (Task 4 note) — flag for user.
